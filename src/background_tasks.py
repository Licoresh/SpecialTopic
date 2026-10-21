"""One bounded worker per app process, with session-owned status and credentials."""
from contextvars import ContextVar
from threading import Event, Lock, Thread
from . import supabase_store

_running = Lock()
_current = ContextVar("research_job", default=None)


class Cancelled(RuntimeError):
    pass


class Job:
    def __init__(self, title):
        self.title = title
        self._lock = Lock()
        self.done = Event()
        self._state = {"status": "running", "value": 0., "message": "Starting…",
                       "cancel_requested": False, "cancellable": True}

    def snapshot(self):
        with self._lock:
            return dict(self._state)

    def cancel(self):
        with self._lock:
            if self._state["status"] == "running" and self._state["cancellable"]:
                self._state["cancel_requested"] = True

    def progress(self, value, message):
        checkpoint()
        with self._lock:
            self._state.update(value=min(max(float(value), 0.), 1.), message=message)


def checkpoint():
    job = _current.get()
    if job is not None and job.snapshot()["cancel_requested"]:
        raise Cancelled("Stopped. Completed draft batches are retained; unfinished analysis was not published.")


def begin_publication():
    """Cancellation stops computation, never interrupts a multi-file publication."""
    job = _current.get()
    if job is not None:
        with job._lock:
            if job._state["cancel_requested"]:
                raise Cancelled("Stopped before publishing results.")
            job._state.update(cancellable=False, message="Saving results…")


def start(title, function, *args, **kwargs):
    credentials = supabase_store.worker_credentials()
    if not _running.acquire(blocking=False):
        raise ValueError("A processing job is already running on this host. You can continue reviewing while it finishes.")
    job = Job(title)

    def work():
        reset = _current.set(job)
        try:
            with supabase_store.worker_session(credentials):
                checkpoint()
                message = function(*args, progress=job.progress, **kwargs)
            status = "complete"
        except Cancelled as exc:
            status, message = "cancelled", str(exc)
        except Exception as exc:
            status, message = "failed", str(exc)
        finally:
            credentials.clear()
            _current.reset(reset)
            _running.release()
        with job._lock:
            job._state.update(status=status, message=message, cancellable=False)
        job.done.set()

    try:
        Thread(target=work, name="research-processing", daemon=True).start()
    except Exception:
        credentials.clear()
        _running.release()
        raise
    return job


def extract(*, progress):
    from .workflow import run_extraction
    result = run_extraction(progress=progress)
    return f"Saved {len(result):,} candidate/match records with source evidence."


def train(test_size=.2, include_irrelevant=False, vectorizer_config=None, *, progress):
    from .model_training import train_and_save_models
    metadata, _ = train_and_save_models(test_size, include_irrelevant, vectorizer_config, progress)
    return (f"Trained and evaluated both classifiers on {metadata['rows_used']:,} reviewed phrases. "
            f"Selected {metadata['model_name']}. Open Evaluate models for measured results; "
            "rerun extraction to apply the model.")


def suggest(rows, taxonomy, root, *, progress):
    from .pretrained_suggestions import suggest_labels, save_ai_suggestions
    from .ollama_review import review_ambiguous
    drafts = []
    for start_row in range(0, len(rows), 5):
        progress(start_row / max(len(rows), 1),
                 f"Preparing drafts {start_row + 1}–{min(start_row + 5, len(rows))}. First use may download/load BGE-M3.")
        batch = rows[start_row:start_row + 5]
        predicted = suggest_labels(batch, taxonomy, review_context=False)
        checkpoint()
        save_ai_suggestions(root, batch, predicted)
        drafts.extend(predicted)
    progress(.9, "Drafts are ready in the table. Finishing optional context checks…")
    reviewed = review_ambiguous(rows, drafts)
    checkpoint()
    save_ai_suggestions(root, rows, reviewed)
    return f"Saved {len(rows):,} AI drafts. Manual review is still required."


def suggest_local(root, *, progress):
    from .unattended_suggestions import run_local_suggestions
    report = run_local_suggestions(root, max_drafts=25, batch_size=5, progress=progress)
    message = f"Saved {report['suggestions_generated']:,} new local drafts. Manual review is still required."
    if report['preparation_errors']:
        message += " Source preparation issues: " + "; ".join(report['preparation_errors'])
    return message
