import importlib.metadata
import pandas as pd
from . import storage
from .config import ROOT, VERSION
from .utils import frame_hash, digest, timestamp
from .classification import cached_load_model
from .psf_mapping import TaxonomyMatcher
from .skill_extraction import extract_skills
from .analytics import accepted_skills, filter_frame
from .alignment import calculate_alignment
from .gap_analysis import calculate_gaps
from .labeling import apply_corrections

def input_signature():
    return digest({"datasets": {k: frame_hash(storage.read_frame("cleaned_"+k)) for k in ("jobs", "psf_aai")},
                   "active_uploads": {k:v["hash"] for k,v in storage.read_json("uploads", {}).items() if k in ("jobs", "psf_aai")},
                   "column_mappings": {k:storage.read_json("mapping_"+k, {}) for k in ("jobs", "psf_aai")},
                   "annotations": frame_hash(storage.read_frame("labeled_competencies")), "settings": storage.settings(), "model": storage.read_json("selected_model", {}), "version": VERSION})

def run_extraction():
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
    annotations = storage.read_frame("labeled_competencies")
    frames, diagnostics = [], []
    for kind in ("jobs",):
        frame = storage.read_frame("cleaned_" + kind)
        result, processed = extract_skills(frame, kind, matcher, model, annotations, stopwords=settings["stopwords"], batch_size=settings["batch_size"], max_candidates=settings["max_candidates"])
        frames.append(result)
        diagnostics.append(processed)
    populated = [frame for frame in frames if not frame.empty]
    output = pd.concat(populated, ignore_index=True) if populated else frames[0]
    if output.empty:
        raise ValueError("No phrases were found. Upload, map and clean text datasets first.")
    storage.save_frame("extractions_original", output)
    storage.save_frame("nlp_processed", pd.concat(diagnostics, ignore_index=True))
    storage.save_json("extraction_metadata", {"signature": input_signature(), "timestamp": timestamp(), "taxonomy_available": matcher is not None, "model_available": model is not None})
    return output

def current_extractions():
    extracted = apply_corrections(storage.read_frame("extractions_original"), "extraction", "extraction_id")
    if not extracted.empty:
        # Human PSF edits update the identity and related taxonomy fields together.
        taxonomy = storage.read_frame("cleaned_psf_aai")
        if not taxonomy.empty:
            references = taxonomy.set_index("competency_name")
            known = extracted.psf_competency.isin(references.index)
            extracted.loc[known, "matched_competency"] = extracted.loc[known, "psf_competency"]
            for target, column in (("competency_id", "competency_id"), ("psf_category", "competency_category"), ("job_role", "job_role"), ("proficiency_level", "proficiency_level"), ("source_page", "source_page"), ("source_url", "source_url"), ("source_hash", "source_hash")):
                extracted.loc[known, target] = extracted.loc[known, "psf_competency"].map(references[column]) if column in references else ""
        unmapped = extracted.psf_competency.eq("")
        extracted.loc[unmapped, "matched_competency"] = extracted.loc[unmapped, "normalized_phrase"]
        extracted.loc[unmapped, ["competency_id", "psf_category", "job_role", "proficiency_level"]] = ""
        category = extracted.competency_category.str.casefold()
        extracted["skill_type"] = "Other / Unclassified"
        extracted.loc[category.str.contains("technical|digital|data|analytics|machine|ai /", regex=True), "skill_type"] = "Technical"
        extracted.loc[category.str.contains("soft|enabling|leadership", regex=True), "skill_type"] = "Soft / Enabling"
    return extracted

def analysis_bundle(job_filters=None, skill_filters=None, statuses=None):
    jobs = filter_frame(storage.read_frame("cleaned_jobs"), job_filters or {})
    taxonomy = storage.read_frame("cleaned_psf_aai")
    extracted = current_extractions()
    if not extracted.empty:
        extracted = extracted[extracted.source_type.eq("jobs") & extracted.source_id.isin(jobs.get("source_id", []))]
        extracted = filter_frame(extracted, skill_filters or {})
    skills = accepted_skills(extracted)
    cfg = storage.settings()
    alignment = calculate_alignment(skills, taxonomy, cfg["aligned_threshold"], cfg["partial_threshold"], cfg["semantic_model"], cfg["semantic_threshold"])
    alignment = apply_corrections(alignment, "alignment", "alignment_id")
    demand, unmapped, emerging, rates = calculate_gaps(skills, jobs, alignment, cfg["emerging_min_jobs"])
    if statuses:
        alignment = alignment[alignment.status.isin(statuses)]
        demand = demand[demand.status.isin(statuses)]
        unmapped = unmapped[unmapped.status.isin(statuses)]
        emerging = emerging[emerging.status.isin(statuses)]
    # Occurrence-level mappings and distinct-phrase alignment share the same reference evidence.
    mapping = skills.reindex(columns=["extraction_id", "source_id", "original_phrase", "normalized_phrase"])
    mapping = mapping.rename(columns={"original_phrase": "employer_skill", "normalized_phrase": "normalized_skill"})
    mapping = mapping.merge(alignment.drop(columns=["employer_skill", "job_source_ids"]), on="normalized_skill", how="inner")
    verified = storage.read_frame("verified_psf_aai")
    tables = {"cleaned_jobs": jobs, "extracted_job_skills": skills,
              "labeled_competencies": storage.read_frame("labeled_competencies"),
              "verified_psf_aai": verified if not verified.empty else taxonomy,
              "ml_predictions": extracted.reindex(columns=["extraction_id", "source_id", "source_type", "original_phrase", "human_label", "model_prediction", "ml_confidence", "model_name", "agreement"]).rename(columns={"ml_confidence": "confidence_score"}),
              "psf_mapping": mapping, "alignment_results": alignment, "employer_skill_demand": demand,
              "unmapped_skills": unmapped, "emerging_skills": emerging,
              "model_metrics": storage.read_frame("model_metrics"), "all_candidates": extracted,
              "test_predictions": pd.read_csv(ROOT/"outputs/tables/test_predictions.csv", keep_default_na=False) if (ROOT/"outputs/tables/test_predictions.csv").exists() else pd.DataFrame(),
              "stakeholder": storage.read_frame("cleaned_stakeholder")}
    metadata = {"timestamp": timestamp(), "software_version": VERSION, "settings": cfg,
                "dataset_counts": {"jobs": len(jobs), "psf_competencies": len(taxonomy)},
                "uploads": {k:v for k,v in storage.read_json("uploads", {}).items() if k in ("jobs", "psf_aai")},
                "model": storage.read_json("selected_model", {}), "extraction": storage.read_json("extraction_metadata", {}),
                "filters": {"jobs": job_filters, "skills": skill_filters, "alignment_status": statuses},
                "rates_before_status_display_filter": rates,
                "denominators": "Demand: distinct selected job ads, including ads with no detection. Alignment and partial rates: distinct ALIGNED + PARTIALLY ALIGNED employer phrases. Unmapped rate: all assessed distinct phrases. UNCLASSIFIED is excluded from assessment rates. Rates precede the status display filter.",
                "limitations": "Thresholds are researcher heuristics, not official PSF standards. Not clearly mapped does not establish absence from the framework. Emerging candidates require human and longitudinal review. Reference roles and levels do not establish applicant proficiency.",
                "libraries": {p: importlib.metadata.version(p) for p in ("pandas", "spacy", "scikit-learn", "streamlit")}}
    return tables, metadata
