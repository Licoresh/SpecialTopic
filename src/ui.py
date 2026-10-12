from io import BytesIO
from pathlib import Path
from copy import deepcopy
import json
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
from .model_training import train_and_save_models, read_model_metadata, training_data_changed
from .training_sources import (resolve_training_file, inspect_training_folder, training_candidates,
                               training_taxonomy, select_training_file)
from .labeling import annotation_conflicts, save_annotations, save_correction, corrections
from .workflow import run_extraction, analysis_bundle, input_signature, current_extractions
from .analytics import demand_matrix
from .job_profile import job_profile_tables
from .alignment import STATUSES
from .visualization import bar, distribution, heatmap
from .reporting import export_csv, export_excel, export_html, export_research_report
from .utils import timestamp, frame_hash, digest
from .readiness import (assess_research_readiness, source_overlap,
                        historical_category_disagreements, research_data_profile)
from . import supabase_store
from .action_guard import action_button, action_form_submit_button, finish_action_run

DESIGN_CSS = """
<style>
:root {
  --fow-ink: #17313b;
  --fow-muted: #60747c;
  --fow-accent: #137c73;
  --fow-border: #dce6e8;
  --fow-surface: #ffffff;
}
[data-testid="stAppViewContainer"] { background: #f5f8f9; }
[data-testid="stHeader"] { background: transparent; }
.block-container { max-width: 1440px; padding-top: 2.15rem; padding-bottom: 3.5rem; }
.fow-eyebrow { color: var(--fow-accent); font-size: .76rem; font-weight: 750; letter-spacing: .13em; margin-bottom: .55rem; }
h1, h2, h3 { color: var(--fow-ink); letter-spacing: -0.025em; }
h1 { font-weight: 720; }
p, label, [data-testid="stCaptionContainer"] { color: var(--fow-muted); }
[data-testid="stMetric"] {
  background: var(--fow-surface); border: 1px solid var(--fow-border);
  border-radius: 12px; padding: 1rem 1.1rem;
}
[data-testid="stMetricLabel"] { color: var(--fow-muted); }
[data-testid="stMetricValue"] { color: var(--fow-ink); }
[data-testid="stSidebar"] { background: #eef4f5; border-right: 1px solid var(--fow-border); }
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p { color: var(--fow-ink); }
div[data-testid="stVerticalBlockBorderWrapper"] {
  border-color: var(--fow-border); border-radius: 14px; background: var(--fow-surface);
}
[data-testid="stDataFrame"] { border: 1px solid var(--fow-border); border-radius: 10px; }
.stButton button[kind="primary"], .stDownloadButton button[kind="primary"] {
  border-radius: 9px; font-weight: 650; min-height: 2.7rem;
  background: var(--fow-accent) !important; border-color: var(--fow-accent) !important;
  color: #ffffff !important;
}
.stButton button[kind="primary"] p { color: #ffffff !important; }
.stButton button[kind="secondary"] { border-radius: 9px; font-weight: 600; min-height: 2.5rem; }
hr { border-color: var(--fow-border); }
</style>
"""


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
    if entry and now - entry[0] < ttl:
        return deepcopy(entry[1])
    value = loader()
    cache[key] = (now, deepcopy(value))
    for stale_key in [item for item, saved in cache.items() if now - saved[0] >= ttl]:
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
    result = load_ai_suggestions(path.parents[2])
    st.session_state["_page_ai_suggestions"] = (signature, result)
    return result


def _load_manual_review_data(labels):
    """Load the real candidate, label, and taxonomy tables for the review page."""
    candidates = pd.DataFrame() if supabase_store.configured() else training_candidates(storage.ROOT)
    shared_candidates = storage.read_frame("team_training_candidates")
    if not shared_candidates.empty:
        candidates = pd.concat([candidates, shared_candidates], ignore_index=True).fillna("")
    extracted = storage.read_frame("extractions_original")
    if not extracted.empty:
        extracted = extracted.rename(columns={"original_phrase": "phrase"})
        jobs = storage.read_frame("cleaned_jobs")
        if not jobs.empty:
            source = jobs.drop_duplicates("source_id").set_index("source_id")
            for target, column in (("source_url", "url"), ("job_title", "job_title"), ("company", "company")):
                extracted[target] = extracted.source_id.map(source[column]).fillna("")
        candidates = pd.concat([candidates, extracted], ignore_index=True).fillna("")
    for column in ("phrase", "normalized_phrase", "source_type", "source_id", "job_title", "company", "source_url", "original_text"):
        if column not in candidates:
            candidates[column] = ""
    if supabase_store.configured() and not candidates.empty:
        jobs = storage.read_frame("cleaned_jobs")
        if not jobs.empty and {"source_id", "job_description"}.issubset(jobs):
            contexts = jobs.drop_duplicates("source_id").set_index("source_id").job_description
            candidates["original_text"] = candidates.original_text.where(candidates.original_text.ne(""), candidates.source_id.map(contexts).fillna(""))
    from .cleaning import normalize_text
    candidates["normalized_phrase"] = candidates.normalized_phrase.where(candidates.normalized_phrase.ne(""), candidates.phrase.map(normalize_text))
    candidates = candidates[candidates.phrase.str.strip().ne("")].drop_duplicates(["normalized_phrase", "source_type", "source_id"])
    from .pretrained_suggestions import is_incomplete_phrase
    candidates["needs_phrase_edit"] = candidates.phrase.map(is_incomplete_phrase)
    reviewed = {(row.normalized_phrase, row.source_type, row.source_id): row for row in labels.itertuples()}
    taxonomy = training_taxonomy(storage.ROOT)
    return candidates, reviewed, taxonomy

