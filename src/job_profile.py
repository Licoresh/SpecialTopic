"""Descriptive job-title and qualification evidence from selected job ads."""

import html
import re

import pandas as pd

from .cleaning import EDUCATION, EXPERIENCE, clean_text, normalize_text


_MISSING = {"", "not stated", "not specified", "not provided", "not available", "unspecified",
            "unknown", "none", "null", "nil", "no information", "no info", "not applicable",
            "n/a", "na", "-", "—"}
_JOB_CODE_PREFIX = re.compile(r"^\s*[A-Z]{2,6}\d{4,}\s*[-–—:]\s*", re.I)
_NUMBER_WORDS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40,
    "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
}
_NUMBER_TOKEN = r"(?:\d+(?:\.\d+)?|(?:twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety)(?:[- ](?:one|two|three|four|five|six|seven|eight|nine))?|zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen)"
_YEARS = re.compile(
    rf"(?<![\w.])(?:between\s+(?P<between_low>{_NUMBER_TOKEN})\s+and\s+(?P<between_high>{_NUMBER_TOKEN})"
    rf"|(?P<low>{_NUMBER_TOKEN})(?:\s*(?:[-–—]|\bto\b)\s*(?P<high>{_NUMBER_TOKEN}))?)"
    r"\s*(?P<plus>\+)?\s*(?:years?|yrs?)\b", re.I,
)
_DURATION_SEPARATOR = re.compile(r"[,;]|\bincluding\b", re.I)
_OTHER_UNITS = re.compile(r"\b(?:months?|mos?|weeks?|days?)\b", re.I)
_NO_EXPERIENCE = re.compile(r"\bno\s+(?:(?:prior|previous|work|professional)\s+)*experience\s+(?:is\s+)?(?:required|necessary|needed)\b", re.I)
_EDUCATION_DURATION_AFTER = re.compile(
    r"\b(?:years?|yrs?)\s+(?:of|in)\s+(?:a\s+|an\s+|the\s+)?"
    r"(?:college|university|school|education|academic(?:\s+study)?|degree|course|study|"
    r"undergraduate|graduate|vocational|shs|senior\s+high|grade\s*\d+)\b", re.I)
_EDUCATION_DURATION_BEFORE = re.compile(
    r"\b(?:college|university|school|education|academic(?:\s+study)?|degree|course|study)\s+(?:for\s+)?$", re.I)
_EXPERIENCE_CONTEXT = re.compile(r"\b(?:experience|experienced|employment|work\s+history|worked|working|career|tenure|professional\s+background)\b", re.I)
_ROLE_DURATION_CONTEXT = re.compile(r"\b(?:years?|yrs?)\s+(?:of\s+(?:this\s+)?(?:job|role|position|profession|industry|field)|as\s+(?:an?\s+)?|in\s+(?:the\s+)?(?:(?:same|similar|related|relevant|previous)\s+)?(?:job|role|position|field|industry))\b", re.I)
_QUALIFICATION_CONTEXT = re.compile(r"\b(?:relevant|professional|related|prior|proven|minimum|at\s+least|must\s+have|required|requirement)\b", re.I)
_EMPLOYER_HISTORY_BEFORE = re.compile(r"\b(?:we|our company|the company|the firm|the organization)\s+(?:have|has|bring|brings|boast|boasts)\s*$", re.I)
_EMPLOYER_HISTORY_AFTER = re.compile(r"^\s+of\s+experience\s*,\s+(?:we|our)\b", re.I)
_TEXT_REQUIREMENT_FIELDS = ("qualifications", "job_description", "required_skills", "preferred_skills")
_TITLE_ROLE_RULES = {
    "data analyst": r"\bdata(?:\s+analytics)?\s+analysts?\b",
    "data scientist": r"\bdata\s+scientists?\b",
    "data engineer": r"\bdata\s+engineers?\b",
    "data analytics engineer": r"\bdata\s+analytics\s+engineers?\b",
    "business analyst": r"\bbusiness\s+analysts?\b",
    "business intelligence analyst": r"\b(?:business\s+intelligence(?:\s*\(\s*bi\s*\))?|bi)\s+analysts?\b",
    "business intelligence developer": r"\b(?:business\s+intelligence|bi)\s+developers?\b",
    "machine learning engineer": r"\b(?:machine\s+learning|ml)\s+engineers?\b",
    "artificial intelligence engineer": r"\b(?:artificial\s+intelligence|ai)\s+engineers?\b",
    "actuarial analyst": r"\bactuarial\s+analysts?\b",
    "analytics consultant": r"\banalytics\s+consultants?\b",
    "analytics engineer": r"(?<!data )\banalytics\s+engineers?\b",
    "business analytics analyst": r"\bbusiness\s+analytics\s+analysts?\b",
    "credit analyst": r"\bcredit\s+analysts?\b",
    "financial analyst": r"\bfinancial\s+analysts?\b",
    "financial planning analyst": r"\bfinancial\s+planning\s+analysts?\b",
    "operations analyst": r"\boperations\s+analysts?\b",
    "pricing analyst": r"\bpricing\s+analysts?\b",
    "reporting analyst": r"\breporting\s+analysts?\b",
    "risk analyst": r"\brisk\s+analysts?\b",
    "sales analyst": r"\bsales\s+analysts?\b",
    "statistical specialist": r"\bstatistical\s+specialists?\b",
    "statistician": r"\bstatisticians?\b",
}
_TITLE_OCCUPATIONS = re.compile(
    r"\b(?:analysts?|scientists?|engineers?|developers?|specialists?|officers?|assistants?|consultants?|"
    r"architects?|designers?|managers?|coordinators?|administrators?|owners?|recruiters?|trainers?|"
    r"instructors?|teachers?|auditors?|technicians?|operators?|executives?|directors?|statisticians?)\b"
)
_TITLE_OTHER_ROLE = re.compile(r"\b(?:manager|recruiter|trainer|instructor|teacher|owner|director|head)\b")
_COMMON_TITLE_ALIASES = {
    "business analyst (erp functional consultant)": "business analyst",
}


