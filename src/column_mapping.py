"""Conservative, local header matching; researcher choices remain editable."""
import re
import unicodedata
from rapidfuzz.fuzz import ratio
from .config import FIELDS

ALIASES = {
    "jobs": {
        "job_id": ["vacancy id", "posting id", "advertisement id"],
        "job_title": ["position", "position title", "title", "role", "job name"],
        "job_family": ["job family", "occupational family", "occupation group", "role family"],
        "company": ["employer", "company name", "organization"],
        "industry": ["sector", "industry sector"],
        "location": ["job location", "work location", "city"],
        "job_description": ["description", "details", "job details", "responsibilities", "description text"],
        "required_skills": ["skills", "skills summary", "technical skills", "skills required", "skills desc"],
        "preferred_skills": ["preferred competencies", "desirable skills"],
        "qualifications": ["qualification", "job qualifications", "requirements"],
        "education_requirement": ["education requirements", "education requirements summary", "education level", "educational attainment", "education"],
        "experience_requirement": ["experience requirements", "experience summary", "work experience", "experience", "formatted experience level"],
        "employment_type": ["job type", "contract type", "formatted work type"],
        "posting_date": ["posted date", "date posted", "publication date", "date published"],
        "source": ["job board", "source name", "platform"],
        "url": ["source url", "source_url", "job url", "posting url", "link", "job posting url"],
        "salary": ["pay", "compensation", "salary range"],
        "employment_size": ["company size", "employer size", "organization size"],
        "search_term": ["query", "collection query", "search query"],
        "collected_at_utc": ["collection time", "collected at", "collected timestamp"],
    },
    "psf_aai": {
        "competency_id": ["competency code", "skill id", "skill code"],
        "competency_name": ["competency", "skill name", "skill", "competence"],
        "competency_description": ["description", "skill description", "definition"],
        "range_of_application": ["range of application", "range/application", "application range", "range of contexts"],
        "competency_category": ["category", "skill category", "domain"],
        "job_role": ["role", "occupation", "job title"],
        "functional_skill": ["functional skills", "technical skill"],
        "enabling_skill": ["enabling skills", "soft skill"],
        "proficiency_level": ["proficiency", "level", "skill level"],
        "keywords": ["key words", "search terms"],
        "aliases": ["alias", "synonyms", "alternate names"],
        "source_page": ["pdf page", "page number", "page"],
        "source_url": ["reference url", "url", "source link"],
    },
    "stakeholder": {
        "respondent_type": ["respondent category", "participant type"],
        "role": ["position", "job title"],
        "organization": ["institution", "company", "employer"],
        "competency": ["skill", "competency name"],
        "importance_rating": ["importance", "importance score"],
        "usability_rating": ["usability", "usability score"],
        "comment": ["comments", "feedback"],
        "recommendation": ["recommendations", "suggestions"],
    },
}

def normalize_header(value):
    value = re.sub(r"([a-z])([A-Z])", r"\1 \2", str(value))
    return re.sub(r"[^a-z0-9]+", "", unicodedata.normalize("NFKC", value).casefold())

def suggest_column_mapping(columns, kind, saved=None):
    if kind not in FIELDS:
        raise ValueError("Unknown dataset type for column mapping.")
    columns = list(columns)
    saved = saved or {}
    mapping = {field: "" for field in FIELDS[kind]}
    evidence, used, unresolved = {}, set(), set()
    # Saved researcher decisions take precedence; duplicate/stale assignments are not reused.
    for field in mapping:
        column = saved.get(field)
        if field in saved and column == "":
            unresolved.add(field)
            evidence[field] = {"field": field, "source_column": "", "method": "saved choice", "score": None, "status": "Previously left blank"}
        if column in columns and column not in used:
            mapping[field] = column
            used.add(column)
            evidence[field] = {"field": field, "source_column": column, "method": "saved choice", "score": None, "status": "Reused"}
    vocabulary = {field: [normalize_header(field)] + [normalize_header(term) for term in ALIASES[kind].get(field, [])] for field in mapping}
    # Canonical matches across all fields are reserved before aliases and fuzzy matches.
    for stage in ("canonical", "alias", "similar header"):
        proposals = {}
        for field in mapping:
            if mapping[field] or field in unresolved:
                continue
            scored = []
            for column in columns:
                if column in used:
                    continue
                header = normalize_header(column)
                if stage == "canonical":
                    score = 100. if header == vocabulary[field][0] else 0.
                elif stage == "alias":
                    score = 100. if header in vocabulary[field][1:] else 0.
                else:
                    score = max((ratio(header, term) for term in vocabulary[field] if min(len(header), len(term)) >= 5), default=0.)
                if score >= (90. if stage == "similar header" else 100.):
                    scored.append((score, column))
            scored.sort(key=lambda pair: (-pair[0], pair[1]))
            if not scored:
                continue
            # Exact alias ordering expresses specificity, but competing aliases are left for review.
            if len(scored) > 1 and scored[0][0] - scored[1][0] < 5:
                unresolved.add(field)
                evidence[field] = {"field": field, "source_column": "", "method": stage, "score": scored[0][0], "status": "Ambiguous: " + ", ".join(column for _,column in scored)}
                continue
            proposals[field] = scored[0]
        for field, (score, column) in proposals.items():
            competing = [other for other,value in proposals.items() if value[1] == column]
            if len(competing) > 1:
                unresolved.add(field)
                evidence[field] = {"field": field, "source_column": "", "method": stage, "score": score, "status": "Ambiguous destination: " + ", ".join(competing)}
                continue
            mapping[field] = column
            used.add(column)
            evidence[field] = {"field": field, "source_column": column, "method": stage, "score": round(score, 1), "status": "Review suggestion" if stage == "similar header" else "Suggested"}
    for field in mapping:
        evidence.setdefault(field, {"field": field, "source_column": "", "method": "", "score": None, "status": "No clear match"})
    return mapping, [evidence[field] for field in mapping]
