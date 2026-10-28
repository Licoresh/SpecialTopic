from .category_schema import category_path
from io import BytesIO
from pathlib import Path
from copy import deepcopy
import json
import os
import time
import pandas as pd
import streamlit as st
import plotly.express as px
from openpyxl import load_workbook
from . import storage
from .config import ROOT, FIELDS, LABELS, VERSION
from .loaders import load_data, map_columns
from .column_mapping import suggest_column_mapping
from .cleaning import clean_dataset, duplicate_ids
from .preprocessing import get_nlp
from .validation import validate_taxonomy
from .classification import VECTORIZER_CONFIG, predict_competency_category
from .training_data import load_labeled_data, validate_labeled_data
from .model_training import read_model_metadata, training_data_changed
from .training_sources import (resolve_training_file, inspect_training_folder, training_candidates,
                               training_taxonomy, select_training_file)
from .labeling import annotation_conflicts, save_annotations, save_correction, corrections
from .workflow import run_extraction, analysis_bundle, input_signature, current_extractions
from .analytics import demand_matrix
from .job_profile import job_profile_tables
from .alignment import STATUSES
from .psf_reviews import REVIEW_TABLE, save_mapping_review, prepare_mapping_review, occurrence_hash
from .visualization import bar, distribution, heatmap
from .reporting import export_csv, export_excel, export_html, export_research_report
from .utils import timestamp, frame_hash, digest
from .readiness import (assess_research_readiness, source_overlap,
                        historical_category_disagreements, research_data_profile)
from . import supabase_store
from .action_guard import action_button, action_form_submit_button, finish_action_run
from .review_queue import (labels_by_phrase, expand_phrase_annotations, group_candidates_by_phrase,
                           manual_mapping_occurrences, preserve_occurrence_references)
from .loading_ui import load_data_with_skeleton

from .design import apply_design, review_workspace_style
from . import background_tasks


def _start_processing(title, function, *args, **kwargs):
    try:
        job = background_tasks.start(title, function, *args, **kwargs)
    except (ValueError, supabase_store.SupabaseError) as exc:
        st.warning(str(exc))
        return
    st.session_state["_background_job"] = job
    st.session_state.pop("_background_job_seen", None)
    st.rerun()


def _processing_status():
    job = st.session_state.get("_background_job")
    if job is None:
        return

    @st.fragment(run_every=1 if job.snapshot()["status"] == "running" else None)
    def status_panel():
        state = job.snapshot()
        with st.container(border=True):
            if state["status"] == "running":
                st.progress(state["value"], text=f"{job.title} · {state['message']}")
                elapsed = int(time.monotonic() - job.started_at)
                st.caption(f"Elapsed {elapsed // 60}:{elapsed % 60:02d} · {state['value']:.0%} through processing stages")
                if state["cancel_requested"]:
                    st.caption("Stopping after the current processing step…")
                else:
                    if st.button("Stop processing", key="cancel_background_job", disabled=not state["cancellable"]):
                        job.cancel()
                        st.rerun(scope="fragment")
                st.caption("You can continue reviewing or open another page. Keep this server running.")
            else:
                if st.session_state.get("_background_job_seen") is not job:
                    supabase_store.clear_read_cache()
                    if state["status"] == "complete":
                        st.session_state.pop("_extraction_results_frame", None)
                    if job.title == "Load saved extraction results" and state["status"] == "complete":
                        st.session_state["_extraction_results_frame"] = job.result
                    st.session_state["_background_job_seen"] = job
                show = st.success if state["status"] == "complete" else st.error if state["status"] == "failed" else st.info
                show(f"{job.title}: {state['message']}")
                if state["status"] == "failed" and job.prepared_extraction is not None:
                    if st.button("Retry saving extraction", key="retry_extraction_save"):
                        _start_processing("Extract skill phrases", background_tasks.extract, prepared=job.prepared_extraction)
                    st.caption("Finished computation is kept in this session. Retry checks for changed inputs before saving. Restarting, dismissing this job, or starting another job discards this retry copy.")
                if st.button("Refresh view", key="refresh_after_processing",
                             help="Save any table edits first. This reloads the page with the latest saved results."):
                    st.session_state.pop("_background_job", None)
                    st.session_state.pop("_background_job_seen", None)
                    st.rerun()
    status_panel()


@st.cache_data(show_spinner=False)
def cached_load(content, filename, sheet, encoding):
    return load_data(content, filename, sheet, encoding)


@st.cache_data(show_spinner=False, max_entries=4)
def cached_load_path(path, modified, size, source_hash, sheet, encoding):
    from .utils import digest
    content = Path(path).read_bytes()
    if digest(content) != source_hash:
        raise ValueError("The raw source bytes no longer match the saved upload hash. Restore or upload the original source.")
    return load_data(content, Path(path).name, sheet, encoding)


cached_label_validation = st.cache_data(show_spinner=False, ttl=60, max_entries=8)(validate_labeled_data)


def _session_cached_value(cache_name, key, loader, *, ttl=12, max_entries=4):
    """Cache derived research data inside one authenticated Streamlit session."""
    cache = st.session_state.setdefault(cache_name, {})
    now = time.monotonic()
    entry = cache.get(key)
    if entry and (ttl is None or now - entry[0] < ttl):
        return deepcopy(entry[1])
    value = loader()
    cache[key] = (time.monotonic(), deepcopy(value))
    for stale_key in [item for item, saved in cache.items() if ttl is not None and now - saved[0] >= ttl]:
        cache.pop(stale_key, None)
    while len(cache) > max_entries:
        oldest = min(cache, key=lambda item: cache[item][0])
        cache.pop(oldest, None)
    return value


def _page_ai_suggestions(path):
    """Avoid parsing the full drafts CSV on every edit while detecting atomic saves."""
    path = Path(path)
    try:
        stat = path.stat()
        signature = (str(path.resolve()), stat.st_mtime_ns, stat.st_size)
    except OSError:
        signature = (str(path.resolve()), None, None)
    saved = st.session_state.get("_page_ai_suggestions")
    if saved and saved[0] == signature:
        return saved[1]
    from .pretrained_suggestions import load_ai_suggestions
    from filelock import Timeout
    try:
        result = load_ai_suggestions(path.parents[2], lock_timeout=0)
    except (Timeout, PermissionError):
        # A background batch is replacing this file. Keep visible drafts and
        # retry next poll instead of blocking or clearing the review editor.
        return saved[1] if saved and saved[0][0] == signature[0] else {}
    st.session_state["_page_ai_suggestions"] = (signature, result)
    return result


def _load_manual_review_data(labels):
    shared = supabase_store.configured()
    local_files = () if shared else tuple(
        (str(path), path.stat().st_mtime_ns, path.stat().st_size)
        for path in sorted((storage.ROOT / "train").rglob("*"))
        if path.is_file() and path.suffix.lower() in (".csv", ".xlsx")
    )
    revision = (str(storage.ROOT), shared, local_files, tuple(
        storage.frame_revision(name) for name in
        ("extractions_original", "cleaned_jobs", "cleaned_psf_aai")
    ), None if shared else storage.frame_revision("team_training_candidates"))
    # Candidate rows live outside app_state in shared mode. The short TTL and
    # explicit Team updates refresh also cover additions from other reviewers.
    return _session_cached_value("_manual_review_queue", revision, _build_manual_review_data,
                                 ttl=15 if shared else None, max_entries=1)


def _build_manual_review_data():
    """Load the real candidate, label, and taxonomy tables for the review page."""
    candidates = pd.DataFrame() if supabase_store.configured() else training_candidates(storage.ROOT)
    shared_candidates = storage.read_frame("team_training_candidates", include_source_text=not supabase_store.configured())
    if supabase_store.configured() and not shared_candidates.empty:
        shared_candidates["_shared_candidate"] = True
    if not shared_candidates.empty:
        candidates = pd.concat([candidates, shared_candidates], ignore_index=True).fillna("")
    extracted = storage.read_frame("extractions_original", columns=[
        "original_phrase", "normalized_phrase", "source_type", "source_id",
    ])
    if not extracted.empty:
        extracted = extracted.rename(columns={"original_phrase": "phrase"})
        extracted["_job_context"] = "jobs"
        jobs = storage.read_frame("cleaned_jobs")
        if not jobs.empty:
            source = jobs.drop_duplicates("source_id").set_index("source_id")
            for target, column in (("source_url", "url"), ("job_title", "job_title"), ("company", "company")):
                extracted[target] = extracted.source_id.map(source[column]).fillna("")
        candidates = pd.concat([candidates, extracted], ignore_index=True).fillna("")
    for column in ("phrase", "normalized_phrase", "source_type", "source_id", "job_title", "company", "source_url", "original_text"):
        if column not in candidates:
            candidates[column] = ""
    from .cleaning import normalize_text
    missing = candidates.normalized_phrase.eq("")
    candidates.loc[missing, "normalized_phrase"] = candidates.loc[missing, "phrase"].map(normalize_text)
    candidates = candidates[candidates.phrase.str.strip().ne("")].drop_duplicates(["normalized_phrase", "source_type", "source_id"])
    from .pretrained_suggestions import is_incomplete_phrase, has_phrase_text
    candidates = candidates.loc[candidates.phrase.map(has_phrase_text).astype(bool)].copy()
    candidates["needs_phrase_edit"] = candidates.phrase.map(
        {phrase: is_incomplete_phrase(phrase) for phrase in candidates.phrase.unique()}
    )
    source_pairs = candidates[["normalized_phrase", "source_type", "source_id"]].copy()
    source_pairs[["source_type", "source_id"]] = source_pairs[["source_type", "source_id"]].apply(lambda values: values.astype(str).str.strip())
    counts = source_pairs[source_pairs.source_id.ne("")].drop_duplicates().groupby("normalized_phrase").size()
    candidates["source_ads"] = candidates.normalized_phrase.map(counts).fillna(0).astype(int)
    taxonomy = training_taxonomy(storage.ROOT)
    return candidates, taxonomy


def _review_contexts(frame):
    """Resolve omitted shared evidence before displaying, suggesting or reviewing it."""
    frame = frame.copy()
    if "original_text" not in frame:
        frame["original_text"] = ""
    shared = (frame.loc[frame["_shared_candidate"].eq(True)]
              if supabase_store.configured() and "_shared_candidate" in frame else frame.iloc[:0])
    keys = list(shared[["normalized_phrase", "source_type", "source_id"]].itertuples(index=False, name=None)) if not shared.empty else []
    if keys:
        contexts = supabase_store.candidate_contexts(supabase_store.get_token(), keys)
        for index, row in shared.iterrows():
            key = (row.normalized_phrase, row.source_type, row.source_id)
            if contexts.get(key):
                frame.loc[index, "original_text"] = contexts[key]
    # Deduplication can keep a training candidate instead of its extraction row,
    # so _job_context is not a reliable gate for restoring source evidence.
    missing = frame.original_text.fillna("").astype(str).str.strip().eq("")
    job_rows = frame.get("source_type", pd.Series("", index=frame.index)).isin(
        ["jobs", "Philippine job advertisement"])
    job_rows |= frame.get("_job_context", pd.Series("", index=frame.index)).eq("jobs")
    selected = missing & job_rows
    if selected.any():
        jobs = storage.read_frame("cleaned_jobs", columns=["source_id", "original_text", "job_description"])
        if not jobs.empty and "source_id" in jobs:
            contexts = jobs.get("original_text", pd.Series("", index=jobs.index)).fillna("")
            descriptions = jobs.get("job_description", pd.Series("", index=jobs.index)).fillna("")
            contexts = contexts.where(contexts.str.strip().ne(""), descriptions)
            contexts = pd.Series(contexts.to_numpy(), index=jobs.source_id)
            contexts = contexts[~contexts.index.duplicated()]
            frame.loc[selected, "original_text"] = frame.loc[selected, "source_id"].map(contexts).fillna("")
    missing = frame.original_text.fillna("").astype(str).str.strip().eq("") & job_rows
    if missing.any():
        from .review_queue import archived_job_contexts
        contexts = archived_job_contexts(storage.ROOT, frame.loc[missing, "source_id"], cached_load_path)
        frame.loc[missing, "original_text"] = frame.loc[missing, "source_id"].map(contexts).fillna("")
    return frame

@st.cache_data(show_spinner=False)
def cached_clean(frame, kind, duplicate_list):
    return clean_dataset(frame, kind, duplicate_list)

@st.cache_resource(show_spinner=False)
def cached_nlp():
    return get_nlp()

def display(frame):
    if frame.empty:
        st.caption("No records to display for the current selection.")
    if len(frame) > 100:
        number = st.session_state.get("_table_number", 0)
        st.session_state["_table_number"] = number + 1
        key = f"table_page_{st.session_state.get('_fow_current_page', '')}_{number}"
        total = (len(frame) + 99) // 100
        if st.session_state.get(key, 1) > total:
            st.session_state[key] = total
        page = st.number_input("Table page (100 rows)", 1, total, key=key)
        st.caption(f"{len(frame):,} total rows. Full tables are available in Reports and downloads.")
        frame, _, _ = _paginate_frame(frame, page)
    text_columns = {key: st.column_config.TextColumn(width="large") for key in
                    ("original_text", "job_description", "rationale", "interpretation", "competency_description", "range_of_application") if key in frame}
    st.dataframe(frame, width="stretch", hide_index=True, row_height=38,
                 column_config=text_columns, height=min(480, max(100, 40 + 38 * len(frame))),
                 alt=f"Research data table with {len(frame):,} rows. Use the table toolbar to search or download.")


