"""Serialize model publication while allowing researchers to continue labeling."""
from functools import wraps
import uuid
from filelock import FileLock, Timeout
from . import storage, supabase_store


def exclusive_training(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        folder = storage.ROOT / "models"
        folder.mkdir(parents=True, exist_ok=True)
        token = supabase_store.get_token() if supabase_store.configured() else ""
        run_id = str(uuid.uuid4())
        lock = FileLock(str(folder / ".training.lock"), timeout=0)
        try:
            lock.acquire()
        except Timeout as exc:
            raise ValueError("A training run is already active. Labeling can continue; wait for the current run to finish.") from exc
        acquired = False
        try:
            if supabase_store.configured():
                acquired = bool(supabase_store._request("POST", "/rest/v1/rpc/training_lock", token=token,
                                                      payload={"action": "acquire", "run_id": run_id}))
                if not acquired:
                    raise ValueError("Another training run is active in the shared workspace. Try again after it finishes.")
                supabase_store.st.session_state["training_run_id"] = run_id
            return function(*args, **kwargs)
        finally:
            if acquired:
                try:
                    supabase_store._request("POST", "/rest/v1/rpc/training_lock", token=supabase_store.get_token(),
                                             payload={"action": "release", "run_id": run_id})
                except supabase_store.SupabaseError:
                    # A failed release expires server-side; do not hide the original result.
                    supabase_store.st.session_state["training_release_warning"] = "The training lock could not be released. It expires within two hours."
                supabase_store.st.session_state.pop("training_run_id", None)
            lock.release()
    return wrapped


def ensure_training_lease():
    if supabase_store.configured():
        valid = supabase_store._request("POST", "/rest/v1/rpc/training_lock", token=supabase_store.get_token(),
                                        payload={"action": "check", "run_id": supabase_store.st.session_state["training_run_id"]})
        if not valid:
            raise ValueError("The training lease expired. No new model was published; rerun training.")
