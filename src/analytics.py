import pandas as pd
from .category_schema import requirement_type
from .cleaning import normalize_text
from .job_profile import experience_phrase_reason
import re
import unicodedata


_CHART_BULLETS = re.compile(r"^[\s•●▪◦‣⁃·*–—-]+|[\s•●▪◦‣⁃·*–—-]+$")
_OCCUPATIONAL_LABEL = re.compile(
    r"^(?:[\w+#.-]+\s+){0,3}(?:analysts?|scientists?|engineers?|developers?|specialists?|officers?|"
    r"assistants?|consultants?|architects?|designers?|managers?|coordinators?|administrators?|auditors?|"
    r"technicians?|operators?|executives?|directors?)$"
)
_GENERIC_NON_SKILL_PHRASES = {"base", "based", "data", "industry experience"}
_BENEFIT_ACCESS_WORDING = re.compile(r"^access(?:\s+to)?\s+benefits?$", re.I)
_LEGAL_BOILERPLATE_PHRASE = re.compile(r"^protect(?:ed)?\s+by\s+applicable(?:\s+laws?)?$", re.I)
_ADOPTION_OUTCOME_PHRASE = re.compile(r"^adoption(?:\s+of)?\s+insights?$", re.I)
_CHART_ONLY_NON_SKILL_PHRASES = {
    "activity and work": "Generic duty wording; no identifiable skill",
    "activities and work": "Generic duty wording; no identifiable skill",
    "communication and train": "Duty wording about supporting communication and training efforts; not a standalone skill",
    "allow individual": "Company marketing wording about customers; not an employer competency",
    "allow individuals": "Company marketing wording about customers; not an employer competency",
    "analyst work": "Occupational experience wording; not a competency",
    "asset across strategy": "Employer corporate-profile wording; not a job requirement",
    "assets across strategy": "Employer corporate-profile wording; not a job requirement",
    "ai base": "Malformed 'AI based' fragment; no competency is identified",
    "ai based": "Malformed 'AI based' fragment; no competency is identified",
    "ai prompt": "Job-title fragment; not a stated competency",
}
_CHART_PHRASE_ALIASES = {
    "powerbi": "power bi", "microsoft power bi": "power bi",
    "ms excel": "excel", "microsoft excel": "excel",
    "communication skill": "communication", "communication skills": "communication",
    "strong communication skill": "communication", "strong communication skills": "communication",
    "collaboration skills": "collaboration", "strong collaboration": "collaboration",
    "strong collaboration skill": "collaboration", "strong collaboration skills": "collaboration",
    "problem solve": "problem solving", "problem-solving": "problem solving",
    "problem solving skill": "problem solving", "problem solving skills": "problem solving",
    "problem-solving skill": "problem solving", "problem-solving skills": "problem solving",
    "ability to learn": "learning and application", "ability learn": "learning and application",
    "learn and apply": "learning and application", "learn apply": "learning and application",
    "ability to learn and apply": "learning and application", "ability learn apply": "learning and application",
    "learn and implement": "learning and application", "learn implement": "learning and application",
    "ability to learn and implement": "learning and application", "ability learn implement": "learning and application",
    "learning application": "learning and application", "learn and application": "learning and application",
    "learning and applying": "learning and application", "learning applying": "learning and application",
    "agile scrum methodology": "agile scrum", "agile scrum methodologies": "agile scrum",
    "agile scrum method": "agile scrum", "agile scrum methods": "agile scrum",
    "scrum": "agile scrum", "scrum methodology": "agile scrum",
    "scrum methodologies": "agile scrum", "scrum method": "agile scrum",
    "scrum methods": "agile scrum",
}
_VAGUE_ONLY_WORDS = {
    "ability", "advanced", "basic", "background", "business", "computer", "different", "digital",
    "domain", "excellent", "experience", "expertise", "exposure", "familiarity", "good", "industry",
    "intermediate", "it", "knowledge", "proficiency", "proven", "related", "relevant", "skills", "software",
    "solid", "strong", "technical", "technologies", "technology", "understanding", "various",
}
_UNCLEAR_LIST_TAIL = re.compile(r"\b(?:etc\.?|and more|among others|and others|and related(?:\s+(?:skills?|areas?|fields?))?)$", re.I)
_SKILL_ACTIONS = {
    "ability", "skill", "skills", "experience", "knowledge", "proficiency",
    "build", "develop", "identify", "maintain", "monitor", "ensure", "perform",
    "provide", "responsible", "requirement", "requirements", "responsibilities",
    "duties", "work", "working", "remote", "hybrid", "onsite", "apply",
    "preferred", "required",
}
_MISSING_SKILL_PHRASES = {
    "none", "nan", "null", "not mentioned", "not mention", "not stated",
    "not specified", "not provided", "not applicable", "not available",
    "not indicated", "not disclosed", "not listed", "unspecified",
    "unclassified", "n/a", "na", "tbd", "unknown", "no information", "no info",
}


