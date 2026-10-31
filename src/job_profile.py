"""Descriptive job-title and qualification evidence from selected job ads."""

import re

import pandas as pd

from .cleaning import EDUCATION, EXPERIENCE, clean_text, normalize_text


_MISSING = {"", "not stated", "not specified", "not provided", "unspecified", "n/a", "na"}
_JOB_CODE_PREFIX = re.compile(r"^\s*[A-Z]{2,6}\d{4,}\s*[-–—:]\s*", re.I)
_YEARS = re.compile(r"(?<![\w.])(?P<low>\d+(?:\.\d+)?)\s*(?:(?:[-–—]|to)\s*(?P<high>\d+(?:\.\d+)?))?\s*(?P<plus>\+)?\s*(?:years?|yrs?)\b", re.I)
_OTHER_UNITS = re.compile(r"\b(?:months?|mos?|weeks?|days?)\b", re.I)
_NO_EXPERIENCE = re.compile(r"\bno\s+(?:(?:prior|previous|work|professional)\s+)*experience\s+(?:is\s+)?(?:required|necessary|needed)\b", re.I)
_TITLE_ROLE_RULES = {
    "data analyst": r"\bdata(?:\s+analytics)?\s+analysts?\b",
    "data scientist": r"\bdata\s+scientists?\b",
    "data engineer": r"\bdata\s+engineers?\b",
    "business analyst": r"\bbusiness\s+analysts?\b",
    "business intelligence analyst": r"\b(?:business\s+intelligence|bi)\s+analysts?\b",
    "business intelligence developer": r"\b(?:business\s+intelligence|bi)\s+developers?\b",
    "machine learning engineer": r"\b(?:machine\s+learning|ml)\s+engineers?\b",
    "artificial intelligence engineer": r"\b(?:artificial\s+intelligence|ai)\s+engineers?\b",
}
_TITLE_OCCUPATIONS = re.compile(
    r"\b(?:analysts?|scientists?|engineers?|developers?|specialists?|officers?|assistants?|consultants?|"
    r"architects?|designers?|managers?|coordinators?|administrators?|owners?|recruiters?|trainers?|"
    r"instructors?|teachers?|auditors?|technicians?|operators?|executives?|directors?)\b"
)
_TITLE_OTHER_ROLE = re.compile(r"\b(?:manager|recruiter|trainer|instructor|teacher|owner|director|head)\b")


def _missing(value):
    return clean_text(value).casefold() in _MISSING


def _analysis_title(value):
    """Drop a clear leading requisition code from analysis labels, not source evidence."""
    original = "" if value is None or pd.isna(value) else str(value)
    return normalize_text(_JOB_CODE_PREFIX.sub("", original, count=1))


def _counts(frame, column, output_name):
    if frame.empty or column not in frame:
        return pd.DataFrame(columns=[column, output_name, "job_ads_pct"])
    values = frame.copy()
    values[column] = values[column].map(normalize_text)
    values = values[values[column].ne("")].copy()
    if "source_id" not in values:
        values["source_id"] = values.index.astype(str)
    result = values.groupby(column).source_id.nunique().rename(output_name).reset_index()
    result = result.sort_values([output_name, column], ascending=[False, True], kind="stable")
    denominator = frame.source_id.nunique() if "source_id" in frame else len(frame)
    result["job_ads_pct"] = (100 * result[output_name] / denominator).round(1) if denominator else 0.0
    return result[[column, output_name, "job_ads_pct"]].reset_index(drop=True)


