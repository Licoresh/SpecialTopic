from .category_schema import category_path, category_parent
from io import BytesIO
from pathlib import Path
from copy import deepcopy
from html import escape
from textwrap import wrap
import json
import os
import re
import time
import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from openpyxl import load_workbook
from . import storage
from .config import ROOT, FIELDS, LABELS, VERSION
from .loaders import load_data, map_columns
from .column_mapping import suggest_column_mapping
from .cleaning import clean_dataset, duplicate_ids, normalize_text, analysis_job_values, analysis_jobs
from .preprocessing import get_nlp
from .validation import validate_taxonomy
from .classification import VECTORIZER_CONFIG, predict_competency_category, SELECTION_BASIS
from .training_data import load_labeled_data, validate_labeled_data
from .model_training import read_model_metadata, training_data_changed
from .training_sources import (resolve_training_file, inspect_training_folder, training_candidates,
                               training_taxonomy, select_training_file)
from .labeling import annotation_conflicts, save_annotations, save_correction, corrections
from .workflow import run_extraction, analysis_bundle, input_signature, current_extractions, extraction_freshness
from .analytics import skill_chart_tables, psf_demand_tables, chart_skill_key, unmapped_chart_counts, chart_mapping_rows
from .job_profile import job_profile_tables
from .geography import location_tables
from .alignment import STATUSES, ALIGNMENT_COLUMNS
from .skill_extraction import EXTRACTION_COLUMNS
from .psf_reviews import REVIEW_TABLE, save_mapping_review, prepare_mapping_review, occurrence_hash
from .visualization import bar, distribution, heatmap, count_axis, ranked_bar
from .reporting import export_csv, export_excel, export_html, export_research_report
from .utils import timestamp, frame_hash, digest
from .readiness import (assess_research_readiness, source_overlap,
                        historical_category_disagreements, research_data_profile)
from . import supabase_store
from .action_guard import action_button, action_form_submit_button, finish_action_run
from .review_queue import (labels_by_phrase, expand_phrase_annotations, group_candidates_by_phrase,
                           manual_mapping_occurrences, preserve_occurrence_references)
from .loading_ui import load_data_with_skeleton, loading_content, _wireframe

from .design import review_workspace_style, workspace_breadcrumb, content_section, content_metrics, content_note, section_heading
from . import background_tasks

MANUAL_REVIEW_COLUMNS = ["Phrase", "Category", "PSF-AAI competencies", "AI category draft", "AI PSF-AAI drafts", "Source ads", "Source advertisement"]



SETTINGS_SECTIONS = (
    ("Matching thresholds", "tune", (
        ("aligned_threshold", "Aligned threshold", "slider", .01, 1., .01),
        ("partial_threshold", "Partially aligned threshold", "slider", .0, .99, .01),
        ("fuzzy_threshold", "Taxonomy fuzzy match threshold", "slider", .5, 1., .01),
        ("semantic_threshold", "Taxonomy semantic match threshold", "slider", .5, 1., .01),
        ("semantic_model", "Optional local sentence-transformers model directory", "text", None, None, None),
    )),
    ("Extraction and screening", "content_paste_search", (
        ("stopwords", "Additional stopwords (one per line; phrases retain internal stopwords)", "textarea", None, None, None),
        ("batch_size", "NLP batch size", "number", 1, 1024, 1),
        ("max_candidates", "Maximum discovered n-grams per record", "number", 50, 10000, 1),
        ("emerging_min_jobs", "Minimum job ads for an emerging-skill candidate", "number", 1, 100000, 1),
    )),
    ("Usability evaluation", "rate_review", (
        ("likert_min", "Likert scale minimum", "number", 0, 9, 1),
        ("likert_max", "Likert scale maximum", "number", 1, 10, 1),
    )),
)
USABILITY_ITEMS = ("ease_of_use", "clarity", "navigation", "usefulness", "visualization_quality", "overall_satisfaction")

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
        with st.container(key="processing_activity"):
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
    cleaned, report = clean_dataset(frame, kind, duplicate_list)
    return (analysis_jobs(cleaned) if kind == "jobs" else cleaned), report

@st.cache_resource(show_spinner=False)
def cached_nlp():
    return get_nlp()

def display(frame, *, key=None):
    if frame.empty:
        st.caption("No records to display for the current selection.")
    if len(frame) > 100:
        if key is None:
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
    row_height = 30 if st.session_state.get("_fow_current_page") == "PSF Mapping" else 38
    st.dataframe(frame, width="stretch", hide_index=True, row_height=row_height,
                 column_config=text_columns, height=min(480, max(100, 40 + row_height * len(frame))),
                 alt=f"Research data table with {len(frame):,} rows. Use the table toolbar to search or download.")


@st.fragment
def evidence_tables(title, tables, *, key, order=None, label=None, value=None, note=None, icon=None):
    """Open and page evidence without rebuilding surrounding charts or reading sources."""
    panel = st.expander(title, key=key, icon=icon, on_change="rerun")
    if panel.open:
        with panel:
            if note:
                st.caption(note)
            for index, (caption, frame) in enumerate(tables.items()):
                if caption:
                    st.caption(caption)
                frame = frame() if callable(frame) else frame
                display(ordered_result_table(frame, label, order, value) if order else frame,
                        key=f"{key}_page_{index}")