def _skill_phrase_reason(value):
    phrase = _CHART_BULLETS.sub("", normalize_text(value).translate(
        {0x200b: None, 0xfeff: None, 0x2060: None})).strip()
    placeholder = re.sub(r"[\s.,;:!?]+$", "", phrase)
    if not placeholder:
        return "Blank phrase; no skill text"
    if placeholder in _MISSING_SKILL_PHRASES:
        return "Not reported (missing placeholder); count only, not a skill"
    experience_reason = experience_phrase_reason(phrase)
    if experience_reason:
        return experience_reason
    if phrase in _GENERIC_NON_SKILL_PHRASES:
        return "Incomplete or context-only wording; not a skill"
    if _BENEFIT_ACCESS_WORDING.fullmatch(placeholder):
        return "Benefit-access wording; verify source context before treating it as a skill"
    if _UNCLEAR_LIST_TAIL.search(placeholder):
        return "Unfinished list wording; verify the named skills before charting"
    words = set(re.findall(r"[a-z]+", placeholder))
    if words and words <= _VAGUE_ONLY_WORDS:
        return "Vague wording without an identifiable competency; check source context"
    if _OCCUPATIONAL_LABEL.fullmatch(phrase):
        return "Job title or occupational wording; not a skill"
    if not any(char.isalpha() for char in phrase):
        return "No identifiable skill text"
    if any(unicodedata.category(char) == "So" for char in phrase):
        return "Non-text symbol in phrase; check the advertisement context"
    if phrase in _SKILL_ACTIONS:
        return "Standalone action or generic wording; specify the skill in context"
    from .pretrained_suggestions import is_incomplete_phrase
    if is_incomplete_phrase(phrase):
        return "Incomplete connector phrase; check the advertisement context"
    return ""


def _chart_phrase_reason(value):
    """Apply conservative graph-only exclusions to source wording already extracted."""
    phrase = _CHART_BULLETS.sub("", normalize_text(value).translate(
        {0x200b: None, 0xfeff: None, 0x2060: None})).strip()
    if phrase in _CHART_ONLY_NON_SKILL_PHRASES:
        return _CHART_ONLY_NON_SKILL_PHRASES[phrase]
    if _LEGAL_BOILERPLATE_PHRASE.fullmatch(phrase):
        return "Equal-employment legal boilerplate; not an employer competency"
    if _ADOPTION_OUTCOME_PHRASE.fullmatch(phrase):
        return "Success-metric wording; review before treating as a competency"
    return _skill_phrase_reason(phrase)

def filter_frame(frame, filters):
    mask = pd.Series(True, index=frame.index)
    for field, values in filters.items():
        if field == "normalized_phrase_contains":
            query = str(values or "").strip()
            if query and "normalized_phrase" in frame:
                mask &= frame.normalized_phrase.astype(str).str.contains(query, case=False, regex=False, na=False)
            continue
        if field in frame and values:
            mask &= frame[field].astype(str).isin([str(v) for v in values])
    return frame.loc[mask]

def accepted_skills(frame):
    if frame.empty:
        return frame
    categories = frame.get("competency_category", pd.Series("", index=frame.index)).fillna("")
    phrases = frame.get("normalized_phrase", pd.Series("", index=frame.index)).fillna("")
    phrase_reasons = {phrase: _skill_phrase_reason(phrase) for phrase in phrases.unique()}
    return frame[frame.accepted.astype(str).str.casefold().eq("true") &
                 categories.astype(str).str.casefold().ne("irrelevant") &
                 categories.map(requirement_type).ne("Credential requirement") &
                 phrases.map(phrase_reasons).eq("")].drop_duplicates(["source_type", "source_id", "normalized_phrase"])