def _job_role_groups(jobs):
    # Explicit role wording only; related seniority variants may share this family.
    rows = []
    for index, job in jobs.iterrows():
        raw_title = job.get("job_title", "")
        original = "" if raw_title is None or pd.isna(raw_title) else str(raw_title)
        title = _analysis_title(original)
        family = normalize_text(job.get("job_family", ""))
        group, basis = title, "specific title retained"
        if not _missing(family) and family not in {"other", "unclassified", "unknown", "general", "not applicable"}:
            group, basis = family, "source-provided job family"
        elif title:
            matches = [name for name, pattern in _TITLE_ROLE_RULES.items() if re.search(pattern, title)]
            composite = re.search(r"[/|;&,]|\b(?:and|or|cum|manager|trainer|recruiter|instructor|teacher)\b", title)
            role_heads = re.findall(r"\b(?:analysts?|scientists?|engineers?|developers?|specialists?|officers?|assistants?|consultants?)\b", title)
            if len(matches) == 1 and len(role_heads) == 1 and not composite:
                group, basis = matches[0], "explicit title rule: " + matches[0]
        rows.append({"source_id": job.get("source_id", str(index)), "original_job_title": original,
                     "normalized_job_title": title, "job_role_group": group, "grouping_basis": basis})
    evidence = pd.DataFrame(rows, columns=["source_id", "original_job_title", "normalized_job_title", "job_role_group", "grouping_basis"])
    return _counts(evidence, "job_role_group", "job_ads"), evidence


def _common_job_title_tables(jobs):
    """Normalize clear title variants for the common-title chart; retain source evidence."""
    rows = []
    for index, job in jobs.iterrows():
        raw = job.get("job_title", "")
        original = "" if raw is None or pd.isna(raw) else str(raw)
        title = _analysis_title(original)
        matches = [name for name, pattern in _TITLE_ROLE_RULES.items() if re.search(pattern, title)]
        occupations = _TITLE_OCCUPATIONS.findall(title)
        if title and len(matches) == 1 and len(occupations) == 1 and not _TITLE_OTHER_ROLE.search(title):
            common_title = matches[0]
            basis = "explicit occupation match; modifiers consolidated" if title != common_title else "explicit occupation match"
        else:
            common_title, basis = title, "specific or composite title retained"
        rows.append({"source_id": job.get("source_id", str(index)), "original_job_title": original,
                     "normalized_job_title": title, "common_job_title": common_title, "grouping_basis": basis})
    evidence = pd.DataFrame(rows, columns=["source_id", "original_job_title", "normalized_job_title",
                                          "common_job_title", "grouping_basis"])
    return _counts(evidence, "common_job_title", "job_ads"), evidence


_EDUCATION_LEVELS = [
    ("high school", r"\bhigh\s+school\b"),
    ("senior high school", r"\b(?:senior\s+high\s+school|shs|grade\s*12)\b"),
    ("undergraduate / college level", r"\b(?:undergraduate|college[ -]level|college\s+undergrad(?:uate)?)\b"),
    ("associate degree", r"\bassociate(?:['’]s)?\s+(?:degree|of)\b"),
    ("bachelor's degree", r"\b(?:bachelor(?:['’]?s)?|baccalaureate|b\.?\s*sc\.?|b\.?s\.?|b\.?a\.?)\b"),
    ("master's degree", r"\b(?:master(?:['’]?s)?|m\.?\s*sc\.?|m\.?s\.?|m\.?a\.?|mba)\b"),
    ("doctoral degree", r"\b(?:doctorate|doctoral|doctor\s+of|ph\.?\s*d\.?)\b"),
]
_EXPERIENCE_BANDS = ["no experience required", "less than 1 year", "1–2 years", "3–5 years", "6–10 years", "more than 10 years"]


