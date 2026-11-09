"""Refresh the browser reference from the tracked framework and analysis rules."""
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.analytics import _CHART_PHRASE_ALIASES
from src.column_mapping import ALIASES
from src.config import FIELDS
from src.geography import _CITIES, _REGIONS, PSGC_REFERENCE_DATE, PSGC_SOURCE
from src.job_profile import _COMMON_TITLE_ALIASES, _EDUCATION_LEVELS, _TITLE_ROLE_RULES
from src.skill_extraction import VOCABULARY
from src.psf_source import reference_role_profiles
import pandas as pd


def main():
    fields = ("competency_id", "competency_name", "competency_description", "range_of_application",
              "competency_category", "job_role", "occupational_family", "proficiency_level", "aliases", "keywords", "source_page")
    with (ROOT / "data/reference/psf_aai_default.csv").open(encoding="utf-8-sig", newline="") as source:
        verified = [row for row in csv.DictReader(source) if row["review_status"] == "Researcher verified"]
    if not verified or len({(row["source_url"], row["source_hash"]) for row in verified}) != 1:
        raise ValueError("The bundled PSF-AAI reference needs a single verified source.")
    data = {
        "sourceUrl": verified[0]["source_url"], "sourceHash": verified[0]["source_hash"],
        "geographyUrl": PSGC_SOURCE, "geographyReferenceDate": PSGC_REFERENCE_DATE,
        "competencies": [{key: row[key] for key in fields} for row in verified],
        "roleProfiles": reference_role_profiles(ROOT, pd.DataFrame(verified)),
        "columns": {"source_id": [], **{field: ALIASES["jobs"].get(field, []) for field in FIELDS["jobs"]}},
        "regions": {alias: region for alias, (_, region) in _REGIONS.items()},
        "cities": {alias: [region, city] for alias, (_, region, city) in _CITIES.items()},
        "titleRules": _TITLE_ROLE_RULES, "titleAliases": _COMMON_TITLE_ALIASES,
        "educationLevels": _EDUCATION_LEVELS, "skillAliases": _CHART_PHRASE_ALIASES,
        "skills": {category: terms.split(";") for category, terms in VOCABULARY.items()
                   if category != "Education / Qualification"},
    }
    output = ROOT / "public-web/site/reference.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
