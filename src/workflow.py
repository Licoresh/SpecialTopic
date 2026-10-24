from .category_schema import requirement_type, category_parent, skill_type
import importlib.metadata
import pandas as pd
from . import storage
from .config import ROOT, VERSION
from .utils import frame_hash, digest, timestamp
from .classification import cached_load_model
from .psf_mapping import TaxonomyMatcher
from .skill_extraction import extract_skills
from .analytics import accepted_skills, filter_frame
from .alignment import calculate_mapping, summarize_alignment
from .psf_reviews import REVIEW_TABLE
from .gap_analysis import calculate_gaps
from .labeling import apply_corrections

def input_signature():
    return digest({"datasets": {k: frame_hash(storage.read_frame("cleaned_"+k)) for k in ("jobs", "psf_aai")},
                   "active_uploads": {k:v["hash"] for k,v in storage.read_json("uploads", {}).items() if k in ("jobs", "psf_aai")},
                   "column_mappings": {k:storage.read_json("mapping_"+k, {}) for k in ("jobs", "psf_aai")},
                   "annotations": frame_hash(storage.read_frame("labeled_competencies")), "settings": storage.settings(), "model": storage.read_json("selected_model", {}), "version": VERSION})


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
    for kind, upload in storage.read_json("uploads", {}).items():
        if kind not in ("jobs", "psf_aai"):
            continue
        cleaned = storage.read_frame("cleaned_" + kind)
        if cleaned.empty or "_dataset_hash" not in cleaned or not cleaned._dataset_hash.eq(upload["hash"]).all():
            raise ValueError(f"The active {kind} upload has not been mapped and cleaned. Complete these steps before extraction.")
        if kind == "jobs" and not storage.read_json("cleaning_jobs", {}).get("philippine_aai_scope_reviewed", False):
            raise ValueError("Review the job sources for Philippine provenance and AI/analytics relevance on Data Quality before extraction.")
        mapped = storage.read_frame("mapped_" + kind)
        if mapped.empty or storage.read_json("cleaning_"+kind, {}).get("source_hash") != frame_hash(mapped):
            raise ValueError(f"The {kind} column mapping changed or has not been cleaned. Save its cleaned dataset again.")
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
                {"signature": signature, "retry_signature": retry_signature, "timestamp": timestamp(), "taxonomy_available": matcher is not None, "model_available": model is not None})
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
    jobs = filter_frame(jobs_source, job_filters or {})
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
    tables = {"cleaned_jobs": jobs, "extracted_job_skills": skills,
              "labeled_competencies": reviewed,
              "verified_psf_aai": verified if not verified.empty else taxonomy,
              "ml_predictions": extracted.reindex(columns=["extraction_id", "source_id", "source_type", "original_phrase", "human_label", "model_prediction", "ml_confidence", "model_name", "agreement"]).rename(columns={"ml_confidence": "confidence_score"}),
              "psf_mapping": mapping, "psf_mapping_reviews": selected_reviews,
              "psf_competency_demand": competency_demand,
              "alignment_results": alignment, "employer_skill_demand": demand,
              "unmapped_skills": unmapped, "emerging_skills": emerging,
              "all_candidates": extracted}
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
                "rates_before_status_display_filter": rates,
                "denominators": "Demand: distinct selected job ads, including ads with no detection. Each phrase is counted once in alignment rates using its strongest observed status (aligned, partial, not mapped, unclassified). Alignment and partial rates divide by mapped phrases; unmapped rate divides by assessed phrases. UNCLASSIFIED is excluded from assessment rates. Competency demand counts each advertisement once per competency, regardless of its number of skills or links. Rates precede the status display filter.",
                "limitations": "Thresholds are researcher heuristics, not official PSF standards. Not clearly mapped does not establish absence from the framework. Emerging candidates require human and longitudinal review. Reference roles and levels do not establish applicant proficiency.",
                "libraries": {p: importlib.metadata.version(p) for p in ("pandas", "spacy", "scikit-learn", "streamlit")}}
    return tables, metadata