@st.cache_data(show_spinner=False)
def cached_clean(frame, kind, duplicate_list):
    return clean_dataset(frame, kind, duplicate_list)

@st.cache_resource(show_spinner=False)
def cached_nlp():
    return get_nlp()

@st.cache_data(show_spinner=False)
def workbook_bytes(tables, metadata):
    return export_excel(tables, metadata)

def display(frame):
    st.dataframe(frame, width="stretch", hide_index=True)

def chart(fig):
    st.plotly_chart(fig, width="stretch")

def page_intro(title, description):
    st.title(title)
    st.caption(description)

def page_button(path, label, *, primary=False, key=None):
    if action_button(label, type="primary" if primary else "secondary", key=key, use_container_width=True,
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
                                     ttl=4, max_entries=1)
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
    analysis_revision = digest({"inputs": signature, "corrections": correction_revision})
    source_key = f"sources:{analysis_revision}"
    source_snapshot = _session_cached_value(
        "_fow_source_cache", source_key,
        lambda: {"jobs": storage.read_frame("cleaned_jobs"),
                 "taxonomy": storage.read_frame("cleaned_psf_aai"),
                 "extracted": current_extractions()},
    )
    jobs, skills = source_snapshot["jobs"], source_snapshot["extracted"]
    with st.sidebar.expander("Job filters"):
        jf = select_filters(jobs, ["job_title", "location", "company", "industry"], "jobs")
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
    )


def home():
    st.markdown("<div class='fow-eyebrow'>RESEARCH WORKSPACE · PHILIPPINES</div>", unsafe_allow_html=True)
    st.title("The Future of Work in the Philippines")
    st.markdown("Explore the skills employers request in Philippine AI and analytics jobs, then compare them with the TESDA PSF-AAI framework.")
    jobs = storage.read_frame("cleaned_jobs")
    taxonomy = storage.read_frame("cleaned_psf_aai")
    mapped_jobs = storage.read_frame("mapped_jobs")
    has_extractions = (storage.ROOT / "data/processed/extractions_original.csv").is_file()
    label_count = reviewed_label_count()
    model = read_model_metadata()
    meta = storage.read_json("extraction_metadata", {})

    metrics = st.columns(4)
    metrics[0].metric("Clean job ads", f"{len(jobs):,}")
    metrics[1].metric("Phrase extraction", "Complete" if has_extractions else "Not started")
    metrics[2].metric("Reviewed labels", f"{label_count:,}")
    metrics[3].metric("PSF-AAI competencies", f"{len(taxonomy):,}")

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

    with st.container(border=True):
        st.markdown("**YOUR NEXT STEP**")
        st.subheader(next_title)
        st.write(next_copy)
        page_button(next_path, next_label, primary=True, key="home_next_step")

    st.subheader("Research workflow")
    st.caption("Complete the steps in order. The TESDA PSF-AAI framework is already included as the default reference.")
    steps = [
        ("01", "Upload job ads", "Add the CSV or Excel file for your study.", "pages/01_Data_Upload.py", "Open upload"),
        ("02", "Review data quality", "Check matched columns and save clean data.", "pages/02_Data_Quality.py", "Review data"),
        ("03", "Extract phrases", "Find candidate skills in the job descriptions.", "pages/05_Competency_Extraction.py", "Extract phrases"),
        ("04", "Review and label", "Check AI suggestions against the source evidence.", "pages/06_Manual_Labeling.py", "Review phrases"),
        ("05", "Train and evaluate", "Train only after the reviewed labels pass validation.", "pages/07_ML_Training.py", "Train models"),
        ("06", "Explore results", "Review employer demand, PSF mapping and reports.", "pages/03_Job_Market.py", "View results"),
    ]
    for start in (0, 3):
        columns = st.columns(3)
        for column, (number, title, description, path, link) in zip(columns, steps[start:start + 3]):
            with column:
                with st.container(border=True):
                    st.caption(f"STEP {number}")
                    st.markdown(f"#### {title}")
                    st.write(description)
                    page_button(path, link, key=f"home_workflow_{number}")
    try:
        readiness_path = resolve_training_file(storage.ROOT)
        readiness_labels = storage.read_frame("labeled_competencies") if supabase_store.configured() else load_labeled_data(readiness_path)
        _, readiness_validation = cached_label_validation(readiness_labels, require_provenance=True)
        readiness_audit = assess_research_readiness(readiness_labels, model, readiness_validation)
    except (ValueError, OSError) as exc:
        readiness_labels, readiness_audit = pd.DataFrame(), {"findings": [{"title": "Training data unavailable", "detail": str(exc)}]}
    if readiness_audit["findings"]:
        with st.container(border=True):
            st.subheader("Research readiness needs attention")
            blocking = [finding for finding in readiness_audit["findings"] if finding.get("status", "blocking") == "blocking"]
            st.warning("The current dataset and evaluation are not ready for defensible research findings.")
            if blocking:
                st.write(" · ".join(finding["title"] for finding in blocking[:3]))
            page_button("pages/18_Research_Readiness.py", "Review readiness", key="home_readiness")
    if model:
        st.caption(f"Saved classifier: {model['model_name']}. It is available for exploratory workflow checks; see Research Readiness before interpreting model outputs.")
    else:
        st.caption("No classifier has been trained. AI-generated phrase suggestions are drafts; they do not count as reviewed labels or model results.")