def _education_tables(jobs):
    rows = []
    for index, job in jobs.iterrows():
        raw = job.get("education_requirement", "")
        original = "" if raw is None or pd.isna(raw) else str(raw)
        text = normalize_text(original)
        levels = [name for name, pattern in _EDUCATION_LEVELS if re.search(pattern, text)]
        if "senior high school" in levels and "high school" in levels:
            levels.remove("high school")
        status = "Not stated" if _missing(text) else "Needs review"
        level = ""
        # Alternatives, preferences and negated credentials are not a minimum degree.
        conditional = re.search(r"\b(?:preferred|preferably|optional|not required|no degree|equivalent experience)\b", text)
        if len(levels) == 1 and not conditional:
            level, status = levels[0], "Parsed single level"
        rows.append({"source_id": job.get("source_id", str(index)), "original_requirement": original,
                     "education_level": level, "mentioned_levels": "; ".join(levels), "parse_status": status,
                     "source_field": "education_requirement", "url": job.get("url", "")})
    evidence = pd.DataFrame(rows, columns=["source_id", "original_requirement", "education_level", "mentioned_levels", "parse_status", "source_field", "url"])
    summary = _counts(evidence[evidence.parse_status.eq("Parsed single level")], "education_level", "job_ads")
    order = {name: index for index, (name, _) in enumerate(_EDUCATION_LEVELS)}
    summary["level_order"] = summary.education_level.map(order)
    denominator = len(jobs)
    summary["job_ads_pct"] = (100 * pd.to_numeric(summary.job_ads) / denominator).round(1) if denominator else 0.0
    return summary.sort_values("level_order", kind="stable").reset_index(drop=True), evidence


def _experience_bands(evidence, denominator):
    evidence = evidence.copy()
    bands, statuses = [], []
    for row in evidence.itertuples(index=False):
        low, high = row.min_years, row.max_years
        band, status = "", "Needs review"
        if row.parse_status == "Not stated":
            status = "Not stated"
        elif row.parse_status == "Parsed no experience":
            band, status = "no experience required", "Banded"
        elif row.parse_status.startswith("Parsed") and pd.notna(low) and pd.notna(high):
            if 0 <= low <= high < 1:
                band = "less than 1 year"
            elif 1 <= low <= high <= 2:
                band = "1–2 years"
            elif 3 <= low <= high <= 5:
                band = "3–5 years"
            elif 6 <= low <= high <= 10:
                band = "6–10 years"
            elif 10 < low <= high:
                band = "more than 10 years"
            if band:
                status = "Banded"
        bands.append(band)
        statuses.append(status)
    evidence["experience_band"], evidence["band_status"] = bands, statuses
    summary = _counts(evidence[evidence.band_status.eq("Banded")], "experience_band", "job_ads")
    summary["band_order"] = summary.experience_band.map({name: index for index, name in enumerate(_EXPERIENCE_BANDS)})
    summary["job_ads_pct"] = (100 * pd.to_numeric(summary.job_ads) / denominator).round(1) if denominator else 0.0
    return summary.sort_values("band_order", kind="stable").reset_index(drop=True), evidence


def _title_family_tables(jobs):
    rows = []
    for index, job in jobs.iterrows():
        family = normalize_text(job.get("job_family", ""))
        if _missing(family):
            family = "not stated"
        raw = job.get("job_title", "")
        original = "" if raw is None or pd.isna(raw) else str(raw)
        rows.append({"source_id": job.get("source_id", str(index)), "job_family": family,
                     "job_title": _analysis_title(original), "original_job_title": original,
                     "source": normalize_text(job.get("source", "")), "url": job.get("url", "")})
    evidence = pd.DataFrame(rows, columns=["source_id", "job_family", "job_title", "original_job_title", "source", "url"])
    grouped = evidence[evidence.job_title.ne("")].groupby(["job_family", "job_title"], sort=True)
    summary = grouped.agg(job_ads=("source_id", "nunique"), sources=("source", lambda values: "; ".join(sorted(set(values) - {""})))).reset_index()
    summary["job_ads_pct"] = (100 * summary.job_ads / len(jobs)).round(1) if len(jobs) else 0.0
    return summary[["job_family", "job_title", "job_ads", "job_ads_pct", "sources"]], evidence