def _missing(value):
    return clean_text(value).casefold() in _MISSING


def _analysis_title(value):
    """Drop a clear leading requisition code from analysis labels, not source evidence."""
    original = "" if value is None or pd.isna(value) else str(value)
    return normalize_text(_JOB_CODE_PREFIX.sub("", original, count=1))


def _explicit_title_role(value):
    matches = [name for name, pattern in _TITLE_ROLE_RULES.items() if re.search(pattern, value)]
    occupations = _TITLE_OCCUPATIONS.findall(value)
    if len(matches) == 1 and len(occupations) == 1 and not _TITLE_OTHER_ROLE.search(value):
        return matches[0]
    return ""


def _common_title_label(title):
    alias = _COMMON_TITLE_ALIASES.get(title)
    if alias:
        return alias, "documented occupation alias"
    parts = [part for part in re.split(r"\s*/\s*", title) if part]
    if len(parts) > 1:
        roles = [_COMMON_TITLE_ALIASES.get(part) or _explicit_title_role(part) for part in parts]
        if all(roles) and len(set(roles)) == 1:
            return roles[0], "repeated same occupation; modifiers consolidated"
    role = _explicit_title_role(title)
    if role:
        basis = "explicit occupation match; modifiers consolidated" if title != role else "explicit occupation match"
        return role, basis
    return title, "specific or composite title retained"


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
        if not _missing(family) and family not in {"other", "unclassified", "general"}:
            group, basis = family, "source-provided job family"
        elif not _missing(title):
            group, basis = _common_title_label(title)
            if basis.startswith("explicit occupation match"):
                basis = "explicit title rule: " + group
        else:
            group, basis = "", "missing title placeholder"
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
        if _missing(title):
            rows.append({"source_id": job.get("source_id", str(index)), "original_job_title": original,
                         "normalized_job_title": title, "common_job_title": "",
                         "grouping_basis": "missing title placeholder"})
            continue
        common_title, basis = _common_title_label(title)
        rows.append({"source_id": job.get("source_id", str(index)), "original_job_title": original,
                     "normalized_job_title": title, "common_job_title": common_title, "grouping_basis": basis})
    evidence = pd.DataFrame(rows, columns=["source_id", "original_job_title", "normalized_job_title",
                                          "common_job_title", "grouping_basis"])
    return _counts(evidence, "common_job_title", "job_ads"), evidence