def counts(frame, column, name="count"):
    if column not in frame or frame.empty:
        return pd.DataFrame(columns=[column, name])
    return frame[column].replace("", pd.NA).dropna().value_counts().rename_axis(column).reset_index(name=name)

def demand_matrix(skills, jobs, group):
    if skills.empty or jobs.empty or group not in jobs:
        return pd.DataFrame()
    joined = skills.merge(jobs[["source_id", group]], on="source_id")
    joined = joined[joined[group].ne("")]
    return joined.groupby(["normalized_phrase", group]).source_id.nunique().unstack(fill_value=0)


def skill_chart_tables(skills, jobs, *, allowed_phrases=None):
    """Create an auditable chart view without changing stored research evidence."""
    def key(value):
        phrase = _CHART_BULLETS.sub("", normalize_text(value).translate({0x200b: None, 0xfeff: None, 0x2060: None})).strip()
        # spaCy lemmatization can turn source "data" into "datum". In this
        # 500-ad corpus no source description uses "datum"; restore its surface
        # form only in chart labels, retaining original and normalized evidence.
        phrase = re.sub(r"\bdatum\b", "data", phrase)
        return _CHART_PHRASE_ALIASES.get(phrase, phrase)

    ids = jobs.get("source_id", pd.Series(dtype=str)).dropna().astype(str)
    ids = ids[ids.str.strip().ne("")]
    view = skills.loc[skills.get("source_id", pd.Series(index=skills.index, dtype=str)).astype(str).isin(ids)].copy()
    view["source_id"] = view.get("source_id", pd.Series(index=view.index, dtype=str))
    if "source_type" in view:
        view = view[view.source_type.isin(["jobs", "Philippine job advertisement"])].copy()
    original = view.get("normalized_phrase", pd.Series("", index=view.index)).fillna("")
    surface = view.get("original_phrase", pd.Series("", index=view.index)).fillna("")
    view["original_normalized_phrase"] = original
    view["normalized_phrase"] = original.where(original.astype(str).str.strip().ne(""), surface).map(key)
    view["skill_label"] = view.normalized_phrase
    reasons = {phrase: _chart_phrase_reason(phrase) for phrase in view.normalized_phrase.unique()}
    view["review_reason"] = view.normalized_phrase.map(reasons)
    categories = view.get("competency_category", pd.Series("", index=view.index)).fillna("")
    needs_category_reason = view.review_reason.eq("")
    view.loc[needs_category_reason & categories.map(requirement_type).eq("Credential requirement"), "review_reason"] = "Credential requirement, not a skill"
    view.loc[needs_category_reason & categories.astype(str).str.casefold().eq("irrelevant"), "review_reason"] = "Researcher or classifier marked this phrase irrelevant"
    accepted = view.get("accepted", pd.Series(True, index=view.index)).astype(str).str.casefold().eq("true")
    reason = view.review_reason.fillna("").astype(str)
    review = view.loc[reason.ne("")].copy()
    eligible = view.loc[accepted & reason.eq("")].copy()
    if allowed_phrases is not None:
        eligible = eligible[eligible.original_normalized_phrase.isin(allowed_phrases)]
    eligible = eligible.drop_duplicates(["source_id", "normalized_phrase"]).copy()
    demand = (eligible.groupby(["normalized_phrase", "skill_label"]).source_id.nunique()
              .rename("employer_demand_count").reset_index()
              .rename(columns={"skill_label": "employer_skill"}))
    denominator = ids.nunique()
    demand["employer_demand_pct"] = demand.employer_demand_count / denominator * 100 if denominator else float("nan")
    demand = demand.sort_values(["employer_demand_count", "employer_skill"], ascending=[False, True], kind="stable").reset_index(drop=True)
    family_source = jobs.reindex(columns=["source_id", "job_family"]).fillna("").drop_duplicates("source_id")
    family_source["job_family"] = family_source.job_family.map(normalize_text).replace(
        {"": "not stated", "not specified": "not stated", "not provided": "not stated",
         "not available": "not stated", "none": "not stated", "null": "not stated", "nil": "not stated",
         "no information": "not stated", "no info": "not stated", "-": "not stated", "—": "not stated",
         "unspecified": "not stated", "n/a": "not stated", "na": "not stated",
         "unknown": "not stated", "unclassified": "not stated", "not applicable": "not stated",
         "other": "not stated", "general": "not stated"})
    family_ads = (family_source.groupby("job_family").source_id.nunique().rename("family_ads").reset_index())
    family_ads["family_ads_pct"] = family_ads.family_ads / denominator * 100 if denominator else float("nan")
    if eligible.empty or family_source.empty:
        family_demand = pd.DataFrame(columns=["job_family", "skill_label", "job_ads"])
    else:
        family_demand = eligible.merge(family_source, on="source_id", how="inner").groupby(
            ["job_family", "skill_label"]).source_id.nunique().rename("job_ads").reset_index()
    if not family_demand.empty:
        family_demand = family_demand.merge(family_ads, on="job_family", how="left")
        family_demand["job_ads_pct"] = family_demand.job_ads / family_demand.family_ads.where(
            family_demand.family_ads.gt(0), 1) * 100
        family_demand = family_demand.sort_values(["job_family", "job_ads", "skill_label"],
                                                  ascending=[True, False, True], kind="stable").reset_index(drop=True)
    else:
        family_demand = pd.DataFrame(columns=["job_family", "skill_label", "job_ads", "family_ads", "job_ads_pct"])
    return {"chart_skill_occurrences": eligible,
            "chart_skill_demand": demand,
            "chart_phrase_review": review,
            "chart_skill_family_demand": family_demand,
            "chart_family_ad_counts": family_ads.sort_values(["family_ads", "job_family"],
                                                              ascending=[False, True], kind="stable").reset_index(drop=True)}