def _experience_years(value):
    """Parse explicit time expressions, leaving ambiguous requirements for review."""
    text = clean_text(value)
    if _missing(text):
        return "", None, None, "Not stated"
    if re.search(r"\b(?:age|aged)\b|\byears?\s+old\b", text, re.I):
        return "", None, None, "Needs review"
    matches = list(_YEARS.finditer(text))
    if _NO_EXPERIENCE.search(text):
        if not matches and not _OTHER_UNITS.search(text):
            return "no experience required", 0., 0., "Parsed no experience"
        return "", None, None, "Needs review"
    if len(matches) != 1 or _OTHER_UNITS.search(text):
        return "", None, None, "Needs review"
    match = matches[0]
    if re.search(r"[-\u2212]\s*$", text[:match.start()]):
        return "", None, None, "Needs review"
    remainder = text[:match.start()] + text[match.end():]
    # Extra numeric clauses or alternatives may describe different experience areas.
    if re.search(r"\d|[<>≥≤]|\b(?:more than|less than|under|over)\b", remainder, re.I):
        return "", None, None, "Needs review"
    lower = bool(match["plus"] or re.match(r"\s*\+", text[match.end():])
                 or re.search(r"\b(?:at least|minimum(?: of)?|min\.?)\s*$", text[:match.start()], re.I)
                 or re.search(r"\b(?:or more|or above|and above)\b", text[match.end():], re.I))
    upper = bool(re.search(r"\b(?:up to|at most|maximum(?: of)?|max\.?)\s*$", text[:match.start()], re.I))
    if re.search(r"\bor\b", re.sub(r"\bor (?:more|above)\b", "", remainder, flags=re.I), re.I) or (lower and upper):
        return "", None, None, "Needs review"
    low = float(match["low"])
    high = float(match["high"]) if match["high"] else None
    if high is not None:
        if high < low or lower or upper:
            return "", None, None, "Needs review"
        return f"{low:g}–{high:g} years", low, high, "Parsed range"
    if lower:
        return f"at least {low:g} years", low, None, "Parsed minimum"
    if upper:
        return f"up to {low:g} years", None, low, "Parsed maximum"
    return f"{low:g} years stated", low, low, "Parsed stated years"


def experience_phrase_reason(value):
    """Keep experience duration and malformed year fragments out of skill matching."""
    text = clean_text(value)
    if _NO_EXPERIENCE.search(text):
        return "No-experience requirement, not a skill"
    if not re.search(r"\b(?:years?|yrs?)\b", text, re.I):
        return ""
    status = _experience_years(text)[3]
    return ("Experience-duration requirement, not a skill" if status.startswith("Parsed")
            else "Unclear year-duration phrase, not a skill")


def _experience_tables(jobs):
    rows = []
    for _, job in jobs.iterrows():
        original = job.get("experience_requirement", "")
        original = "" if original is None or pd.isna(original) else str(original)
        label, minimum, maximum, status = _experience_years(original)
        rows.append({"source_id": job.get("source_id", ""), "job_title": job.get("job_title", ""),
                     "original_requirement": original, "requirement": label,
                     "min_years": minimum, "max_years": maximum, "parse_status": status,
                     "source_field": "experience_requirement", "url": job.get("url", "")})
    evidence = pd.DataFrame(rows, columns=["source_id", "job_title", "original_requirement", "requirement",
                                         "min_years", "max_years", "parse_status", "source_field", "url"])
    parsed = evidence[evidence.parse_status.str.startswith("Parsed")]
    summary = _counts(parsed, "requirement", "job_ads")
    denominator = jobs.source_id.nunique() if "source_id" in jobs else len(jobs)
    summary["job_ads_pct"] = (100 * pd.to_numeric(summary.job_ads) / denominator).round(1) if denominator else 0.0
    coverage = []
    for field in ("education_requirement", "experience_requirement"):
        missing = jobs.get(field, pd.Series("", index=jobs.index)).map(_missing)
        stated = int((~missing).sum())
        coverage.append({"source_field": field, "stated_job_ads": stated,
                         "not_stated_job_ads": int(missing.sum()), "job_ads": len(jobs),
                         "stated_pct": round(100 * stated / len(jobs), 1) if len(jobs) else 0.0})
    return summary, evidence, pd.DataFrame(coverage)