def _paginate_frame(frame, page, page_size=100):
    total_pages = max(1, (len(frame) + page_size - 1) // page_size)
    page = min(max(int(page), 1), total_pages)
    start = (page - 1) * page_size
    return frame.iloc[start:start + page_size], page, total_pages

def chart(fig):
    from .visualization import style_chart
    st.plotly_chart(style_chart(fig), width="stretch", config={"displaylogo": False, "scrollZoom": False},
                    alt=fig.layout.title.text or "Research analysis chart")

def page_intro(title, description):
    with st.container(key="page_heading", gap="xsmall"):
        st.title(title)
        st.write(description)

def page_button(path, label, *, primary=False, key=None):
    if action_button(label, type="primary" if primary else "secondary", key=key, width="stretch",
                 icon=":material/arrow_forward:"):
        st.switch_page(path)

def project_relative_path(path):
    try:
        return "./" + Path(path).resolve().relative_to(storage.ROOT.resolve()).as_posix()
    except ValueError:
        return Path(path).name

def reviewed_label_count():
    """Read only the small selected annotation table for the overview page."""
    if supabase_store.configured():
        return len(storage.read_frame("labeled_competencies"))
    selection = storage.read_json("training_source", {})
    paths = []
    if selection.get("file"):
        paths.append(storage.ROOT / "train" / selection["file"])
    paths.extend((storage.ROOT / "train/labeled_competencies.csv",
                  storage.ROOT / "data/processed/labeled_competencies.csv"))
    path = next((candidate for candidate in paths if candidate.is_file()), None)
    if path is None:
        return 0
    frame = pd.read_csv(path, usecols=lambda column: column in {"phrase", "label"},
                        dtype=str, keep_default_na=False)
    if not {"phrase", "label"}.issubset(frame.columns):
        return 0
    return int((frame.phrase.str.strip().ne("") & frame.label.str.strip().ne("")).sum())

def current_analysis():
    meta = storage.read_json("extraction_metadata", {})
    if not meta:
        st.info("Upload, map and clean data, then run Competency Extraction to create results.")
        return False
    signature = _session_cached_value("_fow_signature_cache", "active", input_signature,
                                     ttl=15, max_entries=1)
    st.session_state["_current_analysis_signature"] = signature
    if meta.get("signature") != signature:
        st.warning("Inputs, labels, settings or the selected model changed. Run Competency Extraction again before interpreting or exporting results.")
        return False
    return True

def select_filters(frame, fields, prefix):
    selected = {}
    for field in fields:
        if field in frame:
            options = sorted(v for v in frame[field].astype(str).unique() if v)
            if options:
                selected[field] = st.multiselect(field.replace("_", " ").title(), options, key=f"filter_{prefix}_{field}")
    return selected

def filtered_bundle():
    signature = st.session_state.get("_current_analysis_signature") or input_signature()
    corrections_path = storage.ROOT / "data/feedback/corrections.csv"
    try:
        corrections_stat = corrections_path.stat()
        correction_revision = (corrections_stat.st_mtime_ns, corrections_stat.st_size)
    except OSError:
        correction_revision = None
    mapping_reviews = storage.read_frame(REVIEW_TABLE)
    analysis_revision = digest({"inputs": signature, "corrections": correction_revision,
                                "extraction": storage.frame_revision("extractions_original"),
                                "mapping_reviews": frame_hash(mapping_reviews)})
    source_key = f"sources:{analysis_revision}"
    source_snapshot = _session_cached_value(
        "_fow_source_cache", source_key,
        lambda: {"jobs": storage.read_frame("cleaned_jobs"),
                 "taxonomy": storage.read_frame("cleaned_psf_aai"),
                 "extracted": current_extractions(), "mapping_reviews": mapping_reviews},
        ttl=None, max_entries=1,
    )
    jobs, skills = source_snapshot["jobs"], source_snapshot["extracted"]
    upload = storage.read_json("uploads", {}).get("jobs", {})
    with st.sidebar.expander("Research sample", expanded=True):
        st.caption("Results use the active cleaned upload. Other training sources are excluded.")
        st.write(upload.get("filename") or upload.get("name") or "Active job upload")
        st.caption(f"{len(jobs):,} cleaned job ads before filters")
        dataset_hashes = sorted(jobs["_dataset_hash"].dropna().astype(str).unique().tolist()) if "_dataset_hash" in jobs else []
        selected_dataset = st.selectbox("Dataset", dataset_hashes, key="research_dataset_hash") if len(dataset_hashes) > 1 else None
    with st.sidebar.expander("Job filters"):
        jf = select_filters(jobs, ["job_title", "location", "company", "industry"], "jobs")
        if selected_dataset:
            jf["_dataset_hash"] = [selected_dataset]
        if "posting_date_parsed" in jobs:
            years = sorted(v for v in jobs.posting_date_parsed.str[:4].unique() if v)
            chosen = st.multiselect("Posting year", years, key="posting_year")
            if chosen:
                jf["posting_date_parsed"] = jobs.loc[jobs.posting_date_parsed.str[:4].isin(chosen), "posting_date_parsed"].unique().tolist()
    with st.sidebar.expander("Competency filters"):
        sf = select_filters(skills, ["competency_category", "job_role", "proficiency_level", "skill_type"], "skills")
        phrase_query = st.text_input("Skill phrase contains", key="filter_skills_phrase_contains")
        if phrase_query.strip():
            sf["normalized_phrase_contains"] = phrase_query.strip()
        status = st.multiselect("Alignment status", STATUSES, key="filter_status")
    bundle_key = digest({"signature": analysis_revision, "jobs": jf, "skills": sf, "statuses": status})
    return _session_cached_value(
        "_fow_analysis_cache", bundle_key,
        lambda: analysis_bundle(job_filters=jf, skill_filters=sf, statuses=status,
                                source_snapshot=source_snapshot),
        ttl=None, max_entries=2,
    )


def home():
    with st.container(key="overview_heading", gap="xsmall"):
        st.caption("PHILIPPINES · AI & ANALYTICS")
        st.title("From job evidence to skills insight.")
        st.write("Your research workspace for employer demand and PSF-AAI alignment.")
    def load_overview_data():
        extraction_meta = storage.read_json("extraction_metadata", {})
        return (
            storage.read_frame("cleaned_jobs"),
            storage.read_frame("cleaned_psf_aai"),
            storage.read_frame("mapped_jobs"),
            bool(extraction_meta),
            reviewed_label_count(),
            read_model_metadata(),
            extraction_meta,
        )
    jobs, taxonomy, mapped_jobs, has_extractions, label_count, model, meta = load_data_with_skeleton(
        load_overview_data, height=120
    )

    with st.container(horizontal=True, key="overview_metrics", gap="medium"):
        for label, value, icon, help_text in [
            ("Clean job ads", f"{len(jobs):,}", "work", "Advertisements saved after data cleaning."),
            ("Reviewed labels", f"{label_count:,}", "task_alt", "Saved annotation rows; a phrase can occur in several ads."),
            ("PSF-AAI competencies", f"{len(taxonomy):,}", "account_tree", "Competencies in the active reviewed reference."),
            ("Phrase extraction", "Saved" if has_extractions else "Not started", "manage_search", "Analysis pages check that saved extraction inputs are still current."),
        ]:
            with st.container(width=240):
                st.metric(label, value, icon=f":material/{icon}:", help=help_text)

    if mapped_jobs.empty:
        next_title, next_copy, next_path, next_label = "Start with your job data", "Upload the job-ad CSV or Excel file you plan to use for the study.", "pages/01_Data_Upload.py", "Upload job data"
    elif jobs.empty:
        next_title, next_copy, next_path, next_label = "Check and clean the uploaded data", "Confirm the automatic column matches, review the quality report, and save the cleaned job table.", "pages/02_Data_Quality.py", "Review data quality"
    elif not meta or not has_extractions:
        next_title, next_copy, next_path, next_label = "Extract skill phrases", "Run the phrase extraction step on your cleaned job ads. Candidate phrases are not research labels until a reviewer checks them.", "pages/05_Competency_Extraction.py", "Open phrase extraction"
    elif label_count == 0:
        next_title, next_copy, next_path, next_label = "Review candidate phrases", "Check each phrase against its source context, then confirm or change the AI category and PSF suggestion.", "pages/06_Manual_Labeling.py", "Open manual labeling"
    elif not model:
        next_title, next_copy, next_path, next_label = "Train the research classifier", "Training becomes available when the real reviewed dataset passes the validation checks.", "pages/07_ML_Training.py", "Open model training"
    elif not meta.get("model_available", False):
        next_title, next_copy, next_path, next_label = "Refresh the analysis", "Run extraction again to apply the current model and labels.", "pages/05_Competency_Extraction.py", "Refresh extraction"
    else:
        next_title, next_copy, next_path, next_label = "Explore the current analysis", "The extraction is complete. Review Research Readiness before interpreting or reporting its results.", "pages/03_Job_Market.py", "Open exploratory analysis"

    with st.container(border=True, key="home_next"):
        with st.container(horizontal=True, vertical_alignment="center", gap="large"):
            with st.container(width="stretch", gap="xsmall"):
                st.caption("CONTINUE YOUR RESEARCH")
                st.subheader(next_title)
                st.write(next_copy)
            with st.container(width=260):
                page_button(next_path, next_label, primary=True, key="home_next_step")

    st.subheader("Your research, step by step")
    st.caption("Keep source evidence, reviewed decisions, and research results connected.")
    steps = [
        ("01", "Upload job ads", "Add the CSV or Excel file for your study.", "pages/01_Data_Upload.py", "Open upload"),
        ("02", "Review data quality", "Check matched columns and save clean data.", "pages/02_Data_Quality.py", "Review data"),
        ("03", "Extract phrases", "Find candidate skills in the job descriptions.", "pages/05_Competency_Extraction.py", "Extract phrases"),
        ("04", "Review and label", "Check AI suggestions against the source evidence.", "pages/06_Manual_Labeling.py", "Review phrases"),
        ("05", "Train and evaluate", "Train only after the reviewed labels pass validation.", "pages/07_ML_Training.py", "Train models"),
        ("06", "Explore results", "Review employer demand, PSF mapping and reports.", "pages/03_Job_Market.py", "View results"),
    ]
    stage_states = ["Data uploaded" if not mapped_jobs.empty else "Start here",
                    "Clean data saved" if not jobs.empty else "Awaiting clean data",
                    "Extraction saved" if has_extractions else "No extraction yet",
                    f"{label_count:,} label rows saved", "Model saved" if model else "No model yet",
                    "Check research readiness"]
    for offset in (0, 3):
        with st.container(horizontal=True, key=f"workflow_{offset}", gap="medium"):
            for index, (number, title, description, path, link) in enumerate(steps[offset:offset + 3], start=offset):
                with st.container(width=330, border=True, key=f"workflow_step_{number}"):
                    st.caption(f"{number} / {stage_states[index]}")
                    st.markdown(f"#### {title}")
                    st.write(description)
                    page_button(path, link, key=f"home_workflow_{number}")
    try:
        readiness_labels = (storage.read_frame("labeled_competencies") if supabase_store.configured()
                            else load_labeled_data(resolve_training_file(storage.ROOT)))
        _, readiness_validation = cached_label_validation(readiness_labels, require_provenance=True)
        readiness_audit = assess_research_readiness(readiness_labels, model, readiness_validation)
    except (ValueError, OSError) as exc:
        readiness_labels, readiness_audit = pd.DataFrame(), {"findings": [{"title": "Training data unavailable", "detail": str(exc)}]}
    if readiness_audit["findings"]:
        with st.container(border=True, key="readiness_summary"):
            st.subheader("Before you report findings")
            blocking = [finding for finding in readiness_audit["findings"] if finding.get("status", "blocking") == "blocking"]
            st.write("Research readiness needs attention. Review the outstanding checks before interpreting results.")
            if blocking:
                st.write(" · ".join(finding["title"] for finding in blocking[:3]))
            page_button("pages/18_Research_Readiness.py", "Review readiness", key="home_readiness")
    if model:
        st.caption(f"Saved classifier: {model['model_name']}. It is available for exploratory workflow checks; see Research Readiness before interpreting model outputs.")
    else:
        st.caption("No classifier has been trained. AI-generated phrase suggestions are drafts; they do not count as reviewed labels or model results.")


def upload(kind=None):
    if kind is None:
        kind = st.selectbox(
            "Dataset to upload",
            ["jobs", "psf_aai"],
            format_func=lambda value: {
                "jobs": "Job advertisements (500-study dataset)",
                "psf_aai": "TESDA PSF-AAI reference",
            }[value],
        )
    title = "Upload job data" if kind == "jobs" else "Upload PSF-AAI reference"
    description = (
        "Upload the selected study dataset. The original file is archived unchanged; review its column matches before saving."
    )
    page_intro(title, description)
    if kind == "jobs":
        st.caption("The original CSV stays on the computer that uploaded it. After cleaning, the active job dataset is shared through Supabase with signed-in teammates.")
    template = (Path(__file__).resolve().parents[1] / "data/templates" / f"{kind}_template.csv")
    if template.exists():
        st.download_button("Download blank template", template.read_bytes(), template.name, "text/csv")
    if kind == "jobs":
        uploads = storage.read_json("uploads", {})
        job_entry, psf_entry = uploads.get("jobs", {}), uploads.get("psf_aai", {})
        if (job_entry.get("filename") == "psf_aai_range_review_draft.csv"
                and job_entry.get("hash") == psf_entry.get("hash")
                and psf_entry.get("filename") == "psf_aai_range_review_draft.csv"):
            with st.container(border=True):
                st.warning("The PSF-AAI draft was also saved as a job upload. The matching PSF reference copy will be kept.")
                if action_button("Remove mistaken PSF draft from job uploads", key="remove_misfiled_psf_range"):
                    storage.remove_misfiled_psf_range_upload()
                    st.success("Removed the mistaken jobs upload. The PSF-AAI reference copy and job dataset were preserved.")
    if kind == "psf_aai":
        draft = Path(__file__).resolve().parents[1] / "data/processed/psf_aai_range_review_draft.csv"
        if draft.is_file() and action_button(
            "Load prepared Range of Application draft",
            help="Imports the prepared TESDA PDF draft as source data. It still needs researcher review before activation.",
            key="load_psf_range_draft",
        ):
            storage.archive_raw(draft.read_bytes(), draft.name, kind)
            storage.save_json(f"read_options_{kind}", {"sheet": 0, "encoding": "utf-8-sig"})
            st.success("PSF-AAI draft imported. Review its column mapping below; the active reference is unchanged until researcher review.")
    uploaded = st.file_uploader("CSV or XLSX", type=["csv", "xlsx"])
    st.caption("Accepted formats: CSV and Excel (.xlsx). Preview the file, save the original, then review its column mapping.")
    encoding = st.selectbox("CSV encoding", ["utf-8-sig", "cp1252", "utf-16"])
    if uploaded:
        content = uploaded.getvalue()
        sheet = 0
        if uploaded.name.lower().endswith(".xlsx"):
            try:
                book = load_workbook(BytesIO(content), read_only=True)
                sheet = st.selectbox("Worksheet", book.sheetnames)
                book.close()
            except Exception as exc:
                raise ValueError("Cannot read the workbook. Upload a valid XLSX file.") from exc
        frame = load_data_with_skeleton(
            lambda: cached_load(content, uploaded.name, sheet, encoding), height=220
        )
        header_changes = frame.attrs.get("header_changes", [])
        if header_changes:
            st.info("Repeated or blank column headers were given unique names for mapping. The uploaded source remains unchanged.")
            with st.expander(f"Review {len(header_changes)} adjusted column header(s)"):
                display(pd.DataFrame(header_changes))
        display(frame.head(50))
        st.caption(f"{len(frame):,} rows. Preview shows at most 50.")
        if action_button("Save raw upload", type="primary"):
            storage.archive_raw(content, uploaded.name, kind)
            storage.save_json(f"read_options_{kind}", {"sheet": sheet, "encoding": encoding})
            st.success("Raw bytes archived without modification. Review the column mapping below.")
    manifest = storage.read_json("uploads", {})
    if manifest:
        manifest_view = pd.DataFrame.from_dict(manifest, orient="index").reset_index(names="dataset")
        visible = [column for column in ("dataset", "filename", "timestamp") if column in manifest_view]
        st.caption("Saved source files")
        display(manifest_view[visible])
    with st.expander("Map uploaded columns", expanded=True):
        column_mapping(kind)

def column_mapping(kind="jobs"):
    st.subheader("Column Mapping")
    manifest = {k:v for k,v in storage.read_json("uploads", {}).items() if k == kind}
    if not manifest:
        st.info("Save a raw upload first.")
        return
    entry = manifest[kind]
    opts = storage.read_json(f"read_options_{kind}", {"sheet": 0, "encoding": "utf-8-sig"})
    path = storage.raw_upload_path(entry, kind)
    stat = path.stat()
    frame = cached_load_path(str(path), stat.st_mtime_ns, stat.st_size, entry["hash"], opts["sheet"], opts["encoding"])
    saved = storage.read_json(f"mapping_{kind}", {})
    suggested, evidence = suggest_column_mapping(frame.columns, kind, saved)
    fresh, _ = suggest_column_mapping(frame.columns, kind)
    scope = f"mapping_{kind}_{entry['hash'][:16]}_{frame_hash(pd.DataFrame(columns=frame.columns))[:8]}"
    st.caption("Columns are matched automatically using saved choices, standard names, common aliases and conservative spelling similarity. Review the prefilled fields, then save. Ambiguous columns stay unassigned.")
    st.info(f"{sum(bool(value) for value in suggested.values())} of {len(suggested)} fields matched. Missing optional fields can remain blank.")
    with st.expander("Automatic matching details"):
        display(pd.DataFrame(evidence))
        st.caption("Scores measure header similarity, not validated mapping accuracy. Source content is not sent to an AI service.")
    mapping_fields = (("competency_id", "competency_name", "range_of_application") if kind == "psf_aai"
                      else ("job_title", "job_description", "required_skills", "qualifications"))
    if any(suggested.get(field) for field in mapping_fields):
        help_text = ("Save the detected PSF-AAI columns, including Range of Application. Review them before activation."
                     if kind == "psf_aai" else
                     "Save the clear job-ad header matches shown above. You can still change them in the form below.")
        if action_button("Apply automatic mapping", type="primary", help=help_text):
            mapped = map_columns(frame, suggested, kind, entry["hash"])
            if kind == "psf_aai":
                validate_taxonomy(mapped)
            storage.save_json(f"mapping_{kind}", suggested)
            storage.save_frame("mapped_"+kind, mapped)
            storage.save_json(f"mapping_audit_{kind}", {"timestamp": timestamp(), "dataset_hash": entry["hash"], "suggestions": evidence, "saved_mapping": suggested})
            st.success("Automatic mapping saved. Review Data Quality before activating the cleaned dataset.")
    options = [""] + list(frame.columns)
    mapping = {}
    with st.form("column_mapping"):
        for start in range(0, len(FIELDS[kind]), 2):
            for column, field in zip(st.columns(2), FIELDS[kind][start:start + 2]):
                with column:
                    default = suggested[field]
                    mapping[field] = st.selectbox(field.replace("_", " ").title(), options, index=options.index(default) if default in options else 0, key=f"{scope}_{field}")
        if action_form_submit_button("Save mapping", type="primary"):
            mapped = map_columns(frame, mapping, kind, entry["hash"])
            if kind == "psf_aai":
                validate_taxonomy(mapped)
            storage.save_json(f"mapping_{kind}", mapping)
            storage.save_frame("mapped_"+kind, mapped)
            storage.save_json(f"mapping_audit_{kind}", {"timestamp": timestamp(), "dataset_hash": entry["hash"], "suggestions": evidence, "saved_mapping": mapping})
            st.success("Mapping saved. Review Data Quality and create the cleaned dataset.")
    def reset_suggestions():
        for field, column in fresh.items():
            st.session_state[f"{scope}_{field}"] = column
    action_button("Re-detect columns", on_click=reset_suggestions, help="Replace these selections with fresh header-based suggestions; save to apply them.")

def _persist_psf_reference_files(verified=None, *, force=False):
    """Sync an already reviewed local framework and its state to shared storage."""
    if verified is None:
        path = Path(storage.ROOT) / "data/processed/verified_psf_aai.csv"
        verified = pd.read_csv(path, dtype=str, keep_default_na=False)
    from .psf_source import enrich_verified_profiles
    official_pdf = Path(storage.ROOT) / "data/reference/psf_aai_official.pdf"
    refreshed = False
    if official_pdf.is_file():
        verified, refreshed = enrich_verified_profiles(verified, official_pdf)
    if not refreshed and not force:
        return False
    processed = Path(storage.ROOT) / "data/processed"
    if verified.empty:
        raise ValueError("No saved reviewed PSF-AAI framework is available to sync.")
    if ("review_status" not in verified or not verified.review_status.eq("Researcher verified").all()
            or "reviewer" not in verified or verified.reviewer.str.strip().eq("").any()
            or "review_timestamp" not in verified or verified.review_timestamp.str.strip().eq("").any()):
        raise ValueError("The saved PSF-AAI table is missing researcher verification details; review and save it again first.")
    if any(column not in verified or verified[column].astype(str).str.strip().eq("").any()
           for column in ("source_page", "source_url")):
        raise ValueError("The saved PSF-AAI table is missing source page or URL provenance; review and save it again first.")
    validate_taxonomy(verified)
    mapped = map_columns(verified, {column: column for column in FIELDS["psf_aai"] if column in verified},
                         "psf_aai", frame_hash(verified))
    cleaned, _ = clean_dataset(mapped, "psf_aai")
    storage.save_frame("verified_psf_aai", verified)
    storage.save_frame("mapped_psf_aai", mapped)
    storage.save_frame("cleaned_psf_aai", cleaned)
    storage.save_json("mapping_psf_aai", {column: column for column in FIELDS["psf_aai"] if column in mapped})
    storage.save_json("cleaning_psf_aai", {
        "timestamp": timestamp(), "source_hash": frame_hash(mapped),
        "reviewer": "; ".join(sorted(verified.reviewer.astype(str).str.strip().unique())), "verified": True,
    })
    # Keep uploaded bytes archived; the verified table replaces its pending draft.
    uploads = storage.read_json("uploads", {})
    uploads.pop("psf_aai", None)
    storage.save_json("uploads", uploads)
    return refreshed


def activate_psf_reference(frame, reviewer):
    """Activate a reviewed PSF table in both local and shared storage."""
    from .psf_source import activate_framework
    activate_framework(frame, reviewer, storage.ROOT)
    _persist_psf_reference_files(force=True)


def _local_verified_psf_available():
    path = Path(storage.ROOT) / "data/processed/verified_psf_aai.csv"
    if not path.is_file():
        return False
    try:
        frame = pd.read_csv(path, dtype=str, keep_default_na=False)
        return bool(not frame.empty and frame.review_status.eq("Researcher verified").all()
                    and frame.reviewer.str.strip().ne("").all()
                    and frame.review_timestamp.str.strip().ne("").all())
    except (OSError, ValueError, KeyError):
        return False
    return verified


def quality():
    page_intro("Review data quality", "Check the uploaded job-ad columns and the cleaned preview, then save the job table used by the analysis.")
    kind = st.selectbox("Dataset", list(FIELDS), format_func=lambda value: {"jobs": "Job advertisements", "psf_aai": "PSF-AAI reference", "stakeholder": "Stakeholder responses"}.get(value, value))
    frame = load_data_with_skeleton(lambda: storage.read_frame("mapped_"+kind), height=180)
    if frame.empty:
        st.info("Map this dataset first.")
        return
    potential = duplicate_ids(frame)
    selected = st.multiselect("Confirm duplicate record IDs to remove from the cleaned copy", potential)
    cleaned, report = load_data_with_skeleton(
        lambda: cached_clean(frame, kind, tuple(selected)), height=220
    )
    st.caption("Missing text remains empty; it is never invented. Raw columns are retained alongside *_clean columns. Source IDs identify the raw dataset hash and row.")
    display(report)
    if potential:
        display(frame[frame.source_id.isin(potential)])
    display(cleaned.head(100))
    scope_reviewed = st.checkbox("I reviewed source evidence and confirm these advertisements have Philippine provenance and relate to AI or analytics") if kind == "jobs" else True
    reviewer = st.text_input("Framework reviewer ID") if kind == "psf_aai" else ""
    confirmed = st.checkbox("I checked this framework table against its cited source pages") if kind == "psf_aai" else True
    if action_button("Save cleaned dataset", type="primary"):
        if kind == "jobs" and not scope_reviewed:
            raise ValueError("Review Philippine provenance and AI/analytics relevance before saving the active job-analysis dataset.")
        if kind == "psf_aai":
            if not confirmed:
                raise ValueError("Review the framework source pages before activating this table.")
            activate_psf_reference(frame, reviewer)
            st.success("Reviewed PSF reference activated. Re-run extraction.")
            return
        storage.save_frame("cleaned_"+kind, cleaned)
        storage.save_frame("quality_"+kind, report)
        storage.save_json("cleaning_"+kind, {"timestamp": timestamp(), "removed_duplicate_ids": selected, "source_hash": frame_hash(frame), "philippine_aai_scope_reviewed": scope_reviewed if kind == "jobs" else False})
        if kind == "jobs" and supabase_store.configured():
            st.success("Cleaned job data and its quality report are saved to the shared workspace. Teammates can refresh to use the same dataset; the original CSV remains on the uploader’s computer.")
        else:
            st.success("Cleaned data and its quality report are saved on this computer. Configure Supabase to share them with teammates.")

def extraction():
    page_intro("Extract skill phrases", "Scan cleaned job ads, carry forward matching researcher-approved labels, and send new phrases to review.")
    with st.expander("How extraction works", expanded=False):
        st.write("Previously approved labels are attached when a normalized phrase matches the reviewed dataset. New phrases remain unreviewed candidates. Classifier predictions and AI drafts are shown separately and are never treated as researcher-approved labels.")
    if storage.read_json("uploads", {}).get("psf_aai") and _local_verified_psf_available():
        st.warning("Your reviewed PSF-AAI framework is saved on this computer but has not reached the shared workspace.")
        if action_button("Sync saved PSF-AAI framework", key="sync_saved_psf_framework", type="secondary"):
            refreshed = _persist_psf_reference_files(force=True)
            st.success("Reviewed framework synced" + (" with full competency profiles." if refreshed else ".") + " You can run extraction now.")
            st.rerun()
    taxonomy = load_data_with_skeleton(lambda: storage.read_frame("cleaned_psf_aai"), height=120)
    if taxonomy.empty:
        st.warning("No PSF-AAI taxonomy is available. Discovery can run, but it cannot claim PSF matches.")
    elif taxonomy.attrs.get("reference_source") == "bundled_default":
        st.caption("Bundled TESDA PSF-AAI reference loaded by default. A reviewed shared reference takes priority when available.")
    if not (ROOT / "models/competency_classifier.joblib").exists():
        st.info("No selected classifier yet. Extract initial phrases for manual labeling, then train both models and select one.")
    else:
        if training_data_changed():
            st.warning("Training data has changed since this model was trained. Retraining is recommended.")
    if action_button("Run extraction and classification", type="primary"):
        uploads = storage.read_json("uploads", {})
        if uploads.get("psf_aai") and _local_verified_psf_available():
            _persist_psf_reference_files(force=True)
        else:
            verified = storage.read_frame("verified_psf_aai")
            if not verified.empty:
                _persist_psf_reference_files(verified)
        _start_processing("Extract skill phrases", background_tasks.extract)
    has_results = "_extraction_results_frame" in st.session_state
    if action_button("Refresh saved results" if has_results else "Load saved results", type="secondary",
                     icon=":material/refresh:", action_id="refresh_extraction_results"):
        st.session_state["_extraction_results_page"] = 1
        _start_processing("Load saved extraction results", background_tasks.extraction_preview)
    if "_extraction_results_frame" not in st.session_state:
        st.caption("Run extraction to prepare phrases, or load previously saved results. Saved results are not downloaded when you open this page.")
        return
    result = st.session_state["_extraction_results_frame"]
    limits = result.attrs.get("discovery_limits", {})
    if result.empty:
        st.info("No saved extraction results yet. Run extraction to prepare phrases for review.")
    if not result.empty:
        approved = result.human_label.fillna("").astype(str).str.strip().ne("") if "human_label" in result else pd.Series(False, index=result.index)
        metrics = st.columns(3)
        metrics[0].metric("Researcher-approved labels", f"{int(approved.sum()):,}")
        metrics[1].metric("Unreviewed extracted phrases", f"{int((~approved).sum()):,}")
        metrics[2].metric("Model predictions (separate)", f"{int(result.model_prediction.fillna('').astype(str).str.strip().ne('').sum()):,}" if "model_prediction" in result else "0")
        choice = st.selectbox("View", ["All extracted phrases", "Researcher-approved labels", "Unreviewed candidates", "Accepted detections"])
        if choice == "Researcher-approved labels":
            result = result[approved]
        elif choice == "Unreviewed candidates":
            result = result[~approved]
        elif choice == "Accepted detections":
            accepted = result.accepted.astype(str).str.casefold().eq("true")
            result = result[accepted]
        if result.empty:
            st.caption("No rows match this view.")
        else:
            page_key = "_extraction_results_page"
            current_page = min(max(int(st.session_state.get(page_key, 1)), 1), (len(result) + 99) // 100)
            st.session_state[page_key] = current_page
            page = st.number_input("Results page", min_value=1, max_value=(len(result) + 99) // 100,
                                   value=current_page, step=1, key=page_key)
            visible, page, _ = _paginate_frame(result, page)
            first_row = (page - 1) * 100 + 1
            last_row = min(page * 100, len(result))
            st.caption(f"Showing {first_row:,}–{last_row:,} of {len(result):,} rows. Full results stay saved; only this page is sent to your browser.")
            display(visible)
        if limits.get("limited", 0):
            st.warning(f"{limits['limited']} of {limits['total']} job ads reached the {limits['cap']}-phrase cap for broad n-gram discovery. Exact vocabulary and PSF-AAI term scans still use the full text. Keeping this cap limits low-confidence review fragments; raise it in Settings only when you want a wider manual review and can inspect the extra candidates.")

def _auto_train_after_review(labels, enabled):
    """Refresh development models only from saved, provenance-checked review labels."""
    if not enabled:
        return
    _, validation = cached_label_validation(labels, .2, False, require_provenance=True)
    if validation["errors"]:
        st.warning(
            "Annotations were saved, but automatic training is waiting for the labeled dataset to pass validation. "
            "Open ML Training to see the specific fixes needed."
        )
        return
    _start_processing("Train reviewed labels", background_tasks.train, .2, False, VECTORIZER_CONFIG)


def _auto_retraining_control():
    """Offer automatic retraining only to users allowed to publish shared models."""
    shared_workspace = supabase_store.configured()
    can_train = supabase_store.is_admin() if shared_workspace else True
    enabled = st.checkbox(
        "Automatically retrain after I save reviewed labels",
        value=False,
        key="auto_train_after_review",
        disabled=not can_train,
        help=(
            "When enabled, saving labels will retrain both classifiers if the complete reviewed dataset passes validation. "
            "Training runs in the background after saving; you can keep reviewing. It never trains on AI drafts."
        ),
    )
    if shared_workspace and not can_train:
        st.caption("Only the project administrator can start model training in the shared workspace. Ask the administrator to use this option.")
    return bool(enabled and can_train)


def labeling():
    page_intro("Review and label phrases", "Choose a category and one or more PSF-AAI competencies together in the manual review table.")
    review_content = st.container()
    source_tools = st.expander("Sources and batch tools", icon=":material/settings:", key="review_source_tools", on_change="rerun")
    if source_tools.open:
        with source_tools:
            with st.expander("Optional: add remote job sources"):
                st.caption("Fetches one page (at most 20 jobs) from Himalayas, keeps only listings that explicitly allow applicants in the Philippines, and records the original listing URL. The provider can rate-limit requests. This adds source evidence only; labels still need your review.")
                if action_button("Fetch latest Philippines-eligible remote jobs", key="fetch_himalayas_jobs", disabled=not supabase_store.is_admin()):
                    from .himalayas_feed import fetch_philippines_jobs
                    try:
                        report = fetch_philippines_jobs(storage.ROOT)
                    except Exception as exc:
                        st.error(f"The feed request did not complete: {exc}")
                    else:
                        st.success(
                            f"Checked {report['response_rows']} listings; found {report['explicit_philippines_eligible_rows']} that explicitly allow applicants in the Philippines; added {report['new_rows_added']} new postings. No labels or models were changed."
                        )
                        st.caption("Source: Himalayas. Credit Himalayas and link the original listing wherever these jobs are displayed.")
                        if report["new_rows_added"]:
                            st.info("The new postings are saved under `train/remote_feeds`. Use the local AI batch tools below to extract phrases and prepare BGE-M3 drafts.")
            with st.expander("Local AI drafts — batch tools"):
                st.caption("Process up to 25 new drafts per run. Saved batches are retained; run again to continue. First use downloads about 2.3 GB and loads the model on CPU.")
                if action_button("Generate next 25 local drafts", key="run_local_suggestions", disabled=not supabase_store.is_admin()):
                    _start_processing("Generate local drafts", background_tasks.suggest_local, storage.ROOT)
            with st.expander("Prepare candidates from posting CSVs"):
                from .posting_import import prepare_posting_candidates, COUNTRY_RULE
                posting_files = [item["filename"] for item in inspect_training_folder(storage.ROOT)
                                 if item["purpose"] == "job-ad source data" and item["filename"].lower().endswith(".csv")
                                 and "derived" not in Path(item["filename"]).parts]
                st.caption("Columns are mapped automatically. " + COUNTRY_RULE)
                st.caption("This prepares blank-label candidates for review. Verify source accuracy and AI/analytics relevance before using them for research.")
                if posting_files:
                    posting_file = st.selectbox("Posting CSV in ./train", posting_files)
                    if action_button("Prepare Philippine posting candidates", disabled=not supabase_store.is_admin()):
                        with st.skeleton(height=240):
                            report = prepare_posting_candidates(storage.ROOT, posting_file)
                            candidate_path = storage.ROOT / "train" / report["candidate_file"]
                            new_candidates = pd.read_csv(candidate_path, dtype=str, keep_default_na=False)
                            shared_candidates = storage.read_frame("team_training_candidates")
                            combined_candidates = pd.concat([shared_candidates, new_candidates], ignore_index=True).drop_duplicates(
                                [column for column in ("normalized_phrase", "source_type", "source_id") if column in new_candidates], keep="last"
                            ) if not shared_candidates.empty else new_candidates
                            storage.save_frame("team_training_candidates", combined_candidates)
                        st.success(f"Prepared {report['candidate_occurrences']:,} candidates from {report['explicit_philippine_postings']:,} of {report['total_postings']:,} postings. Labels remain blank until reviewed.")
                for report_path in sorted((storage.ROOT / "train/derived").glob("postings_*/import_report.json")):
                    report = json.loads(report_path.read_text(encoding="utf-8"))
                    st.write(f"{report['source_file']}: {report['explicit_philippine_postings']:,} postings with explicit Philippine locations; {report['excluded_without_explicit_philippine_location']:,} excluded; {report['candidate_occurrences']:,} candidate occurrences.")
                    if report["postings_reaching_candidate_limit"]:
                        st.caption(f"{report['postings_reaching_candidate_limit']} postings reached the {report['candidate_limit_per_posting']}-phrase discovery limit. Full source text remains available for review.")

    with review_content:
        review_tools = st.container(horizontal=True, key="review_tools", vertical_alignment="center")
        with review_tools:
            with st.popover("Review settings", icon=":material/tune:"):
                auto_train = _auto_retraining_control()
        if supabase_store.configured():
            with review_tools:
                with st.popover("Team updates", icon=":material/sync:"):
                    st.caption("Your team can review simultaneously. Saves detect changes made by another reviewer. Refresh before starting a new batch; unsaved table edits will be discarded.")
                    if action_button("Refresh shared review table"):
                        supabase_store.clear_read_cache()
                        for key in list(st.session_state):
                            if str(key).startswith(("review_snapshot", "manual_labels_", "review_draft_", "resolve_label_")):
                                del st.session_state[key]
                        st.rerun()
            if "review_snapshot" not in st.session_state:
                st.session_state["review_snapshot"] = load_data_with_skeleton(
                    lambda: storage.read_frame("labeled_competencies"), height=120
                )
            labels = st.session_state["review_snapshot"].copy()
        else:
            labels = load_data_with_skeleton(lambda: storage.read_frame("labeled_competencies"), height=120)
        candidates, taxonomy = load_data_with_skeleton(
            lambda: _load_manual_review_data(labels), height=220
        )
        from .cleaning import normalize_text
        st.caption(f"{candidates.normalized_phrase.nunique():,} distinct phrases · {len(candidates):,} source occurrences · {len(labels):,} saved review rows")
        occurrences = candidates
        reviewed_phrases = labels_by_phrase(labels)
        categories = list(dict.fromkeys(LABELS + (labels.label.tolist() if not labels.empty else [])))
        with review_tools:
            with st.popover("Review guide", icon=":material/menu_book:"):
                st.write("Choose one leaf category. Technical / Digital is the parent of AI / Machine Learning, Data / Analytics, and general programming and digital tools. Credentials are recorded separately from competencies.")
                st.write("Use AI / Machine Learning for explicit model development or AI methods; Data / Analytics for analysis, statistics, SQL and reporting; general programming and digital tools for programming or IT without an explicit AI or analytics task. Leadership covers directing people; other enabling capabilities cover communication and personal effectiveness. Classify the phrase in its source context.")
                st.write("Examples: Python programming → general programming and digital tools; machine-learning model development → AI / Machine Learning; statistical analysis → Data / Analytics; bachelor’s degree → Credential requirement. Legacy categories require review. PSF-AAI mapping remains a separate decision.")
                st.caption("Count parent totals from distinct advertisements or occurrences, using the same unit throughout. Do not add parent totals to their child totals.")
                st.caption("Category decisions apply across a phrase. PSF-AAI decisions apply only to the source advertisement in that row.")
        with st.container(key="manual_review_workspace"):
            account_reviewer = str(st.session_state.get("supabase_user_email", "")).strip()
            if account_reviewer or supabase_store.configured():
                reviewer = account_reviewer
                st.caption(f"Signed-in reviewer: {reviewer}")
            else:
                with st.expander("Reviewer details"):
                    reviewer = st.text_input("Reviewer ID", key="label_reviewer")
            _category_review(candidates, occurrences, reviewed_phrases, categories, taxonomy, labels, reviewer, auto_train)



def _category_review(candidates, occurrences, reviewed_phrases, categories, taxonomy, labels, reviewer, auto_train):
    from .cleaning import normalize_text
    if not candidates.empty:
        source_filtered = candidates
        review_controls = st.container(horizontal=True, vertical_alignment="bottom", key="review_controls")
        with review_controls:
            review_view = st.selectbox("Review view", ["Unique phrases", "All advertisement occurrences"],
                                       key="manual_review_view", width=250)
            query = st.text_input("Find candidate phrase", placeholder="Search phrases…", width=300)
            with st.popover("Filters", icon=":material/filter_list:"):
                if "candidate_file" in candidates:
                    sources = sorted(candidates.candidate_file.unique())
                    selected_sources = st.multiselect("Candidate source files", sources)
                    if selected_sources:
                        source_filtered = candidates[candidates.candidate_file.isin(selected_sources)]
                if st.checkbox("Only show phrases awaiting category review", value=True):
                    source_filtered = source_filtered.loc[~source_filtered.normalized_phrase.isin(reviewed_phrases)]
                if st.checkbox("Hide obvious connector fragments", value=True, help="This hides phrases beginning or ending with a common connector, such as ‘with strong’ or ‘written and’. Turn it off to inspect and manually label or correct them."):
                    source_filtered = source_filtered.loc[~source_filtered.needs_phrase_edit]
        if query:
            source_filtered = source_filtered[source_filtered.phrase.str.contains(query, case=False, regex=False)]
        phrase_rows = (group_candidates_by_phrase(source_filtered) if review_view == "Unique phrases"
                       else source_filtered.drop_duplicates(["normalized_phrase", "source_type", "source_id"]).copy())
        with review_controls:
            page = st.number_input("Review page (10 rows per page)", 1, max(1, (len(phrase_rows)+9)//10), 1, width=200)
        shown = _review_contexts(phrase_rows.iloc[(page-1)*10:page*10])
        detail_tools = st.container(horizontal=True, key="review_detail_tools")
        with detail_tools, st.popover("Source evidence", icon=":material/article:"):
            # Context for the selected rows is always loaded, including training
            # sources outside the study dataset.
            st.dataframe(shown[["phrase", "source_type", "source_id", "job_title", "company", "source_url", "original_text"]], hide_index=True, width="stretch", column_config={"source_url": st.column_config.LinkColumn("Original source")})
            st.caption("Evidence belongs to the advertisement shown in each row. Use All advertisement occurrences to inspect other contexts for the same phrase.")
    else:
        st.info("No candidate phrases yet. Add Philippine job-ad source/candidate data to ./train or run Competency Extraction on uploaded jobs. No example labels are added automatically.")
        occurrences = candidates.copy()
        shown = pd.DataFrame(columns=["phrase", "normalized_phrase", "source_type", "source_id", "source_ads", "original_text"])
    from .pretrained_suggestions import (
        MODEL_ID, MODEL_REVISION,
        suggestion_key, psf_draft_candidates, draft_complete, PSF_DRAFT_LIMIT,
    )
    if shown.empty and not candidates.empty:
        st.info("No phrases match these filters. Clear the search or turn off awaiting-category review to revisit saved phrases.")
    page_rows = shown.to_dict("records") if not shown.empty else []
    page_identity = frame_hash(shown[["normalized_phrase", "phrase", "source_type", "source_id"]]) if not shown.empty else "empty"
    def generate_ai_drafts(rows):
        _start_processing("Generate AI drafts", background_tasks.suggest,
                          deepcopy(rows), taxonomy.copy(deep=True), storage.ROOT)

    if not shown.empty:
        with detail_tools, st.popover("AI details", icon=":material/auto_awesome:"):
            st.caption(f"{MODEL_ID} · revision {MODEL_REVISION[:8]} · CPU. First use downloads about 2.3 GB. Similarity scores rank suggestions; they are not accuracy measurements.")
            st.write(f"Generate drafts for each review page on this host. Up to {PSF_DRAFT_LIMIT} ranked PSF-AAI candidates per occurrence; select only those supported by the source. Manual decisions stay blank until you enter them.")
            st.caption("IRRELEVANT drafts intentionally have no PSF-AAI candidate. Drafts are local to this host; saved researcher decisions use your configured research storage.")
        if os.environ.get("VERCEL") == "1" or os.environ.get("VERCEL_URL"):
            st.warning("The Vercel image installs the suggestion package, but BGE-M3 weights download separately on first use. Vercel Hobby has 2 GB maximum function memory, so loading this model may exceed its limit; use a Pro function with sufficient memory or run suggestions on the persistent Docker/local host if it fails.")
        if taxonomy.empty:
            st.warning("Map and review the official PSF-AAI taxonomy first. Category suggestions can be generated only after competency matches have a verified taxonomy to compare against.")

    if not shown.empty:
        unit = "unique phrases" if review_view == "Unique phrases" else "advertisement occurrences"
        st.caption(f"Showing {(page - 1) * 10 + 1:,}–{min(page * 10, len(phrase_rows)):,} of {len(phrase_rows):,} {unit} · Category applies to the phrase; PSF-AAI applies only to the displayed advertisement.")
    active_taxonomy = storage.read_frame("cleaned_psf_aai")
    reference = active_taxonomy.set_index("competency_id") if not active_taxonomy.empty else pd.DataFrame()
    mapping_available = not reference.empty
    try:
        mapping_reviews = storage.read_frame(REVIEW_TABLE) if mapping_available else pd.DataFrame()
    except supabase_store.SupabaseError:
        mapping_reviews = pd.DataFrame()
        mapping_available = False
        st.warning("Competency reviews could not be loaded. Check the shared connection and occurrence-mapping migration. Category review remains available.")
    if reference.empty:
        st.caption("Activate the reviewed PSF-AAI reference to enable competency selections.")
    page_identity = digest([page_identity, frame_hash(active_taxonomy), frame_hash(mapping_reviews)])[:24]
    mapping_occurrences = manual_mapping_occurrences(shown, current_extractions(source_ids=shown.source_id.unique()))
    occurrence_lookup = {(row.source_id, row.normalized_phrase): row._asdict() for row in mapping_occurrences.itertuples(index=False)}
    page_occurrences, page_reviews = [], []
    table_rows = []
    for index, row in enumerate(page_rows):
        row_normalized = normalize_text(row.get("normalized_phrase") or row.get("phrase", ""))
        saved = reviewed_phrases.get(row_normalized)
        occurrence = occurrence_lookup.get((row.get("source_id", ""), row.get("normalized_phrase", "")))
        existing = mapping_reviews[mapping_reviews.extraction_id.eq(occurrence["extraction_id"])] if occurrence and not mapping_reviews.empty else pd.DataFrame()
        page_occurrences.append(occurrence)
        page_reviews.append(existing)
        table_row = {
            "Phrase": row.get("phrase", ""),
            "Source ads": int(row.get("source_ads", 0)),
            "Source advertisement": row.get("source_id", ""),
            "Category": saved.get("label", "") if saved else "",
            "PSF-AAI competencies": [key for key in existing.competency_id if key in reference.index] if not existing.empty else [],
        }
        table_rows.append(table_row)
    manual_table = pd.DataFrame(table_rows)
    table_config = {
        "Phrase": st.column_config.TextColumn(disabled=True, width=160, pinned=True),
        "Source ads": st.column_config.NumberColumn(help="Number of distinct source job ads containing this normalized phrase.", disabled=True),
        "Category": st.column_config.SelectboxColumn(options=[""] + list(dict.fromkeys(categories)), width=180, format_func=lambda value: category_path(value) if value else "", help="Choose one leaf in the hierarchy. Education is a credential requirement, not a competency."),
    }
    table_config["Source advertisement"] = st.column_config.TextColumn(disabled=True, width=200)
    table_config["PSF-AAI competencies"] = st.column_config.MultiselectColumn(
        options=sorted(reference.index.tolist(), key=lambda key: str(reference.loc[key, "competency_name"]).casefold()),
        format_func=lambda key: str(reference.loc[key, "competency_name"]) if key in reference.index else key,
        accept_new_options=False, disabled=not mapping_available, width=300,
        help="Select two or more competencies when this advertisement supports each. Each link requires a separate rationale below.")
    disabled_columns = ["Phrase", "Source ads", "Source advertisement"]
    table_config.update({
        "AI category draft": st.column_config.SelectboxColumn(options=[""] + LABELS, format_func=lambda value: category_path(value) if value else "", disabled=True),
        "AI PSF-AAI drafts": st.column_config.ListColumn(width=300, help="Up to three ranked candidates. Similarity ranks alternatives; it does not establish that every candidate applies."),
    })
    disabled_columns.extend(["AI category draft", "AI PSF-AAI drafts"])
    job = st.session_state.get("_background_job")
    polling_drafts = bool(job and job.title in ("Generate AI drafts", "Generate local drafts")
                          and job.snapshot()["status"] == "running")

    @st.fragment(run_every=2 if polling_drafts else None)
    def review_editor():
        nonlocal labels
        saved_suggestions = _page_ai_suggestions(storage.ROOT / "data/processed/pretrained_label_suggestions.csv")
        page_suggestions = [saved_suggestions.get(suggestion_key(row), {}) for row in page_rows]
        missing_rows = [row for row, draft in zip(page_rows, page_suggestions) if not draft_complete(draft)]
        manual_table["AI category draft"] = [item.get("category", "") if item.get("category") in LABELS else "" for item in page_suggestions]
        manual_table["AI PSF-AAI drafts"] = [[item["competency_name"] for item in psf_draft_candidates(draft)] for draft in page_suggestions]
        with st.container(horizontal=True, vertical_alignment="center", key="manual_review_actions"):
            save_action = st.container(width="content")
            generate_action = st.container(width="content")
            fullscreen = st.toggle("Full-screen review", key="manual_review_fullscreen",
                                   help="Expand the entire review workspace, including actions and evidence. Turn off to return to the page.")
        review_workspace_style(fullscreen)
        draft_key = f"review_draft_{page_identity}"
        revision_key = draft_key + "_revision"
        editor_key = f"manual_labels_{page_identity}_{st.session_state.get(revision_key, 0)}"
        if draft_key not in st.session_state:
            st.session_state[draft_key] = manual_table.copy()
        # Refresh draft values after generation without discarding manual edits.
        draft_revision = frame_hash(manual_table.drop(columns=["Category", "PSF-AAI competencies"], errors="ignore"))
        if st.session_state.get(draft_key + "_source") != draft_revision:
            current = st.session_state[draft_key].reindex(columns=manual_table.columns).copy()
            # Apply any just-arrived browser edits before replacing the widget
            # key for new read-only drafts. Never overwrite a manual selection.
            for index, changes in st.session_state.get(editor_key, {}).get("edited_rows", {}).items():
                if int(index) in current.index:
                    for column in ("Category", "PSF-AAI competencies"):
                        if column in changes:
                            current.at[int(index), column] = changes[column]
            for column in manual_table.columns:
                if column not in ("Category", "PSF-AAI competencies"):
                    current[column] = manual_table[column]
            st.session_state[draft_key] = current
            st.session_state[draft_key + "_source"] = draft_revision
            st.session_state[revision_key] = st.session_state.get(revision_key, 0) + 1
        edited_table = st.data_editor(
            st.session_state[draft_key],
            hide_index=True,
            num_rows="fixed",
            width="stretch",
            disabled=disabled_columns,
            column_config=table_config,
            column_order=["Phrase", "Category", "PSF-AAI competencies", "AI category draft", "AI PSF-AAI drafts", "Source ads", "Source advertisement"],
            row_height=52,
            height=min(580, 52 * len(manual_table) + 40),
            alt="Manual review: phrase, category, selected competencies, AI drafts and source advertisement",
            key=f"manual_labels_{page_identity}_{st.session_state.get(revision_key, 0)}",
        ) if not manual_table.empty else manual_table
        st.session_state[draft_key] = edited_table.copy()
        if page_rows:
            st.caption(f"{len(page_rows) - len(missing_rows)} of {len(page_rows)} drafts ready on this page · {len(missing_rows)} need generation. Drafts update here as batches finish.")
        mapping_updates = []
        for index, row in edited_table.iterrows():
            occurrence = page_occurrences[index]
            saved = page_reviews[index]
            selected = list(row["PSF-AAI competencies"]) if row["PSF-AAI competencies"] is not None else []
            original = list(manual_table.iloc[index]["PSF-AAI competencies"])
            changed = set(selected) != set(original)
            if not mapping_available or not (selected or not saved.empty or changed):
                continue
            with st.expander(f"Evidence: {row['Phrase']} — ad {row['Source advertisement']}", expanded=changed):
                if not occurrence or not str(occurrence.get("original_text", "")).strip():
                    st.warning("Source text is missing. Restore the advertisement context before saving competency links.")
                else:
                    st.text(str(occurrence["original_text"]))
                if occurrence and occurrence.get("pending_extraction"):
                    st.caption("This candidate enters analysis only after the same occurrence is extracted and accepted. Changed evidence requires another review.")
                stale = bool(occurrence and not saved.empty and (
                    saved.reference_hash.ne(frame_hash(active_taxonomy)).any() or
                    saved.occurrence_hash.ne(occurrence_hash(occurrence)).any()))
                if stale:
                    st.warning("Saved links are stale. Review the source and selected competencies again.")
                key = f"table_psf_{page_identity}_{index}"
                update_evidence = st.checkbox("Update or confirm this occurrence's mapping", value=changed,
                                              key=key + "_update")
                old_reasons = dict(zip(saved.competency_id, saved.rationale)) if not saved.empty else {}
                reasons = {}
                for competency in selected:
                    if competency not in reference.index:
                        continue
                    st.write(reference.loc[competency, "competency_name"])
                    st.caption(str(reference.loc[competency].get("competency_description", "")))
                    if reference.loc[competency].get("range_of_application", ""):
                        st.caption("Range of application: " + str(reference.loc[competency]["range_of_application"]))
                    reasons[competency] = st.text_area("Source evidence and rationale", value=old_reasons.get(competency, ""), key=key + "_" + competency)
                no_match = st.text_area("Reason for no mapping", value=old_reasons.get("", ""), key=key + "_none") if not selected else ""
                confirmed = st.checkbox("I checked the source context and each selected competency; every link is justified.", key=key + "_confirmed_" + digest(selected)[:8])
                if changed or update_evidence:
                    mapping_updates.append((occurrence, reasons, confirmed, no_match, saved, selected))
        reviewed_rows = []
        for index, row in edited_table.iterrows():
            category = row.get("Category", "")
            source_row = page_rows[index]
            reviewed_rows.append({
                "phrase": source_row.get("phrase", ""), "normalized_phrase": normalize_text(source_row.get("normalized_phrase") or source_row.get("phrase", "")),
                "source_type": source_row.get("source_type", ""), "source_id": source_row.get("source_id", ""),
                "label": str(category or "").strip(), "psf_competency": "",
            })
        edited = pd.DataFrame(reviewed_rows, columns=["phrase", "normalized_phrase", "source_type", "source_id", "label", "psf_competency"])

        def show_conflict_resolutions(rows, key_prefix):
            conflicts = annotation_conflicts(rows, labels)
            saved_conflicts = annotation_conflicts(pd.DataFrame(columns=["phrase", "label"]), labels)
            for normalized, item in saved_conflicts.items():
                if normalized not in conflicts:
                    conflicts[normalized] = item
                else:
                    conflicts[normalized]["labels"] = sorted(
                        set(conflicts[normalized]["labels"]) | set(item["labels"]), key=str.casefold
                    )
            resolutions = {}
            invalid_choices = []
            if conflicts:
                st.warning(f"{len(conflicts)} normalized phrase(s) have more than one category across the saved dataset and this page. Choose one category for each; it will be applied to every occurrence, including previously saved rows.")
                st.caption("One row per phrase. Choose a category from the values shown for that phrase; the choice will be applied to all saved occurrences.")
                table = pd.DataFrame([
                    {"Phrase": item["phrase"], "Existing categories": " · ".join(item["labels"]), "Choose category": "— Choose a category —"}
                    for item in conflicts.values()
                ], index=list(conflicts.keys()))
                choices = ["— Choose a category —"] + sorted(
                    {label for item in conflicts.values() for label in item["labels"]}, key=str.casefold
                )
                edited_resolutions = st.data_editor(
                    table,
                    hide_index=True,
                    num_rows="fixed",
                    width="stretch",
                    key=f"{key_prefix}_conflict_table_{frame_hash(table)}",
                    disabled=["Phrase", "Existing categories"],
                    column_config={
                        "Phrase": st.column_config.TextColumn("Normalized phrase", disabled=True),
                        "Existing categories": st.column_config.TextColumn(disabled=True),
                        "Choose category": st.column_config.SelectboxColumn(options=choices, required=True),
                    },
                )
                for normalized, row in edited_resolutions.iterrows():
                    choice = row["Choose category"]
                    if choice == "— Choose a category —":
                        continue
                    if choice in conflicts[normalized]["labels"]:
                        resolutions[normalized] = choice
                    else:
                        invalid_choices.append(conflicts[normalized]["phrase"])
                if invalid_choices:
                    st.warning("Choose only a category already listed for each phrase: " + ", ".join(invalid_choices))
                st.caption("Saving your choices makes each phrase use one category everywhere. Previous values are retained in annotation history.")
            resolved = len(resolutions) == len(conflicts) and not invalid_choices
            return conflicts, resolutions, resolved

        conflicts, conflict_resolutions, conflicts_resolved = show_conflict_resolutions(edited, "resolve_label")
        if supabase_store.configured() and not reviewer.strip():
            st.warning("Your account session is unavailable. Sign in again to save.")
        has_category = bool(not edited.empty and edited.label.astype(str).str.strip().ne("").any())
        if not has_category:
            st.caption("Choose a category or review competency links before saving.")
        st.caption("Saving records the values currently in the manual fields, reviewer ID, source, and timestamp. AI drafts remain in a separate file and are never training labels by themselves.")
        can_submit = has_category or bool(conflicts) or bool(mapping_updates)
        with generate_action:
            generate_clicked = action_button("Generate missing AI drafts" if missing_rows or shown.empty else "Regenerate page drafts", icon=":material/auto_awesome:", key=f"suggest_labels_{page_identity}", disabled=shown.empty or taxonomy.empty or not supabase_store.is_admin() or bool(job and job.snapshot()["status"] == "running"))
        with save_action:
            save_clicked = action_button("Save annotations", icon=":material/save:", type="primary", disabled=not reviewer.strip() or not conflicts_resolved or not can_submit)
        if generate_clicked:
            generate_ai_drafts(missing_rows or page_rows)
        if save_clicked:
            try:
                for occurrence, reasons, confirmed, no_match, saved, selected in mapping_updates:
                    if not occurrence or not str(occurrence.get("original_text", "")).strip():
                        raise ValueError("Restore the source advertisement text before saving competency links.")
                    if set(selected) != set(reasons):
                        raise ValueError("Select competencies from the active PSF-AAI reference.")
                    prepare_mapping_review(occurrence, active_taxonomy, reasons, reviewer, confirmed, no_match)
            except ValueError as exc:
                st.error(str(exc))
                return
            submitted_rows = edited[edited.label.str.strip().ne("")]
            versions = None
            if supabase_store.configured():
                versions = {r.normalized_phrase: int(r.version) for r in labels.itertuples()}
                changed = [i for i, row in edited_table.iterrows()
                           if row.get("Category", "") != manual_table.iloc[i].get("Category", "")]
                changed_phrases = {normalize_text(page_rows[index].get("normalized_phrase") or page_rows[index].get("phrase", "")) for index in changed}
                submitted_rows = submitted_rows[submitted_rows.normalized_phrase.isin(changed_phrases)]
            submitted_rows = preserve_occurrence_references(expand_phrase_annotations(submitted_rows, occurrences), labels)
            categories_saved = bool(submitted_rows.label.str.strip().ne("").any() or conflicts)
            if categories_saved:
                labels = save_annotations(submitted_rows, reviewer, conflict_resolutions=conflict_resolutions, expected_versions=versions)
            saved_links = 0
            try:
                for occurrence, reasons, confirmed, no_match, saved, selected in mapping_updates:
                    save_mapping_review(occurrence, active_taxonomy, reasons, reviewer,
                                        expected_version=int(saved.version.iloc[0]) if not saved.empty else 0,
                                        context_confirmed=confirmed, unmapped_reason=no_match)
                    saved_links += 1
            except (ValueError, supabase_store.SupabaseError) as exc:
                supabase_store.clear_read_cache()
                st.warning(f"Partial save: category annotations {'were saved' if categories_saved else 'were unchanged'}; {saved_links} occurrence mapping(s) saved. Refresh before retrying. {exc}")
                return
            if mapping_updates:
                supabase_store.clear_read_cache()
                # Refresh these defaults and versions after the successful batch.
                fresh = storage.read_frame(REVIEW_TABLE)
                for index, occurrence in enumerate(page_occurrences):
                    if occurrence:
                        page_reviews[index] = fresh[fresh.extraction_id.eq(occurrence["extraction_id"])] if not fresh.empty else pd.DataFrame()
                manual_table["PSF-AAI competencies"] = edited_table["PSF-AAI competencies"].copy()
            if supabase_store.configured():
                st.session_state.pop("review_snapshot", None)
                for key in list(st.session_state):
                    if str(key).startswith(("manual_labels_", "review_draft_")):
                        del st.session_state[key]
            st.success(f"Saved. The dataset has {len(labels):,} category review rows; updated competency links for {saved_links} advertisement occurrence(s).")
            if st.session_state.get("backup_warning"):
                st.warning(st.session_state.pop("backup_warning"))
            _auto_train_after_review(labels, auto_train)
        uploaded = None
        if not supabase_store.configured():
            with st.expander("Import team annotations", icon=":material/upload:"):
                st.caption("Merge reviewed files from teammates. Reviewer IDs and timestamps are preserved; resolve any category conflicts before importing.")
                uploaded = st.file_uploader("Import teammate-reviewed CSV/XLSX (preserves reviewer IDs and timestamps)", type=["csv", "xlsx"])
        imported = load_data(uploaded.getvalue(), uploaded.name) if uploaded else pd.DataFrame()
        import_conflicts, import_resolutions, import_conflicts_resolved = show_conflict_resolutions(imported, "resolve_import_label") if uploaded else ({}, {}, True)
        if uploaded and action_button("Import annotations", disabled=not import_conflicts_resolved):
            labels = save_annotations(imported, reviewer, conflict_resolutions=import_resolutions, preserve_row_provenance=True)
            st.success("Teammate annotations merged. Original reviewer IDs and timestamps were preserved; rows without source provenance will not qualify for training.")
            _auto_train_after_review(labels, auto_train)
        if not labels.empty:
            with st.expander("Saved category annotations"):
                display(labels)
        st.download_button("Download reviewed training data", export_csv(labels), "labeled_competencies.csv", "text/csv")
        # End polling only when it cannot interrupt a manual decision. Otherwise
        # retain this view and its original conflict versions until navigation.
        manual_columns = ["Category", "PSF-AAI competencies"]
        pending_edits = not edited_table.reindex(columns=manual_columns).equals(manual_table.reindex(columns=manual_columns))
        evidence_visible = bool(mapping_updates) or any(
            len(value) for value in edited_table.get("PSF-AAI competencies", []) if value is not None
        ) or any(not saved.empty for saved in page_reviews)
        if polling_drafts and job.snapshot()["status"] != "running" and not pending_edits and not evidence_visible:
            st.rerun()
    review_editor()


def training():
    page_intro("Train classifier", "Train Naive Bayes and Logistic Regression models using researcher-reviewed labels. Training stays disabled until the real dataset passes the validation checks.")
    if supabase_store.configured():
        path = None
        st.caption("Training source: saved researcher-reviewed labels in the shared workspace.")
    else:
        inventory = load_data_with_skeleton(lambda: inspect_training_folder(storage.ROOT), height=140)
        with st.expander("Detected files in ./train"):
            display(pd.DataFrame(inventory))
        try:
            path = resolve_training_file(storage.ROOT)
        except ValueError as exc:
            st.warning(str(exc))
            path = None
        options = [item["filename"] for item in inventory if item["purpose"] in ("labeled phrases", "empty label schema") and item["filename"].lower().endswith(".csv")]
        if len(options) > 1:
            current = str(path.relative_to(storage.ROOT / "train")) if path else ""
            choice = st.selectbox("Labeled training file", options, index=options.index(current) if current in options else 0)
            if action_button("Use selected training file"):
                path = select_training_file(storage.ROOT, choice)
        if path is None:
            return
        st.caption(f"Training data file: `{project_relative_path(path)}`")
    fraction = st.slider("Holdout fraction", .1, .5, .2, .05)
    include_irrelevant = st.checkbox("Intentionally train IRRELEVANT as a separate class", value=False)
    max_features = st.number_input("Maximum TF-IDF features", 100, 100000, 10000, 100)
    def load_training_review_data():
        current_labels = (storage.read_frame("labeled_competencies") if supabase_store.configured()
                          else load_labeled_data(path))
        validated, report = cached_label_validation(
            current_labels, fraction, include_irrelevant, require_provenance=True
        )
        return current_labels, validated, report
    labels, data, validation = load_data_with_skeleton(load_training_review_data, height=240)
    a, b, c = st.columns(3)
    a.metric("Labeled file rows", validation["total_rows"])
    b.metric("Distinct usable phrases", validation["rows_used"])
    c.metric("Classes", validation["number_of_classes"])
    if not data.empty:
        chart(distribution(data, "label", "Usable manually labeled examples per category"))
    for warning in validation["warnings"]:
        st.warning(warning)
    if validation["errors"]:
        st.info("Training unavailable: " + " ".join(validation["errors"]))
        st.write(f"At least {validation.get('additional_distinct_labels_needed', 30)} more distinct usable labels needed; {validation.get('additional_classes_needed', 2)} additional classes needed. Each class must have five examples with source IDs, reviewer and timestamp.")
    with st.expander("Dataset validation details"):
        st.json(validation)
    config = VECTORIZER_CONFIG | {"max_features": int(max_features)}
    with st.expander("Advanced training settings", expanded=False):
        st.json({"TF-IDF": config, "holdout_fraction": fraction, "random_state": 42,
                 "Logistic Regression": {"max_iter": 1000, "class_weight": "balanced"},
                 "Multinomial Naive Bayes": {"alpha": 1.0}, "include_irrelevant": include_irrelevant})
    if supabase_store.configured():
        st.caption("Team reviewers label together. Only the administrator starts model training; each run uses a fixed shared-label snapshot.")
    st.caption("Minimum software gate: 30 distinct phrases, two classes, five examples per class, no conflicting labels, complete provenance and a feasible holdout by job-ad source. These minimums do not establish adequate research validation. Cross-validation is grouped by source where each fold can contain all categories. Models are trained only by the button below.")
    if training_data_changed():
        st.warning("Training data has changed since this model was trained. Retraining is recommended.")
    if action_button("Train / Retrain Models", type="primary", disabled=bool(validation["errors"]) or not supabase_store.is_admin()):
        _start_processing("Train reviewed labels", background_tasks.train, fraction, include_irrelevant,
                          {"max_features": int(max_features)})
    metadata = read_model_metadata()
    if metadata:
        comparison = storage.read_frame("model_metrics")
        if not comparison.empty:
            st.dataframe(comparison.style.apply(lambda row: ["background-color: #d9f0e8" if str(row.get("selected", "")).casefold() == "true" else ""] * len(row), axis=1), hide_index=True, width="stretch")
        st.write("Selected model:", metadata["model_name"])
        st.caption("Based on the current labeled validation sample. The evaluated training-partition model is saved without refitting on holdout examples. Review per-class errors and validate on an independent sample before publication.")


def evaluation():
    page_intro("Evaluate models", "Review model evaluation only when the holdout represents independent job-ad sources.")
    with st.expander("How to read the evaluation metrics", expanded=False):
        st.markdown("**Precision** is the share of a model's category predictions that are correct. **Recall** is the share of actual items in a category that the model finds. **F1-score** balances precision and recall. Macro F1 weighs categories equally; Weighted F1 accounts for category frequency.")
    metadata, metrics = load_data_with_skeleton(
        lambda: (read_model_metadata(), storage.read_frame("model_metrics")), height=160
    )
    if not metadata or metrics.empty:
        st.info("No research model has been trained. Complete manual labeling and the training gate before any F1-scores or other model results can be reported.")
        return
    st.write("Selected model:", metadata["model_name"])
    try:
        training_frame = (storage.read_frame("training_snapshot") if supabase_store.configured() else load_labeled_data(resolve_training_file(storage.ROOT)))
        overlap = source_overlap(training_frame, metadata)
    except (ValueError, OSError):
        overlap = None
        training_frame = pd.DataFrame()
    split_info = metadata.get("split", {})
    too_few_test_sources = split_info.get("strategy", "").startswith("source-disjoint") and len(set(split_info.get("test_source_ids", []))) < 2
    if overlap or too_few_test_sources or split_info.get("strategy", "").startswith("stratified phrase-level"):
        st.error("These saved scores do not provide adequate evidence of generalization across independent job ads, so they are withheld from research reporting. Label more independent ads across categories, then retrain with a source-disjoint evaluation.")
        if overlap:
            st.caption(f"Detected {len(overlap)} source ID(s) in both partitions. Existing model artifacts and metrics are retained for audit, but are not displayed as research results.")
        elif too_few_test_sources:
            st.caption(f"The held-out partition contains only {len(set(split_info.get('test_source_ids', [])))} independent job-ad source. That is too limited to show generalization across postings; the saved metrics are withheld.")
        return
    a, b, c = st.columns(3)
    a.metric("Selected holdout accuracy", f"{metadata['accuracy']:.3f}")
    b.metric("Selected holdout Macro F1", f"{metadata['macro_f1']:.3f}")
    c.metric("Selected holdout Weighted F1", f"{metadata['weighted_f1']:.3f}")
    st.caption("Based on the current labeled validation sample. Selection uses Macro F1, then Weighted F1 and minimum per-class F1; accuracy is not the selection criterion.")
    if training_data_changed():
        st.warning("Training data has changed since this model was trained. Retraining is recommended.")
    display(metrics)
    data = metrics.melt(id_vars="model", value_vars=["accuracy", "macro_f1", "weighted_f1"], var_name="metric", value_name="score")
    data.score = pd.to_numeric(data.score)
    chart(bar(data, "model", "score", "Model Metric Comparison", "metric"))
    choice = st.selectbox("Evaluation model", metrics.model.tolist(), index=metrics.model.tolist().index(metadata["model_name"]))
    slug = "nb" if choice.startswith("Multinomial") else "lr"
    matrix, per_class, predictions = load_data_with_skeleton(
        lambda: (
            storage.read_frame(f"evaluation_{slug}_confusion"),
            storage.read_frame(f"evaluation_{slug}_per_class"),
            storage.read_frame(f"evaluation_{slug}_predictions"),
        ), height=220
    )
    matrix = matrix.set_index("actual").apply(pd.to_numeric)
    chart(heatmap(matrix, "Model Confusion Matrix — actual rows, predicted columns"))
    display(per_class)
    display(predictions)
    st.subheader("Stratified cross-validation (training partition only)")
    st.json(metadata["cross_validation_results"][choice])
    with st.expander("Reproducibility metadata"):
        st.json(metadata)
    phrase = st.text_input("Phrase to classify with the saved selected model")
    if action_button("Predict competency category", disabled=not phrase.strip()):
        prediction = predict_competency_category(phrase)
        st.json(prediction)
        st.caption("Confidence is the classifier's uncalibrated probability estimate, not a guarantee of correctness. This preview does not change human annotations.")
    for filename in ("model_metrics.csv", "classification_report.csv", "confusion_matrix.csv", "model_comparison.csv", "test_predictions.csv"):
        path = storage.ROOT / "outputs/tables" / filename
        if path.exists():
            st.download_button(filename, path.read_bytes(), filename, "text/csv", key="evaluation_"+filename)
    st.download_button("model_metadata.json", json.dumps(metadata, indent=2), "model_metadata.json", "application/json")


def psf_mapping_review(skills, jobs, taxonomy, mapping, reviews, *, prefix="psf", reviewer_id=None):
    if prefix != "manual":
        st.subheader("Review competency links")
    st.caption("A skill occurrence is a distinct phrase in one advertisement. Select several competencies only when this source context supports each meaning. Broad wording alone is insufficient. Saving replaces the links for this occurrence only.")
    if skills.empty or taxonomy.empty:
        st.info("Accepted skill occurrences and an active PSF-AAI reference are required to review links.")
        return
    if "range_of_application" not in taxonomy or taxonomy.range_of_application.fillna("").astype(str).str.strip().eq("").all():
        st.caption("The active TESDA PDF has no separate Range of Application field; no range text is available to compare.")
    if st.session_state.pop(f"{prefix}_review_saved", False):
        st.success("Competency links saved. Other advertisements keep their own mappings.")
    occurrences = skills.drop_duplicates("extraction_id").set_index("extraction_id")
    extraction_id = st.selectbox("Source advertisement" if prefix == "manual" else "Skill occurrence", occurrences.index.tolist(),
                                 format_func=lambda key: f"{occurrences.loc[key, 'original_phrase']} — ad {occurrences.loc[key, 'source_id']}",
                                 key=f"{prefix}_review_occurrence")
    occurrence = occurrences.loc[extraction_id].to_dict() | {"extraction_id": extraction_id}
    source = jobs[jobs.source_id.eq(occurrence["source_id"])] if not jobs.empty else jobs
    if not source.empty:
        display(source.reindex(columns=[key for key in ("source_id", "job_title", "company", "url") if key in source]))
    with st.expander("Source advertisement text", expanded=True):
        st.text(str(occurrence.get("original_text", "")))
    if occurrence.get("pending_extraction") is True:
        st.info("This candidate is not in the current extraction. Saved links enter analysis only after the same occurrence is extracted and accepted. Changed evidence will require another review.")
    if not str(occurrence.get("original_text", "")).strip():
        st.warning("Source text is missing. Restore the advertisement context before reviewing competency links.")
        return
    saved = reviews[reviews.extraction_id.eq(extraction_id)] if not reviews.empty else reviews
    current = mapping[mapping.extraction_id.eq(extraction_id)]
    reference = taxonomy.fillna("").set_index("competency_id")
    defaults = saved.competency_id.tolist() if not saved.empty else current.competency_id.tolist()
    defaults = [key for key in defaults if key in reference.index]
    if not current.empty and current.mapping_review_status.eq("STALE").any():
        st.warning("The source or reference changed. Check the saved choices and update this review.")
    from .psf_reviews import occurrence_hash
    if not saved.empty and (saved.reference_hash.ne(frame_hash(taxonomy)).any()
                            or saved.occurrence_hash.ne(occurrence_hash(occurrence)).any()):
        st.warning("Saved links need review because the source or PSF-AAI reference changed. Check each choice and rationale before saving again.")
    revision = prefix + digest([extraction_id, frame_hash(taxonomy), occurrence_hash(occurrence), frame_hash(saved)])[:16]
    chosen = st.multiselect("PSF-AAI competencies", sorted(reference.index.tolist(), key=lambda key: str(reference.loc[key, 'competency_name']).casefold()), default=defaults,
                            format_func=lambda key: f"{reference.loc[key, 'competency_name']} ({key})",
                            key=f"psf_choices_{revision}", placeholder="Search and select one or more competencies",
                            help="Select another option to add it. Remove a selected tag with its × button. Each link needs its own source-based rationale.")
    st.caption(f"{len(chosen)} competencies selected. Broad wording alone does not justify multiple links.")
    old_reasons = dict(zip(saved.competency_id, saved.rationale)) if not saved.empty else {}
    with st.form(f"psf_review_{revision}"):
        reviewer = reviewer_id
        account_reviewer = str(st.session_state.get("supabase_user_email", "")).strip()
        if account_reviewer or supabase_store.configured():
            reviewer = account_reviewer
            if not reviewer:
                st.warning("Your account session is unavailable. Sign in again to save.")
        elif reviewer is None:
            reviewer = st.text_input("Reviewer ID", key=f"psf_reviewer_{revision}")
        reasons = {}
        for key in chosen:
            st.write(reference.loc[key, "competency_name"])
            st.caption(str(reference.loc[key].get("competency_description", "")) or "No description supplied in the active reference.")
            if reference.loc[key].get("range_of_application", ""):
                st.caption("Range of application: " + str(reference.loc[key]["range_of_application"]))
            reasons[key] = st.text_area("Source evidence and rationale", value=old_reasons.get(key, ""),
                                        key=f"psf_reason_{revision}_{key}",
                                        help="Explain how the phrase in this advertisement corresponds to this specific competency.")
        no_match_reason = st.text_area("Reason for no mapping", value=old_reasons.get("", "")) if not chosen else ""
        confirmed = st.checkbox("I checked the source context and each selected competency; every link is justified.")
        if action_form_submit_button("Save competency links", action_id=f"psf_review_{revision}"):
            try:
                save_mapping_review(occurrence, taxonomy, reasons, reviewer,
                                    expected_version=int(saved.version.iloc[0]) if not saved.empty else 0,
                                    context_confirmed=confirmed, unmapped_reason=no_match_reason)
            except (ValueError, supabase_store.SupabaseError) as exc:
                st.error(str(exc))
            else:
                supabase_store.clear_read_cache()
                st.session_state[f"{prefix}_review_saved"] = True
                st.rerun()


def research_page(page):
    descriptions = {
        "Job Market Analysis": "Explore employer demand within the selected job-ad sample.",
        "PSF Mapping": "Review each skill in its advertisement context and justify its framework links.",
        "Employer–PSF Alignment": "Compare employer phrases with the reviewed framework reference.",
        "Unmapped / Emerging Skills": "Investigate recurring demand that needs further framework review.",
        "Reports": "Export the selected evidence, research tables, and analysis metadata.",
    }
    page_intro(page, descriptions.get(page, ""))
    if not current_analysis():
        return
    tables, meta = load_data_with_skeleton(filtered_bundle, height=300)
    jobs, skills = tables["cleaned_jobs"], tables["extracted_job_skills"]
    demand, alignment = tables["employer_skill_demand"], tables["alignment_results"]
    if page == "Job Market Analysis":
        profile = job_profile_tables(jobs)
        st.subheader("Occupations and job requirements")
        st.caption("Counts use distinct selected job advertisements. Requirement categories use source-provided fields; text matches are shown separately as candidates for researcher verification.")
        for key, title, label in (
            ("job_title_counts", "Most common job titles", "Job title"),
            ("job_family_counts", "Source-provided occupational families", "Job family"),
            ("education_requirement_counts", "Education requirement fields", "Education requirement"),
            ("experience_requirement_counts", "Experience requirement fields", "Experience requirement"),
        ):
            frame = profile[key]
            if not frame.empty:
                chart(bar(frame.head(20), frame.columns[0], "job_ads", title))
                display(frame)
        with st.expander("Source text candidates for education and experience evidence"):
            evidence = profile["requirement_evidence"]
            if evidence.empty:
                st.info("No matching requirement evidence was found in the selected job records.")
            else:
                st.caption("Pattern matches are candidates only. Verify each source field and context before describing it as a job requirement.")
                display(evidence)
        if not demand.empty:
            chart(bar(demand.head(20), "employer_skill", "employer_demand_count", "Top Employer-Demanded Skills"))
        for kind, title in (("Soft / Enabling", "Top Soft / Enabling Skills"), ("Technical", "Top Technical Skills")):
            if not skills.empty:
                chart(distribution(skills[skills.skill_type.eq(kind)], "normalized_phrase", title))
        if not skills.empty:
            chart(distribution(skills, "competency_category", "Competency Category Distribution"))
        for field, title in (("job_title", "Skills by Job Title"), ("location", "Skills by Location")):
            matrix = demand_matrix(skills, jobs, field)
            if not matrix.empty:
                chart(heatmap(matrix.head(30), title))
        mappings = tables["psf_mapping"]
        if not mappings.empty:
            roles = mappings.assign(psf_job_role=mappings.psf_job_role.str.split("; ")).explode("psf_job_role")
            chart(distribution(roles.drop_duplicates(["source_id", "psf_job_role"]), "psf_job_role", "PSF Job Role Demand"))
            chart(distribution(mappings.drop_duplicates(["source_id", "psf_competency"]), "psf_competency", "Employer Demand by PSF Competency"))
        if "posting_date_parsed" in jobs:
            dates = pd.to_datetime(jobs.posting_date_parsed, errors="coerce").dropna().dt.to_period("M").astype(str).value_counts().sort_index().rename_axis("month").reset_index(name="postings")
            if not dates.empty:
                chart(px.line(dates, x="month", y="postings", markers=True, title="Job Posting Trend"))
        display(jobs)
    elif page == "PSF Mapping":
        st.caption("Employer skill → PSF-AAI competency. Roles and levels are reference metadata, not inferred applicant attainment. Similarity scores are heuristic evidence, not calibrated probabilities.")
        psf_mapping_review(skills, jobs, storage.read_frame("cleaned_psf_aai"),
                           tables["psf_mapping"], tables["psf_mapping_reviews"])
        st.subheader("Competency demand")
        st.caption("Distinct advertisements and distinct skill phrases per competency. Repeated skills and multiple links do not count an advertisement twice for the same competency.")
        display(tables["psf_competency_demand"])
        st.subheader("Occurrence-level mapping evidence")
        display(tables["psf_mapping"])
    elif page == "Employer–PSF Alignment":
        st.caption("Thresholds are researcher-configurable heuristics, not official PSF standards. Default: ≥0.80 aligned; ≥0.60 partially aligned; lower scores not mapped. Missing reference: unclassified.")
        active_reference = storage.read_frame("cleaned_psf_aai")
        has_range = ("range_of_application" in active_reference and
                     active_reference.range_of_application.fillna("").astype(str).str.strip().ne("").any())
        st.caption("Results show the PSF competency description and verified Range of Application as supporting reference evidence; these fields help researchers inspect the comparison and do not establish equivalence." if has_range else "Results show the PSF competency description as supporting evidence. The active TESDA PDF has no separate Range of Application field, so no range text is available to compare.")
        rates = meta["rates_before_status_display_filter"]
        cols = st.columns(3)
        for col, field in zip(cols, ("alignment_rate", "partially_aligned_rate", "unmapped_rate")):
            if rates.get(field) is not None:
                col.metric(field.replace("_", " ").title(), f"{rates[field]:.1f}%")
        chart(distribution(alignment, "status", "Status of Phrase–Competency Evidence Groups"))
        st.subheader("Phrase-level results and PSF-AAI basis")
        display(alignment)
        display(demand)
        st.caption(meta["denominators"])
    elif page == "Unmapped / Emerging Skills":
        st.caption("Not clearly mapped to PSF-AAI does not establish that the framework lacks a skill. Emerging candidates require human and longitudinal validation.")
        for key, title in (("unmapped_skills", "Top Unmapped Skills"), ("emerging_skills", "Emerging Skill Candidates")):
            st.subheader(title)
            frame = tables[key]
            if not frame.empty:
                chart(bar(frame.head(20), "employer_skill", "employer_demand_count", title))
            display(frame)
        st.caption(f"Emerging-candidate screening requires at least {meta['settings']['emerging_min_jobs']} distinct job ads and NOT MAPPED status. Rejected/unreviewed n-grams are not counted as employer skills.")
    elif page == "Reports":
        tables.update(job_profile_tables(jobs))
        tables["corrections"] = corrections()
        def load_report_tables():
            extras = {
                "nlp_processed": storage.read_frame("nlp_processed"),
                "usability": storage.read_frame("usability"),
            }
            for slug in ("nb", "lr"):
                for report_name in ("per_class", "confusion", "predictions"):
                    extras[f"evaluation_{slug}_{report_name}"] = storage.read_frame(
                        f"evaluation_{slug}_{report_name}"
                    )
            for kind in FIELDS:
                extras["quality_"+kind] = storage.read_frame("quality_"+kind)
            return extras
        tables.update(load_data_with_skeleton(load_report_tables, height=220))
        downloads = st.expander(f"Individual research tables ({len(tables)})", key="individual_exports", on_change="rerun")
        if downloads.open:
            with downloads:
                for name, frame in tables.items():
                    st.download_button(name + ".csv", lambda frame=frame: export_csv(frame), name + ".csv", "text/csv", key="download_"+name, on_click="ignore")
        st.subheader("Research deliverables")
        st.caption("Downloads use the current sample and filters. Keep the metadata with the exported evidence.")
        st.download_button("Download research_results.xlsx", lambda: export_excel(tables, meta), "research_results.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", type="primary", icon=":material/table_view:", on_click="ignore")
        st.download_button("Download written research report (.md)", lambda: export_research_report(tables, meta), "philippine_job_ads_psf_aai_report.md", "text/markdown", on_click="ignore")
        st.download_button("Download HTML research summary", lambda: export_html(tables, meta), "research_summary.html", "text/html", on_click="ignore")
        st.download_button("Download analysis metadata", json.dumps(meta, indent=2, default=str), "analysis_metadata.json", "application/json")
        if action_button("Save this report snapshot locally"):
            with st.spinner("Preparing the complete report snapshot…"):
                workbook = export_excel(tables, meta)
                research_report = export_research_report(tables, meta)
                summary = export_html(tables, meta)
            folder = ROOT / "outputs/reports" / timestamp().replace(":", "-")
            folder.mkdir(parents=True, exist_ok=True)
            storage.atomic_bytes(folder / "research_results.xlsx", workbook)
            storage.atomic_bytes(folder / "philippine_job_ads_psf_aai_report.md", research_report)
            storage.atomic_bytes(folder / "research_summary.html", summary)
            storage.atomic_bytes(folder / "analysis_metadata.json", json.dumps(meta, indent=2, default=str).encode())
            for name, frame in tables.items():
                storage.atomic_bytes(folder / f"{name}.csv", export_csv(frame))
            st.success(f"Report saved to {folder}")


def feedback():
    page_intro("Feedback", "Record corrections and usability feedback while preserving the original predictions.")
    reviewer = st.text_input("Reviewer ID", key="feedback_reviewer")
    source = st.selectbox("Correction target", ["extraction", "alignment"])
    if current_analysis():
        tables, _ = load_data_with_skeleton(filtered_bundle, height=240)
        frame = tables["all_candidates"] if source == "extraction" else tables["alignment_results"]
        key = "extraction_id" if source == "extraction" else "alignment_id"
        if not frame.empty:
            display(frame)
            row_id = st.selectbox("Record ID", frame[key].tolist())
            row = frame.loc[frame[key].eq(row_id)].iloc[0]
            if source == "extraction":
                st.caption("Review one or several competency links for this occurrence on PSF Mapping.")
            fields = ["normalized_phrase", "competency_category", "accepted"] if source == "extraction" else ["status"]
            field = st.selectbox("Field to correct", fields)
            st.write("Original/current value:", str(row[field]))
            if field == "status":
                corrected = st.selectbox("Corrected value", STATUSES)
            elif field == "accepted":
                corrected = st.selectbox("Corrected value", ["True", "False"])
            else:
                corrected = st.text_input("Corrected value", str(row[field]))
            comment = st.text_area("Reason / comment")
            if action_button("Save correction", key=f"save_correction_{source}_{row_id}"):
                if not corrected.strip():
                    raise ValueError("Enter a corrected value.")
                save_correction(source, row_id, field, row[field], corrected, reviewer, comment)
                st.success("Correction saved separately from original predictions. Dependent comparisons use the corrected value.")
            if source == "extraction" and action_button(
                "Add this reviewed phrase to training data",
                key=f"add_reviewed_phrase_{source}_{row_id}",
            ):
                save_annotations(pd.DataFrame([{"phrase": row.normalized_phrase, "label": row.competency_category, "psf_competency": row.psf_competency, "source_type": "jobs", "source_id": row.source_id}]), reviewer)
                st.success("Added to annotations. Retraining requires an explicit action on ML Training.")
    correction_rows = load_data_with_skeleton(corrections, height=140)
    display(correction_rows)
    st.subheader("Usability evaluation")
    cfg = storage.settings()
    with st.form("usability"):
        respondent_type = st.selectbox("Respondent type", ["industry professionals", "employers", "researchers", "job seekers"])
        responses = {name: st.slider(name.replace("_", " ").title(), cfg["likert_min"], cfg["likert_max"], cfg["likert_min"]) for name in ("ease_of_use", "clarity", "navigation", "usefulness", "visualization_quality", "overall_satisfaction")}
        comment = st.text_area("Evaluation comment")
        if action_form_submit_button("Save usability evaluation"):
            if not reviewer.strip():
                raise ValueError("Enter a reviewer ID above the form.")
            record = responses | {"reviewer": reviewer, "respondent_type": respondent_type, "comment": comment, "timestamp": timestamp(), "scale_min": cfg["likert_min"], "scale_max": cfg["likert_max"]}
            data = pd.concat([storage.read_frame("usability"), pd.DataFrame([record])], ignore_index=True)
            storage.save_frame("usability", data)
            st.success("Evaluation recorded.")
    usability = load_data_with_skeleton(lambda: storage.read_frame("usability"), height=120)
    if not usability.empty:
        display(usability)
        st.download_button("Download usability evaluations", export_csv(usability), "usability.csv")
    stakeholder = load_data_with_skeleton(lambda: storage.read_frame("cleaned_stakeholder"), height=120)
    if not stakeholder.empty:
        st.subheader("Stakeholder evaluations")
        display(stakeholder)
        for field in ("importance_rating", "usability_rating"):
            numeric = pd.to_numeric(stakeholder[field], errors="coerce")
            st.write(f"{field}: {numeric.count()} numeric responses; mean {numeric.mean():.2f}" if numeric.count() else f"{field}: no numeric responses")

def methodology():
    page_intro("Methodology", "Definitions, analytical decisions, and limits of the study.")
    st.markdown((Path(__file__).resolve().parents[1] / "METHODOLOGY.md").read_text(encoding="utf-8"))

def research_readiness():
    page_intro("Research readiness", "A practical audit of the current data and model workflow. Passing app checks does not by itself make results ready for a thesis or publication.")
    try:
        path = resolve_training_file(storage.ROOT)
        def load_readiness_labels():
            current_labels = (storage.read_frame("labeled_competencies") if supabase_store.configured()
                              else load_labeled_data(path))
            current_usable, current_validation = cached_label_validation(
                current_labels, require_provenance=True
            )
            return current_labels, current_usable, current_validation
        labels, usable, validation = load_data_with_skeleton(load_readiness_labels, height=220)
    except (ValueError, OSError) as exc:
        path, labels, usable, validation = None, pd.DataFrame(), pd.DataFrame(), {"errors": [str(exc)], "warnings": []}
    metadata = read_model_metadata()
    audit = assess_research_readiness(labels, metadata, validation)
    history_path = storage.ROOT / "data/feedback/annotation_history.csv"
    history = (pd.DataFrame(supabase_store.read_annotation_history(supabase_store.get_token())) if supabase_store.configured()
               else pd.read_csv(history_path, dtype=str, keep_default_na=False) if history_path.is_file() else pd.DataFrame())
    disagreements = historical_category_disagreements(history)
    profile = research_data_profile(labels)
    st.warning("Not yet ready for defensible research findings" if audit["findings"] else "No software risks detected; researcher sign-off is still required")
    st.caption("This page separates mechanical checks from decisions that require the research team. It never certifies labels, sampling, or model validity automatically.")
    a, b, c, d = st.columns(4)
    a.metric("Saved labels", f"{len(labels):,}")
    b.metric("Usable distinct phrases", f"{validation.get('rows_used', 0):,}")
    source_count = labels.source_id.fillna("").astype(str).str.strip().nunique() if "source_id" in labels else 0
    c.metric("Distinct job-ad source IDs", f"{source_count:,}")
    d.metric("Reviewer ID spellings", f"{len(audit['reviewer_ids']):,}")
    st.subheader("Active job-ad sample")
    jobs = load_data_with_skeleton(lambda: storage.read_frame("cleaned_jobs"), height=160)
    if jobs.empty:
        st.warning("No cleaned job-ad sample is active. Upload, review, and save the study sample before extracting or reporting findings.")
    else:
        job_sources = jobs.get("source_id", pd.Series(dtype=str)).fillna("").astype(str).str.strip()
        job_titles = jobs.get("job_title", pd.Series(dtype=str)).fillna("").astype(str).str.strip()
        posting_dates = pd.to_datetime(jobs.get("posting_date", pd.Series(dtype=str)), errors="coerce").dropna()
        scope_reviewed = bool(storage.read_json("cleaning_jobs", {}).get("philippine_aai_scope_reviewed", False))
        job_a, job_b, job_c, job_d = st.columns(4)
        job_a.metric("Cleaned job ads", f"{len(jobs):,}")
        job_b.metric("Distinct ad IDs", f"{job_sources[job_sources.ne('')].nunique():,}")
        job_c.metric("Job titles", f"{job_titles[job_titles.ne('')].nunique():,}")
        job_d.metric("Scope review recorded", "Yes" if scope_reviewed else "No")
        if not posting_dates.empty:
            st.caption(f"Posting dates in the active file: {posting_dates.min().date()} to {posting_dates.max().date()}. A saved scope check records a researcher action; it does not independently verify every ad.")
        else:
            st.caption("Posting dates are missing or could not be parsed. Record the sample collection window in the study notes.")
        label_sources = set(labels.get("source_id", pd.Series(dtype=str)).fillna("").astype(str).str.strip())
        active_sources = set(job_sources[job_sources.ne("")])
        shared_sources = label_sources & active_sources
        if not shared_sources:
            st.warning("The labeled phrases come from different source IDs than the active 16-ad analysis sample. Treat classifier predictions on this sample as exploratory and review them against each ad.")
        else:
            st.caption(f"{len(shared_sources)} source ID(s) occur in both the labeled phrase data and the active analysis sample.")
        extraction_meta = storage.read_json("extraction_metadata", {})
        if not extraction_meta or extraction_meta.get("signature") != input_signature():
            st.warning("The saved extraction is out of date. Run Competency Extraction again after finalizing the job sample, reviewed PSF-AAI reference, and selected model before using reports.")
        elif not extraction_meta.get("model_available"):
            st.info("The current extraction was created without the selected classifier. Rerun extraction if you intend to use classifier categories.")
        else:
            st.success("The saved extraction matches the current jobs, taxonomy, labels, settings, and model.")
    st.subheader("Where the labels came from")
    st.caption("Counts below describe saved annotation rows and distinct phrases within each posting. Several phrase rows from one posting still represent one job ad, not independent observations.")
    display(profile["sources"])
    st.subheader("Reviewer IDs recorded")
    st.caption("Spellings are shown exactly as saved. The app does not merge or correct reviewer identities; confirm whether variants belong to the same person before reporting reviewer counts.")
    display(profile["reviewers"])
    class_distribution = validation.get("class_distribution", {})
    if class_distribution:
        classes = pd.DataFrame([{"category": name, "distinct usable phrases": count}
                                for name, count in class_distribution.items()])
        classes["share of usable phrases"] = classes["distinct usable phrases"] / max(1, int(validation.get("rows_used", 0)))
        classes["share of usable phrases"] = classes["share of usable phrases"].map(lambda value: f"{value:.1%}")
        st.subheader("Categories included in model training")
        st.caption("IRRELEVANT rows and duplicate phrases are excluded from this count. A model score cannot make up for narrow source coverage or inconsistent labels.")
        display(classes.sort_values("distinct usable phrases", ascending=False, ignore_index=True))
    st.subheader("What needs attention")
    for item in audit["findings"]:
        st.warning(f"**{item['title']}**\n\n{item['detail']}")
    if not disagreements.empty:
        st.subheader("Earlier category disagreements to review")
        st.caption("These are historical saved decisions, not current rows in the training table. The table is read-only; use the source evidence and your labeling protocol to decide whether any follow-up is needed.")
        display(disagreements)
    with st.expander("Dataset and model checks", expanded=False):
        if validation:
            st.json(validation)
        if metadata:
            st.json({key: metadata.get(key) for key in ("training_timestamp", "training_file", "rows_available", "rows_used", "number_of_classes", "selected_model", "split")})
        else:
            st.info("No saved classifier metadata is available.")
    st.subheader("Recommended next actions")
    st.markdown("1. Confirm every ad meets the written Philippine AI/analytics inclusion rules; remove out-of-scope ads with a saved audit trail.\n2. Label phrases from more distinct job ads; the app's 20-source warning threshold is only a workflow flag, not a statistically justified sample-size target. More phrases from the same ads do not replace independent sources.\n3. Reconcile reviewer IDs with the actual reviewers, agree on category definitions, double-code a planned subset, and document disagreement resolution.\n4. Rerun extraction after the final sample, framework, and model are selected; manually verify phrases and PSF-AAI mappings against source evidence.\n5. Train only for an explicit classifier purpose and only when whole-ad holdout evaluation is possible. Keep its metrics exploratory until evaluated on untouched job-ad sources.\n6. Report job-ad counts and percentages using the number of eligible, reviewed ads as the denominator; archive source URLs, collection dates, inclusion rules, and the dataset hash.")
    if path:
        st.caption(f"Audited training file: `{project_relative_path(path)}`")

def settings_page():
    page_intro("Settings", "Configure the research workspace and documented analysis parameters.")
    st.subheader("Shared team workspace")
    if supabase_store.configured():
        st.success("Supabase is connected. Saved tables and settings are shared with signed-in teammates; local CSVs remain as backups.")
        local_jobs_path = Path(ROOT) / "data/processed/cleaned_jobs.csv"
        if local_jobs_path.is_file() and storage.read_frame("cleaned_jobs").empty:
            st.warning("This computer has a cleaned job dataset, but the shared workspace does not yet. An admin can copy it below; teammates will then see it after refreshing.")
        st.caption("To copy this computer's existing processed tables into empty shared slots, use the one-time import below. Existing shared rows are preserved.")
        if action_button("Copy local workspace to shared database", type="secondary"):
            with st.spinner("Copying local processed tables and annotations to Supabase…"):
                seeded, skipped = storage.seed_shared_workspace()
            st.success(f"Copied {len(seeded)} tables: {', '.join(seeded) if seeded else 'none needed'}.")
            if skipped:
                st.info(f"Kept {len(skipped)} existing shared tables unchanged: {', '.join(skipped)}.")
    else:
        st.info("Supabase is not configured. This app is using local files on this computer.")
        st.caption("For a shared site, configure SUPABASE_URL and SUPABASE_PUBLISHABLE_KEY in Streamlit secrets, then run the schema in supabase_schema.sql.")
    st.subheader("Generated extraction results")
    st.caption("Clear a full extraction to free active storage. A compressed local archive is created first; uploaded data, labels, mapping reviews, and candidate phrases are kept.")
    if supabase_store.is_admin():
        if action_button("Prepare extraction cleanup", type="secondary", icon=":material/delete_sweep:", action_id="prepare_extraction_cleanup"):
            st.session_state["confirm_clear_extraction_data"] = True
        if st.session_state.get("confirm_clear_extraction_data"):
            st.warning("This clears active extracted phrases and NLP diagnostics for the whole team. The generated extraction can be rebuilt later from the saved uploads.")
            if action_button("Confirm archive and clear", type="primary", icon=":material/delete_forever:", action_id="confirm_extraction_cleanup"):
                try:
                    archive = storage.clear_extraction_data()
                    st.session_state.pop("confirm_clear_extraction_data", None)
                    backup = archive.relative_to(ROOT) if archive else "no local extraction files were present"
                    st.success(f"Extraction results cleared. Compressed backup: {backup}.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Cleanup stopped safely: {exc}")
            if action_button("Cancel cleanup", type="secondary", action_id="cancel_extraction_cleanup"):
                st.session_state.pop("confirm_clear_extraction_data", None)
                st.rerun()
    else:
        st.info("Sign in with a workspace admin account to clear shared extraction results.")
    cfg = storage.settings()
    with st.form("settings_form"):
        st.subheader("Matching thresholds")
        aligned = st.slider("Aligned threshold", .01, 1., float(cfg["aligned_threshold"]), .01)
        partial = st.slider("Partially aligned threshold", .0, .99, float(cfg["partial_threshold"]), .01)
        fuzzy = st.slider("Taxonomy fuzzy match threshold", .5, 1., float(cfg["fuzzy_threshold"]), .01)
        semantic = st.slider("Taxonomy semantic match threshold", .5, 1., float(cfg["semantic_threshold"]), .01)
        path = st.text_input("Optional local sentence-transformers model directory", cfg["semantic_model"])
        st.subheader("Extraction and screening")
        stopwords = st.text_area("Additional stopwords (one per line; phrases retain internal stopwords)", "\n".join(cfg["stopwords"]))
        batch = st.number_input("NLP batch size", 1, 1024, cfg["batch_size"])
        limit = st.number_input("Maximum discovered n-grams per record", 50, 10000, cfg["max_candidates"])
        emerging = st.number_input("Minimum job ads for an emerging-skill candidate", 1, 100000, cfg["emerging_min_jobs"])
        st.subheader("Usability evaluation")
        low = st.number_input("Likert scale minimum", 0, 9, cfg["likert_min"])
        high = st.number_input("Likert scale maximum", 1, 10, cfg["likert_max"])
        if action_form_submit_button("Save settings", type="primary"):
            if partial >= aligned or low >= high:
                raise ValueError("Partial threshold must be below aligned, and Likert minimum below maximum.")
            if path.strip():
                from .psf_mapping import semantic_model
                semantic_model(path.strip())
            storage.save_json("settings", {"aligned_threshold": aligned, "partial_threshold": partial, "fuzzy_threshold": fuzzy, "semantic_threshold": semantic, "semantic_model": path.strip(), "stopwords": [s.strip().casefold() for s in stopwords.splitlines() if s.strip()], "batch_size": batch, "max_candidates": limit, "emerging_min_jobs": emerging, "likert_min": low, "likert_max": high})
            st.success("Settings saved. Re-run extraction to refresh the analysis snapshot.")
    st.caption("Extraction semantic mode uses only a model already present in the local directory above. Manual Labeling AI drafts use the pinned model described on that page and download it on first use. The app does not call a generative AI API.")

PAGES = {"Home": home, "Job Data Upload": upload, "Data Quality": quality,
         "Job Market Analysis": lambda: research_page("Job Market Analysis"),
         "Competency Extraction": extraction,
         "Manual Labeling": labeling, "ML Training": training, "Model Evaluation": evaluation,
         "PSF Mapping": lambda: research_page("PSF Mapping"),
         "Employer–PSF Alignment": lambda: research_page("Employer–PSF Alignment"),
         "Unmapped / Emerging Skills": lambda: research_page("Unmapped / Emerging Skills"),
         "Reports": lambda: research_page("Reports"), "Feedback": feedback,
         "Methodology": methodology, "Research Readiness": research_readiness, "Settings": settings_page}


def render(page):
    storage.initialize()
    st.session_state["_table_number"] = 0
    st.session_state["_fow_current_page"] = page
    apply_design()
    st.sidebar.caption(f"Research workspace · v{VERSION}")
    from .auth_ui import render_account_menu
    with st.container(horizontal=True, vertical_alignment="center", key="workspace_toolbar"):
        with st.container(width="stretch"):
            st.caption("FUTURE OF WORK  /  " + ("OVERVIEW" if page == "Home" else page.upper()))
        render_account_menu()
    _processing_status()
    try:
        if supabase_store.configured() and page in {"Job Data Upload", "Data Quality", "Competency Extraction", "Settings", "Feedback", "PSF Framework"} and not supabase_store.is_admin():
            st.info("This step is managed by the project administrator. Open Review and label phrases to contribute your annotations.")
            return
        PAGES[page]()
    except (ValueError, OSError, KeyError, TypeError, supabase_store.SupabaseError) as exc:
        st.error(str(exc))
        st.caption("Review the input or configuration and try again. Raw uploads have not been changed.")
    finally:
        finish_action_run()
