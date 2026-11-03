from .category_schema import requirement_type, category_parent, skill_type
import importlib.metadata
import pandas as pd
from . import storage
from .config import ROOT, VERSION
from .cleaning import analysis_jobs, analysis_job_values
from .utils import frame_hash, digest, timestamp
from .classification import cached_load_model
from .psf_mapping import TaxonomyMatcher
from .skill_extraction import extract_skills
from .analytics import accepted_skills, filter_frame, skill_chart_tables, psf_demand_tables
from .job_profile import job_profile_tables
from .geography import location_tables
from .alignment import calculate_mapping, summarize_alignment
from .psf_reviews import REVIEW_TABLE
from .gap_analysis import calculate_gaps
from .labeling import apply_corrections

# Bump when extraction/matching/classification semantics change, not for UI fixes.
EXTRACTION_PIPELINE_VERSION = 1
_LEGACY_COMPATIBLE_VERSIONS = {1: tuple(f"2.0.{patch}" for patch in range(60, 66))}


def _extraction_inputs():
    return {"datasets": {k: frame_hash(storage.read_frame("cleaned_"+k)) for k in ("jobs", "psf_aai")},
            "annotations": frame_hash(storage.read_frame("labeled_competencies")),
            "settings": storage.settings(), "model": storage.read_json("selected_model", {})}


def _legacy_extraction_inputs(inputs=None):
    """Recognize saved runs made before pending uploads were separated from active data."""
    return (inputs if inputs is not None else _extraction_inputs()) | {
        "active_uploads": {k: v["hash"] for k, v in storage.read_json("uploads", {}).items()
                           if k in ("jobs", "psf_aai")},
        "column_mappings": {k: storage.read_json("mapping_" + k, {}) for k in ("jobs", "psf_aai")},
    }


def input_signature():
    return digest(_extraction_inputs() | {"pipeline_version": EXTRACTION_PIPELINE_VERSION})


def extraction_freshness(metadata):
    """Return the active signature and whether the saved inputs still match.

    Old runs kept only a hash containing their app version. Reconstruct those
    hashes for known compatible releases without rewriting the original record.
    """
    inputs = _extraction_inputs()
    signature = digest(inputs | {"pipeline_version": EXTRACTION_PIPELINE_VERSION})
    if metadata.get("pipeline_version") is not None:
        if metadata["pipeline_version"] != EXTRACTION_PIPELINE_VERSION:
            return signature, False
        if metadata.get("signature") == signature:
            return signature, True
        legacy = _legacy_extraction_inputs(inputs)
        return signature, metadata.get("signature") == digest(legacy | {"pipeline_version": EXTRACTION_PIPELINE_VERSION})
    saved = metadata.get("signature")
    if not saved:
        return signature, False
    legacy = _legacy_extraction_inputs(inputs)
    return signature, any(saved == digest(legacy | {"version": version})
                          for version in _LEGACY_COMPATIBLE_VERSIONS.get(EXTRACTION_PIPELINE_VERSION, ()))


def _extraction_retry_signature(signature):
    # Local model identity guards retries on this host, not shared result freshness.
    return digest({"inputs": signature,
                   "cleaning": {k: storage.read_json("cleaning_" + k, {}) for k in ("jobs", "psf_aai")},
                   "published_model": storage.read_json("model_metadata", {}),
                   "local_model": {name: digest(path.read_bytes()) if path.is_file() else None
                                   for name in ("competency_classifier.joblib", "model_metadata.json")
                                   for path in [ROOT / "models" / name]}})