def _requirements(jobs, field, patterns=()):
    """Return explicit-field distribution plus traceable text evidence candidates."""
    if jobs.empty:
        return (pd.DataFrame(columns=["requirement", "job_ads"]),
                pd.DataFrame(columns=["source_id", "job_title", "requirement_type", "phrase", "source_field", "evidence", "url"]))

    explicit_rows = []
    evidence_rows = []
    for _, job in jobs.iterrows():
        source_id = clean_text(job.get("source_id", ""))
        title = clean_text(job.get("job_title", ""))
        url = clean_text(job.get("url", ""))
        explicit = clean_text(job.get(field, ""))
        explicit_rows.append({"source_id": source_id, "requirement": "Not stated" if _missing(explicit) else explicit})
        if not _missing(explicit):
            evidence_rows.append({"source_id": source_id, "job_title": title,
                                  "requirement_type": field.removesuffix("_requirement").title(),
                                  "phrase": explicit, "source_field": field,
                                  "evidence": explicit, "url": url,
                                  "evidence_status": "Source-provided requirement"})

        # Text matching only creates reviewable candidates; it never upgrades a mention
        # to a confirmed requirement. Search qualifications first, then description.
        for text_field in ("qualifications", "job_description", "required_skills", "preferred_skills"):
            text = clean_text(job.get(text_field, ""))
            for pattern in patterns:
                for match in pattern.finditer(text):
                    start, end = match.span()
                    evidence = text[max(0, start - 90):min(len(text), end + 90)]
                    evidence_rows.append({"source_id": source_id, "job_title": title,
                                          "requirement_type": "Education" if pattern is EDUCATION else "Experience",
                                          "phrase": clean_text(match.group()), "source_field": text_field,
                                          "evidence": evidence, "url": url,
                                          "evidence_status": "Text mention candidate; researcher should verify context"})
    explicit_frame = pd.DataFrame(explicit_rows)
    summary = _counts(explicit_frame, "requirement", "job_ads")
    evidence = pd.DataFrame(evidence_rows)
    if not evidence.empty:
        evidence = evidence.drop_duplicates(["source_id", "requirement_type", "phrase", "source_field", "evidence"])
        evidence = evidence.sort_values(["requirement_type", "phrase", "job_title"], kind="stable")
    return summary, evidence


def job_profile_tables(jobs):
    """Build export-ready job-market tables using unique advertisements as units."""
    job_ads = jobs.drop_duplicates("source_id") if "source_id" in jobs else jobs.copy()
    common_titles, common_title_evidence = _common_job_title_tables(job_ads)
    role_groups, title_group_evidence = _job_role_groups(job_ads)
    title_families, title_sources = _title_family_tables(job_ads)
    titles = _counts(title_sources, "job_title", "job_ads").sort_values("job_title", kind="stable").reset_index(drop=True)
    families = _counts(job_ads, "job_family", "job_ads")
    locations = _counts(job_ads, "location", "job_ads")
    education, education_evidence = _requirements(job_ads, "education_requirement", (EDUCATION,))
    experience, experience_evidence = _requirements(job_ads, "experience_requirement", (EXPERIENCE,))
    evidence = pd.concat([education_evidence, experience_evidence], ignore_index=True)
    years, year_evidence, coverage = _experience_tables(job_ads)
    education_levels, education_level_evidence = _education_tables(job_ads)
    experience_bands, experience_band_evidence = _experience_bands(year_evidence, len(job_ads))
    tables = {"job_title_counts": titles,
              "common_job_title_counts": common_titles,
              "common_job_title_evidence": common_title_evidence,
              "job_role_group_counts": role_groups,
              "job_title_group_evidence": title_group_evidence,
              "job_family_counts": families,
              "location_counts": locations,
              "education_requirement_counts": education,
              "experience_requirement_counts": experience,
              "requirement_evidence": evidence,
              "experience_year_counts": years,
              "experience_year_evidence": year_evidence,
              "requirement_field_coverage": coverage,
              "education_level_counts": education_levels,
              "education_level_evidence": education_level_evidence,
              "experience_band_counts": experience_bands,
              "experience_band_evidence": experience_band_evidence,
              "job_title_family_counts": title_families,
              "job_title_source_evidence": title_sources}
    return tables