def job_title_timeline(jobs):
    """Count distinct dated ads by canonical title; preserve missing-date evidence."""
    ads = (jobs.drop_duplicates("source_id") if "source_id" in jobs else jobs).reset_index(drop=True)
    _, titles = _common_job_title_tables(ads)
    evidence = titles[["source_id", "common_job_title", "original_job_title"]].rename(
        columns={"common_job_title": "job_title"})
    # Cleaned dates remain authoritative, including blanks; collection dates are never used.
    date_field = "posting_date_parsed" if "posting_date_parsed" in ads else "posting_date"
    raw_dates = ads.get(date_field, pd.Series("", index=ads.index)).map(clean_text)
    number_parts = raw_dates.str.findall(r"\d+").str.len()
    has_month_name = raw_dates.str.contains(r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\b", case=False)
    complete_date = raw_dates.str.contains(r"(?<!\d)\d{4}(?!\d)") & (number_parts.ge(3) | (has_month_name & number_parts.ge(2)))
    dates = (pd.to_datetime(raw_dates.where(complete_date), errors="coerce", format="mixed", utc=True)
             .dt.tz_convert("Asia/Manila").dt.tz_localize(None))
    evidence["original_posting_date"] = raw_dates
    evidence["source_field"] = date_field
    evidence["url"] = ads.get("url", pd.Series("", index=ads.index)).map(clean_text)
    evidence["posting_date"] = dates
    evidence["month"] = dates.dt.to_period("M").astype(str).where(dates.notna(), "")
    evidence["date_status"] = "Dated"
    evidence.loc[dates.isna(), "date_status"] = "Invalid posting date"
    evidence.loc[raw_dates.map(_missing), "date_status"] = "Not stated"
    dated = evidence.loc[evidence.month.ne("") & evidence.job_title.ne("")]
    monthly = pd.DataFrame(columns=["month", "job_title", "job_ads"])
    if not dated.empty:
        months = pd.period_range(dated.month.min(), dated.month.max(), freq="M").astype(str)
        title_names = sorted(dated.job_title.unique())
        counts = dated.groupby(["month", "job_title"]).source_id.nunique()
        # The UI fills zero months after selecting at most eight titles for large inputs.
        if len(months) * len(title_names) <= 50000:
            grid = pd.MultiIndex.from_product([months, title_names], names=["month", "job_title"])
            counts = counts.reindex(grid, fill_value=0)
        monthly = counts.rename("job_ads").reset_index()
    return monthly, evidence


_EDUCATION_LEVELS = [
    ("high school", r"\bhigh\s+school\b"),
    ("senior high school", r"\b(?:senior\s+high(?:\s+school)?|shs|grade\s*1[12])\b"),
    ("vocational / technical", r"\b(?:technical[ -]?vocational|vocational(?:\s+(?:graduate|qualification|course))?|tesda\s+certification)\b"),
    ("undergraduate / college level", r"\b(?:undergrad(?:uate)?|college(?:[ -](?:level|graduate|graduated|degree))?|college\s+undergrad(?:uate)?|2(?:nd|\s*nd)\s+year\s+college\s+level)\b"),
    ("associate degree", r"\bassociate(?:['’]s)?\s+(?:degree|of)\b"),
    ("bachelor's degree", r"\b(?:bachelor(?:['’]?s)?|baccalaureate|b\.?\s*sc\.?|b\.?s\.?|b\.?a\.?)\b"),
    ("postgraduate degree", r"\bpostgraduate\s+(?:degree|qualification)\b"),
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
        status = "Not stated" if _education_missing(text) else "Needs review"
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


def _education_missing(value):
    text = normalize_text(value)
    return _missing(text) or bool(re.fullmatch(
        r"(?:educ(?:ation(?:al)?)?\s+)?(?:level\s+)?not\s+specified|not\s+specified\s+(?:education\s+)?level",
        text,
    ))


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
        title = _analysis_title(original)
        if _missing(title):
            title = ""
        rows.append({"source_id": job.get("source_id", str(index)), "job_family": family,
                     "job_title": title, "original_job_title": original,
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
                 or re.match(r"\s*(?:or more|or above|and above)\b", text[match.end():], re.I))
    upper = bool(re.search(r"\b(?:up to|at most|maximum(?: of)?|max\.?)\s*$", text[:match.start()], re.I))
    # Alternatives before the duration ("two or four years") are ambiguous;
    # alternatives between experience areas after it do not change the duration.
    if re.search(rf"\b(?:{_NUMBER_TOKEN}\s+or|between)\s*$", text[:match.start()], re.I) or (lower and upper):
        return "", None, None, "Needs review"
    low = _year_number(match["low"] or match["between_low"])
    high_token = match["high"] or match["between_high"]
    high = _year_number(high_token) if high_token else None
    if high is not None:
        if high < low or lower or upper:
            return "", None, None, "Needs review"
        return f"{low:g}–{high:g} years", low, high, "Parsed range"
    years = f"{low:g} {'year' if low == 1 else 'years'}"
    if lower:
        return f"at least {years}", low, None, "Parsed minimum"
    if upper:
        return f"up to {years}", None, low, "Parsed maximum"
    return f"{years} stated", low, low, "Parsed stated years"


def _duration_clauses(text, matches):
    """Keep nearby qualifiers while separating explicitly delimited durations."""
    starts, ends = [0], []
    for current, following in zip(matches, matches[1:]):
        gap = text[current.end():following.start()]
        separator = _DURATION_SEPARATOR.search(gap)
        # Without a delimiter both matches stay together for review.
        ends.append(current.end() + separator.start() if separator else len(text))
        starts.append(current.end() + separator.end() if separator else 0)
    return [clean_text(text[start:end]) for start, end in zip(starts, [*ends, len(text)])]


def _year_number(value):
    text = clean_text(value).casefold().replace("-", " ")
    try:
        return float(text)
    except ValueError:
        parts = text.split()
        if len(parts) == 2 and parts[0] in _NUMBER_WORDS and parts[1] in _NUMBER_WORDS:
            return float(_NUMBER_WORDS[parts[0]] + _NUMBER_WORDS[parts[1]])
        if len(parts) == 2 and parts[0] == "one" and parts[1] == "hundred":
            return 100.0
        return float(_NUMBER_WORDS.get(text, 0))


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
        if status == "Needs review":
            text = clean_text(original)
            matches = list(_YEARS.finditer(text))
            if len(matches) > 1 and not _NO_EXPERIENCE.search(text):
                durations = [_experience_years(clause) for clause in _duration_clauses(text, matches)]
                label = "; ".join(dict.fromkeys(value for value, _, _, state in durations if state.startswith("Parsed")))
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
        missing_check = _education_missing if field == "education_requirement" else _missing
        missing = jobs.get(field, pd.Series("", index=jobs.index)).map(missing_check)
        stated = int((~missing).sum())
        coverage.append({"source_field": field, "stated_job_ads": stated,
                         "not_stated_job_ads": int(missing.sum()), "job_ads": len(jobs),
                         "stated_pct": round(100 * stated / len(jobs), 1) if len(jobs) else 0.0})
    return summary, evidence, pd.DataFrame(coverage)


def _experience_text_candidates(job):
    """Find source clauses that clearly state a duration of work or role experience."""
    candidates = []
    for field in _TEXT_REQUIREMENT_FIELDS:
        raw = job.get(field, "")
        raw = "" if raw is None or pd.isna(raw) else str(raw)
        # Preserve list and paragraph boundaries before clean_text collapses whitespace.
        raw = html.unescape(raw)
        raw = re.sub(r"(?i)<\s*/?\s*(?:br|p|li|ul|ol|div|tr|h[1-6])\b[^>]*>", "\n", raw)
        raw = re.sub(r"[\r\n]+|[•▪◦●]+", "\n", raw)
        clauses = []
        for block in raw.splitlines():
            block = clean_text(block).lstrip("-–—* ")
            if block:
                clauses.extend(re.split(r"(?<=[.!?;])\s+", block))
        for clause in clauses:
            clause = clean_text(clause)
            if not clause:
                continue
            matches = list(_YEARS.finditer(clause))
            for match, duration_clause in zip(matches, _duration_clauses(clause, matches)):
                left = clause[max(0, match.start() - 90):match.start()]
                right = clause[match.end():min(len(clause), match.end() + 90)]
                local_context = f"{left} {match.group()} {right}"
                if (_EMPLOYER_HISTORY_BEFORE.search(left) or _EMPLOYER_HISTORY_AFTER.search(right)
                        or re.match(r"\s+old\b", right, re.I)):
                    continue
                # Exclude durations that describe years of schooling, degrees or courses,
                # without discarding a nearby experience clause in the same sentence.
                if (_EDUCATION_DURATION_AFTER.search(f"{match.group()} {right}")
                        or _EDUCATION_DURATION_BEFORE.search(left)):
                    continue
                has_experience_context = bool(_EXPERIENCE_CONTEXT.search(local_context)
                                              or _ROLE_DURATION_CONTEXT.search(local_context))
                qualification_duration = field == "qualifications" and bool(_QUALIFICATION_CONTEXT.search(local_context))
                if not (has_experience_context or qualification_duration):
                    continue
                phrase = clean_text(match.group())
                candidates.append({
                    "source_id": clean_text(job.get("source_id", "")),
                    "job_title": clean_text(job.get("job_title", "")),
                    "candidate_phrase": phrase,
                    "original_requirement": clean_text(clause),
                    "duration_clause": duration_clause,
                    "source_field": field,
                    "evidence": clean_text(clause),
                    "url": clean_text(job.get("url", "")),
                })
    # A clause repeated in multiple imported text fields remains one requirement.
    unique = {}
    for row in candidates:
        key = (normalize_text(row["candidate_phrase"]), normalize_text(row["original_requirement"]))
        unique.setdefault(key, row)
    return list(unique.values())


def _experience_text_tables(jobs):
    candidate_rows, analysis_rows = [], []
    for index, job in jobs.iterrows():
        source_id = clean_text(job.get("source_id", str(index)))
        explicit = job.get("experience_requirement", "")
        if not _missing(explicit):
            continue
        candidates = _experience_text_candidates(job)
        parsed = []
        for candidate in candidates:
            label, minimum, maximum, status = _experience_years(candidate["duration_clause"])
            candidate_rows.append({**candidate, "requirement": label, "min_years": minimum,
                                   "max_years": maximum, "parse_status": status,
                                   "evidence_status": "Text evidence; researcher should verify context"})
            parsed.append((label, minimum, maximum, status, candidate))
        if not parsed:
            continue
        signatures = {(item[1], item[2], item[3]) for item in parsed if item[3].startswith("Parsed")}
        all_parsed = all(item[3].startswith("Parsed") for item in parsed)
        consistent = all_parsed and len(signatures) == 1
        first = parsed[0]
        if consistent:
            label, minimum, maximum, status = first[:4]
            source_fields = "; ".join(dict.fromkeys(item[4]["source_field"] for item in parsed))
            original = " | ".join(dict.fromkeys(item[4]["original_requirement"] for item in parsed))
        else:
            label = "; ".join(dict.fromkeys(item[0] for item in parsed if item[3].startswith("Parsed")))
            minimum, maximum, status = None, None, "Needs review"
            source_fields = "; ".join(dict.fromkeys(item[4]["source_field"] for item in parsed))
            original = " | ".join(dict.fromkeys(item[4]["original_requirement"] for item in parsed))
        analysis_rows.append({
            "source_id": source_id, "job_title": clean_text(job.get("job_title", "")),
            "original_requirement": original, "requirement": label,
            "min_years": minimum, "max_years": maximum, "parse_status": status,
            "source_field": source_fields, "url": clean_text(job.get("url", "")),
            "evidence": original, "evidence_origin": "text fallback",
        })
    candidate_columns = ["source_id", "job_title", "candidate_phrase", "original_requirement", "duration_clause", "requirement",
                         "min_years", "max_years", "parse_status", "source_field", "evidence", "url", "evidence_status"]
    analysis_columns = ["source_id", "job_title", "original_requirement", "requirement", "min_years", "max_years",
                        "parse_status", "source_field", "url", "evidence", "evidence_origin"]
    return pd.DataFrame(candidate_rows, columns=candidate_columns), pd.DataFrame(analysis_rows, columns=analysis_columns)


def _requirements(jobs, field, patterns=(), missing_check=None):
    """Return explicit-field distribution plus traceable text evidence candidates."""
    if jobs.empty:
        return (pd.DataFrame(columns=["requirement", "job_ads"]),
                pd.DataFrame(columns=["source_id", "job_title", "requirement_type", "phrase", "source_field", "evidence", "url"]))

    missing_check = missing_check or _missing
    explicit_rows = []
    evidence_rows = []
    for _, job in jobs.iterrows():
        source_id = clean_text(job.get("source_id", ""))
        title = clean_text(job.get("job_title", ""))
        url = clean_text(job.get("url", ""))
        explicit = clean_text(job.get(field, ""))
        is_missing = missing_check(explicit)
        explicit_rows.append({"source_id": source_id, "requirement": "Not stated" if is_missing else explicit})
        if not is_missing:
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
    education, education_evidence = _requirements(job_ads, "education_requirement", (EDUCATION,), _education_missing)
    experience, experience_evidence = _requirements(job_ads, "experience_requirement", (EXPERIENCE,))
    evidence = pd.concat([education_evidence, experience_evidence], ignore_index=True)
    years, year_evidence, coverage = _experience_tables(job_ads)
    year_evidence = year_evidence.copy()
    year_evidence["evidence_origin"] = "explicit field"
    text_year_evidence, text_analysis_evidence = _experience_text_tables(job_ads)
    if not text_year_evidence.empty:
        text_requirement_evidence = text_year_evidence[["source_id", "job_title", "candidate_phrase", "source_field", "evidence", "url", "evidence_status"]].copy()
        text_requirement_evidence = text_requirement_evidence.rename(columns={"candidate_phrase": "phrase"})
        text_requirement_evidence["requirement_type"] = "Experience"
        evidence = pd.concat([evidence, text_requirement_evidence], ignore_index=True, sort=False)
    text_source_ids = set(text_analysis_evidence.source_id) if not text_analysis_evidence.empty else set()
    year_evidence["evidence"] = year_evidence["original_requirement"]
    explicit_analysis_evidence = year_evidence.loc[~year_evidence.source_id.isin(text_source_ids)].copy()
    if text_analysis_evidence.empty:
        analysis_year_evidence = explicit_analysis_evidence.reset_index(drop=True)
    elif explicit_analysis_evidence.empty:
        analysis_year_evidence = text_analysis_evidence.reset_index(drop=True)
    else:
        for frame in (explicit_analysis_evidence, text_analysis_evidence):
            for column in ("min_years", "max_years"):
                frame[column] = pd.to_numeric(frame[column], errors="coerce").astype(float)
        analysis_year_evidence = pd.concat(
            [explicit_analysis_evidence, text_analysis_evidence], ignore_index=True, sort=False
        )
    text_parsed = text_year_evidence[text_year_evidence.parse_status.str.startswith("Parsed")]
    analysis_parsed = analysis_year_evidence[analysis_year_evidence.parse_status.str.startswith("Parsed")]
    text_year_counts = _counts(text_parsed, "requirement", "job_ads")
    analysis_year_counts = _counts(analysis_parsed, "requirement", "job_ads")
    denominator = job_ads.source_id.nunique() if "source_id" in job_ads else len(job_ads)
    duration_mentions = analysis_year_evidence[["source_id", "requirement"]].copy()
    duration_mentions["requirement"] = duration_mentions.requirement.str.split("; ")
    duration_counts = _counts(duration_mentions.explode("requirement"), "requirement", "job_ads")
    for counts in (text_year_counts, analysis_year_counts, duration_counts):
        counts["job_ads_pct"] = (100 * pd.to_numeric(counts.job_ads) / denominator).round(1) if denominator else 0.0
    education_levels, education_level_evidence = _education_tables(job_ads)
    experience_bands, experience_band_evidence = _experience_bands(analysis_year_evidence, len(job_ads))
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
              "experience_text_year_counts": text_year_counts,
              "experience_text_year_evidence": text_year_evidence,
              "experience_analysis_year_counts": analysis_year_counts,
              "experience_duration_counts": duration_counts,
              "experience_analysis_year_evidence": analysis_year_evidence,
              "requirement_field_coverage": coverage,
              "education_level_counts": education_levels,
              "education_level_evidence": education_level_evidence,
              "experience_band_counts": experience_bands,
              "experience_band_evidence": experience_band_evidence,
              "job_title_family_counts": title_families,
              "job_title_source_evidence": title_sources}
    return tables
