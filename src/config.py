from pathlib import Path
import os

VERSION = "2.0.63"
ROOT = Path(os.environ.get("FOW_HOME", Path(__file__).resolve().parents[1]))
SEED = 42
FIELDS = {
    "jobs": "job_id job_title job_family company industry location job_description required_skills preferred_skills qualifications education_requirement experience_requirement employment_type posting_date source url salary employment_size search_term collected_at_utc".split(),
    "psf_aai": "competency_id competency_name competency_description range_of_application competency_category job_role functional_skill enabling_skill proficiency_level keywords aliases source_page source_url source_hash review_status".split(),
    "stakeholder": "respondent_type role organization competency importance_rating usability_rating comment recommendation".split(),
}
TEXT_FIELDS = {
    "jobs": "job_title job_description required_skills preferred_skills qualifications education_requirement experience_requirement".split(),
}
DEFAULTS = {"aligned_threshold": .8, "partial_threshold": .6, "fuzzy_threshold": .9,
            "semantic_threshold": .8, "semantic_model": "", "stopwords": [],
            "likert_min": 1, "likert_max": 5, "batch_size": 64, "max_candidates": 300, "emerging_min_jobs": 2}
LABELS = ["AI / Machine Learning", "Data / Analytics", "Technical / Digital", "Business / Domain",
          "Soft / Enabling", "Leadership / Management", "Education / Qualification", "IRRELEVANT"]