def upload(kind="jobs"):
    page_intro("Upload job data" if kind == "jobs" else "Upload supporting data",
               "Add the Philippine job-ad dataset for this study. Your original file is archived unchanged; you can review the automatic column matches before saving.")
    template = (Path(__file__).resolve().parents[1] / "data/templates" / f"{kind}_template.csv")
    if template.exists():
        st.download_button("Download blank template", template.read_bytes(), template.name, "text/csv")
    uploaded = st.file_uploader("CSV or XLSX", type=["csv", "xlsx"])
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
        frame = cached_load(content, uploaded.name, sheet, encoding)
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
    if any(suggested.get(field) for field in ("job_title", "job_description", "required_skills", "qualifications")):
        if action_button("Apply automatic mapping", type="primary", help="Save the clear header matches shown above. You can still change them in the form below."):
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
        for field in FIELDS[kind]:
            default = suggested[field]
            mapping[field] = st.selectbox(field.replace("_", " ").title(), options, index=options.index(default) if default in options else 0, key=f"{scope}_{field}")
        if action_form_submit_button("Save mapping"):
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

def quality():
    page_intro("Review data quality", "Check the uploaded job-ad columns and the cleaned preview, then save the job table used by the analysis.")
    kind = st.selectbox("Dataset", list(FIELDS), format_func=lambda value: {"jobs": "Job advertisements", "psf_aai": "PSF-AAI reference", "stakeholder": "Stakeholder responses"}.get(value, value))
    frame = storage.read_frame("mapped_"+kind)
    if frame.empty:
        st.info("Map this dataset first.")
        return
    potential = duplicate_ids(frame)
    selected = st.multiselect("Confirm duplicate record IDs to remove from the cleaned copy", potential)
    cleaned, report = cached_clean(frame, kind, tuple(selected))
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
            from .psf_source import activate_framework
            activate_framework(frame, reviewer, storage.ROOT)
            st.success("Reviewed PSF reference activated. Re-run extraction.")
            return
        storage.save_frame("cleaned_"+kind, cleaned)
        storage.save_frame("quality_"+kind, report)
        storage.save_json("cleaning_"+kind, {"timestamp": timestamp(), "removed_duplicate_ids": selected, "source_hash": frame_hash(frame), "philippine_aai_scope_reviewed": scope_reviewed if kind == "jobs" else False})
        st.success("Cleaned data and quality report saved. Re-run extraction if analysis inputs changed.")

def extraction():
    page_intro("Extract skill phrases", "Scan cleaned job ads, carry forward matching researcher-approved labels, and send new phrases to review.")
    with st.expander("How extraction works", expanded=False):
        st.write("Previously approved labels are attached when a normalized phrase matches the reviewed dataset. New phrases remain unreviewed candidates. Classifier predictions and AI drafts are shown separately and are never treated as researcher-approved labels.")
    if storage.read_frame("cleaned_psf_aai").empty:
        st.warning("No PSF-AAI taxonomy is available. Discovery can run, but it cannot claim PSF matches.")
    if not (ROOT / "models/competency_classifier.joblib").exists():
        st.info("No selected classifier yet. Extract initial phrases for manual labeling, then train both models and select one.")
    else:
        if training_data_changed():
            st.warning("Training data has changed since this model was trained. Retraining is recommended.")
    if action_button("Run extraction and classification", type="primary"):
        with st.spinner("Processing unique texts and mapping competencies…"):
            cached_nlp()
            result = run_extraction()
        st.success(f"Saved {len(result):,} candidate/match records with evidence.")
    result = storage.read_frame("extractions_original")
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
        display(result)
        diagnostics = storage.read_frame("nlp_processed")
        if not diagnostics.empty and diagnostics.candidate_limit_reached.astype(str).str.casefold().eq("true").any():
            limited = int(diagnostics.candidate_limit_reached.astype(str).str.casefold().eq("true").sum())
            cap = storage.settings()["max_candidates"]
            st.warning(f"{limited} of {len(diagnostics)} job ads reached the {cap}-phrase cap for broad n-gram discovery. Exact vocabulary and PSF-AAI term scans still use the full text. Keeping this cap limits low-confidence review fragments; raise it in Settings only when you want a wider manual review and can inspect the extra candidates.")

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
    progress = st.progress(0., text="Validating reviewed annotations before automatic retraining")
    try:
        metadata, _ = train_and_save_models(
            .2, False, VECTORIZER_CONFIG,
            progress=lambda value, message: progress.progress(value, text=message),
        )
    except (ValueError, OSError, RuntimeError) as exc:
        progress.empty()
        st.warning(f"Annotations were saved, but automatic retraining did not complete: {exc}")
        return
    progress.empty()
    st.success(
        f"Development classifier refreshed from the reviewed dataset ({metadata['rows_used']:,} usable phrases). "
        "These iterative holdout results are not final research metrics."
    )


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
            "Training runs during the save and can take a few minutes. It never trains on AI drafts."
        ),
    )
    if shared_workspace and not can_train:
        st.caption("Only the project administrator can start model training in the shared workspace. Ask the administrator to use this option.")
    return bool(enabled and can_train)