def psf_demand_tables(mapping, jobs, taxonomy, *, denominator=None):
    """Aggregate linked evidence; framework row order is presentation metadata only."""
    from .cleaning import normalize_text
    reference = taxonomy.reindex(columns=["competency_id", "competency_name", "job_role"]).fillna("").copy()
    reference["framework_order"] = range(len(reference))
    reference["psf_competency"] = reference.competency_name.map(normalize_text)
    columns = ["source_id", "psf_competency", "psf_job_role", "status"]
    linked = mapping.reindex(columns=columns).fillna("")
    linked = linked[linked.source_id.isin(jobs.get("source_id", [])) &
                    linked.status.isin(["ALIGNED", "PARTIALLY ALIGNED"]) & linked.psf_competency.ne("")].copy()
    linked["psf_competency"] = linked.psf_competency.map(normalize_text)
    linked["psf_job_role"] = linked.psf_job_role.map(normalize_text).str.split("; ")
    roles = linked.explode("psf_job_role")
    roles = roles[roles.psf_job_role.ne("")]
    families = jobs.reindex(columns=["source_id", "job_family"]).fillna("").drop_duplicates("source_id")
    families["job_family"] = families.job_family.map(normalize_text).replace("", "not stated")
    role_family = roles.merge(families, on="source_id", how="left").groupby(
        ["psf_job_role", "job_family"]).source_id.nunique().rename("job_ads").reset_index()
    role_competency = roles.groupby(["psf_job_role", "psf_competency"]).source_id.nunique().rename(
        "job_ads").reset_index()
    demand = linked.groupby("psf_competency").source_id.nunique().rename("job_ads").reset_index()
    order = reference.groupby("psf_competency").framework_order.min()
    demand["framework_order"] = demand.psf_competency.map(order).fillna(len(reference)).astype(int)
    denominator = jobs.source_id.nunique() if denominator is None and "source_id" in jobs else (denominator or 0)
    demand["job_ads_pct"] = demand.job_ads / denominator * 100 if denominator else 0.
    return {"psf_framework_order": reference, "psf_chart_demand": demand,
            "psf_role_family_demand": role_family,
            "psf_role_competency_demand": role_competency}