def run_extraction(progress=None, on_prepared=None):
    from . import supabase_store
    progress = progress or (lambda value, message: None)
    progress(0., "Checking source data and review provenance")
    signature = input_signature()
    retry_signature = _extraction_retry_signature(signature)
    settings = storage.settings()
    uploads = storage.read_json("uploads", {})
    for kind in ("jobs", "psf_aai"):
        cleaned = storage.read_frame("cleaned_" + kind)
        if kind == "psf_aai" and (cleaned.empty or cleaned.attrs.get("reference_source") == "bundled_default"):
            continue
        hashes = cleaned["_dataset_hash"].astype(str).unique() if "_dataset_hash" in cleaned else []
        if cleaned.empty or len(hashes) != 1 or not hashes[0]:
            raise ValueError(f"No valid cleaned {kind} dataset is saved. Review Data Quality and save it before extraction.")
        cleaning = storage.read_json("cleaning_" + kind, {})
        if cleaning.get("dataset_hash") and cleaning["dataset_hash"] != hashes[0]:
            raise ValueError(f"The saved {kind} cleaning record does not match the cleaned dataset. Save the cleaned dataset again.")
        upload = uploads.get(kind, {})
        if upload and not cleaning:
            raise ValueError(f"The {kind} dataset has no saved cleaning review. Complete Data Quality before extraction.")
        if kind == "jobs" and (upload or cleaning) and not cleaning.get("philippine_aai_scope_reviewed", False):
            raise ValueError("Review the job sources for Philippine provenance and AI/analytics relevance on Data Quality before extraction.")
        mapped = storage.read_frame("mapped_" + kind)
        mapped_is_active = (not mapped.empty and "_dataset_hash" in mapped
                            and mapped._dataset_hash.astype(str).eq(hashes[0]).all())
        if mapped_is_active and cleaning and cleaning.get("source_hash") != frame_hash(mapped):
            raise ValueError(f"The {kind} column mapping changed or has not been cleaned. Save its cleaned dataset again.")
        if upload and upload.get("hash") != hashes[0]:
            progress(.02, f"A newer {kind} upload is pending; using the saved cleaned dataset")
    taxonomy = storage.read_frame("cleaned_psf_aai")
    matcher = TaxonomyMatcher(taxonomy, settings["fuzzy_threshold"], settings["semantic_model"], settings["semantic_threshold"]) if not taxonomy.empty else None
    model_path = ROOT / "models/competency_classifier.joblib"
    model = cached_load_model(model_path) if model_path.exists() else None
    from . import supabase_store
    if supabase_store.configured():
        from .model_training import read_model_metadata
        import json
        local_meta = ROOT / "models/model_metadata.json"
        published = read_model_metadata()
        local = json.loads(local_meta.read_text()) if local_meta.exists() else {}
        if not published or local.get("training_timestamp") != published.get("training_timestamp"):
            model = None
    annotations = storage.read_frame("labeled_competencies")
    frames, diagnostics = [], []
    for kind in ("jobs",):
        frame = storage.read_frame("cleaned_" + kind)
        result, processed = extract_skills(frame, kind, matcher, model, annotations, stopwords=settings["stopwords"], batch_size=settings["batch_size"], max_candidates=settings["max_candidates"], progress=progress)
        frames.append(result)
        diagnostics.append(processed)
    populated = [frame for frame in frames if not frame.empty]
    output = pd.concat(populated, ignore_index=True) if populated else frames[0]
    if output.empty:
        raise ValueError("No phrases were found. Upload, map and clean text datasets first.")
    prepared = (output, pd.concat(diagnostics, ignore_index=True),
                {"signature": signature, "retry_signature": retry_signature, "timestamp": timestamp(),
                 "pipeline_version": EXTRACTION_PIPELINE_VERSION, "software_version": VERSION,
                 "taxonomy_available": matcher is not None, "model_available": model is not None})
    if on_prepared:
        on_prepared(prepared)
    return publish_extraction(prepared, progress)


def publish_extraction(prepared, progress=None):
    """Retry publication only after rechecking every input used in computation."""
    from .background_tasks import begin_publication
    from . import supabase_store
    progress = progress or (lambda value, message: None)
    output, diagnostics, metadata = prepared
    progress(.95, "Checking that research inputs are unchanged")
    supabase_store.clear_read_cache(frames=True)
    signature = input_signature()
    if metadata["signature"] != signature or metadata.get("retry_signature") != _extraction_retry_signature(signature):
        raise ValueError("Research inputs changed during extraction. Previous results were retained; rerun with the current data and reviewed labels.")
    begin_publication()
    storage.save_frame("extractions_original", output)
    storage.save_frame("nlp_processed", diagnostics)
    storage.save_json("extraction_metadata", metadata)
    return output

def current_extractions(*, source_ids=None):
    extracted = storage.read_frame("extractions_original", source_ids=source_ids) if source_ids is not None else storage.read_frame("extractions_original")
    if source_ids is not None and not extracted.empty:
        extracted = extracted[extracted.source_id.isin(source_ids)]
    extracted = apply_corrections(extracted, "extraction", "extraction_id")
    if not extracted.empty:
        # Human PSF edits update the identity and related taxonomy fields together.
        taxonomy = storage.read_frame("cleaned_psf_aai")
        if not taxonomy.empty:
            references = taxonomy.set_index("competency_name")
            known = extracted.psf_competency.isin(references.index)
            extracted.loc[known, "matched_competency"] = extracted.loc[known, "psf_competency"]
            for target, column in (("competency_id", "competency_id"), ("psf_category", "competency_category"), ("job_role", "job_role"), ("proficiency_level", "proficiency_level"), ("psf_competency_description", "competency_description"), ("psf_range_of_application", "range_of_application"), ("source_page", "source_page"), ("source_url", "source_url"), ("source_hash", "source_hash")):
                extracted.loc[known, target] = extracted.loc[known, "psf_competency"].map(references[column]) if column in references else ""
        unmapped = extracted.psf_competency.eq("")
        extracted.loc[unmapped, "matched_competency"] = extracted.loc[unmapped, "normalized_phrase"]
        extracted.loc[unmapped, ["competency_id", "psf_category", "job_role", "proficiency_level", "psf_competency_description", "psf_range_of_application"]] = ""
    if "competency_category" in extracted:
        extracted["requirement_type"] = extracted.competency_category.map(requirement_type)
        extracted["category_parent"] = extracted.competency_category.map(category_parent)
        extracted["skill_type"] = extracted.competency_category.map(skill_type)
    return extracted