def _paginate_frame(frame, page, page_size=100):
    total_pages = max(1, (len(frame) + page_size - 1) // page_size)
    page = min(max(int(page), 1), total_pages)
    start = (page - 1) * page_size
    return frame.iloc[start:start + page_size], page, total_pages

def chart(fig):
    from .visualization import style_chart
    fig = style_chart(fig)
    heading = fig.layout.title.text
    title = heading or "Research analysis chart"
    if st.session_state.get("_fow_current_page") in {"Job Market Analysis", "PSF Mapping", "Employer–PSF Alignment", "Unmapped / Emerging Skills"}:
        icon = "grid_view" if any(trace.type == "heatmap" for trace in fig.data) else "bar_chart"
        if heading:
            st.subheader(title, icon=f":material/{icon}:")
        fig.update_layout(font=dict(size=12, color="#171923"), title=dict(font=dict(size=15), x=.015),
                          paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", title_text="")
        if fig.data and all(trace.type == "bar" and trace.orientation == "h" for trace in fig.data):
            labels = list(dict.fromkeys(str(label) for trace in fig.data for label in trace.y))
            ticktext = ["<br>".join(escape(line) for line in wrap(label, 24)) for label in labels]
            fig.update_yaxes(tickmode="array", tickvals=labels, ticktext=ticktext)
            row_space = sum(max(28, 14 * (label.count("<br>") + 1) + 8) for label in ticktext)
            fig.update_layout(height=max(250, 55 + row_space), margin=dict(l=10, r=35, t=8, b=40))
        elif any(trace.type == "heatmap" for trace in fig.data):
            rows = max(len(trace.y) for trace in fig.data if trace.type == "heatmap")
            ticktext = fig.layout.yaxis.ticktext or ()
            line_count = max((str(label).count("<br>") + 1 for label in ticktext), default=1)
            fig.update_layout(height=max(300, 135 + max(28, 14 * line_count + 8) * rows), margin=dict(l=25, r=75, t=12, b=105))
    if any(trace.type == "heatmap" for trace in fig.data):
        columns = max(len(trace.x) for trace in fig.data if trace.type == "heatmap")
        minimum = max(640, 280 + 72 * columns)
        key = f"matrix_viewport_{digest([title])}"
        with st.container(key=key):
            st.html(f'<style>.st-key-{key}' + '{--fow-matrix-width:' + str(minimum) + 'px}</style>'
                    '<p class="fow-matrix-scroll-hint">Scroll horizontally to read all chart columns.</p>')
            st.plotly_chart(fig, width="stretch", theme=None, key=f"{key}_plot_{VERSION}",
                            config={"displaylogo": False, "scrollZoom": False}, alt=title)
    else:
        st.plotly_chart(fig, width="stretch", config={"displaylogo": False, "scrollZoom": False}, alt=title)

def page_intro(title, description):
    key = {"Job Market Analysis": "job_market_heading", "PSF Mapping": "psf_mapping_heading",
           "Employer–PSF Alignment": "employer_psf_heading"}.get(title, "page_heading")
    with st.container(key=key, gap="xsmall"):
        st.caption("PHILIPPINE JOBS · SKILLS · PSF-AAI")
        st.title(title)
        st.write(description)
    _processing_status()

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
    signature, current = _session_cached_value(
        "_fow_signature_cache", (meta.get("signature"), meta.get("pipeline_version")),
        lambda: extraction_freshness(meta), ttl=15, max_entries=1)
    st.session_state["_current_analysis_signature"] = signature
    if not current:
        st.warning("Inputs, labels, settings or the selected model changed. Run Competency Extraction again before interpreting or exporting results.")
        return False
    return True

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
    bundle_key = digest({"presentation_version": VERSION, "signature": analysis_revision})
    result = _session_cached_value(
        "_fow_analysis_cache", bundle_key,
        lambda: analysis_bundle(source_snapshot=source_snapshot),
        ttl=None, max_entries=2,
    )
    st.session_state["_fow_loaded_bundle_revision"] = bundle_key
    return result


def home():
    with st.container(key="overview_heading", gap="xsmall"):
        st.caption("PHILIPPINES · AI & ANALYTICS")
        st.title("From job evidence to skills insight.")
        st.write("Your research workspace for employer demand and PSF-AAI alignment.")
    _processing_status()
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
    with loading_content("overview_summary_content", "overview", cards=4) as content:
        jobs, taxonomy, mapped_jobs, has_extractions, label_count, model, meta = load_overview_data()
        with content():
            with st.container(horizontal=True, key="overview_metrics", gap="medium"):
                for index, (label, value, icon, help_text) in enumerate([
                    ("Clean job ads", f"{len(jobs):,}", "work", "Advertisements saved after data cleaning."),
                    ("Reviewed labels", f"{label_count:,}", "task_alt", "Saved annotation rows; a phrase can occur in several ads."),
                    ("PSF-AAI competencies", f"{len(taxonomy):,}", "account_tree", "Competencies in the active reviewed reference."),
                    ("Phrase extraction", "Saved" if has_extractions else "Not started", "manage_search", "Analysis pages check that saved extraction inputs are still current."),
                ], 1):
                    key = f"overview_metric_{index}"
                    if index == 4:
                        key += "_ready" if has_extractions else "_pending"
                    with st.container(width=240, key=key):
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
                            icon = ("cloud_upload", "database", "manage_search", "sell", "bar_chart", "query_stats")[index]
                            st.html('<div class="fow-workflow-card">'
                                    f'<span class="material-symbols-rounded" aria-hidden="true">{icon}</span><div>'
                                    f'<small>{number} / {escape(stage_states[index])}</small><h4>{escape(title)}</h4>'
                                    f'<p>{escape(description)}</p></div></div>')
                            page_button(path, link, key=f"home_workflow_{number}")
            with loading_content("overview_readiness_note", "notice") as content:
                try:
                    readiness_labels = (storage.read_frame("labeled_competencies") if supabase_store.configured()
                                        else load_labeled_data(resolve_training_file(storage.ROOT)))
                    _, readiness_validation = cached_label_validation(readiness_labels, require_provenance=True)
                    readiness_audit = assess_research_readiness(readiness_labels, model, readiness_validation)
                except (ValueError, OSError) as exc:
                    readiness_labels, readiness_audit = pd.DataFrame(), {"findings": [{"title": "Training data unavailable", "detail": str(exc)}]}
                with content():
                    if readiness_audit["findings"]:
                        with st.container(border=True, key="readiness_summary"):
                            with st.container(horizontal=True, vertical_alignment="center", gap="large", wrap=True):
                                copy_slot = st.container(width="stretch")
                                action_slot = st.container(width=260)
                            with copy_slot:
                                st.subheader("Before you report findings")
                                blocking = [finding for finding in readiness_audit["findings"] if finding.get("status", "blocking") == "blocking"]
                                st.write("Research readiness needs attention. Review the outstanding checks before interpreting results.")
                                if blocking:
                                    st.write(" · ".join(finding["title"] for finding in blocking[:3]))
                            with action_slot:
                                page_button("pages/18_Research_Readiness.py", "Review readiness", key="home_readiness")
                    if model:
                        st.caption(f"Saved classifier: {model['model_name']}. It is available for exploratory workflow checks; see Research Readiness before interpreting model outputs.")
                    else:
                        st.caption("No classifier has been trained. AI-generated phrase suggestions are drafts; they do not count as reviewed labels or model results.")


def upload(kind=None):
    if kind is None:
        upload_types = ["jobs", "psf_aai"]
        selected_kind = st.session_state.get("upload_dataset_choice", "jobs")
        if selected_kind not in upload_types:
            selected_kind = "jobs"
        title = "Upload job data" if selected_kind == "jobs" else "Upload PSF-AAI reference"
        page_intro(title, "Upload the selected study dataset. The original file is archived unchanged; review its column matches before saving.")
        kind = st.selectbox(
            "Dataset to upload",
            upload_types,
            index=upload_types.index(selected_kind),
            key="upload_dataset_choice",
            format_func=lambda value: {
                "jobs": "Job advertisements (500-study dataset)",
                "psf_aai": "TESDA PSF-AAI reference",
            }[value],
        )
    else:
        title = "Upload job data" if kind == "jobs" else "Upload PSF-AAI reference"
        page_intro(title, "Upload the selected study dataset. The original file is archived unchanged; review its column matches before saving.")
    with st.container(border=True, key="upload_file_panel"):
        st.subheader("Select a source file", icon=":material/upload_file:")
        st.caption("Preview the source, archive the original, then confirm its column matches.")
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
        with loading_content("upload_preview", "file_preview", rows=5) as preview_content:
            frame = load_data_with_skeleton(
                lambda: cached_load(content, uploaded.name, sheet, encoding), height=220
            )
            with preview_content():
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
    with loading_content("upload_sources", "table", columns=["dataset", "filename", "timestamp"]) as content:
        manifest = storage.read_json("uploads", {})
        with content():
            if manifest:
                manifest_view = pd.DataFrame.from_dict(manifest, orient="index").reset_index(names="dataset")
                visible = [column for column in ("dataset", "filename", "timestamp") if column in manifest_view]
                st.caption("Saved source files")
                display(manifest_view[visible])
    with st.expander("Map uploaded columns", expanded=True):
        column_mapping(kind)

def column_mapping(kind="jobs"):
    st.subheader("Column Mapping")
    with loading_content(f"column_mapping_{kind}", "form", controls=["select"] * len(FIELDS[kind]) + ["button"], field_columns=2) as content:
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
        with content():
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
    with st.container(key="quality_dataset_selector"):
        kind = st.selectbox("Dataset", list(FIELDS), format_func=lambda value: {"jobs": "Job advertisements", "psf_aai": "PSF-AAI reference", "stakeholder": "Stakeholder responses"}.get(value, value))
    with loading_content(f"quality_source_{kind}", "pending") as content:
        frame = load_data_with_skeleton(lambda: storage.read_frame("mapped_"+kind), height=180)
        prior = storage.read_json("cleaning_jobs", {}).get("screening_exclusions", {}) if kind == "jobs" and not frame.empty else {}
        with content():
            if frame.empty:
                st.info("Map this dataset first.")
                return
            mapped_source_hash = frame_hash(frame)
            screening = pd.DataFrame(columns=["source_id", "exclude", "exclusion_reason"])
            if kind == "jobs":
                screening = frame.reindex(columns=["source_id", "job_title", "company", "location", "url"]).copy()
                screening["exclude"] = screening.source_id.isin(prior)
                screening["exclusion_reason"] = screening.source_id.map(prior).fillna("")
                screen = st.expander("Screen advertisements and document exclusions", key="quality_screening", on_change="rerun")
                if screen.open:
                    with screen:
                        st.caption("Exclude ads outside the Philippine AI/analytics scope or without sufficient evidence. Each exclusion needs a reason. The original upload stays archived.")
                        screening = st.data_editor(screening, disabled=["source_id", "job_title", "company", "location", "url"],
                                                   hide_index=True, key="quality_screening_editor", width="stretch")
                excluded = screening[screening.exclude]
                frame = frame[~frame.source_id.isin(excluded.source_id)]
                if not excluded.empty:
                    st.caption(f"{len(excluded):,} ads excluded from this cleaned copy; {len(frame):,} remain.")
            potential = duplicate_ids(frame)
            with st.container(key="quality_duplicate_selector"):
                selected = st.multiselect("Confirm duplicate record IDs to remove from the cleaned copy", potential)
            with loading_content(f"quality_preview_{kind}", "quality", columns=["source_id", *FIELDS[kind]] if kind == "jobs" else list(frame.columns), rows=min(8, len(frame))) as content:
                cleaned, report = load_data_with_skeleton(
                    lambda: cached_clean(frame, kind, tuple(selected)), height=220
                )
                st.caption("Missing text remains empty; it is never invented. Raw columns are retained alongside *_clean columns. Source IDs identify the raw dataset hash and row.")
                with content():
                    report_view = report.rename(columns={"check": "Quality check", "count": "Count"}).copy()
                    report_view["Quality check"] = report_view["Quality check"].astype(str).map(
                        lambda value: "Total records" if value == "records" else value.replace("_", " ").capitalize()
                    )
                    checks = dict(zip(report.check, pd.to_numeric(report["count"], errors="coerce").fillna(0)))
                    core = [field for field in ("job_id", "job_title", "company", "location", "job_description") if field in cleaned]
                    missing = sum(int(checks.get(f"missing: {field}", 0)) for field in core)
                    notes = [f"Potential duplicate rows in this preview: {int(checks.get('potential_duplicate_rows', 0)):,}."]
                    if core:
                        notes.append(f"Blank values across {len(core)} core fields: {missing:,}. Blank cells are counted separately, not as distinct records.")
                    if kind == "jobs" and {"required_skills", "preferred_skills"}.issubset(cleaned):
                        blank = cleaned[["required_skills", "preferred_skills"]].fillna("").astype(str).apply(lambda col: col.str.strip().eq("")).all(axis=1).sum()
                        notes.append(f"Both dedicated skill fields are blank in {int(blank):,} of {len(cleaned):,} {'ad' if len(cleaned) == 1 else 'ads'}. Skills may still be present in the advertisement text.")
                    content_note("Data quality insights", f"This preview contains {len(cleaned):,} {'record' if len(cleaned) == 1 else 'records'} after the selected exclusions and duplicate removals.", items=notes, icon="fact_check")
                    details = st.expander("Detailed quality checks", icon=":material/fact_check:", key="quality_report_details", on_change="rerun")
                    if details.open:
                        with details:
                            display(report_view)
                    if kind == "jobs":
                        coverage = st.expander("Job-title, location and requirement summaries", key="quality_job_summaries", on_change="rerun")
                        if coverage.open:
                            with coverage:
                                preview = job_profile_tables(cleaned)
                                display(preview["requirement_field_coverage"])
                                st.caption("Result summaries combine case, Unicode and spacing variants. Original fields remain unchanged. Missing requirements stay missing; ambiguous experience wording is retained for review.")
                                display(preview["experience_year_evidence"].drop(columns=["url"], errors="ignore"))
                    if potential:
                        duplicates = st.expander("Potential duplicate evidence", key="quality_duplicate_evidence", on_change="rerun")
                        if duplicates.open:
                            with duplicates:
                                display(frame[frame.source_id.isin(potential)])
                    if kind == "jobs":
                        st.caption("Lowercase cleaned job values (source IDs, dates and case-sensitive links keep their original identity).")
                        with content_section("Cleaned data preview", "table_view", "quality_preview"):
                            display(analysis_job_values(cleaned).head(100))
                        original = st.expander("Original source evidence", key="quality_original_evidence", on_change="rerun")
                        if original.open:
                            with original:
                                display(frame.head(100))
                    else:
                        with content_section("Cleaned data preview", "table_view", "quality_preview"):
                            display(cleaned.head(100))
                    scope_reviewed = st.checkbox("I reviewed source evidence and confirm these advertisements have Philippine provenance and relate to AI or analytics") if kind == "jobs" else True
                    reviewer = st.text_input("Framework reviewer ID") if kind == "psf_aai" else ""
                    confirmed = st.checkbox("I checked this framework table against its cited source pages") if kind == "psf_aai" else True
                    if action_button("Save cleaned dataset", type="primary", icon=":material/save:"):
                        if kind == "jobs" and (screening.loc[screening.exclude, "exclusion_reason"].str.strip().eq("").any() or frame.empty):
                            raise ValueError("Provide a reason for every exclusion and retain at least one advertisement.")
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
                        screening_exclusions = screening.loc[screening.exclude].set_index("source_id").exclusion_reason.to_dict() if kind == "jobs" else {}
                        storage.save_json("cleaning_"+kind, {"timestamp": timestamp(), "removed_duplicate_ids": selected, "source_hash": mapped_source_hash, "philippine_aai_scope_reviewed": scope_reviewed if kind == "jobs" else False, "screening_exclusions": screening_exclusions})
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
    with loading_content("extraction_reference_status", "notice") as content:
        taxonomy = load_data_with_skeleton(lambda: storage.read_frame("cleaned_psf_aai"), height=120)
        with content():
            if taxonomy.empty:
                st.warning("No PSF-AAI taxonomy is available. Discovery can run, but it cannot claim PSF matches.")
            elif taxonomy.attrs.get("reference_source") == "bundled_default":
                st.caption("Bundled TESDA PSF-AAI reference loaded by default. A reviewed shared reference takes priority when available.")
            if not (ROOT / "models/competency_classifier.joblib").exists():
                st.info("No selected classifier yet. Extract initial phrases for manual labeling, then train both models and select one.")
            else:
                if training_data_changed():
                    st.warning("Training data has changed since this model was trained. Retraining is recommended.")
    has_results = "_extraction_results_frame" in st.session_state
    if not has_results:
        content_metrics([
            ("PSF-AAI reference entries", f"{len(taxonomy):,}", "layers"),
            ("Local classifier", "Available" if (ROOT / "models/competency_classifier.joblib").exists() else "Unavailable", "model_training"),
            ("Results view", "Not loaded", "format_list_bulleted"),
        ], "extraction_start")
    if has_results:
        with st.container(horizontal=True, key="extraction_setup_and_run", gap="medium", wrap=True):
            setup_slot = st.container(width="stretch")
            run_slot = st.container(width="stretch")
        with setup_slot, content_section("Extraction setup", "tune", "extraction_setup"):
            view_fields = st.container(horizontal=True, vertical_alignment="bottom", gap="medium")
            with view_fields:
                choice = st.selectbox("View", ["All extracted phrases", "Researcher-approved labels", "Unreviewed candidates", "Accepted detections"], width="stretch")
    else:
        run_slot = st.container()
    with run_slot, content_section("Run extraction", "play_arrow", "extraction_run"):
        with st.container(horizontal=True, key="extraction_actions", gap="medium", vertical_alignment="center"):
            if action_button("Run extraction and classification", type="primary"):
                uploads = storage.read_json("uploads", {})
                if uploads.get("psf_aai") and _local_verified_psf_available():
                    _persist_psf_reference_files(force=True)
                else:
                    verified = storage.read_frame("verified_psf_aai")
                    if not verified.empty:
                        _persist_psf_reference_files(verified)
                _start_processing("Extract skill phrases", background_tasks.extract)
            if action_button("Refresh saved results" if has_results else "Load saved results", type="secondary",
                             icon=":material/refresh:", action_id="refresh_extraction_results"):
                st.session_state["_extraction_results_page"] = 1
                _start_processing("Load saved extraction results", background_tasks.extraction_preview)
    if "_extraction_results_frame" not in st.session_state:
        job = st.session_state.get("_background_job")
        if job is not None and job.title in {"Load saved extraction results", "Extract skill phrases"} and job.snapshot()["status"] == "running":
            with st.container(key="extraction_pending_results"):
                st.html(_wireframe("metrics", cards=3))
                st.html(_wireframe("selector"))
                st.html(_wireframe("table", columns=EXTRACTION_COLUMNS))
            return
        st.caption("Run extraction to prepare phrases, or load previously saved results. Saved results are not downloaded when you open this page.")
        return
    result = st.session_state["_extraction_results_frame"]
    limits = result.attrs.get("discovery_limits", {})
    if result.empty:
        st.info("No saved extraction results yet. Run extraction to prepare phrases for review.")
    if not result.empty:
        approved = result.human_label.fillna("").astype(str).str.strip().ne("") if "human_label" in result else pd.Series(False, index=result.index)
        content_metrics([
            ("Researcher-approved labels", f"{int(approved.sum()):,}", "sell"),
            ("Unreviewed extracted phrases", f"{int((~approved).sum()):,}", "description"),
            ("Model predictions (separate)", f"{int(result.model_prediction.fillna('').astype(str).str.strip().ne('').sum()):,}" if "model_prediction" in result else "0", "deployed_code"),
        ], "extraction")
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
            with view_fields:
                page = st.number_input("Results page", min_value=1, max_value=(len(result) + 99) // 100,
                                       value=current_page, step=1, key=page_key, width=200)
            visible, page, _ = _paginate_frame(result, page)
            first_row = (page - 1) * 100 + 1
            last_row = min(page * 100, len(result))
            st.caption(f"Showing {first_row:,}–{last_row:,} of {len(result):,} rows. Full results stay saved; only this page is sent to your browser.")
            with content_section("Extracted skill phrases", "table_view", "extraction_results"):
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
                        with st.spinner("Preparing posting candidates…"):
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
        review_tools = st.container(horizontal=True, key="review_tools", vertical_alignment="center", wrap=True)
        with review_tools:
            with st.popover("Review settings", icon=":material/tune:"):
                auto_train = _auto_retraining_control()
        if supabase_store.configured():
            with review_tools:
                with st.popover("Team updates", icon=":material/sync:"):
                    st.caption("Your team can review simultaneously. Saves detect changes made by another reviewer. Refresh before starting a new batch; unsaved table edits will be discarded.")
                    if action_button("Restore shared ad evidence", help="Admin: run on the computer with the original uploads. Restores missing source text for teammates without changing labels or the active study dataset."):
                        if not supabase_store.is_admin():
                            st.error("Ask the workspace admin to run this on the computer with the original uploads.")
                        else:
                            from .review_queue import archived_job_contexts
                            with st.spinner("Restoring original advertisement evidence for the team…"):
                                token = supabase_store.get_token()
                                records = supabase_store.read_candidates(token, include_source_text=False)
                                sources = {row["source_id"] for row in records
                                           if row.get("source_type") in ("jobs", "Philippine job advertisement")}
                                contexts = archived_job_contexts(storage.ROOT, sources, cached_load_path)
                                updated = supabase_store.restore_candidate_evidence(contexts, token) if contexts else 0
                            st.session_state.pop("_manual_review_queue", None)
                            if contexts:
                                st.success(f"Restored missing evidence for {updated:,} shared candidate rows. Teammates can refresh their shared review table.")
                            else:
                                st.warning("No matching original uploads were found on this computer. Run this repair on the computer that first uploaded these advertisements.")
                    if action_button("Refresh shared review table"):
                        supabase_store.clear_read_cache()
                        for key in list(st.session_state):
                            if str(key).startswith(("review_snapshot", "manual_labels_", "review_draft_", "resolve_label_")):
                                del st.session_state[key]
                        st.rerun()
        with loading_content("review_queue_content", "metrics", cards=4) as content:
            if supabase_store.configured():
                if "review_snapshot" not in st.session_state:
                    st.session_state["review_snapshot"] = storage.read_frame("labeled_competencies")
                labels = st.session_state["review_snapshot"].copy()
            else:
                labels = storage.read_frame("labeled_competencies")
            candidates, taxonomy = _load_manual_review_data(labels)
            with content():
                from .cleaning import normalize_text
                content_metrics([
                    ("Distinct phrases", f"{candidates.normalized_phrase.nunique():,}", "sell"),
                    ("Source occurrences", f"{len(candidates):,}", "layers"),
                    ("Saved review rows", f"{len(labels):,}", "description"),
                    ("Signed-in reviewer", str(st.session_state.get("supabase_user_email") or st.session_state.get("label_reviewer") or "Not set"), "person"),
                ], "review")
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
                    else:
                        with st.expander("Reviewer details"):
                            reviewer = st.text_input("Reviewer ID", key="label_reviewer")
                    _category_review(candidates, occurrences, reviewed_phrases, categories, taxonomy, labels, reviewer, auto_train)



def _category_review(candidates, occurrences, reviewed_phrases, categories, taxonomy, labels, reviewer, auto_train):
    from .cleaning import normalize_text
    if not candidates.empty:
        with content_section("Review setup", "tune", "review_setup"):
            source_filtered = candidates
            review_controls = st.container(horizontal=True, vertical_alignment="bottom", key="review_controls", wrap=True)
            with review_controls:
                review_view = st.selectbox("Review view", ["Unique phrases", "All advertisement occurrences"],
                                           key="manual_review_view", width="stretch")
                query = st.text_input("Find candidate phrase", placeholder="Search phrases…", width="stretch")
                with st.popover("Filters", icon=":material/filter_list:", width="stretch"):
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
                page = st.number_input("Review page (10 rows per page)", 1, max(1, (len(phrase_rows)+9)//10), 1, width="stretch")
            shown = phrase_rows.iloc[(page-1)*10:page*10].copy()
    else:
        st.info("No candidate phrases yet. Add Philippine job-ad source/candidate data to ./train or run Competency Extraction on uploaded jobs. No example labels are added automatically.")
        occurrences = candidates.copy()
        shown = pd.DataFrame(columns=["phrase", "normalized_phrase", "source_type", "source_id", "source_ads", "original_text"])
    with content_section("Review results", "fact_check", "review_results"):
        with loading_content("manual_review_table_content", "review", columns=MANUAL_REVIEW_COLUMNS, rows=len(shown)) as content:
            shown = _review_contexts(shown) if not shown.empty else shown
            active_taxonomy = storage.read_frame("cleaned_psf_aai")
            reference = active_taxonomy.set_index("competency_id") if not active_taxonomy.empty else pd.DataFrame()
            mapping_available = not reference.empty
            mapping_warning = False
            try:
                mapping_reviews = storage.read_frame(REVIEW_TABLE) if mapping_available else pd.DataFrame()
            except supabase_store.SupabaseError:
                mapping_reviews = pd.DataFrame()
                mapping_available = False
                mapping_warning = True
            mapping_occurrences = manual_mapping_occurrences(shown, current_extractions(source_ids=shown.source_id.unique()))
            _page_ai_suggestions(storage.ROOT / "data/processed/pretrained_label_suggestions.csv")
            with content():
                if mapping_warning:
                    st.warning("Competency reviews could not be loaded. Check the shared connection and occurrence-mapping migration. Category review remains available.")
                if not shown.empty:
                    detail_tools = st.container(horizontal=True, key="review_detail_tools")
                    with detail_tools, st.popover("Source evidence", icon=":material/article:"):
                        # Context for the selected rows is always loaded, including training
                        # sources outside the study dataset.
                        st.dataframe(shown[["phrase", "source_type", "source_id", "job_title", "company", "source_url", "original_text"]], hide_index=True, width="stretch", column_config={"source_url": st.column_config.LinkColumn("Original source")})
                        st.caption("Evidence belongs to the advertisement shown in each row. Use All advertisement occurrences to inspect other contexts for the same phrase.")
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
                if reference.empty:
                    st.caption("Activate the reviewed PSF-AAI reference to enable competency selections.")
                page_identity = digest([page_identity, frame_hash(active_taxonomy), frame_hash(mapping_reviews)])[:24]
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
                    with st.container(horizontal=True, vertical_alignment="center", key="manual_review_actions", wrap=True):
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
                        column_order=MANUAL_REVIEW_COLUMNS,
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
                                st.warning("This advertisement's source text is unavailable on this device. Ask the admin to open Team updates → Restore shared ad evidence on the computer with the original uploads, then refresh this review table.")
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
        with loading_content("training_sources", "pending") as content:
            inventory = load_data_with_skeleton(lambda: inspect_training_folder(storage.ROOT), height=140)
            with content():
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
    with content_section("Training configuration", "settings", "training_configuration"):
        st.caption("Use reviewed labels with a job-ad holdout for evaluation.")
        left, right = st.columns([1, 1], gap="large")
        with left:
            fraction = st.slider("Holdout fraction", .1, .5, .2, .05)
        with right:
            include_irrelevant = st.checkbox("Intentionally train IRRELEVANT as a separate class", value=False)
            max_features = st.number_input("Maximum TF-IDF features", 100, 100000, 10000, 100)
    def load_training_review_data():
        current_labels = (storage.read_frame("labeled_competencies") if supabase_store.configured()
                          else load_labeled_data(path))
        validated, report = cached_label_validation(
            current_labels, fraction, include_irrelevant, require_provenance=True
        )
        return current_labels, validated, report
    with loading_content("training_validation", "metrics", cards=3) as content:
        labels, data, validation = load_data_with_skeleton(load_training_review_data, height=240)
        with content():
            content_metrics([
                ("Labeled file rows", validation["total_rows"], "database"),
                ("Distinct usable phrases", validation["rows_used"], "sell"),
                ("Classes", validation["number_of_classes"], "layers"),
            ], "training")
            if not data.empty:
                with content_section("Usable manually labeled examples per category", "bar_chart", "training_distribution"):
                    left, right = st.columns([2.5, 1], gap="medium", vertical_alignment="center")
                    with left:
                        figure = distribution(data, "label", "Usable manually labeled examples per category")
                        figure.update_layout(title_text="")
                        chart(figure)
                    with right:
                        plotted = list(zip(figure.data[0].y, figure.data[0].x))
                        small = [(name, int(count)) for name, count in plotted if count < 5]
                        content_note("Training data insight", f"The chart shows {sum(int(n) for _, n in plotted):,} distinct usable phrases across {len(plotted):,} displayed categories.",
                                     items=([f"{name}: {n} usable phrases; below the five-example software minimum." for name, n in small]
                                            or ["Every displayed category meets the five-example software minimum. Validation may still block training."]))
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
            st.caption("Minimum software gate: 30 distinct phrases, two classes, five examples per class, no conflicting labels, complete provenance and a feasible holdout by job-ad source. These minimums do not establish adequate research validation. Model selection requires valid training-only cross-validation, grouped by source with every category in each fold. Holdout scores never choose the winner. Models are trained only by the button below.")
            if training_data_changed():
                st.warning("Training data has changed since this model was trained. Retraining is recommended.")
            if action_button("Train / Retrain Models", type="primary", disabled=bool(validation["errors"]) or not supabase_store.is_admin()):
                _start_processing("Train reviewed labels", background_tasks.train, fraction, include_irrelevant,
                                  {"max_features": int(max_features)})
            with loading_content("training_saved_model", "table", columns=["model", "accuracy", "macro_f1", "weighted_f1"]) as content:
                metadata = read_model_metadata()
                comparison = storage.read_frame("model_metrics") if metadata else pd.DataFrame()
                with content():
                    if metadata:
                        with content_section("Saved model", "model_training", "training_saved"):
                            if not comparison.empty:
                                st.dataframe(comparison.style.apply(lambda row: ["background-color: #F5E2E7" if str(row.get("selected", "")).casefold() == "true" else ""] * len(row), axis=1), hide_index=True, width="stretch")
                            st.write("Selected model:", metadata["model_name"])
                            st.caption("Based on the current labeled validation sample. The evaluated training-partition model is saved without refitting on holdout examples. Review per-class errors and validate on an independent sample before publication.")


def evaluation():
    page_intro("Evaluate models", "Review model evaluation only when the holdout represents independent job-ad sources.")
    with st.expander("How to read the evaluation metrics", expanded=False):
        st.markdown("**Precision** is the share of a model's category predictions that are correct. **Recall** is the share of actual items in a category that the model finds. **F1-score** balances precision and recall. Macro F1 weighs categories equally; Weighted F1 accounts for category frequency.")
    with loading_content("evaluation_eligibility", "evaluation") as content:
        metadata, metrics = load_data_with_skeleton(
            lambda: (read_model_metadata(), storage.read_frame("model_metrics")), height=160
        )
        if metadata and not metrics.empty:
            try:
                training_frame = (storage.read_frame("training_snapshot") if supabase_store.configured() else load_labeled_data(resolve_training_file(storage.ROOT)))
                overlap = source_overlap(training_frame, metadata)
            except (ValueError, OSError):
                overlap = None
                training_frame = pd.DataFrame()
            split_info = metadata.get("split", {})
            too_few_test_sources = split_info.get("strategy", "").startswith("source-disjoint") and len(set(split_info.get("test_source_ids", []))) < 2
            labels_changed = (training_data_changed() if not (
                overlap or too_few_test_sources or split_info.get("strategy", "").startswith("stratified phrase-level")) else False)
        with content():
            if not metadata or metrics.empty:
                with content_section("Model evaluation results", "query_stats", "evaluation_empty"):
                    st.info("No research model has been trained. Complete manual labeling and the training gate before any F1-scores or other model results can be reported.")
                    with st.container(horizontal=True, gap="medium", wrap=True):
                        page_button("pages/07_ML_Training.py", "Open model training", primary=True, key="evaluation_open_training")
                        page_button("pages/06_Manual_Labeling.py", "Review phrases", key="evaluation_open_review")
                return
            st.write("Selected model:", metadata["model_name"])
            if overlap or too_few_test_sources or split_info.get("strategy", "").startswith("stratified phrase-level"):
                st.error("These saved scores do not provide adequate evidence of generalization across independent job ads, so they are withheld from research reporting. Label more independent ads across categories, then retrain with a source-disjoint evaluation.")
                if overlap:
                    st.caption(f"Detected {len(overlap)} source ID(s) in both partitions. Existing model artifacts and metrics are retained for audit, but are not displayed as research results.")
                elif too_few_test_sources:
                    st.caption(f"The held-out partition contains only {len(set(split_info.get('test_source_ids', [])))} independent job-ad source. That is too limited to show generalization across postings; the saved metrics are withheld.")
                return
            content_metrics([
                ("Selected holdout accuracy", f"{metadata['accuracy']:.3f}", "target"),
                ("Selected holdout Macro F1", f"{metadata['macro_f1']:.3f}", "query_stats"),
                ("Selected holdout Weighted F1", f"{metadata['weighted_f1']:.3f}", "bar_chart"),
            ], "evaluation")
            if metadata.get("selection_basis") == SELECTION_BASIS:
                st.caption("Model selected by training cross-validation before holdout scoring. Holdout scores do not choose the winner; other model scores are diagnostic comparisons.")
            else:
                st.warning("This saved run used the earlier model-selection procedure. Its scores are internal model comparisons, not an independent final evaluation. Retrain to select by training cross-validation; existing artifacts are preserved.")
            if labels_changed:
                st.warning("Training data has changed since this model was trained. Retraining is recommended.")
            with content_section("Model evaluation results", "bar_chart", "evaluation_results"):
                display(metrics)
                data = metrics.melt(id_vars="model", value_vars=["accuracy", "macro_f1", "weighted_f1"], var_name="metric", value_name="score")
                data.score = pd.to_numeric(data.score)
                left, right = st.columns([2.5, 1], gap="medium", vertical_alignment="center")
                with left:
                    chart(bar(data, "model", "score", "Model Metric Comparison", "metric"))
                with right:
                    macro = data.loc[data.metric.eq("macro_f1"), ["model", "score"]].dropna()
                    detail = (f"Displayed holdout Macro F1 ranges from {macro.score.min():.3f} to {macro.score.max():.3f}."
                              if not macro.empty else "No Macro F1 values are available in this comparison.")
                    content_note("Evaluation insight", f"The chart compares {data.model.nunique()} saved {'model' if data.model.nunique() == 1 else 'models'}. {detail}",
                                 items=[f"Selected classifier: {metadata['model_name']}.",
                                        ("This run selected its model using training cross-validation. These holdout comparisons do not select a new winner."
                                         if metadata.get("selection_basis") == SELECTION_BASIS else
                                         "This legacy run used an earlier selection procedure. Treat its scores as internal comparisons and retrain before final evaluation.")], icon="target")
            choice = st.selectbox("Evaluation model", metrics.model.tolist(), index=metrics.model.tolist().index(metadata["model_name"]))
            slug = "nb" if choice.startswith("Multinomial") else "lr"
            with loading_content("evaluation_details", "heatmap", columns=range(min(12, metadata.get("number_of_classes", 1))), rows=min(12, metadata.get("number_of_classes", 1))) as content:
                matrix, per_class, predictions = load_data_with_skeleton(
                    lambda: (
                        storage.read_frame(f"evaluation_{slug}_confusion"),
                        storage.read_frame(f"evaluation_{slug}_per_class"),
                        storage.read_frame(f"evaluation_{slug}_predictions"),
                    ), height=220
                )
                with content():
                    matrix = matrix.set_index("actual").apply(pd.to_numeric)
                    result_heatmap(matrix, "Model Confusion Matrix — actual rows, predicted columns")
                    display(per_class)
                    display(predictions)
                    with st.expander("Stratified cross-validation (training partition only)"):
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
        with st.container(key="psf_mapping_review_heading", gap="xsmall"):
            section_heading("Review competency links", "link",
                            "Employer skill → PSF-AAI competency. Roles and levels are reference metadata, not inferred applicant attainment. Similarity scores are heuristic evidence, not calibrated probabilities.")
    else:
        st.caption("A skill occurrence is a distinct phrase in one advertisement. Select several competencies only when this source context supports each meaning. Broad wording alone is insufficient. Saving replaces the links for this occurrence only.")
    if skills.empty or taxonomy.empty:
        st.info("Accepted skill occurrences and an active PSF-AAI reference are required to review links.")
        return
    if "range_of_application" not in taxonomy or taxonomy.range_of_application.fillna("").astype(str).str.strip().eq("").all():
        st.caption("The active TESDA PDF has no separate Range of Application field; no range text is available to compare.")
    occurrences = skills.drop_duplicates("extraction_id").set_index("extraction_id")
    extraction_id = st.selectbox("Source advertisement" if prefix == "manual" else "Skill occurrence", occurrences.index.tolist(),
                                 format_func=lambda key: f"{occurrences.loc[key, 'original_phrase']} — ad {occurrences.loc[key, 'source_id']}",
                                 index=0 if prefix == "manual" else None, placeholder="Choose a skill occurrence",
                                 key=f"{prefix}_review_occurrence" if prefix == "manual" else f"{prefix}_review_occurrence_choice",
                                 help="A skill occurrence is one distinct phrase in one advertisement. Save only competencies justified by this source context; saving replaces the links for this occurrence only.")
    if extraction_id is None:
        st.caption("Choose a skill occurrence to inspect its source and review competency links.")
        return
    occurrence = occurrences.loc[extraction_id].to_dict() | {"extraction_id": extraction_id}
    source = jobs[jobs.source_id.eq(occurrence["source_id"])] if not jobs.empty else jobs
    if not source.empty:
        source_record = source.reindex(columns=[key for key in ("source_id", "job_title", "company", "url") if key in source])
        source_record = source_record.rename(columns={"source_id": "Source ad ID", "job_title": "Job title",
                                                     "company": "Employer", "url": "Source URL"})
        st.dataframe(source_record, width="stretch", hide_index=True, row_height=38 if prefix == "manual" else 30, height=100 if prefix == "manual" else 70,
                     column_config={"Source URL": st.column_config.LinkColumn("Source URL")},
                     alt="Source advertisement record for the selected competency review")
    with st.expander("Source advertisement text", expanded=prefix == "manual"):
        st.text(str(occurrence.get("original_text", "")))
    if occurrence.get("pending_extraction") is True:
        st.info("This candidate is not in the current extraction. Saved links enter analysis only after the same occurrence is extracted and accepted. Changed evidence will require another review.")
    if not str(occurrence.get("original_text", "")).strip():
        st.warning("Source text is missing. Restore the advertisement context before reviewing competency links.")
        return
    saved = reviews[reviews.extraction_id.eq(extraction_id)] if not reviews.empty else reviews
    current = mapping[mapping.extraction_id.eq(extraction_id)]
    reference = taxonomy.fillna("").set_index("competency_id")
    defaults = saved.competency_id.tolist() if not saved.empty else []
    defaults = [key for key in defaults if key in reference.index]
    if not current.empty and current.mapping_review_status.eq("STALE").any():
        st.warning("The source or reference changed. Check the saved choices and update this review.")
    from .psf_reviews import occurrence_hash
    if not saved.empty:
        stale = (saved.reference_hash.ne(frame_hash(taxonomy)).any()
                 or saved.occurrence_hash.ne(occurrence_hash(occurrence)).any())
        names = [str(reference.loc[key, "competency_name"]) if key in reference.index else f"{key} (outside current reference)"
                 for key in saved.competency_id if key]
        if stale:
            st.warning("Saved links need review because the source or PSF-AAI reference changed. Check each choice and rationale before saving again.")
            st.write("Previously saved competencies: " + (" · ".join(names) or "No justified match"))
        else:
            st.success("Saved competencies: " + " · ".join(names) if names else "Saved: no justified competency match.", icon=":material/check_circle:")
        saved_at = pd.to_datetime(saved.iloc[0].get("timestamp", ""), utc=True, errors="coerce")
        when = saved_at.tz_convert("Asia/Manila").strftime("%d %b %Y, %I:%M %p PHT") if pd.notna(saved_at) else "Date unavailable"
        st.caption(f"Saved by {saved.iloc[0].get('reviewer', '')} · {when}")
    revision = prefix + digest([extraction_id, frame_hash(taxonomy), occurrence_hash(occurrence), frame_hash(saved)])[:16]
    chosen = st.multiselect("PSF-AAI competencies", sorted(reference.index.tolist(), key=lambda key: str(reference.loc[key, 'competency_name']).casefold()), default=defaults,
                            format_func=lambda key: f"{reference.loc[key, 'competency_name']} ({key})",
                            key=f"psf_choices_{revision}", placeholder="Search and select one or more competencies",
                            help="Select another option to add it. Remove a selected tag with its × button. Each link needs its own source-based rationale.")
    st.caption(f"{len(chosen)} competencies selected. Broad wording alone does not justify multiple links.")
    if not saved.empty and set(chosen) != set(defaults):
        st.info("Unsaved competency changes. Complete the evidence below and update the links.", icon=":material/info:")
    old_reasons = dict(zip(saved.competency_id, saved.rationale)) if not saved.empty else {}
    with st.form(f"psf_review_{revision}", border=True):
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
        save_label = "Update competency links" if not saved.empty else "Save competency links"
        if action_form_submit_button(save_label, action_id=f"psf_review_{revision}", type="primary"):
            try:
                save_mapping_review(occurrence, taxonomy, reasons, reviewer,
                                    expected_version=int(saved.version.iloc[0]) if not saved.empty else 0,
                                    context_confirmed=confirmed, unmapped_reason=no_match_reason)
            except (ValueError, supabase_store.SupabaseError) as exc:
                st.error(str(exc))
            else:
                supabase_store.clear_read_cache()
                st.rerun()


def analysis_workflow():
    stages = [
        ("Select job ads", "Choose dataset, sources and scope.", "database"),
        ("Clean and group", "Standardize text and reconcile title variants.", "cleaning_services"),
        ("Extract and review", "Identify skills, education and experience.", "content_paste_search"),
        ("Compare PSF-AAI", "Match job evidence with PSF-AAI competencies.", "layers"),
        ("Describe results", "Analyze demand, gaps and key findings.", "bar_chart"),
    ]
    cards = ''.join(f'<li><span class="material-symbols-rounded" aria-hidden="true">{icon}</span>'
                    f'<div><strong>{title}</strong><p>{detail}</p></div></li>' for title, detail, icon in stages)
    st.html('<section class="fow-analysis-pipeline" aria-label="Analysis pipeline">'
            '<h2>Analysis Pipeline</h2><ol>' + cards + '</ol></section>')


def result_chart_options(*, include_export=False):
    with st.container(horizontal=True, gap="medium", vertical_alignment="bottom", key="result_chart_controls"):
        with st.container(horizontal=True, key="result_chart_selectors"):
            order = st.selectbox("Chart order", ["Alphabetical", "Highest demand", "Lowest demand"], index=1, key="result_chart_order")
            limit = st.selectbox("Items per chart", [10, 15, 20, 30], index=1, key="result_chart_limit")
        with st.container(key="result_chart_note"):
            st.caption(f"Up to {limit} aggregated categories per chart. Full evidence tables are paginated and exportable. " +
                       ("Darker bars mark the highest count, including ties." if order == "Highest demand" else
                        "Darker bars mark the lowest displayed count, including ties." if order == "Lowest demand" else
                        "Alphabetical order supports label lookup, rather than demand ranking."))
        if include_export:
            with st.container(key="result_chart_export"):
                if action_button("Export results", icon=":material/download:", key="results_export", type="primary"):
                    st.switch_page("pages/14_Reports.py")
    return order, limit


def ordered_result_table(frame, label, order, value=None):
    if frame.empty or label not in frame:
        return frame
    out = frame.assign(_display_order=frame[label].map(normalize_text))
    fields = [value, "_display_order"] if order in ("Highest demand", "Lowest demand") and value in frame else ["_display_order"]
    return out.sort_values(fields, ascending=[order == "Lowest demand", True] if len(fields) == 2 else True, kind="stable").drop(columns="_display_order")


def result_single_metric(title, label, value, unit, detail, *, key):
    """Show a single observed value with its category and scope instead of a one-item chart."""
    with st.container(key=key):
        st.subheader(title)
        st.metric(str(label), f"{int(value):,}", help=f"{title}. {detail}")
        st.caption(" · ".join(part for part in (unit, detail) if part))


def result_count_chart(frame, label, value, title, *, order="Highest demand", limit=15, highlight_max=False):
    if frame.empty:
        st.caption("No evidence for this chart in the current selection.")
        return
    if order == "Lowest demand":
        title = re.sub(r"^Top\b", "Least frequent", title)
        title = re.sub(r"^Most common\b", "Least common", title)
    fields = [field for field in (label, value, "job_ads_pct", "employer_demand_pct", "framework_order") if field in frame]
    chart_key = digest([VERSION, frame[fields].to_dict("list"), label, value, title, order, limit,
                        st.get_option("theme.primaryColor"), st.get_option("theme.chartCategoricalColors")])
    def prepare_chart():
        prepared = ranked_bar(frame, label, value, title, order=order, limit=limit)
        # Plotly binary-array exports are transport data, not iterable count arrays.
        specification = prepared.to_dict()
        specification["data"][0]["x"] = list(prepared.data[0].x)
        specification["data"][0]["y"] = list(prepared.data[0].y)
        return specification
    specification = _session_cached_value("_fow_bar_figures", chart_key,
                                          prepare_chart,
                                          ttl=None, max_entries=32)
    figure = go.Figure(specification)
    if highlight_max:
        extremum = min if order == "Lowest demand" else max
        maximum = extremum((count for trace in figure.data for count in trace.x), default=0)
        for trace in figure.data:
            trace.update(marker_color=["#99043B" if count == maximum else "#958277" for count in trace.x])
    if len(frame) != 1:
        chart(figure)
        return figure
    category = figure.data[0].y[0]
    count = figure.data[0].x[0]
    percentage = next((field for field in ("job_ads_pct", "employer_demand_pct") if field in frame), None)
    detail = "Only one category appears in the current selection."
    if percentage:
        share = pd.to_numeric(frame[percentage].iloc[0], errors="coerce")
        if pd.notna(share):
            detail = f"{share:.1f}% of selected job advertisements. {detail}"
    key_part = "".join(character.lower() if character.isalnum() else "_" for character in f"{title}_{category}")[:72]
    result_single_metric(title, category, count, "Job advertisements", detail,
                         key=f"result_single_{key_part}")
    return figure


def psf_competency_demand_insight(figure, total_competencies, *, order="Highest demand"):
    rows = [(str(label), int(count)) for trace in figure.data for label, count in zip(trace.y, trace.x)] if figure else []
    if not rows:
        st.caption("No displayed competency demand is available for an insight.")
        return
    shown = pd.DataFrame(rows, columns=["competency", "job_ads"]).sort_values(
        ["job_ads", "competency"], ascending=[False, True], kind="stable")
    levels = shown.job_ads.drop_duplicates().tolist()

    def group_names(count):
        names = shown.loc[shown.job_ads.eq(count), "competency"].tolist()
        return ", ".join(names[:3]) + (f" and {len(names) - 3} others" if len(names) > 3 else "")

    maximum, minimum = levels[0], levels[-1]
    if len(shown) == 1:
        summary = f"{group_names(maximum)} appears in {maximum:,} distinct advertisements. Only one competency is displayed."
        implication = "A single displayed competency does not provide a comparison of demand."
    elif len(levels) == 1:
        summary = f"All {len(shown):,} displayed competencies have the same count: {maximum:,} distinct advertisements each."
        implication = "The displayed counts do not distinguish a higher-demand competency."
    else:
        leaders = int(shown.job_ads.eq(maximum).sum())
        summary = (f"{group_names(maximum)} {'has' if leaders == 1 else 'share'} the highest displayed count, "
                   f"at {maximum:,} distinct advertisements{' each' if leaders > 1 else ''}.")
        implication = (f"Observed coverage varies from {minimum:,} to {maximum:,} advertisements among the displayed competencies. "
                       "These counts describe the selected advertisements and their competency links.")
    takeaways = [f"Highest shown: {group_names(maximum)} ({maximum:,} ads each)."]
    if len(levels) > 2:
        takeaways.append(f"Next count: {group_names(levels[1])} ({levels[1]:,} ads each).")
    if len(levels) > 1:
        takeaways.append(f"Lowest shown: {group_names(minimum)} ({minimum:,} ads each).")
    takeaways.append(f"View coverage: {len(shown):,} of {total_competencies:,} competencies. Full results remain in the table below.")
    emphasis = "lowest" if order == "Lowest demand" else "highest"
    st.html('<aside class="fow-key-insight fow-competency-demand-insight" aria-label="Competency Demand Insight">'
            '<h3><span class="material-symbols-rounded" aria-hidden="true">target</span>Competency Demand Insight</h3>'
            f'<p>{escape(summary)}</p><h4>Implication</h4><p>{escape(implication)}</p><h4>Key Takeaways</h4><ul>'
            + ''.join(f'<li>{escape(text)}</li>' for text in takeaways)
            + f'</ul><p class="fow-insight-scope">Maroon marks the {emphasis} displayed count, including ties. '
            'An advertisement can support several competencies.</p></aside>')


def alignment_status_insight(figure):
    counts = {str(label): int(count) for trace in figure.data for label, count in zip(trace.y, trace.x)}
    total = sum(counts.values())
    if not total:
        st.caption("No alignment evidence groups are available for an insight.")
        return
    maximum = max(counts.values())
    leaders = [label for label, count in counts.items() if count == maximum]
    unit = "evidence group" if maximum == 1 else "evidence groups"
    if len(counts) == 1:
        summary = f"Only one status is displayed: {leaders[0]} ({maximum:,} {unit})."
    elif len(leaders) == len(counts):
        summary = f"All {len(leaders)} displayed statuses are tied at {maximum:,} {unit} each."
    else:
        summary = (f"{', '.join(leaders).capitalize()} {'has' if len(leaders) == 1 else 'share'} the highest displayed count: "
                   f"{maximum:,} {unit}{' each' if len(leaders) > 1 else ''} ({maximum / total:.1%}{' each' if len(leaders) > 1 else ''}).")
    breakdown = " · ".join(f"{label}: {count:,} ({count / total:.1%})" for label, count in counts.items())
    implication = "These statuses describe recorded correspondence under the configured thresholds; they do not establish competency equivalence or model accuracy."
    if len(counts) == 1:
        implication = "Only one recorded status is present, so this view does not compare different alignment outcomes."
    elif leaders == ["not mapped"]:
        implication = "Inspect recurring unmapped skills against the source reference. This status alone does not establish a framework gap or an emerging skill."
    elif leaders == ["partially aligned"]:
        implication = "Partial correspondence is the most common recorded status. Review the supporting source evidence before interpreting these links as confirmed matches."
    st.html('<aside class="fow-key-insight" aria-label="Alignment Insight">'
            '<h3><span class="material-symbols-rounded" aria-hidden="true">target</span>Alignment Insight</h3>'
            f'<p>{escape(summary)}</p><p>{escape(breakdown)}</p><h4>Implication</h4><p>{escape(implication)}</p>'
            f'<p>{total:,} displayed phrase–competency evidence {"group" if total == 1 else "groups"}; these percentages do not use distinct job advertisements as their denominator.</p></aside>')


def result_insight(title, summary, rows, list_title="Top 3"):
    items = "".join(
        f"<li><span>{escape(str(name))}</span><strong>{int(count):,} {'ad' if int(count) == 1 else 'ads'}</strong></li>"
        for name, count in rows[:3]
    )
    icon = {"Title Insight": "workspace_premium", "Heatmap Insight": "bar_chart", "Selection Insight": "target",
            "Location Insight": "location_on", "Education Insight": "menu_book", "Timeline Insight": "schedule"}.get(title, "lightbulb")
    st.html(
        '<aside class="fow-key-insight" aria-label="' + escape(title) + '">'
        f'<h3><span class="material-symbols-rounded" aria-hidden="true">{icon}</span>{escape(title)}</h3><p>{escape(summary)}</p>'
        + (f"<h4>{escape(list_title)}</h4><ol>{items}</ol>" if items else "")
        + "</aside>"
    )


def featured_visual_chart(render_chart, summary, rows, *, key, insight_title="Key Insight", list_title="Top 3"):
    """Use the reference's single chart-and-insight card without changing data."""
    embedded = key in {"titles", "family_heatmap", "selected_title"}
    with st.container(border=not embedded, key=f"job_market_{'embedded' if embedded else 'featured'}_{key}"):
        chart_column, insight_column = st.columns([3.2, 1], vertical_alignment="center")
        with chart_column:
            render_chart()
        with insight_column:
            result_insight(insight_title, summary, rows, list_title)


def result_role_distribution(roles):
    bands = roles.groupby("job_ads").size().sort_index(ascending=False)
    total = int(bands.sum())
    if not total:
        return
    colors = ("#86142D", "#A99B92", "#D6A33D", "#D9C7BE")
    groups = [(f"{int(ads):,} ads each", int(count)) for ads, count in bands.head(3).items()]
    if len(bands) > 3:
        groups.append(("Other ad counts", int(bands.iloc[3:].sum())))
    stops, legend, offset = [], [], 0
    for color, (label, count) in zip(colors, groups):
        end = offset + count / total * 100
        stops.append(f"{color} {offset:.3f}% {end:.3f}%")
        legend.append(f'<li><i style="background:{color}" aria-hidden="true"></i><span>{escape(label)}<small>{count:,} {"role" if count == 1 else "roles"} · {count / total:.1%}</small></span></li>')
        offset = end
    st.html('<aside class="fow-key-insight fow-distribution" aria-label="Reference-role distribution">'
            '<h3><span class="material-symbols-rounded" aria-hidden="true">pie_chart</span>Distribution Summary</h3>'
            f'<p>{total:,} displayed reference roles have competency links to the selected advertisements. An advertisement may link to several roles.</p>'
            f'<div class="fow-role-distribution"><div class="fow-role-donut" role="img" aria-label="{total} linked reference roles grouped by advertisement count" style="background:conic-gradient({", ".join(stops)})">'
            f'<span><strong>{total:,}</strong><small>Linked roles</small></span></div><ul>{"".join(legend)}</ul></div></aside>')


def _plotted_counts(figure, label, value):
    return pd.DataFrame([(str(name), int(count)) for trace in (figure.data if figure is not None else [])
                         for name, count in zip(trace.y, trace.x)], columns=[label, value])


def featured_result_chart(label, value, heading, total, render_chart, *, key):
    """Derive the companion insight from the exact visible chart rows."""
    embedded = key in {"titles", "selected_title", "unmapped_evidence", "unmapped_recurring"}
    with st.container(border=not embedded, key=f"job_market_{'embedded' if embedded else 'featured'}_{key}"):
        chart_column, insight_column = st.columns([3.2, 1], vertical_alignment="center")
        with chart_column:
            figure = render_chart()
        data = _plotted_counts(figure, label, value)
        data = data.sort_values([value, label], ascending=[False, True], kind="stable")
        if data.empty:
            summary, rows = "No reportable evidence in this selection.", []
        else:
            concept = {
                "Top requested skills": "skill",
                "Top technical skills": "technical skill",
                "Top enabling skills": "enabling skill",
                "Most common broad area": "competency area",
                "Top occupational titles": "job title",
                "Most stated education level": "education level",
                "Most linked competency": "PSF-AAI competency",
                "Most represented reference roles": "PSF-AAI reference role",
                "Most frequent unmapped skill": "unmapped skill",
                "Recurring unmapped skill": "recurring unmapped skill",
            }.get(heading, "category")
            maximum = int(data[value].max())
            leaders = data.loc[data[value].eq(maximum), label].astype(str).tolist()
            share = f" ({maximum / total * 100:.1f}% of {total:,} selected ads)" if total else ""
            unit = "ad" if maximum == 1 else "ads"
            if len(data) == 1:
                summary = f"{leaders[0]} appears in {maximum:,} {unit}{share}. Only one {concept} is displayed."
            elif len(leaders) == 1:
                summary = f"{leaders[0]} has the highest displayed {concept} count, appearing in {maximum:,} {unit}{share}."
            else:
                plural = concept[:-1] + "ies" if concept.endswith("y") else concept + "s"
                summary = f"{len(leaders):,} {plural} tie for the highest displayed count at {maximum:,} {unit} each{share}."
            rows = list(zip(data[label].head(3), data[value].head(3)))
        insight_title, list_title = {
            "titles": ("Title Insight", "Top Displayed Titles"),
            "education": ("Education Insight", "Stated Levels"),
            "selected_title": ("Selection Insight", "Top Displayed Skills"),
            "psf_competencies": ("Key Insight", "Top Displayed Competencies"),
            "unmapped_evidence": ("Evidence Insight", "Top Displayed Skills"),
            "unmapped_recurring": ("Review Insight", "Top Displayed Candidates"),
        }.get(key, ("Key Insight", "Top Displayed Skills"))
        with insight_column:
            result_insight(insight_title, summary, rows, list_title)


def result_heatmap(matrix, title, *, count_label="Count", share_matrix=None, row_denominators=None,
                   share_label="Share within row group", denominator_label="Row-group advertisements",
                   row_group_label="row group", transpose=False):
    if matrix.empty:
        st.caption("No evidence for this heatmap in the current selection.")
    elif matrix.size == 1:
        label = f"Actual: {matrix.index[0]} · predicted: {matrix.columns[0]}" if "Confusion Matrix" in title else f"{matrix.index[0]} · {matrix.columns[0]}"
        detail = "Only one cell is present, so there is no category comparison."
        if share_matrix is not None:
            share = float(pd.DataFrame(share_matrix).reindex(index=matrix.index, columns=matrix.columns).iat[0, 0])
            detail = f"{share:.1f}% of advertisements in this {row_group_label}. " + detail
            if row_denominators is not None:
                total = int(pd.to_numeric(pd.Series(row_denominators), errors="coerce").reindex(matrix.index).fillna(0).iloc[0])
                unit = "job ad" if total == 1 else "job ads"
                detail = f"{share:.1f}% of {total:,} {unit} in this {row_group_label}. Only one cell is present, so there is no category comparison."
        result_single_metric(title, label, matrix.iat[0, 0], count_label,
                             detail,
                             key="result_single_heatmap")
    else:
        chart(heatmap(matrix, title, count_label=count_label, share_matrix=share_matrix,
                      row_denominators=row_denominators, share_label=share_label,
                      denominator_label=denominator_label, transpose=transpose))


@st.fragment
def _competency_heatmap_view(cells, roles, competence, limit):
    """Rerun only this chart when its role or competency filters change."""
    role_sizes = roles.set_index("psf_job_role").job_ads
    role_options = sorted(cells.psf_job_role.unique(), key=lambda name: (-role_sizes.get(name, 0), name))
    competency_sizes = competence.set_index("psf_competency").job_ads
    competency_options = sorted(cells.psf_competency.unique(),
                                key=lambda name: (-competency_sizes.get(name, 0), name))
    role_default = role_options[:8]
    competency_default = competency_options[:min(limit, 15)]
    role_key = "result_competency_heatmap_roles"
    competency_key = "result_competency_heatmap_competencies"
    selected_roles = [name for name in st.session_state.get(role_key, role_default) if name in role_options]
    selected_competencies = [name for name in st.session_state.get(competency_key, competency_default)
                             if name in competency_options]
    if selected_roles != st.session_state.get(role_key, role_default):
        st.session_state[role_key] = selected_roles
    if selected_competencies != st.session_state.get(competency_key, competency_default):
        st.session_state[competency_key] = selected_competencies

    heatmap_output = st.container(key="psf_role_competency_heatmap_output")
    chosen_roles = st.multiselect("Reference roles in the heatmap", role_options,
                                  default=role_default, key=role_key)
    chosen_competencies = st.multiselect("PSF-AAI competencies in the heatmap", competency_options,
                                         default=competency_default, key=competency_key)
    selected_cells = cells[cells.psf_job_role.isin(chosen_roles) & cells.psf_competency.isin(chosen_competencies)]
    if selected_cells.empty:
        heatmap_output.info("Select at least one role and competency with reviewed mapping evidence.")
    else:
        matrix = selected_cells.pivot(index="psf_job_role", columns="psf_competency", values="job_ads")
        matrix = matrix.reindex(index=chosen_roles, columns=chosen_competencies).fillna(0).astype(int)
        row_denominators = roles.set_index("psf_job_role").job_ads.reindex(matrix.index).fillna(0).astype(int)
        shares = matrix.div(row_denominators.where(row_denominators.gt(0), 1), axis=0).mul(100)
        with heatmap_output:
            result_heatmap(matrix, "Reviewed PSF-AAI competencies across reference roles", count_label="Job advertisements",
                           share_matrix=shares, row_denominators=row_denominators,
                           share_label="Share of role ads", denominator_label="Advertisements linked to role",
                           row_group_label="reference role", transpose=True)
            st.caption("Cells count distinct advertisements with existing ALIGNED or PARTIALLY ALIGNED researcher-reviewed links. Color uses the share of all ads linked to that role; hidden competencies stay in the denominator. An ad can support several competencies and roles, so percentages may overlap and cell counts must not be summed into unique ads.")
    evidence_tables("View all role-by-competency counts", {"": cells.rename(columns={
        "psf_job_role": "PSF-AAI reference role", "psf_competency": "PSF-AAI competency", "job_ads": "Job advertisements"})},
        key="result_role_competency_table")


@st.fragment(key="job_market_results")
def _job_market_results(tables, meta, revision=None):
    try:
        _job_market_content(tables, meta, revision)
    except (ValueError, OSError, KeyError, TypeError, supabase_store.SupabaseError) as exc:
        loaded = st.session_state.get("_fow_market_loaded", {})
        loaded.get("sections", set()).discard(st.session_state.get("_fow_market_active_section"))
        st.error(str(exc))
        st.caption("Review the input or configuration and try again. Raw uploads have not been changed.")


def _job_market_content(tables, meta, revision=None):
    st.session_state["_table_number"] = 0
    # Normal page loads pass the existing bundle revision; standalone renders hash their inputs.
    revision = revision or digest([VERSION, meta, {
        name: frame_hash(tables[name].drop(columns=["original_text"], errors="ignore")) for name in (
            "cleaned_jobs", "extracted_job_skills", "psf_mapping", "psf_framework_order", "verified_psf_aai"
        ) if name in tables
    }])
    loaded = st.session_state.get("_fow_market_loaded", {})
    if loaded.get("revision") != revision:
        loaded = {"revision": revision, "sections": set()}
        st.session_state["_fow_market_loaded"] = loaded
        st.session_state.setdefault("_fow_loading_ready", {}).pop("job_market_psf_charts", None)
    # Keep hidden section controls out of Streamlit's widget-cleanup cycle.
    for key in ("result_title_view", "result_family", "result_specific_title", "result_region", "result_city",
                "result_skill_family_heatmap_families", "result_psf_role",
                "result_competency_heatmap_roles", "result_competency_heatmap_competencies"):
        if key in st.session_state:
            st.session_state[key] = st.session_state[key]
    jobs = tables["cleaned_jobs"]
    chart_keys = {"chart_skill_occurrences", "chart_skill_demand", "chart_phrase_review", "chart_skill_family_demand", "chart_family_ad_counts"}
    views = (tables if chart_keys.issubset(tables) else _session_cached_value(
        "_fow_market_skill_cache", revision, lambda: skill_chart_tables(tables["extracted_job_skills"], jobs),
        ttl=None, max_entries=1))
    skills, demand, unclear = (views[key] for key in ("chart_skill_occurrences", "chart_skill_demand", "chart_phrase_review"))
    denominator = jobs.source_id.nunique() if "source_id" in jobs else 0
    unclear_count = unclear.normalized_phrase.nunique() if not unclear.empty else 0
    framework = tables.get("psf_framework_order", tables.get("verified_psf_aai", pd.DataFrame()))
    role_field = next((field for field in ("job_role", "psf_job_role") if field in framework), None)
    if role_field and not framework.empty:
        reference_roles = framework[role_field].fillna("").map(normalize_text).str.split("; ").explode()
        reference_role_count = int(reference_roles.loc[reference_roles.ne("")].nunique())
        reference_role_value = f"{reference_role_count:,}"
    else:
        reference_role_value = "—"
    metrics = [("Job ads in sample", denominator, "work"),
               ("Distinct chart skills", len(demand), "bar_chart"),
               ("Distinct phrases withheld", unclear_count, "sell"),
               ("PSF-AAI reference roles", reference_role_value, "layers")]
    with st.container(horizontal=True, gap="medium", key="result_metrics"):
        for index, (label, value, icon) in enumerate(metrics, 1):
            with st.container(border=True, key=f"result_metric_{index}"):
                st.metric(label, f"{value:,}" if isinstance(value, int) else value, icon=f":material/{icon}:")
    order, limit = result_chart_options(include_export=True)

    def plot(frame, label, value, title):
        return result_count_chart(frame, label, value, title, order=order, limit=limit)

    def skill_counts(rows, total):
        out = rows.groupby("skill_label").source_id.nunique().rename("job_ads").reset_index()
        out["job_ads_pct"] = out.job_ads / total * 100 if total else float("nan")
        return out

    st.subheader("Results Section", icon=":material/bar_chart:")
    with st.container(key="result_sections"):
        section = st.segmented_control("Results section", ["Skills", "Roles and locations", "Qualifications", "PSF-AAI demand"],
                                       default="Skills", key="result_section", width="stretch", label_visibility="collapsed")
    section_key = {"Skills": "skills", "Roles and locations": "roles", "Qualifications": "qualifications",
                   "PSF-AAI demand": "psf_aai"}.get(section, "none")
    changed_section = st.session_state.get("_fow_market_active_section") != section_key
    st.session_state["_fow_market_active_section"] = section_key
    if changed_section:
        st.session_state["_fow_market_transition"] = st.session_state.get("_fow_market_transition", 0) + 1
    ready = st.session_state.setdefault("_fow_loading_ready", {})
    if section_key in loaded["sections"]:
        ready["job_market_view_load"] = True
    else:
        ready.pop("job_market_view_load", None)
    st.html('<style>[class*="st-key-job_market_section_"]{display:none!important}'
            f'.st-key-job_market_section_{section_key}' + '{display:flex!important}</style>')
    with loading_content("job_market_view_load", "market_section", view=section, rows=limit, defer=True,
                         transition=st.session_state["_fow_market_transition"] if changed_section else None) as section_content:
        with section_content(), st.container(key=f"job_market_section_{section_key}"):
            if section == "Skills":
                featured_result_chart(
                    "employer_skill", "employer_demand_count", "Top requested skills", denominator,
                    lambda: plot(demand, "employer_skill", "employer_demand_count", "Employer-requested skills"),
                    key="skills",
                )
                withheld_reasons = unclear.review_reason.fillna("") if not unclear.empty else pd.Series(dtype=str)
                def ads_for_reason(prefixes):
                    if unclear.empty:
                        return 0
                    return int(unclear.loc[withheld_reasons.str.startswith(tuple(prefixes)), "source_id"].nunique())
                not_reported_ads = ads_for_reason(("Not reported (missing placeholder)",))
                experience_phrase_ads = ads_for_reason(("Experience-duration requirement", "Unclear year-duration phrase", "No-experience requirement"))
                irrelevant_ads = ads_for_reason(("Researcher or classifier marked",))
                chart_summary = meta.get("chart_presentation", {})
                no_chartable_ads = int(chart_summary.get("ads_without_chartable_skill", max(0, denominator - skills.source_id.nunique()))) if denominator else 0
                st.caption(f"Missing / not-mentioned placeholders: {not_reported_ads:,} ads. No chartable skill evidence, regardless of PSF status: {no_chartable_ads:,} of {denominator:,} ads.")
                st.caption(f"Experience/year wording: {experience_phrase_ads:,} ads; excluded from skills and PSF-AAI demand. Irrelevant labels: {irrelevant_ads:,} ads; excluded.")
                st.caption(f"One advertisement counts once per grouped skill, including equivalent wording. Percentages use all {denominator:,} selected ads; an ad can request several skills.")
                st.caption("Unmapped but skill-like phrases remain in employer demand; their PSF-AAI correspondence is reviewed separately.")
                for kind, title in (("Technical", "Technical skills"), ("Soft / Enabling", "Enabling and interpersonal skills")):
                    rows = skills[skills.get("skill_type", pd.Series("", index=skills.index)).eq(kind)]
                    skill_heading = "Top technical skills" if kind == "Technical" else "Top enabling skills"
                    counts = skill_counts(rows, denominator)
                    featured_result_chart("skill_label", "job_ads", skill_heading, denominator,
                                          lambda: plot(counts, "skill_label", "job_ads", title),
                                          key=f"{kind.casefold().replace(' ', '_')}_skills")
                if not skills.empty:
                    categories = skills.copy()
                    categories["category_group"] = categories.competency_category.map(category_parent).replace("Not applicable", "Category needs review").str.casefold()
                    if "category_conflict" in categories:
                        categories.loc[categories.category_conflict.eq(True), "category_group"] = "category needs review"
                    counts = categories.groupby("category_group").source_id.nunique().rename("job_ads").reset_index()
                    featured_result_chart("category_group", "job_ads", "Most common broad area", denominator,
                                          lambda: plot(counts, "category_group", "job_ads", "Broad competency areas"),
                                          key="broad_competency_areas")
                    st.caption("An advertisement may contribute to several broad areas; these counts are overlapping categories, not parts of one whole.")
                with st.expander("How technical and enabling categories are determined"):
                    st.write("Technical / Digital includes AI and machine learning, data and analytics, and general digital tools. Enabling capabilities include communication, personal effectiveness and leadership. Domain knowledge is separate. Education is a credential, not a skill category.")
                    st.write("Basis: the project's discovery vocabulary includes sql under technical / digital and collaboration under soft / enabling. Saved researcher labels override automated category assignments; a trained classifier can categorize other phrases. Matching-method and label provenance remain in the exported occurrence data. The discovery dictionary is not an official TESDA category list.")
                    st.write("Analytical categories and PSF-AAI links are separate decisions. Category needs review means the current label does not resolve to the study hierarchy; it is not a new skill type.")
                evidence_tables(f"Excluded and unclear phrases ({len(unclear):,} source occurrences)", {"": unclear},
                                key="result_unclear_evidence", note="Missing values, experience wording, vague-only descriptors and unfinished phrases are omitted from skill charts and automatic PSF-AAI demand. Original phrases and saved labels stay here for review; specific skill mentions remain counted.")
                evidence_tables("Skill-demand table", {"": demand}, key="result_skill_demand_evidence")
                evidence_tables("Skill wording groups and original phrases", {"": views.get("chart_skill_variants", pd.DataFrame())},
                                key="job_market_wording_groups", note="Equivalent wording shares one chart label. Each advertisement counts once per label; variant counts must not be added. Original wording and saved labels remain unchanged.")

            if section == "Roles and locations":
                profile = (tables if "education_level_counts" in tables else _session_cached_value(
                    "_fow_market_profile_cache", revision, lambda: job_profile_tables(jobs), ttl=None, max_entries=1))
                geography = (tables if "location_evidence" in tables else _session_cached_value(
                    "_fow_market_geography_cache", revision, lambda: location_tables(jobs), ttl=None, max_entries=1))
                @st.fragment
                def title_overview():
                    with st.container(border=True, key="job_market_title_overview"):
                        st.subheader("Job-title overview", icon=":material/work:")
                        title_view = st.selectbox("Job-title overview", ["Most common job titles", "Related role groups", "Specific titles (alphabetical)"], key="result_title_view", label_visibility="collapsed")
                        grouped = title_view == "Related role groups"
                        common_titles = title_view == "Most common job titles"
                        alphabetical_titles = title_view == "Specific titles (alphabetical)"
                        title_field = "job_role_group" if grouped else "common_job_title" if common_titles else "job_title"
                        title_counts = (profile["job_role_group_counts"] if grouped else
                                        profile["common_job_title_counts"] if common_titles else profile["job_title_counts"])
                        if not title_counts.empty:
                            chart_title = "Related role groups" if grouped else ("Specific job titles (alphabetical)" if alphabetical_titles else "Most common job titles")
                            title_order = "Alphabetical" if alphabetical_titles else order
                            featured_result_chart(
                                title_field, "job_ads", "Top occupational titles", denominator,
                                lambda: result_count_chart(title_counts, title_field, "job_ads", chart_title,
                                                           order=title_order, limit=limit),
                                key="titles",
                            )
                        st.caption("Most-common titles consolidate clear seniority and branch/specialty variants when one recognized occupation is stated. Composite and unrecognized titles stay distinct. Related role groups use source families; specific titles preserve exact normalized wording. Counts are distinct ads, and original titles remain auditable.")
                        evidence_tables("Inspect common-title normalization", {"": profile["common_job_title_evidence"]},
                                        key="result_title_normalization")
                        evidence_tables("Inspect source-family role grouping", {
                            "Source-title evidence": profile["job_title_group_evidence"], "Family counts": profile["job_title_family_counts"]},
                            key="result_title_family_evidence")
                title_overview()

                evidence = profile["job_title_group_evidence"]
                def reset_exploration():
                    for key in ("result_family", "result_specific_title", "result_region", "result_city"):
                        st.session_state[key] = "All"
                    st.session_state.pop("result_skill_family_heatmap_families", None)
                st.button("Reset exploration filters", on_click=reset_exploration, icon=":material/restart_alt:")

                @st.fragment
                def family_comparison():
                    with st.container(border=True, key="job_market_family_section"):
                        st.subheader("How do requested skills vary by occupational family?", icon=":material/layers:")
                        family_demand = views.get("chart_skill_family_demand", pd.DataFrame())
                        family_ads = views.get("chart_family_ad_counts", pd.DataFrame())
                        family_options = family_ads.loc[family_ads.job_family.ne("not stated"), "job_family"].tolist() if not family_ads.empty else []
                        top_skills = ordered_result_table(demand, "employer_skill", order, "employer_demand_count").head(min(limit, 15)).employer_skill.tolist()
                        if family_options and top_skills:
                            family_sizes = family_ads.set_index("job_family").family_ads
                            heatmap_families_default = sorted(family_options, key=lambda name: (-family_sizes.get(name, 0), name))[:8]
                            family_key = "result_skill_family_heatmap_families"
                            family_selection = [name for name in st.session_state.get(family_key, heatmap_families_default) if name in family_options]
                            if family_selection != st.session_state.get(family_key, heatmap_families_default):
                                st.session_state[family_key] = family_selection
                            chosen_families = st.multiselect("Occupational families in the heatmap", family_options,
                                                             default=heatmap_families_default, key=family_key)
                            selected_family_demand = family_demand[
                                family_demand.job_family.isin(chosen_families) & family_demand.skill_label.isin(top_skills)]
                            if selected_family_demand.empty:
                                st.info("No chartable skill evidence is available for the selected occupational families.")
                            else:
                                matrix = selected_family_demand.pivot(index="job_family", columns="skill_label", values="job_ads")
                                matrix = matrix.reindex(index=chosen_families, columns=top_skills).fillna(0).astype(int)
                                row_denominators = family_sizes.reindex(matrix.index).fillna(0).astype(int)
                                shares = matrix.div(row_denominators.where(row_denominators.gt(0), 1), axis=0).mul(100)
                                cells = selected_family_demand.copy()
                                cells["family_ads"] = cells.job_family.map(family_sizes).fillna(0).astype(int)
                                cells["share"] = cells.job_ads.div(cells.family_ads.where(cells.family_ads.gt(0), 1)).mul(100)
                                cells = cells.sort_values(["share", "job_ads", "skill_label", "job_family"],
                                                          ascending=[False, False, True, True], kind="stable")
                                best = cells.iloc[0]
                                tied = cells[cells.share.eq(best.share)]
                                family_summary = (f"{len(tied):,} displayed skill–family pairs tie for the highest within-family share ({best.share:.1f}%)."
                                                  if len(tied) > 1 else
                                                  f"{best.skill_label} has the highest displayed within-family share in {best.job_family}: "
                                                  f"{int(best.job_ads):,} of {int(best.family_ads):,} ads ({best.share:.1f}%).")
                                family_rows = [(f"{row.skill_label} · {row.job_family}", row.job_ads)
                                               for row in cells.head(3).itertuples()]
                                featured_visual_chart(
                                    lambda: result_heatmap(matrix, "Least frequent requested skills by occupational family" if order == "Lowest demand" else "Top requested skills by occupational family",
                                                            count_label="Job advertisements", share_matrix=shares,
                                                            row_denominators=row_denominators, share_label="Share of family ads",
                                                            denominator_label="Advertisements in family",
                                                            row_group_label="occupational family", transpose=True),
                                    family_summary, family_rows, key="family_heatmap", insight_title="Heatmap Insight",
                                    list_title="Top Skill × Family",
                                )
                            missing_family_ads = int(family_ads.loc[family_ads.job_family.eq("not stated"), "family_ads"].sum())
                            if missing_family_ads:
                                st.caption(f"Occupational family not stated or classifiable: {missing_family_ads:,} ads; excluded from this comparison.")
                            st.caption("Color compares the share of advertisements in each family that request a skill. Denominators include ads with no chartable skill; skill categories overlap, so row percentages can exceed 100% in total. Hover for counts and family size.")
                            evidence_tables("View all skill-by-family counts", {"": family_demand.rename(columns={
                                "job_family": "Occupational family", "skill_label": "Skill", "job_ads": "Job advertisements",
                                "family_ads": "Family advertisements", "job_ads_pct": "Share of family ads (%)"})},
                                key="result_all_skill_family_table")
                        elif family_options:
                            st.info("No chartable skill evidence is available for the selected advertisements.")
                        else:
                            st.info("No classifiable occupational families are available for the skill comparison.")
                family_comparison()

                @st.fragment
                def title_and_location_exploration():
                    with st.container(border=True, key="job_market_title_section"):
                        st.subheader("Explore a selected title", icon=":material/person_search:")
                        title_evidence = profile["job_title_source_evidence"]
                        family_options = sorted(title_evidence.job_family.unique().tolist())
                        with st.container(horizontal=True, key="result_title_exploration_filters"):
                            family = st.selectbox("Occupational family", ["All", *family_options], key="result_family")
                            family_rows = title_evidence if family == "All" else title_evidence[title_evidence.job_family.eq(family)]
                            specific_options = ["All", *sorted(family_rows.job_title.unique().tolist())]
                            if st.session_state.get("result_specific_title", "All") not in specific_options:
                                st.session_state["result_specific_title"] = "All"
                            specific = st.selectbox("Specific job title", specific_options, key="result_specific_title")
                        scoped = family_rows if specific == "All" else family_rows[family_rows.job_title.eq(specific)]
                        source_ids = scoped.source_id
                        selected_title_demand = skill_counts(skills[skills.source_id.isin(source_ids)], source_ids.nunique())
                        selected_title_label = specific if specific != "All" else (family if family != "All" else "all selected advertisements")
                        featured_result_chart(
                            "skill_label", "job_ads", "Top requested skills", source_ids.nunique(),
                            lambda: result_count_chart(selected_title_demand, "skill_label", "job_ads",
                                                       f"Top skills for {selected_title_label}",
                                                       order=order, limit=min(limit, 10)),
                            key="selected_title",
                        )
                        st.caption(f"Selected group: {selected_title_label} · {source_ids.nunique():,} advertisements. Percentages use these ads as the denominator.")
                        if 0 < source_ids.nunique() < 10:
                            st.caption("Small group; treat this ranking as descriptive for these advertisements, not a stable estimate for the occupation.")
                        if len(selected_title_demand) > min(limit, 10):
                            evidence_tables("View all skills for this selection", {"": selected_title_demand},
                                            key="result_all_title_skills", order=order, label="skill_label", value="job_ads",
                                            note="The searchable table includes every chartable skill for the selected group, not only the displayed bars.")
                    st.subheader("Geographical distribution", icon=":material/location_on:")
                    locations = geography["location_evidence"]
                    focused_locations = locations[locations.source_id.isin(source_ids)]
                    region_options = sorted(value for value in focused_locations.region.unique() if value)
                    if st.session_state.get("result_region", "All") not in ["All", *region_options]:
                        st.session_state["result_region"] = "All"
                    selected_region = st.selectbox("Region", ["All", *region_options], key="result_region")
                    if selected_region == "All":
                        st.session_state["result_city"] = "All"
                        location_rows = focused_locations[focused_locations.region.ne("")]
                        count_field = "region"
                        denominator_for_locations = source_ids.nunique()
                        location_title = "Advertisements by Philippine region"
                        area_rows = location_rows
                    else:
                        region_rows = focused_locations[focused_locations.region.eq(selected_region)]
                        city_options = sorted(value for value in region_rows.locality.unique() if value)
                        if st.session_state.get("result_city", "All") not in ["All", *city_options]:
                            st.session_state["result_city"] = "All"
                        selected_city = st.selectbox("City or municipality", ["All", *city_options], key="result_city")
                        locality_rows = region_rows[region_rows.locality.ne("")]
                        location_rows = locality_rows if selected_city == "All" else locality_rows[locality_rows.locality.eq(selected_city)]
                        count_field = "locality"
                        denominator_for_locations = region_rows.source_id.nunique()
                        location_title = f"Cities and municipalities in {selected_region}"
                        area_rows = region_rows if selected_city == "All" else region_rows[region_rows.locality.eq(selected_city)]
                    location_counts = location_rows.groupby(count_field).source_id.nunique().rename("job_ads").reset_index()
                    if denominator_for_locations:
                        location_counts["job_ads_pct"] = location_counts.job_ads / denominator_for_locations * 100
                    else:
                        location_counts["job_ads_pct"] = float("nan")
                    location_ids = area_rows.source_id
                    location_skill_counts = skill_counts(skills[skills.source_id.isin(location_ids)], location_ids.nunique())
                    with st.container(border=True, key="job_market_featured_geography"):
                        location_chart_col, skill_chart_col, insight_col = st.columns([1.05, 1.2, .9], vertical_alignment="center")
                        with location_chart_col:
                            location_figure = result_count_chart(location_counts, count_field, "job_ads", location_title,
                                                                 order=order, limit=limit)
                        with skill_chart_col:
                            skill_figure = result_count_chart(location_skill_counts, "skill_label", "job_ads",
                                                              "Skills in the selected geographical area", order=order, limit=min(limit, 10))
                        with insight_col:
                            locations_shown = _plotted_counts(location_figure, count_field, "job_ads")
                            location_summary = "No classifiable location is available in this selection."
                            if not locations_shown.empty:
                                maximum = int(locations_shown.job_ads.max())
                                leaders = locations_shown.loc[locations_shown.job_ads.eq(maximum), count_field].tolist()
                                location_summary = (f"{leaders[0]} is the only displayed location: {maximum:,} of {denominator_for_locations:,} ads."
                                                    if len(locations_shown) == 1 else
                                                    f"{leaders[0]} has the highest displayed location count: {maximum:,} of {denominator_for_locations:,} ads."
                                                    if len(leaders) == 1 else
                                                    f"{len(leaders):,} displayed locations tie at {maximum:,} of {denominator_for_locations:,} ads each.")
                            skill_shown = _plotted_counts(skill_figure, "skill_label", "job_ads").sort_values(
                                ["job_ads", "skill_label"], ascending=[False, True], kind="stable")
                            skill_top_rows = list(zip(skill_shown.skill_label.head(3), skill_shown.job_ads.head(3)))
                            result_insight("Location Insight", f"{location_summary} Skill counts describe this area.",
                                           skill_top_rows, "Top Displayed Skills")
                    missing_locations = int(focused_locations.loc[focused_locations.location_status.eq("not stated"), "source_id"].nunique())
                    unresolved_locations = int(focused_locations.loc[focused_locations.region.eq("") & focused_locations.location_status.ne("not stated"), "source_id"].nunique())
                    if selected_region == "All":
                        st.caption(f"{source_ids.nunique():,} advertisements form the regional comparison denominator; {location_ids.nunique():,} have a classifiable region.")
                    else:
                        st.caption(f"{denominator_for_locations:,} advertisements are associated with {selected_region}; exact city counts may not cover ads with region-only locations.")
                    st.caption("These are counts of collected advertisements, not population- or labor-force-adjusted employment rates.")
                    st.caption(f"Location not stated: {missing_locations:,} ads. Broad, remote or unresolved location: {unresolved_locations:,} ads.")
                    evidence_tables("View all regional or city counts", {"": location_counts.rename(columns={
                        count_field: "Region" if selected_region == "All" else "City or municipality", "job_ads": "Job advertisements",
                        "job_ads_pct": "Share of comparison group (%)"})}, key="result_all_location_counts")
                    evidence_tables("Location standardization evidence", {"": focused_locations}, key="result_location_standardization")
                    trend_jobs = jobs[jobs.source_id.isin(location_ids)]
                    if "posting_date_parsed" in trend_jobs:
                        dates = pd.to_datetime(trend_jobs.posting_date_parsed, errors="coerce").dropna()
                        monthly = dates.dt.to_period("M").astype(str).value_counts().sort_index().rename_axis("month").reset_index(name="postings")
                        if len(monthly) > 1:
                            coverage = px.bar(monthly, x="month", y="postings", title="Posting months represented in the dataset",
                                              labels={"month": "Posting month", "postings": "Job advertisements"},
                                              color_discrete_sequence=[st.get_option("theme.primaryColor")])
                            coverage.update_traces(texttemplate="%{y:,d}", textposition="outside", cliponaxis=False,
                                                   hovertemplate="<b>%{x}</b><br>Job advertisements: %{y:,d}<extra></extra>")
                            coverage.update_xaxes(type="category", categoryorder="array", categoryarray=monthly.month.tolist(),
                                                  title="Posting month", automargin=True)
                            coverage.update_yaxes(**count_axis(monthly.postings.max()), rangemode="tozero",
                                                  title="Job advertisements", showgrid=False, zeroline=False)
                            timeline_sorted = monthly.sort_values(["postings", "month"], ascending=[False, True], kind="stable")
                            peak = timeline_sorted.iloc[0]
                            peak_months = timeline_sorted.loc[timeline_sorted.postings.eq(peak.postings), "month"]
                            timeline_summary = (f"{peak.month} has the most dated postings ({int(peak.postings):,} ads)."
                                                if len(peak_months) == 1 else
                                                f"{len(peak_months):,} displayed months tie for the most dated postings ({int(peak.postings):,} ads each).")
                            timeline_rows = list(zip(timeline_sorted.month.head(3), timeline_sorted.postings.head(3)))
                            featured_visual_chart(
                                lambda: chart(coverage),
                                timeline_summary + " This describes dataset coverage, not market growth.",
                                timeline_rows, key="posting_timeline", insight_title="Timeline Insight",
                                list_title="Most represented months",
                            )
                        elif len(monthly) == 1:
                            result_single_metric("Posting months represented in the dataset", monthly.month.iloc[0],
                                                 monthly.postings.iloc[0], "Job advertisements",
                                                 "One month is present; this is coverage, not a time trend.",
                                                 key="result_single_posting_month")
                        if not dates.empty:
                            st.caption(f"Observation dates: {dates.min():%Y-%m-%d} to {dates.max():%Y-%m-%d}. {len(dates):,} ads have usable dates; {len(trend_jobs) - len(dates):,} do not. This shows collection coverage, not market growth.")
                        else:
                            st.caption(f"Posting dates are unavailable for all {len(trend_jobs):,} selected ads.")
                title_and_location_exploration()

            if section == "Qualifications":
                profile = (tables if "education_level_counts" in tables else _session_cached_value(
                    "_fow_market_profile_cache", revision, lambda: job_profile_tables(jobs), ttl=None, max_entries=1))
                coverage = profile["requirement_field_coverage"].set_index("source_field")
                with st.container(border=True, key="job_market_qualification_summary"):
                    st.subheader("What qualifications are stated?", icon=":material/school:")
                    for row in profile["requirement_field_coverage"].itertuples():
                        label = row.source_field.removesuffix("_requirement").capitalize()
                        st.write(f"{label}: stated in {row.stated_job_ads:,} of {row.job_ads:,} ads; not stated in {row.not_stated_job_ads:,}.")
                education = profile["education_level_counts"]
                missing_education = int(coverage.loc["education_requirement", "not_stated_job_ads"])
                stated_education = int(coverage.loc["education_requirement", "stated_job_ads"])
                education_coverage = pd.DataFrame({"education_requirement": ["stated", "not stated"],
                                                   "job_ads": [stated_education, missing_education]})
                education_coverage["job_ads_pct"] = education_coverage.job_ads / denominator * 100 if denominator else 0.0
                with st.container(border=True, key="job_market_education"):
                    education_column, insight_column = st.columns([2.7, 1.2], vertical_alignment="center")
                    with education_column:
                        if denominator:
                            plot(education_coverage, "education_requirement", "job_ads", "Education requirement coverage")
                        else:
                            st.info("No selected advertisements are available for education coverage.")
                    with insight_column:
                        summary = (f"Education requirements are stated in {stated_education:,} of {denominator:,} advertisements "
                                   f"({100 * stated_education / denominator if denominator else 0:.1f}%) and not stated in {missing_education:,} "
                                   f"({100 * missing_education / denominator if denominator else 0:.1f}%).")
                        result_insight("Education Insight", summary, [])
                    st.caption("Stated means the education field contains a requirement, including wording that still needs review. Not stated describes missing information; it does not mean education was not required.")
                    evidence_tables("Education standardization evidence", {
                        "Recognized qualification levels": education.drop(columns="level_order", errors="ignore"),
                        "Source education requirements": profile["education_level_evidence"]}, key="result_education_evidence")
                with st.container(border=True, key="job_market_experience"):
                    st.subheader("Experience requirements", icon=":material/work:")
                    experience_evidence = profile["experience_year_evidence"]
                    exact_year_rows = experience_evidence.loc[experience_evidence.parse_status.eq("Parsed stated years")].drop_duplicates("source_id")
                    exact_years = pd.to_numeric(exact_year_rows.min_years, errors="coerce").dropna()
                    if len(exact_years) >= 2:
                        exact_pct = 100 * len(exact_years) / denominator if denominator else 0
                        st.caption(f"Single-value numeric requirements: median {exact_years.median():g} years (observed range {exact_years.min():g}–{exact_years.max():g}), from {len(exact_years):,} of {denominator:,} selected ads ({exact_pct:.1f}%). Ranges and open-ended wording are excluded from these statistics.")
                    elif len(exact_years) == 1:
                        st.caption(f"One advertisement states exactly {exact_years.iloc[0]:g} years; a single observation is not summarized as a distribution. Ranges and open-ended wording remain separate.")
                    if not profile["experience_band_counts"].empty:
                        display(profile["experience_band_counts"].drop(columns="band_order", errors="ignore").rename(
                            columns={"experience_band": "Experience requirement", "job_ads": "Job advertisements", "job_ads_pct": "Share of selected ads (%)"}))
                    else:
                        st.html('<div class="fow-experience-empty"><span class="material-symbols-rounded" aria-hidden="true">assignment</span>'
                                '<h4>No numerical requirement falls unambiguously within a single experience band.</h4></div>')
                    st.caption("Bands include only numerical requirements contained entirely within one interval. Spanning, open-ended and descriptive requirements remain in the evidence table rather than being forced into a band.")
                    years = profile["experience_year_counts"]
                    if years.empty:
                        st.info("No unambiguous experience-year requirement is available in the source fields. Missing years are not treated as zero experience.")
                    else:
                        display(years.rename(columns={"requirement": "Experience requirement", "job_ads": "Job advertisements", "job_ads_pct": "Share of selected ads (%)"}))
                    st.caption("Year summaries use explicit experience fields only. Missing and ambiguous wording is excluded from the numeric summary and retained below. A stated number is not assumed to be an upper hiring limit.")
                    evidence_tables("Requirement fields and parsing evidence", {
                        "Education requirements": profile["education_requirement_counts"],
                        "Experience requirements": profile["experience_requirement_counts"],
                        "Year parsing": profile["experience_year_evidence"],
                        "Experience bands": profile["experience_band_evidence"]}, key="result_requirement_evidence")
                    evidence_tables("Potential requirements found in advertisement text", {"": profile["requirement_evidence"]},
                                    key="result_requirement_candidates", note="Text matches are candidates for researcher verification; they do not fill missing source fields or enter confirmed year counts.")

            if section == "PSF-AAI demand":
                st.subheader("How does observed demand relate to PSF-AAI?")
                st.caption("These counts use existing mapping evidence; they do not certify alignment or change researcher decisions. Several skill phrases may support the same competency, but an ad counts once per competency.")
                def prepare_psf_links():
                    columns = [key for key in ("source_id", "psf_competency", "psf_job_role", "status", "normalized_skill") if key in tables["psf_mapping"]]
                    mappings = chart_mapping_rows(tables["psf_mapping"][columns])
                    if mappings.empty:
                        return mappings
                    linked = mappings.loc[mappings.status.isin(["ALIGNED", "PARTIALLY ALIGNED"]) &
                                          mappings.psf_competency.fillna("").ne("")].copy()
                    for field in ("psf_competency", "psf_job_role"):
                        linked[field] = linked[field].map(normalize_text)
                    return linked
                all_linked = _session_cached_value("_fow_psf_links", revision, prepare_psf_links, ttl=None, max_entries=1)
                if not all_linked.empty:
                    reference = tables.get("psf_framework_order", tables.get("verified_psf_aai", pd.DataFrame()))
                    if "competency_name" not in reference:
                        reference = reference.rename(columns={"psf_competency": "competency_name"})
                    role_options = sorted(set(role for value in all_linked.psf_job_role for role in value.split("; ") if role))
                    with st.container(horizontal=True, gap="medium", key="result_psf_controls"):
                        if st.session_state.get("result_psf_role", "All") not in ["All", *role_options]:
                            st.session_state["result_psf_role"] = "All"
                        role = st.selectbox("PSF-AAI reference role", ["All", *role_options], key="result_psf_role")
                    linked = all_linked
                    if role != "All":
                        linked = all_linked[all_linked.psf_job_role.str.split("; ").map(lambda roles: role in roles)].copy()
                        linked["psf_job_role"] = role
                    role_denominator = linked.source_id.nunique()
                    with loading_content("job_market_psf_charts", "psf_charts", columns=role_options[:8], rows=st.session_state.get("result_chart_limit", 15), defer=True) as content:
                        def prepare_psf_charts():
                            available = {"psf_chart_demand", "psf_role_competency_demand"}.issubset(tables)
                            psf_views = (tables if role == "All" and available else
                                         psf_demand_tables(linked, jobs, reference,
                                                          denominator=role_denominator if role != "All" else denominator))
                            roles = linked.assign(psf_job_role=linked.psf_job_role.fillna("").str.split("; ")).explode("psf_job_role")
                            roles = roles[roles.psf_job_role.ne("")]
                            roles = roles.groupby("psf_job_role").source_id.nunique().rename("job_ads").reset_index()
                            roles["job_ads_pct"] = roles.job_ads / denominator * 100 if denominator else float("nan")
                            return psf_views["psf_chart_demand"], roles, psf_views["psf_role_competency_demand"]
                        cache_key = digest([VERSION, revision, role, denominator])
                        competence, roles, cells = _session_cached_value(
                            "_fow_psf_chart_cache", cache_key, prepare_psf_charts, ttl=None, max_entries=2)
                        with content():
                            if not competence.empty:
                                featured_result_chart(
                                    "psf_competency", "job_ads", "Most linked competency",
                                    role_denominator if role != "All" else denominator,
                                    lambda: result_count_chart(competence, "psf_competency", "job_ads",
                                                               "PSF-AAI competencies linked to employer demand",
                                                               order=order, limit=limit),
                                    key="psf_competencies",
                                )
                            st.caption("Counts describe distinct selected advertisements with existing ALIGNED or PARTIALLY ALIGNED researcher-reviewed links. Percentages use all selected ads, or the selected role's ads when a role filter is active. Role links can overlap.")
                            with st.container(border=True, key="job_market_featured_psf_roles"):
                                role_chart_column, distribution_column = st.columns([3.2, 1], vertical_alignment="center")
                                with role_chart_column:
                                    role_figure = result_count_chart(roles, "psf_job_role", "job_ads", "Related PSF-AAI reference roles", order=order, limit=limit)
                                with distribution_column:
                                    result_role_distribution(_plotted_counts(role_figure, "psf_job_role", "job_ads"))
                            if not cells.empty:
                                with st.container(border=True, key="job_market_featured_psf_heatmap"):
                                    _competency_heatmap_view(cells, roles, competence, limit)
                            else:
                                st.info("No role-level PSF-AAI competency evidence is available for this selection.")
                            st.html('<span data-fow-psf-ready="true" hidden></span>')
                else:
                    st.info("No PSF-AAI mapping evidence is available for this selection.")
    loaded["sections"].add(section_key)
    evidence_tables("Selected job records", {"": lambda: tables["normalized_jobs"] if "normalized_jobs" in tables else analysis_job_values(jobs)},
                    key="job_market_source_records", note="Lowercase analysis values. Source IDs and case-sensitive links are preserved; original evidence is available in Reports.")


def _unmapped_results(tables, meta):
    st.caption("A missing PSF-AAI match does not establish a framework gap. Recurring phrases remain candidates for researcher review.")
    order, limit = result_chart_options()
    jobs, skills = tables["cleaned_jobs"], tables["extracted_job_skills"]
    views = tables if "chart_skill_occurrences" in tables else skill_chart_tables(skills, jobs)
    counts = unmapped_chart_counts(views["chart_skill_occurrences"], tables["alignment_results"])
    threshold = int(meta["settings"]["emerging_min_jobs"])
    recurring = counts.loc[counts.job_ads.ge(threshold)].copy()
    denominator = jobs.source_id.nunique() if "source_id" in jobs else 0
    with st.container(horizontal=True, key="unmapped_summary", gap="medium"):
        for key, label, value, icon in (("labels", "Unmapped skill labels", len(counts), "layers"),
                                       ("recurring", "Recurring labels for review", len(recurring), "bar_chart")):
            with st.container(key=f"unmapped_metric_{key}", width="stretch"):
                st.metric(label, f"{value:,}", icon=f":material/{icon}:",
                          help="Distinct chartable labels across the active study dataset, before the chart display limit.")
        with st.container(key="unmapped_review_status", width="stretch"):
            status = "Researcher review required" if len(counts) else "No unmapped labels to review"
            st.html('<div class="fow-unmapped-status"><span class="material-symbols-rounded" aria-hidden="true">manage_search</span>'
                    f'<div><strong>{escape(status)}</strong><p>Unmapped does not establish an emerging skill.</p></div></div>')
    raw = tables["unmapped_skills"]
    for key, title, shown, insight_heading in (
        ("unmapped_evidence", "Unmapped skill evidence", counts, "Most frequent unmapped skill"),
        ("unmapped_recurring", "Recurring unmapped phrases for review", recurring, "Recurring unmapped skill"),
    ):
        with st.container(border=True, key=f"{key}_panel"):
            if shown.empty:
                st.subheader(title, icon=":material/bar_chart:" if key == "unmapped_evidence" else ":material/manage_search:")
                st.info("No chartable unmapped skills in the active dataset." if key == "unmapped_evidence" else
                        f"No chartable unmapped labels meet the {threshold}-advertisement review threshold.")
            else:
                featured_result_chart("skill_label", "job_ads", insight_heading, denominator,
                    lambda shown=shown, title=title: result_count_chart(shown, "skill_label", "job_ads", title,
                                                                     order=order, limit=limit), key=key)
            evidence_tables("Unmapped evidence (detailed)" if key == "unmapped_evidence" else "Recurring phrases (detailed)",
                            {"": lambda key=key, shown=shown: raw if key == "unmapped_evidence" or raw.empty else
                             raw.loc[raw.normalized_skill.map(chart_skill_key).isin(shown.normalized_skill)].copy()},
                            icon=":material/table_view:", key=f"{key}_details", order=order,
                            label="employer_skill", value="employer_demand_count")
    st.caption("Wording variants share one chart label; each advertisement counts once per label. Detailed evidence retains original unmapped rows for audit, including groups excluded from the charts. Charts omit mapped groups; full evidence remains exportable.")
    st.info(f"Review candidates require at least {threshold} distinct advertisements and NOT MAPPED status. Rejected or unreviewed fragments are not counted as employer skills. Recurrence alone does not establish emergence.", icon=":material/info:")


def report_deliverables(tables, meta):
    with st.container(key="reports_deliverables_heading", gap="xsmall"):
        st.html('<header class="fow-deliverables-heading">'
                '<span class="material-symbols-rounded" aria-hidden="true">description</span>'
                '<h3>Research deliverables</h3>'
                '<p>Downloads cover the active study dataset. Keep the metadata with the exported evidence.</p>'
                '</header>')
    cards = [
        ("excel", "Research Results (Excel)", "Download the full research results in spreadsheet format (.xlsx).", "table_view",
         "Download research_results.xlsx", lambda: export_excel(tables, meta), "research_results.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        ("report", "Written Research Report", "Download the generated research report draft for review (.md).", "description",
         "Download report (.md)", lambda: export_research_report(tables, meta), "philippine_job_ads_psf_aai_report.md", "text/markdown"),
        ("summary", "HTML Research Summary", "Download the research summary in HTML format.", "code",
         "Download summary (HTML)", lambda: export_html(tables, meta), "research_summary.html", "text/html"),
        ("metadata", "Analysis Metadata", "Download the dataset scope, counts, settings and analysis metadata.", "database",
         "Download metadata", lambda: json.dumps(meta, indent=2, default=str), "analysis_metadata.json", "application/json"),
    ]
    with st.container(horizontal=True, key="reports_deliverables_grid", gap="medium", vertical_alignment="top"):
        for key, title, description, icon, label, content, filename, mime in cards:
            with st.container(border=True, key=f"report_deliverable_{key}", width="stretch", gap="small"):
                st.html(f'<div class="fow-deliverable-icon"><span class="material-symbols-rounded" aria-hidden="true">{icon}</span></div>')
                st.markdown(f"#### {title}")
                st.write(description)
                st.download_button(label, content, filename, mime, key=f"report_download_{key}",
                                   type="primary" if key == "excel" else "secondary", icon=":material/download:",
                                   width="stretch", on_click="ignore")
        with st.container(border=True, key="report_deliverable_snapshot", width="stretch", gap="small"):
            st.html('<div class="fow-deliverable-icon"><span class="material-symbols-rounded" aria-hidden="true">photo_camera</span></div>')
            st.markdown("#### Report Snapshot")
            st.write("Save these research files together on this host.")
            save_snapshot = action_button("Save snapshot locally", key="save_report_snapshot", icon=":material/download:", width="stretch")
    if save_snapshot:
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


def research_page(page):
    descriptions = {
        "Job Market Analysis": "Explore skills and career requirements in the selected Philippine job advertisements.",
        "PSF Mapping": "Review each skill in its advertisement context and justify its framework links.",
        "Employer–PSF Alignment": "Compare employer phrases with the reviewed framework reference.",
        "Unmapped / Emerging Skills": "Investigate recurring demand that needs further framework review.",
        "Reports": "Export the selected evidence, research tables, and analysis metadata.",
    }
    page_intro(page, descriptions.get(page, ""))
    if page == "Job Market Analysis":
        analysis_workflow()
    loading_kind = {"Job Market Analysis": "market", "Employer–PSF Alignment": "alignment",
                    "PSF Mapping": "mapping", "Unmapped / Emerging Skills": "unmapped", "Reports": "reports"}[page]
    loading_cards = 3 if page == "Employer–PSF Alignment" else 4 if page == "Job Market Analysis" else None
    loading_view = st.session_state.get("result_section", "Skills") if page == "Job Market Analysis" else "selected" if st.session_state.get("psf_review_occurrence_choice") else None
    with loading_content("research_results_content", loading_kind, cards=loading_cards, view=loading_view,
                         rows=st.session_state.get("result_chart_limit", 15)) as content:
        if not current_analysis():
            return
        tables, meta = filtered_bundle()
        jobs, skills = tables["cleaned_jobs"], tables["extracted_job_skills"]
        demand, alignment = tables["employer_skill_demand"], tables["alignment_results"]
        active_reference = storage.read_frame("cleaned_psf_aai") if page in {"PSF Mapping", "Employer–PSF Alignment"} else None
        if page == "Reports":
            meta = dict(meta, chart_view_settings={
                "order": st.session_state.get("result_chart_order", "Highest demand"),
                "job_title_view": st.session_state.get("result_title_view", "Most common job titles"),
                "items_per_chart": st.session_state.get("result_chart_limit", 15),
                "focused_job_title": st.session_state.get("result_focus_job_title"),
                "focused_location": st.session_state.get("result_focus_location"),
                "note": "Display settings do not limit the complete exported tables or selected-job denominator.",
            })
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
            tables.update(load_report_tables())
        with content():
            if page == "Job Market Analysis":
                _job_market_results(tables, meta, revision=st.session_state.get("_fow_loaded_bundle_revision"))
            elif page == "PSF Mapping":
                with st.container(border=True, key="psf_mapping_review_panel"):
                    psf_mapping_review(skills, jobs, active_reference,
                                       tables["psf_mapping"], tables["psf_mapping_reviews"])
                with st.container(border=True, key="psf_mapping_demand_panel"):
                    with st.container(key="psf_mapping_demand_heading", gap="xsmall"):
                        section_heading("Competency demand", "bar_chart",
                                        "Distinct advertisements and distinct skill phrases per competency. Repeated skills and multiple links do not count an advertisement twice for the same competency.")
                    order, limit = result_chart_options()
                    competence = tables["psf_competency_demand"]
                    if not competence.empty:
                        plot_competence = tables.get("psf_chart_demand")
                        if plot_competence is None:
                            plot_competence = psf_demand_tables(tables["psf_mapping"], jobs, active_reference)["psf_chart_demand"]
                        with st.container(horizontal=True, key="psf_mapping_chart_and_insight", gap="medium", vertical_alignment="center"):
                            with st.container(key="psf_mapping_demand_chart", width="stretch"):
                                plotted = result_count_chart(plot_competence, "psf_competency", "job_ads", "PSF-AAI competency demand", order=order, limit=limit, highlight_max=True)
                            with st.container(key="psf_mapping_demand_insight", width="stretch"):
                                psf_competency_demand_insight(plotted, plot_competence.psf_competency.nunique(), order=order)
                    display(ordered_result_table(competence, "psf_competency", order, "job_ad_count"))
                evidence_tables("Occurrence-level mapping evidence", {"": tables["psf_mapping"]}, icon=":material/layers:",
                                key="psf_mapping_evidence", order=order, label="psf_competency")
            elif page == "Employer–PSF Alignment":
                st.caption("Thresholds are researcher-configurable heuristics, not official PSF standards. Default: ≥0.80 aligned; ≥0.60 partially aligned; lower scores not mapped. Missing reference: unclassified.")
                has_range = ("range_of_application" in active_reference and
                             active_reference.range_of_application.fillna("").astype(str).str.strip().ne("").any())
                st.caption("Results show the PSF competency description and verified Range of Application as supporting reference evidence; these fields help researchers inspect the comparison and do not establish equivalence." if has_range else "Results show the PSF competency description as supporting evidence. The active TESDA PDF has no separate Range of Application field, so no range text is available to compare.")
                rates = meta["rates_before_status_display_filter"]
                with st.container(horizontal=True, gap="medium", key="alignment_metrics"):
                    for field, icon in (("alignment_rate", "bar_chart"), ("partially_aligned_rate", "layers"), ("unmapped_rate", "warning")):
                        if rates.get(field) is not None:
                            with st.container(key=f"alignment_metric_{field}"):
                                st.metric(field.replace("_", " ").title(), f"{rates[field]:.1f}%", icon=f":material/{icon}:")
                order, limit = result_chart_options()
                with st.container(border=True, key="employer_psf_status_panel"):
                    status_chart = distribution(alignment.assign(status=alignment.status.map(normalize_text)), "status",
                                                "Status of Phrase–Competency Evidence Groups", limit=limit, order=order)
                    status_chart.update_traces(texttemplate="%{x:,d}", textposition="outside", cliponaxis=False,
                                               textfont=dict(color="#171923", size=12))
                    maximum = max((max(trace.x) for trace in status_chart.data if len(trace.x)), default=0)
                    status_chart.update_xaxes(range=[0, max(1, maximum * 1.05)])
                    with st.container(horizontal=True, key="alignment_chart_and_insight", gap="medium", vertical_alignment="center"):
                        with st.container(key="alignment_status_chart", width="stretch"):
                            chart(status_chart)
                        with st.container(key="alignment_status_insight", width="stretch"):
                            alignment_status_insight(status_chart)
                evidence_tables("Phrase-level results and PSF-AAI basis", {
                    "Phrase–competency evidence groups": alignment, "Occurrence-level employer demand": demand},
                    icon=":material/layers:", key="employer_psf_evidence", order=order,
                    label="employer_skill", value="employer_demand_count")
                with st.container(key="employer_psf_denominators"):
                    st.info(meta["denominators"], icon=":material/info:")
            elif page == "Unmapped / Emerging Skills":
                _unmapped_results(tables, meta)
            elif page == "Reports":
                downloads = st.expander(f"Individual research tables ({len(tables)})", key="individual_exports", icon=":material/database:", on_change="rerun")
                if downloads.open:
                    with downloads:
                        for name, frame in tables.items():
                            st.download_button(name + ".csv", lambda frame=frame: export_csv(frame), name + ".csv", "text/csv", key="download_"+name, on_click="ignore")
                report_deliverables(tables, meta)


def feedback():
    page_intro("Feedback", "Record corrections and usability feedback while preserving the original predictions.")
    with loading_content("feedback_summary", "metrics", cards=4) as summary_content:
        frame = pd.DataFrame()
        with content_section("Add correction", "edit_square", "feedback_correction"):
            with st.container(horizontal=True, key="feedback_identity", vertical_alignment="bottom", wrap=True):
                reviewer = st.text_input("Reviewer ID", key="feedback_reviewer", width="stretch")
                source = st.selectbox("Correction target", ["extraction", "alignment"], width="stretch")
            with loading_content("feedback_records", "table", columns=EXTRACTION_COLUMNS if source == "extraction" else ALIGNMENT_COLUMNS) as content:
                if current_analysis():
                    tables, _ = filtered_bundle()
                    frame = tables["all_candidates"] if source == "extraction" else tables["alignment_results"]
                    key = "extraction_id" if source == "extraction" else "alignment_id"
                    with content():
                        if not frame.empty:
                            display(frame)
                            record_column, field_column = st.columns(2, gap="medium")
                            with record_column:
                                row_id = st.selectbox("Record ID", frame[key].tolist())
                            row = frame.loc[frame[key].eq(row_id)].iloc[0]
                            if source == "extraction":
                                st.caption("Review one or several competency links for this occurrence on PSF Mapping.")
                            fields = ["normalized_phrase", "competency_category", "accepted"] if source == "extraction" else ["status"]
                            with field_column:
                                field = st.selectbox("Field to correct", fields)
                            original_column, corrected_column = st.columns(2, gap="medium")
                            with original_column:
                                st.text_input("Original/current value", str(row[field]), disabled=True, key=f"feedback_current_{source}_{row_id}_{field}")
                            with corrected_column:
                                if field == "status":
                                    corrected = st.selectbox("Corrected value", STATUSES)
                                elif field == "accepted":
                                    corrected = st.selectbox("Corrected value", ["True", "False"])
                                else:
                                    corrected = st.text_input("Corrected value", str(row[field]))
                            comment = st.text_area("Reason / comment")
                            if action_button("Save correction", key=f"save_correction_{source}_{row_id}", type="primary", icon=":material/save:"):
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
        with loading_content("feedback_correction_history", "table", columns=["table", "row_id", "field", "original_prediction", "corrected_prediction", "reviewer", "comment", "timestamp"]) as content:
            correction_rows = load_data_with_skeleton(corrections, height=140)
            with content():
                with content_section("Recent corrections", "history", "feedback_history"):
                    if correction_rows.empty:
                        st.caption("No saved corrections yet.")
                    else:
                        display(correction_rows)
        with summary_content():
            content_metrics([
                ("Available records", f"{len(frame):,}", "description"),
                ("Saved corrections", f"{len(correction_rows):,}", "edit_square"),
                ("Correction target", source.title(), "layers"),
                ("Reviewer", reviewer.strip() or "Not set", "person"),
            ], "feedback")
        with content_section("Usability evaluation", "bar_chart", "feedback_usability"):
            with loading_content("feedback_usability_form", "form", controls=["select", *["slider" for _ in USABILITY_ITEMS], "textarea", "button"], view="usability") as content:
                cfg = storage.settings()
                with content():
                    with st.form("usability", border=False):
                        left, right = st.columns([1, 2.5], gap="large")
                        with left:
                            respondent_type = st.selectbox("Respondent type", ["industry professionals", "employers", "researchers", "job seekers"])
                            content_note("Evaluation scale", f"Rate each aspect from {cfg['likert_min']} (low) to {cfg['likert_max']} (high).", icon="info")
                        with right:
                            responses = {name: st.slider(name.replace("_", " ").title(), cfg["likert_min"], cfg["likert_max"], cfg["likert_min"]) for name in USABILITY_ITEMS}
                        comment = st.text_area("Evaluation comment")
                        if action_form_submit_button("Save usability evaluation", type="primary", icon=":material/save:"):
                            if not reviewer.strip():
                                raise ValueError("Enter a reviewer ID above the form.")
                            record = responses | {"reviewer": reviewer, "respondent_type": respondent_type, "comment": comment, "timestamp": timestamp(), "scale_min": cfg["likert_min"], "scale_max": cfg["likert_max"]}
                            data = pd.concat([storage.read_frame("usability"), pd.DataFrame([record])], ignore_index=True)
                            storage.save_frame("usability", data)
                            st.success("Evaluation recorded.")
        with loading_content("feedback_usability_results", "table", columns=["ease_of_use", "clarity", "navigation", "usefulness", "visualization_quality", "overall_satisfaction", "reviewer", "respondent_type", "comment", "timestamp", "scale_min", "scale_max"]) as content:
            usability = load_data_with_skeleton(lambda: storage.read_frame("usability"), height=120)
            with content():
                if not usability.empty:
                    display(usability)
                    st.download_button("Download usability evaluations", export_csv(usability), "usability.csv")
        with loading_content("feedback_stakeholders", "table", columns=FIELDS["stakeholder"]) as content:
            stakeholder = load_data_with_skeleton(lambda: storage.read_frame("cleaned_stakeholder"), height=120)
            with content():
                if not stakeholder.empty:
                    st.subheader("Stakeholder evaluations")
                    display(stakeholder)
                    for field in ("importance_rating", "usability_rating"):
                        numeric = pd.to_numeric(stakeholder[field], errors="coerce")
                        st.write(f"{field}: {numeric.count()} numeric responses; mean {numeric.mean():.2f}" if numeric.count() else f"{field}: no numeric responses")

def methodology():
    page_intro("Methodology", "Definitions, analytical decisions, and limits of the study.")
    analysis_workflow()
    with loading_content("methodology_document", "document", rows=8) as content:
        document = (Path(__file__).resolve().parents[1] / "METHODOLOGY.md").read_text(encoding="utf-8")
        with content():
            st.download_button("Download methodology", document, "methodology.md", "text/markdown",
                               key="download_methodology", icon=":material/download:", on_click="ignore")
            sections = document.split("\n## ")
            with st.container(key="methodology_sections"):
                introduction = sections[0].split("\n", 1)[1] if sections[0].startswith("# ") else sections[0]
                st.markdown(introduction)
                for index, section in enumerate(sections[1:]):
                    title, _, body = section.partition("\n")
                    with st.expander(title, expanded=index == 0, icon=":material/menu_book:"):
                        st.markdown(body)


def research_readiness():
    page_intro("Research readiness", "A practical audit of the current data and model workflow. Passing app checks does not by itself make results ready for a thesis or publication.")
    with loading_content("readiness_review_audit", "readiness", cards=4) as content:
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
        with content():
            st.warning("Not yet ready for defensible research findings" if audit["findings"] else "No software risks detected; researcher sign-off is still required", icon=":material/info:")
            st.caption("This page separates mechanical checks from decisions that require the research team. It never certifies labels, sampling, or model validity automatically.")
            sources = labels.get("source_id", pd.Series(dtype=str)).fillna("").astype(str).str.strip()
            content_metrics([
                ("Saved labels", f"{len(labels):,}", "layers"),
                ("Usable distinct phrases", f"{validation.get('rows_used', 0):,}", "sell"),
                ("Distinct job-ad source IDs", f"{sources[sources.ne('')].nunique():,}", "database"),
                ("Reviewer ID spellings", f"{len(audit['reviewer_ids']):,}", "person"),
            ], "readiness")
            with loading_content("readiness_job_audit", "study_metrics", cards=4) as content:
                jobs = load_data_with_skeleton(lambda: storage.read_frame("cleaned_jobs"), height=160)
                with content():
                    if jobs.empty:
                        with content_section("Active study dataset", "work", "readiness_study"):
                            st.warning("No cleaned study dataset is active. Upload, review, and save the job ads before extracting or reporting findings.")
                    else:
                        job_sources = jobs.get("source_id", pd.Series(dtype=str)).fillna("").astype(str).str.strip()
                        job_titles = jobs.get("job_title", pd.Series(dtype=str)).fillna("").astype(str).str.strip()
                        posting_dates = pd.to_datetime(jobs.get("posting_date", pd.Series(dtype=str)), errors="coerce").dropna()
                        scope_reviewed = bool(storage.read_json("cleaning_jobs", {}).get("philippine_aai_scope_reviewed", False))
                        with st.container(horizontal=True, key="readiness_study_metrics", vertical_alignment="center", gap="medium", wrap=True):
                            with st.container(width=220, key="readiness_study_title"):
                                st.subheader("Active study dataset", icon=":material/work:")
                            for index, (label, value) in enumerate([
                                ("Cleaned job ads", f"{len(jobs):,}"),
                                ("Distinct ad IDs", f"{job_sources[job_sources.ne('')].nunique():,}"),
                                ("Job titles", f"{job_titles[job_titles.ne('')].nunique():,}"),
                                ("Scope review recorded", "Yes" if scope_reviewed else "No"),
                            ]):
                                suffix = ("_yes" if scope_reviewed else "_no") if index == 3 else ""
                                with st.container(width="stretch", key=f"readiness_study_metric_{index}{suffix}"):
                                    st.metric(label, value)
                        if not posting_dates.empty:
                            st.caption(f"Posting dates in the active file: {posting_dates.min().date()} to {posting_dates.max().date()}. A saved scope check records a researcher action; it does not independently verify every ad.")
                        else:
                            st.caption("Posting dates are missing or could not be parsed. Record the dataset collection window in the study notes.")
                        label_sources = set(labels.get("source_id", pd.Series(dtype=str)).fillna("").astype(str).str.strip())
                        active_sources = set(job_sources[job_sources.ne("")])
                        shared_sources = label_sources & active_sources
                        if labels.empty:
                            st.info("No researcher-reviewed training labels are saved yet. Complete manual review before training a classifier.")
                        elif not shared_sources:
                            st.warning("The labeled phrases come from different source IDs than the active study dataset. Review classifier predictions against each advertisement before using them in findings.")
                        else:
                            st.caption(f"{len(shared_sources)} source ID(s) occur in both the labeled phrase data and the active analysis sample.")
                        extraction_meta = storage.read_json("extraction_metadata", {})
                        if not extraction_meta or not extraction_freshness(extraction_meta)[1]:
                            st.warning("The saved extraction is out of date. Run Competency Extraction again after finalizing the job sample, reviewed PSF-AAI reference, and selected model before using reports.")
                        elif not extraction_meta.get("model_available"):
                            st.info("The current extraction was created without the selected classifier. Rerun extraction if you intend to use classifier categories.")
                        else:
                            st.success("The saved extraction matches the current jobs, taxonomy, labels, settings, and model.")
                    with content_section("Where the labels came from", "source", "readiness_sources"):
                        st.caption("Counts describe saved annotation rows and distinct phrases within each posting. Several phrases from one posting still represent one job ad, not independent observations.")
                        display(profile["sources"])
                    class_distribution = validation.get("class_distribution", {})
                    with st.container(horizontal=True, key="readiness_label_profiles", gap="medium", wrap=True):
                        with st.container(width="stretch"), content_section("Reviewer IDs recorded", "person", "readiness_reviewers"):
                            st.caption("IDs are shown exactly as saved. Confirm whether spelling variants belong to the same person before reporting reviewer counts.")
                            display(profile["reviewers"])
                        with st.container(width="stretch"), content_section("Categories included in model training", "layers", "readiness_categories"):
                            st.caption("IRRELEVANT rows and duplicate phrases are excluded. Model scores cannot make up for narrow source coverage or inconsistent labels.")
                            if class_distribution:
                                classes = pd.DataFrame([{"category": name, "distinct usable phrases": count}
                                                        for name, count in class_distribution.items()])
                                classes["share of usable phrases"] = classes["distinct usable phrases"] / max(1, int(validation.get("rows_used", 0)))
                                classes["share of usable phrases"] = classes["share of usable phrases"].map(lambda value: f"{value:.1%}")
                                display(classes.sort_values("distinct usable phrases", ascending=False, ignore_index=True))
                            else:
                                st.info("No usable category counts are available. Review and save labels before model training.")
                    with content_section("What needs attention", "warning", "readiness_attention"):
                        findings = []
                        for item in audit["findings"]:
                            icon = "error_outline" if item.get("status") == "blocking" else "manage_search"
                            findings.append('<li><span class="material-symbols-rounded" aria-hidden="true">' + icon + '</span><div><strong>'
                                            + escape(item["title"]) + '</strong><p>' + escape(item["detail"]) + '</p></div></li>')
                        if findings:
                            st.html('<ul class="fow-readiness-findings">' + ''.join(findings) + '</ul>')
                        else:
                            st.caption("No software risks detected; researcher sign-off is still required.")
                    if not disagreements.empty:
                        history_details = st.expander("Earlier category disagreements to review", icon=":material/history:", key="readiness_disagreements", on_change="rerun")
                        if history_details.open:
                            with history_details:
                                st.caption("These are historical saved decisions, not current training rows. Use the source evidence and your labeling protocol to decide whether follow-up is needed.")
                                display(disagreements)
                    checks = st.expander("Dataset and model checks", icon=":material/fact_check:", key="readiness_diagnostics", on_change="rerun")
                    if checks.open:
                        with checks:
                            if validation:
                                st.json(validation)
                            if metadata:
                                st.json({key: metadata.get(key) for key in ("training_timestamp", "training_file", "rows_available", "rows_used", "number_of_classes", "selected_model", "split")})
                            else:
                                st.info("No saved classifier metadata is available.")
                    with content_section("Recommended next actions", "checklist", "readiness_actions"):
                        st.markdown("1. Confirm every ad meets the written Philippine AI/analytics inclusion rules; remove out-of-scope ads with a saved audit trail.\n2. Label phrases from more distinct job ads; the app's 20-source warning threshold is only a workflow flag, not a statistically justified sample-size target. More phrases from the same ads do not replace independent sources.\n3. Reconcile reviewer IDs with the actual reviewers, agree on category definitions, double-code a planned subset, and document disagreement resolution.\n4. Rerun extraction after the final study dataset, framework, and model are selected; manually verify phrases and PSF-AAI mappings against source evidence.\n5. Train only for an explicit classifier purpose and only when whole-ad holdout evaluation is possible. Keep its metrics exploratory until evaluated on untouched job-ad sources.\n6. Report job-ad counts and percentages using the number of eligible, reviewed ads as the denominator; archive source URLs, collection dates, inclusion rules, and the dataset hash.")
                        if path:
                            st.caption(f"Audited training file: `{project_relative_path(path)}`")

def settings_page():
    page_intro("Settings", "Configure the research workspace and documented analysis parameters.")
    with loading_content("settings_workspace_status", "workspace_status", view="shared" if supabase_store.configured() else "local") as content:
        local_jobs_path = Path(ROOT) / "data/processed/cleaned_jobs.csv"
        needs_shared_copy = supabase_store.configured() and local_jobs_path.is_file() and storage.read_frame("cleaned_jobs").empty
        with content():
            connection_status = st.empty()
            maintenance = st.container(horizontal=True, key="settings_maintenance", gap="medium", wrap=True)
            if supabase_store.configured():
                connection_status.success("Supabase is connected. Saved tables and settings are shared with signed-in teammates; local CSVs remain as backups.")
                with maintenance, content_section("Shared team workspace", "database", "settings_shared"):
                    local_jobs_path = Path(ROOT) / "data/processed/cleaned_jobs.csv"
                    if needs_shared_copy:
                        st.warning("This computer has a cleaned job dataset, but the shared workspace does not yet. An admin can copy it below; teammates will then see it after refreshing.")
                    st.caption("To copy this computer's existing processed tables into empty shared slots, use the one-time import below. Existing shared rows are preserved.")
                    if action_button("Copy local workspace to shared database", type="secondary"):
                        with st.spinner("Copying local processed tables and annotations to Supabase…"):
                            seeded, skipped = storage.seed_shared_workspace()
                        st.success(f"Copied {len(seeded)} tables: {', '.join(seeded) if seeded else 'none needed'}.")
                        if skipped:
                            st.info(f"Kept {len(skipped)} existing shared tables unchanged: {', '.join(skipped)}.")
            else:
                connection_status.info("Supabase is not configured. This app is using local files on this computer.")
                with maintenance, content_section("Shared team workspace", "database", "settings_shared"):
                    st.caption("For a shared site, configure SUPABASE_URL and SUPABASE_PUBLISHABLE_KEY in Streamlit secrets, then run the schema in supabase_schema.sql.")
    with maintenance, content_section("Generated extraction results", "folder_delete", "settings_cleanup"):
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
    controls = [control for _, _, fields in SETTINGS_SECTIONS
                for control in ["heading", *(field[2] for field in fields)]] + ["button"]
    with loading_content("settings_form_content", "settings", controls=controls, field_columns=2) as content:
        cfg = storage.settings()
        with content():
            with st.form("settings_form", border=False):
                values = {}
                for title, icon, fields in SETTINGS_SECTIONS:
                    with content_section(title, icon, f"settings_{fields[0][0]}"):
                        with st.container(horizontal=True, key=f"settings_fields_{fields[0][0]}", gap="medium"):
                            if title == "Usability evaluation":
                                content_note("Likert scale range", "Set the minimum and maximum values used for usability ratings.", icon="info")
                            for key, label, control, minimum, maximum, step in fields:
                                with st.container(key=f"setting_input_{key}", width="stretch"):
                                    if key == "semantic_model":
                                        content_note("About matching thresholds", "These configurable similarity cutoffs are research heuristics. Higher cutoffs require a closer match; they are not official PSF-AAI standards or calibrated probabilities.", icon="info")
                                    if control == "slider":
                                        values[key] = st.slider(label, minimum, maximum, float(cfg[key]), step)
                                    elif control == "number":
                                        values[key] = st.number_input(label, minimum, maximum, int(cfg[key]), step)
                                    elif control == "textarea":
                                        values[key] = st.text_area(label, "\n".join(cfg[key]))
                                    else:
                                        values[key] = st.text_input(label, cfg[key])
                if action_form_submit_button("Save settings", type="primary"):
                    if values["partial_threshold"] >= values["aligned_threshold"] or values["likert_min"] >= values["likert_max"]:
                        raise ValueError("Partial threshold must be below aligned, and Likert minimum below maximum.")
                    path = values["semantic_model"].strip()
                    if path:
                        from .psf_mapping import semantic_model
                        semantic_model(path)
                    values["semantic_model"] = path
                    values["stopwords"] = [word.strip().casefold() for word in values["stopwords"].splitlines() if word.strip()]
                    storage.save_json("settings", values)
                    st.success("Settings saved. Re-run extraction to refresh the analysis snapshot.")
            st.caption("Extraction semantic mode uses a model already present in the configured local directory. Manual-review drafts use the separate pretrained model shown on that page.")

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
    if st.session_state.get("_fow_current_page") != page:
        st.session_state["_fow_loading_ready"] = {}
    st.session_state["_fow_first_page_render"] = st.session_state.get("_fow_rendered_page") != page
    st.session_state["_fow_current_page"] = page
    st.sidebar.caption(f"Research workspace · v{VERSION}")
    from .auth_ui import render_account_menu
    with st.container(horizontal=True, vertical_alignment="center", key="workspace_toolbar"):
        with st.container(width="stretch"):
            workspace_breadcrumb(page)
        render_account_menu()
    try:
        if supabase_store.configured() and page in {"Job Data Upload", "Data Quality", "Competency Extraction", "Settings", "Feedback", "PSF Framework"} and not supabase_store.is_admin():
            st.info("This step is managed by the project administrator. Open Review and label phrases to contribute your annotations.")
            return
        content_key = {
            "Home": "overview", "Job Data Upload": "upload", "Data Quality": "quality",
            "Competency Extraction": "extraction", "Manual Labeling": "review", "ML Training": "training",
            "Model Evaluation": "evaluation", "Feedback": "feedback", "Methodology": "methodology",
            "Research Readiness": "readiness", "Settings": "settings",
        }.get(page)
        if content_key:
            with st.container(key=f"workspace_page_{content_key}"):
                PAGES[page]()
        else:
            PAGES[page]()
        st.session_state["_fow_rendered_page"] = page
    except (ValueError, OSError, KeyError, TypeError, supabase_store.SupabaseError) as exc:
        st.error(str(exc))
        st.caption("Review the input or configuration and try again. Raw uploads have not been changed.")
    finally:
        finish_action_run()