def labeling():
    page_intro("Review and label phrases", "Enter each category and PSF-AAI competency yourself. Optional AI drafts stay separate until you explicitly copy a value into a field.")
    st.info("Nothing from AI fills a label automatically. Typed values and values you explicitly copy are saved only when you click Save, under your reviewer ID and timestamp.")
    auto_train = _auto_retraining_control()
    with st.container(border=True):
        st.subheader("Add a small, free remote-job feed")
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
                    st.info("The new postings are saved under `train/remote_feeds`. Run ‘Run all local suggestions’ below to extract phrases and prepare BGE-M3 drafts.")
    with st.container(border=True):
        st.subheader("Automate local candidate preparation and suggestions")
        st.caption("Scans posting CSVs already in ./train, prepares Philippine-location candidates, and generates BGE-M3 category and PSF drafts in resumable batches. It does not fetch new websites, save labels, or train a classifier. Keep this app running until the progress bar completes.")
        if action_button("Run all local suggestions", type="primary", key="run_local_suggestions", disabled=not supabase_store.is_admin()):
            from .unattended_suggestions import run_local_suggestions
            progress = st.progress(0.0, text="Starting local candidate scan")
            try:
                report = run_local_suggestions(
                    storage.ROOT,
                    progress=lambda value, message: progress.progress(value, text=message),
                )
            except ImportError:
                progress.empty()
                st.error("Install the optional local models once: `..\\.venv\\Scripts\\python.exe -m pip install -r requirements-suggestions.txt`. The first BGE-M3 run downloads about 2.3 GB.")
            except Exception as exc:
                progress.empty()
                st.error(f"The local suggestion run stopped safely. Suggestions saved in earlier batches remain available to resume: {exc}")
            else:
                st.success(
                    f"Finished scanning {report['candidate_rows_scanned']:,} candidate rows. "
                    f"Created {report['suggestions_generated']:,} new drafts; "
                    f"skipped {report['already_reviewed']:,} reviewed and {report['already_suggested']:,} already-suggested phrases. "
                    "No research labels or classifier models were changed."
                )
                if report["missing_source_id"]:
                    st.caption(f"Skipped {report['missing_source_id']:,} candidate rows without a source ID so they cannot enter the review workflow without provenance.")
                for skipped in report["preparation_skips"]:
                    st.caption(f"Posting source skipped: {skipped}")
                for error in report["preparation_errors"]:
                    st.warning(f"Could not prepare one posting file: {error}")
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
                with st.spinner("Scanning postings and extracting candidate phrases…"):
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
    if supabase_store.configured():
        st.caption("Your team can review simultaneously. Saves detect changes made by another reviewer. Refresh before starting a new batch; unsaved table edits will be discarded.")
        if action_button("Refresh shared review table"):
            supabase_store.clear_read_cache()
            for key in list(st.session_state):
                if str(key).startswith(("review_snapshot", "manual_labels_", "resolve_label_")):
                    del st.session_state[key]
            st.rerun()
        if "review_snapshot" not in st.session_state:
            st.session_state["review_snapshot"] = storage.read_frame("labeled_competencies")
        labels = st.session_state["review_snapshot"].copy()
    else:
        labels = storage.read_frame("labeled_competencies")
    path = resolve_training_file(storage.ROOT)
    st.caption("Reviewed annotations save to the shared database; a local CSV backup is kept separately." if supabase_store.configured() else f"Reviewed annotations save to `{project_relative_path(path)}`.")
    candidates, reviewed, taxonomy = _load_manual_review_data(labels)
    from .cleaning import normalize_text
    st.caption(f"{len(candidates)} candidate occurrences; {candidates.normalized_phrase.nunique()} distinct phrases; {int(candidates.needs_phrase_edit.sum())} likely connector fragments to inspect or edit; {len(labels)} saved review rows. Source-pack descriptions are researcher-provided summaries; check their original URLs before final research use.")
    categories = list(dict.fromkeys(LABELS + (taxonomy.competency_category.tolist() if not taxonomy.empty else []) + (labels.label.tolist() if not labels.empty else [])))
    extra = st.text_input("Additional category (optional)")
    if extra.strip():
        categories.append(extra.strip())
    if supabase_store.configured():
        reviewer = st.session_state.get("supabase_user_email", "")
        st.caption(f"Signed-in reviewer: {reviewer}")
    else:
        reviewer = st.text_input("Reviewer ID", key="label_reviewer")
    if not candidates.empty:
        if "candidate_file" in candidates:
            sources = sorted(candidates.candidate_file.unique())
            selected_sources = st.multiselect("Candidate source files", sources)
            if selected_sources:
                candidates = candidates[candidates.candidate_file.isin(selected_sources)]
        if st.checkbox("Only show phrases awaiting review", value=True):
            pending = pd.Series([((row.normalized_phrase, row.source_type, row.source_id) not in reviewed and
                                  (normalize_text(row.phrase), row.source_type, row.source_id) not in reviewed) for row in candidates.itertuples()], index=candidates.index, dtype=bool)
            candidates = candidates.loc[pending]
        if st.checkbox("Hide obvious connector fragments", value=True, help="This hides phrases beginning or ending with a common connector, such as ‘with strong’ or ‘written and’. Turn it off to inspect and manually label or correct them."):
            candidates = candidates.loc[~candidates.needs_phrase_edit]
        query = st.text_input("Find candidate phrase")
        if query:
            candidates = candidates[candidates.phrase.str.contains(query, case=False, regex=False)]
        page = st.number_input("Phrase page (10 per page)", 1, max(1, (len(candidates)+9)//10), 1)
        shown = candidates.iloc[(page-1)*10:page*10]
        with st.expander("Read-only source evidence (open to check context)", expanded=False):
            st.dataframe(shown[["phrase", "source_type", "source_id", "job_title", "company", "source_url", "original_text"]], hide_index=True, width="stretch", column_config={"source_url": st.column_config.LinkColumn("Original source")})
    else:
        st.info("No candidate phrases yet. Add Philippine job-ad source/candidate data to ./train or run Competency Extraction on uploaded jobs. No example labels are added automatically.")
        shown = pd.DataFrame(columns=["phrase", "source_type", "source_id", "original_text"])
    from .pretrained_suggestions import (
        MODEL_ID, MODEL_REVISION,
        save_ai_suggestions, suggest_labels, suggestion_key,
    )
    page_rows = shown.to_dict("records") if not shown.empty else []
    page_identity = frame_hash(shown[["phrase", "source_type", "source_id"]]) if not shown.empty else "empty"
    saved_suggestions = _page_ai_suggestions(storage.ROOT / "data/processed/pretrained_label_suggestions.csv")
    page_suggestions = [saved_suggestions.get(suggestion_key(row), {}) for row in page_rows]
    def generate_ai_drafts(rows):
        progress = st.progress(0, text="Preparing local pretrained models…")
        batch_size = 25
        try:
            with st.spinner("Generating category and PSF suggestions. This can take several minutes on the first run."):
                for start in range(0, len(rows), batch_size):
                    batch = rows[start:start + batch_size]
                    predicted = suggest_labels(batch, taxonomy)
                    save_ai_suggestions(storage.ROOT, batch, predicted)
                    complete = min(start + len(batch), len(rows))
                    progress.progress(complete / max(len(rows), 1), text=f"Generated suggestions for {complete:,} of {len(rows):,} phrases")
        except ImportError:
            st.error("Install the optional local models once from the project folder: `..\\.venv\\Scripts\\python.exe -m pip install -r requirements-suggestions.txt`.")
        except Exception as exc:
            st.error(f"The pretrained models stopped before completing all suggestions. Completed batches remain saved separately: {exc}")
        else:
            st.success(f"Saved AI drafts for {len(rows):,} phrases. They remain separate from researcher-reviewed labels.")
            st.rerun()

    if not shown.empty:
        st.caption(f"Local pretrained embedding model: {MODEL_ID} (pinned revision {MODEL_REVISION[:8]}). Its first run downloads about 2.3 GB; inference runs on CPU. It ranks category descriptions and competencies in the active PSF-AAI taxonomy, and each saved draft records the model and similarity scores.")
        if taxonomy.empty:
            st.warning("Map and review the official PSF-AAI taxonomy first. Category suggestions can be generated only after competency matches have a verified taxonomy to compare against.")
        else:
            if action_button("Generate AI suggestions for this page", key=f"suggest_labels_{page_identity}", disabled=not supabase_store.is_admin()):
                generate_ai_drafts(page_rows)

    has_page_suggestions = bool(page_suggestions and any(item.get("category") for item in page_suggestions))
    if has_page_suggestions:
        st.caption("AI drafts are optional. The manual fields remain blank until you enter a value or explicitly check a Copy draft box. Similarity scores rank suggestions; they are not calibrated confidence or research metrics.")
    if not shown.empty:
        st.subheader("Manual review")
        st.caption("Review phrases in the table. New category and PSF-AAI fields start blank. A checked Copy draft box uses that AI value instead of the manual cell for that field when you save.")
    taxonomy_names = taxonomy.competency_name.astype(str).tolist() if not taxonomy.empty else []
    table_rows = []
    for index, row in enumerate(page_rows):
        suggestion = page_suggestions[index] if index < len(page_suggestions) else {}
        row_normalized = normalize_text(row.get("normalized_phrase") or row.get("phrase", ""))
        saved = reviewed.get((row_normalized, row.get("source_type", ""), row.get("source_id", "")))
        table_row = {
            "Phrase": row.get("phrase", ""),
            "Category": saved.label if saved else "",
            "PSF-AAI competency": saved.psf_competency if saved else "",
        }
        if has_page_suggestions:
            table_row.update({
                "AI category draft": suggestion.get("category", ""),
                "Copy category draft": False,
                "AI PSF-AAI draft": suggestion.get("psf_competency", ""),
                "Copy PSF-AAI draft": False,
            })
        table_rows.append(table_row)
    manual_table = pd.DataFrame(table_rows)
    table_config = {
        "Phrase": st.column_config.TextColumn(disabled=True),
        "Category": st.column_config.SelectboxColumn(options=[""] + list(dict.fromkeys(categories)), help="Choose one competency category. Leave blank until reviewed."),
        "PSF-AAI competency": st.column_config.SelectboxColumn(options=[""] + list(dict.fromkeys(taxonomy_names)), help="Optional: choose an exact competency from the active taxonomy."),
    }
    disabled_columns = ["Phrase"]
    if has_page_suggestions:
        table_config.update({
            "AI category draft": st.column_config.TextColumn(disabled=True),
            "Copy category draft": st.column_config.CheckboxColumn(help="Explicitly copy this row's AI category into the label when you save."),
            "AI PSF-AAI draft": st.column_config.TextColumn(disabled=True),
            "Copy PSF-AAI draft": st.column_config.CheckboxColumn(help="Explicitly copy this row's AI PSF-AAI suggestion when you save."),
        })
        disabled_columns.extend(["AI category draft", "AI PSF-AAI draft"])
    edited_table = st.data_editor(
        manual_table,
        hide_index=True,
        num_rows="fixed",
        width="stretch",
        disabled=disabled_columns,
        column_config=table_config,
        key=f"manual_labels_{page_identity}",
    ) if not manual_table.empty else manual_table
    reviewed_rows = []
    for index, row in edited_table.iterrows():
        suggestion = page_suggestions[index] if index < len(page_suggestions) else {}
        category = suggestion.get("category", "") if row.get("Copy category draft", False) else row.get("Category", "")
        psf = suggestion.get("psf_competency", "") if row.get("Copy PSF-AAI draft", False) else row.get("PSF-AAI competency", "")
        source_row = page_rows[index]
        reviewed_rows.append({
            "phrase": source_row.get("phrase", ""), "source_type": source_row.get("source_type", ""), "source_id": source_row.get("source_id", ""),
            "label": str(category or "").strip(), "psf_competency": str(psf or "").strip(),
        })
    edited = pd.DataFrame(reviewed_rows, columns=["phrase", "source_type", "source_id", "label", "psf_competency"])

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
    if not reviewer.strip():
        st.caption("Enter your Reviewer ID above before saving.")
    has_category = bool(not edited.empty and edited.label.astype(str).str.strip().ne("").any())
    if not has_category:
        st.caption("Choose at least one competency category before saving. PSF-AAI competency is optional.")
    st.caption("Saving records the values currently in the manual fields, reviewer ID, source, and timestamp. AI drafts remain in a separate file and are never training labels by themselves.")
    can_submit = has_category or bool(conflicts)
    if action_button("Save annotations", type="primary", disabled=not reviewer.strip() or not conflicts_resolved or not can_submit):
        submitted_rows = edited
        versions = None
        if supabase_store.configured():
            versions = {r.normalized_phrase: int(r.version) for r in labels.itertuples()}
            changed = [i for i, row in edited_table.iterrows()
                       if row.get("Copy category draft", False) or row.get("Copy PSF-AAI draft", False)
                       or row.get("Category", "") != manual_table.iloc[i].get("Category", "")
                       or row.get("PSF-AAI competency", "") != manual_table.iloc[i].get("PSF-AAI competency", "")]
            submitted_rows = edited.iloc[changed]
        labels = save_annotations(submitted_rows, reviewer, conflict_resolutions=conflict_resolutions, expected_versions=versions)
        if supabase_store.configured():
            st.session_state.pop("review_snapshot", None)
            for key in list(st.session_state):
                if str(key).startswith("manual_labels_"):
                    del st.session_state[key]
        st.success(f"Saved. The dataset now has {len(labels):,} reviewed rows.")
        if st.session_state.get("backup_warning"):
            st.warning(st.session_state.pop("backup_warning"))
        _auto_train_after_review(labels, auto_train)
    st.caption("For offline/local work only: to combine work from teammates' own devices, import their downloaded reviewed-label CSV. Reviewer IDs and timestamps are preserved; unresolved phrase conflicts must be resolved in the table above.")
    uploaded = None if supabase_store.configured() else st.file_uploader("Import teammate-reviewed CSV/XLSX (preserves reviewer IDs and timestamps)", type=["csv", "xlsx"])
    imported = load_data(uploaded.getvalue(), uploaded.name) if uploaded else pd.DataFrame()
    import_conflicts, import_resolutions, import_conflicts_resolved = show_conflict_resolutions(imported, "resolve_import_label") if uploaded else ({}, {}, True)
    if uploaded and action_button("Import annotations", disabled=not import_conflicts_resolved):
        labels = save_annotations(imported, reviewer, conflict_resolutions=import_resolutions, preserve_row_provenance=True)
        st.success("Teammate annotations merged. Original reviewer IDs and timestamps were preserved; rows without source provenance will not qualify for training.")
        _auto_train_after_review(labels, auto_train)
    if not labels.empty:
        display(labels)
    st.download_button("Download reviewed training data", export_csv(labels), "labeled_competencies.csv", "text/csv")


def training():
    page_intro("Train classifier", "Train Naive Bayes and Logistic Regression models using researcher-reviewed labels. Training stays disabled until the real dataset passes the validation checks.")
    inventory = inspect_training_folder(storage.ROOT)
    with st.expander("Detected files in ./train"):
        display(pd.DataFrame(inventory))
    try:
        path = resolve_training_file(storage.ROOT)
    except ValueError as exc:
        st.warning(str(exc))
        path = None
    options = [item["filename"] for item in inspect_training_folder(storage.ROOT) if item["purpose"] in ("labeled phrases", "empty label schema") and item["filename"].lower().endswith(".csv")]
    if len(options) > 1:
        current = str(path.relative_to(storage.ROOT / "train")) if path else ""
        choice = st.selectbox("Labeled training file", options, index=options.index(current) if current in options else 0)
        if action_button("Use selected training file"):
            path = select_training_file(storage.ROOT, choice)
    if path is None:
        return
    st.caption(f"Training data file: `{project_relative_path(path)}`")
    labels = (storage.read_frame("labeled_competencies") if supabase_store.configured() else load_labeled_data(path))
    fraction = st.slider("Holdout fraction", .1, .5, .2, .05)
    include_irrelevant = st.checkbox("Intentionally train IRRELEVANT as a separate class", value=False)
    max_features = st.number_input("Maximum TF-IDF features", 100, 100000, 10000, 100)
    data, validation = cached_label_validation(labels, fraction, include_irrelevant, require_provenance=True)
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
        progress = st.progress(0., text="Validating reviewed annotations")
        try:
            metadata, comparison = train_and_save_models(fraction, include_irrelevant, {"max_features": int(max_features)},
                                                        progress=lambda value, message: progress.progress(value, text=message))
        except ValueError as exc:
            progress.empty()
            st.error(f"Training failed: {exc}")
        else:
            progress.progress(1., text="Models, evaluation tables and metadata saved")
            st.success(f"Both models trained. Selected {metadata['model_name']} using Macro F1, then Weighted F1 and per-class F1. Re-run Competency Extraction to apply this saved model.")
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
    metadata = read_model_metadata()
    metrics = storage.read_frame("model_metrics")
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
    matrix = storage.read_frame(f"evaluation_{slug}_confusion").set_index("actual").apply(pd.to_numeric)
    chart(heatmap(matrix, "Model Confusion Matrix — actual rows, predicted columns"))
    display(storage.read_frame(f"evaluation_{slug}_per_class"))
    display(storage.read_frame(f"evaluation_{slug}_predictions"))
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


def research_page(page):
    st.header(page)
    if not current_analysis():
        return
    tables, meta = filtered_bundle()
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
        display(tables["psf_mapping"])
    elif page == "Employer–PSF Alignment":
        st.caption("Thresholds are researcher-configurable heuristics, not official PSF standards. Default: ≥0.80 aligned; ≥0.60 partially aligned; lower scores not mapped. Missing reference: unclassified.")
        rates = meta["rates_before_status_display_filter"]
        cols = st.columns(3)
        for col, field in zip(cols, ("alignment_rate", "partially_aligned_rate", "unmapped_rate")):
            if rates.get(field) is not None:
                col.metric(field.replace("_", " ").title(), f"{rates[field]:.1f}%")
        chart(distribution(alignment, "status", "Alignment Status"))
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
        tables["nlp_processed"] = storage.read_frame("nlp_processed")
        tables["usability"] = storage.read_frame("usability")
        for slug in ("nb", "lr"):
            for report in ("per_class", "confusion", "predictions"):
                tables[f"evaluation_{slug}_{report}"] = storage.read_frame(f"evaluation_{slug}_{report}")
        for kind in FIELDS:
            tables["quality_"+kind] = storage.read_frame("quality_"+kind)
        with st.expander(f"Individual research tables ({len(tables)})"):
            for name, frame in tables.items():
                st.download_button(name + ".csv", export_csv(frame), name + ".csv", "text/csv", key="download_"+name)
        workbook = workbook_bytes(tables, meta)
        st.download_button("Download research_results.xlsx", workbook, "research_results.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        research_report = export_research_report(tables, meta)
        st.download_button("Download written research report (.md)", research_report, "philippine_job_ads_psf_aai_report.md", "text/markdown")
        summary = export_html(tables, meta)
        st.download_button("Download HTML research summary", summary, "research_summary.html", "text/html")
        st.download_button("Download analysis metadata", json.dumps(meta, indent=2, default=str), "analysis_metadata.json", "application/json")
        if action_button("Save this report snapshot locally"):
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
    st.header("Feedback")
    reviewer = st.text_input("Reviewer ID", key="feedback_reviewer")
    source = st.selectbox("Correction target", ["extraction", "alignment"])
    if current_analysis():
        tables, _ = filtered_bundle()
        frame = tables["all_candidates"] if source == "extraction" else tables["alignment_results"]
        key = "extraction_id" if source == "extraction" else "alignment_id"
        if not frame.empty:
            display(frame)
            row_id = st.selectbox("Record ID", frame[key].tolist())
            row = frame.loc[frame[key].eq(row_id)].iloc[0]
            fields = ["normalized_phrase", "competency_category", "psf_competency", "accepted"] if source == "extraction" else ["status"]
            field = st.selectbox("Field to correct", fields)
            st.write("Original/current value:", str(row[field]))
            if field == "status":
                corrected = st.selectbox("Corrected value", STATUSES)
            elif field == "accepted":
                corrected = st.selectbox("Corrected value", ["True", "False"])
            elif field == "psf_competency":
                tax = storage.read_frame("cleaned_psf_aai")
                corrected = st.selectbox("Corrected value", [""] + (tax.competency_name.tolist() if not tax.empty else []))
            else:
                corrected = st.text_input("Corrected value", str(row[field]))
            comment = st.text_area("Reason / comment")
            if action_button("Save correction", key=f"save_correction_{source}_{row_id}"):
                if field not in ("psf_competency",) and not corrected.strip():
                    raise ValueError("Enter a corrected value.")
                save_correction(source, row_id, field, row[field], corrected, reviewer, comment)
                st.success("Correction saved separately from original predictions. Dependent comparisons use the corrected value.")
            if source == "extraction" and action_button(
                "Add this reviewed phrase to training data",
                key=f"add_reviewed_phrase_{source}_{row_id}",
            ):
                save_annotations(pd.DataFrame([{"phrase": row.normalized_phrase, "label": row.competency_category, "psf_competency": row.psf_competency, "source_type": "jobs", "source_id": row.source_id}]), reviewer)
                st.success("Added to annotations. Retraining requires an explicit action on ML Training.")
    display(corrections())
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
    usability = storage.read_frame("usability")
    if not usability.empty:
        display(usability)
        st.download_button("Download usability evaluations", export_csv(usability), "usability.csv")
    stakeholder = storage.read_frame("cleaned_stakeholder")
    if not stakeholder.empty:
        st.subheader("Stakeholder evaluations")
        display(stakeholder)
        for field in ("importance_rating", "usability_rating"):
            numeric = pd.to_numeric(stakeholder[field], errors="coerce")
            st.write(f"{field}: {numeric.count()} numeric responses; mean {numeric.mean():.2f}" if numeric.count() else f"{field}: no numeric responses")

def methodology():
    st.header("Methodology")
    st.markdown((Path(__file__).resolve().parents[1] / "METHODOLOGY.md").read_text(encoding="utf-8"))

def research_readiness():
    page_intro("Research readiness", "A practical audit of the current data and model workflow. Passing app checks does not by itself make results ready for a thesis or publication.")
    try:
        path = resolve_training_file(storage.ROOT)
        labels = (storage.read_frame("labeled_competencies") if supabase_store.configured() else load_labeled_data(path))
        usable, validation = cached_label_validation(labels, require_provenance=True)
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
    jobs = storage.read_frame("cleaned_jobs")
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
    st.header("Settings")
    st.subheader("Shared team workspace")
    if supabase_store.configured():
        st.success("Supabase is connected. Saved tables and settings are shared with signed-in teammates; local CSVs remain as backups.")
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
    cfg = storage.settings()
    with st.form("settings"):
        aligned = st.slider("Aligned threshold", .01, 1., float(cfg["aligned_threshold"]), .01)
        partial = st.slider("Partially aligned threshold", .0, .99, float(cfg["partial_threshold"]), .01)
        fuzzy = st.slider("Taxonomy fuzzy match threshold", .5, 1., float(cfg["fuzzy_threshold"]), .01)
        semantic = st.slider("Taxonomy semantic match threshold", .5, 1., float(cfg["semantic_threshold"]), .01)
        path = st.text_input("Optional local sentence-transformers model directory", cfg["semantic_model"])
        stopwords = st.text_area("Additional stopwords (one per line; phrases retain internal stopwords)", "\n".join(cfg["stopwords"]))
        batch = st.number_input("NLP batch size", 1, 1024, cfg["batch_size"])
        limit = st.number_input("Maximum discovered n-grams per record", 50, 10000, cfg["max_candidates"])
        emerging = st.number_input("Minimum job ads for an emerging-skill candidate", 1, 100000, cfg["emerging_min_jobs"])
        low = st.number_input("Likert scale minimum", 0, 9, cfg["likert_min"])
        high = st.number_input("Likert scale maximum", 1, 10, cfg["likert_max"])
        if action_form_submit_button("Save settings"):
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
    st.session_state["_fow_current_page"] = page
    st.markdown(DESIGN_CSS, unsafe_allow_html=True)
    st.sidebar.caption(f"Research workspace · v{VERSION}")
    from .auth_ui import render_account_menu
    render_account_menu()
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