def analysis_bundle(job_filters=None, skill_filters=None, statuses=None, *, source_snapshot=None):
    source_snapshot = source_snapshot or {}
    jobs_source = source_snapshot["jobs"] if "jobs" in source_snapshot else storage.read_frame("cleaned_jobs")
    taxonomy = source_snapshot["taxonomy"] if "taxonomy" in source_snapshot else storage.read_frame("cleaned_psf_aai")
    extracted_source = source_snapshot["extracted"] if "extracted" in source_snapshot else current_extractions()
    jobs = analysis_jobs(filter_frame(jobs_source, job_filters or {}))
    extracted = extracted_source.copy()
    if not extracted.empty:
        extracted = extracted[extracted.source_type.eq("jobs") & extracted.source_id.isin(jobs.get("source_id", []))]
        extracted = filter_frame(extracted, skill_filters or {})
    skills = accepted_skills(extracted)
    cfg = storage.settings()
    reviews = source_snapshot["mapping_reviews"] if "mapping_reviews" in source_snapshot else storage.read_frame(REVIEW_TABLE)
    mapping = calculate_mapping(skills, taxonomy, cfg["aligned_threshold"], cfg["partial_threshold"], cfg["semantic_model"], cfg["semantic_threshold"], reviews)
    alignment = summarize_alignment(mapping)
    alignment = apply_corrections(alignment, "alignment", "alignment_id")
    mapping["status"] = mapping.alignment_id.map(alignment.set_index("alignment_id").status)
    # Advertisement provenance has a separate name from the PSF reference URL.
    job_columns = [key for key in ("source_id", "job_title", "url") if key in jobs]
    if "source_id" in job_columns:
        mapping = mapping.merge(jobs[job_columns].drop_duplicates("source_id").rename(columns={"url": "job_source_url"}), on="source_id", how="left")
    demand, unmapped, emerging, rates = calculate_gaps(skills, jobs, alignment, cfg["emerging_min_jobs"])
    if statuses:
        alignment = alignment[alignment.status.isin(statuses)]
        demand = demand[demand.status.isin(statuses)]
        unmapped = unmapped[unmapped.status.isin(statuses)]
        emerging = emerging[emerging.status.isin(statuses)]
    mapping = mapping[mapping.alignment_id.isin(alignment.alignment_id)]
    linked = mapping[mapping.psf_competency.ne("") & mapping.status.isin(["ALIGNED", "PARTIALLY ALIGNED"])]
    competency_demand = linked.groupby(["competency_id", "psf_competency"]).agg(
        job_ad_count=("source_id", "nunique"), skill_phrase_count=("normalized_skill", "nunique"),
        occurrence_count=("extraction_id", "nunique")).reset_index()
    selected_reviews = reviews[reviews.extraction_id.isin(skills.get("extraction_id", []))].copy() if not reviews.empty else reviews
    reviewed = storage.read_frame("labeled_competencies")
    if {"source_id", "source_type"}.issubset(reviewed.columns):
        reviewed = reviewed[reviewed.source_id.isin(jobs.get("source_id", [])) &
                            reviewed.source_type.isin(["jobs", "Philippine job advertisement"])].copy()
    else:
        reviewed = reviewed.iloc[0:0].copy()
    verified = storage.read_frame("verified_psf_aai")
    tables = {"cleaned_jobs": jobs, "normalized_jobs": analysis_job_values(jobs), "extracted_job_skills": skills,
              "labeled_competencies": reviewed,
              "verified_psf_aai": verified if not verified.empty else taxonomy,
              "ml_predictions": extracted.reindex(columns=["extraction_id", "source_id", "source_type", "original_phrase", "human_label", "model_prediction", "ml_confidence", "model_name", "agreement"]).rename(columns={"ml_confidence": "confidence_score"}),
              "psf_mapping": mapping, "psf_mapping_reviews": selected_reviews,
              "psf_competency_demand": competency_demand,
              "alignment_results": alignment, "employer_skill_demand": demand,
              "unmapped_skills": unmapped, "emerging_skills": emerging,
              "all_candidates": extracted}
    # Chart audit links back to existing full source evidence without copying ad text.
    columns = ["extraction_id", "source_id", "source_type", "original_phrase", "original_normalized_phrase", "normalized_phrase", "skill_label", "competency_category", "skill_type", "category_conflict", "human_label", "review_reason"]
    allowed_phrases = set(demand.normalized_skill) if statuses and not demand.empty else (set() if statuses else None)
    chart_tables = skill_chart_tables(extracted, jobs, allowed_phrases=allowed_phrases)
    for name in ("chart_skill_occurrences", "chart_phrase_review"):
        chart_tables[name] = chart_tables[name].reindex(columns=columns)
    tables.update(chart_tables)
    tables.update(job_profile_tables(jobs))
    tables.update(location_tables(jobs))
    tables.update(psf_demand_tables(mapping, jobs, taxonomy))
    metadata = {"timestamp": timestamp(), "software_version": VERSION, "settings": cfg,
                "dataset_counts": {"jobs": len(jobs), "psf_competencies": len(taxonomy)},
                "research_sample": {"source": "active cleaned job upload", "selected_rows": len(jobs),
                                    "fingerprint": frame_hash(jobs),
                                    "source_ids": sorted(jobs.get("source_id", pd.Series(dtype=str)).astype(str).unique().tolist()),
                                    "training_data_included": False,
                                    "note": "Training may use other sources. Findings use only selected job records; model evaluation is exported separately from Evaluate models."},
                "uploads": {k:v for k,v in storage.read_json("uploads", {}).items() if k in ("jobs", "psf_aai")},
                "model": {k: v for k, v in storage.read_json("selected_model", {}).items() if k != "metrics"}, "extraction": storage.read_json("extraction_metadata", {}),
                "filters": {"jobs": job_filters, "skills": skill_filters, "alignment_status": statuses},
                "data_preparation": storage.read_json("cleaning_jobs", {}),
                "chart_presentation": {"version": 12, "job_ad_denominator": int(jobs.source_id.nunique()) if "source_id" in jobs else 0,
                    "chartable_skill_ads": int(chart_tables["chart_skill_occurrences"].source_id.nunique()),
                    "ads_without_chartable_skill": max(0, int(jobs.source_id.nunique()) - int(chart_tables["chart_skill_occurrences"].source_id.nunique())) if "source_id" in jobs else 0,
                    "unclear_occurrences": len(chart_tables["chart_phrase_review"]),
                    "policy": "Skill-demand, PSF-mapping, alignment and gap summaries share one source-linked phrase eligibility screen before aggregation. Eligibility requires a recognized named skill/tool, complete capability wording or a concrete technical task after structural checks; generic objects, benefit/opportunity wording and incomplete clauses stay in the review audit. Unfamiliar wording requires source review rather than automatic rejection as a training label. All skill charts (overall, category, occupational-family, title, location, unmapped) use screened occurrences and distinct-ad counts. Canonical wording rules reconcile neutral skill wrappers/suffixes, bounded head inflections and equivalent concrete tasks before per-ad counting; chart_skill_variants preserves all eligible original variants before deduplication. Variant counts overlap. Conflicting broad types within an ad and canonical skill are flagged for category review. Official PSF labels and source-specific mappings are never merged by chart aliases. All candidates, source evidence, saved researcher labels and competency-link decisions are retained unchanged. Power BI/Excel spelling and explicit Scrum method variants share chart labels; standalone Agile stays distinct. Missing placeholders, experience phrases, credentials, irrelevant labels, vague-only wording, unfinished phrases/lists, access-to-benefit fragments, equal-employment boilerplate, generic activity/work wording, and adoption KPI wording stay out of skill charts. Lemmatizer artifact datum displays as data only. Job-title graphs withhold exact missing placeholders and merge only clear single occupations; location graphs use exact-name geography matching and leave missing/unresolved values outside region/city counts. Education and experience plots use structured parsed requirements. PSF-AAI graphs show active reference labels and existing mapping decisions; model graphs show validated label classes and metrics. Source evidence stays auditable; no fuzzy synonym merging. Documented communication variants share communication, and explicit ability-to-learn/learn-and-apply variants share learning and application. Unmapped chart groups suppress mapped aliases and apply recurrence thresholds after canonical distinct-ad aggregation; original phrase-level evidence remains available."},
                "rates_before_status_display_filter": rates,
                "denominators": "Demand: distinct selected job ads, including ads with no detection. Each phrase is counted once in alignment rates using its strongest observed status (aligned, partial, not mapped, unclassified). Alignment and partial rates divide by mapped phrases; unmapped rate divides by assessed phrases. UNCLASSIFIED is excluded from assessment rates. Competency demand counts each advertisement once per competency, regardless of its number of skills or links. Rates precede the status display filter.",
                "limitations": "Thresholds are researcher heuristics, not official PSF standards. Not clearly mapped does not establish absence from the framework. Emerging candidates require human and longitudinal review. Reference roles and levels do not establish applicant proficiency.",
                "libraries": {p: importlib.metadata.version(p) for p in ("pandas", "spacy", "scikit-learn", "streamlit")}}
    return tables, metadata
