import pandas as pd
from .category_schema import requirement_type
from .cleaning import normalize_text
from .job_profile import experience_phrase_reason
from .skill_extraction import GENERAL
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
    "train and development": "training and development",
}
_VAGUE_ONLY_WORDS = {
    "ability", "advanced", "basic", "background", "business", "computer", "different", "digital",
    "domain", "excellent", "experience", "expertise", "exposure", "familiarity", "good", "industry",
    "intermediate", "it", "knowledge", "proficiency", "proven", "related", "relevant", "skills", "software",
    "solid", "strong", "technical", "technologies", "technology", "understanding", "various",
    "accept", "accepted", "acceptance", "action", "actions", "actionable", "activities", "activity",
    "adjacent", "and", "or", "of", "to", "current", "existing", "new", "modern", "latest",
    "enterprise", "improve", "improvement", "opportunities", "opportunity", "long", "successful",
    "service", "services", "system", "systems", "tool", "tools", "tooling", "toolkit", "toolkits",
    "usage", "use", "workflow", "workflows",
}
_MODIFIER_ONLY_PHRASE = re.compile(r"^ad[\s-]+hoc$", re.I)
_DANGLING_ACCESS_PHRASE = re.compile(
    r"^access\s+(?:to\s+)?(?:clean|accurate|complete|reliable|secure|timely|quality)$", re.I)
_UNSPECIFIED_TECH_OBJECT = re.compile(
    r"^(?:enterprise\s+)?(?:ai|artificial intelligence|data|analytics|digital|technical)\s+"
    r"(?:tools?|systems?|services?|platforms?|workflows?)$", re.I)
_OUTPUT_MODIFIED_PHRASE = re.compile(
    r"^(?:actionable|successful)\s+(?:solutions?|solution designs?|outcomes?|results?)$", re.I)
_NON_REQUIREMENT_WORDING = re.compile(
    r"^(?:(?:free|paid|sponsored|complimentary)\s+(?:training|learning|development|courses?)|"
    r"opportunit(?:y|ies)\s+(?:for|to|in)\b.*|long\s+and\s+successful\b.*)$", re.I)
_CAPABILITY_HEADS = set("""analysis analytics design management integration engineering testing governance programming
research development learning modelling modeling visualization visualisation mining processing validation
optimization optimisation planning automation mapping forecasting prediction classification elicitation
architecture security privacy compliance auditing negotiation training configuration deployment troubleshooting
maintenance documentation reporting presentation communication collaboration accountability engagement resolution
response reasoning storytelling balancing selection reduction cleaning assurance making implementation
administration orchestration statistics inference debugging reconciliation extraction transformation
literacy acumen intelligence diligence control redesign improvement thinking listening speaking innovation synthesis""".split())
_NAMED_SKILL_TERMS = ({term for term, category in GENERAL.items()
                       if requirement_type(category) != "Credential requirement"}
                      | set(_CHART_PHRASE_ALIASES.values()) | set("""aws azure gcp sas scala rust julia go swift access
stata spss qlik dbt airflow spark hadoop figma jira word mongodb mysql postgresql snowflake databricks
tensorflow pytorch pandas numpy langchain llamaindex communication research learning programming
forecasting troubleshooting resilience flexibility negotiation accountability finance accounting economics typescript pyspark xgboost
mathematics algebra calculus probability marketing english tagalog filipino c etl agile""".split()) | {
    "microsoft access", "microsoft word", "apache spark", "apache airflow", "apache hadoop", "qlik sense",
    "amazon web services", "microsoft azure", "google cloud platform", "scikit-learn", "hugging face",
    "attention to detail", "open to change", "research and development", "ownership and accountability",
    "etl process", "quality standard", "quality standards", "cloud compute", "service level agreements",
    "willingness to learn", "ability to communicate", "customer service", "statistical methods",
})
_UNRECOGNIZED_SKILL_REASON = "No recognized standalone skill or complete technical task; verify wording and source context"
_SKILL_LEVEL_PREFIX = re.compile(r"^(?:advanced|basic|intermediate|expert|proficient|strong|good|excellent)\s+", re.I)
_SKILL_REQUIREMENT_PREFIX = re.compile(
    r"^(?:(?:(?:working|practical|hands-on)\s+)?(?:knowledge|understanding|experience|proficiency|"
    r"expertise|familiarity|skills?)\s+(?:of|in|with)|participate\s+in|assist\s+(?:in|with))\s+", re.I)
_CONCRETE_TECH_TASK = re.compile(
    r"^(?:build|develop|create|maintain|enhance|configure|deploy|implement|design|operate|test|debug|"
    r"optimize|optimise|validate|monitor|manage|troubleshoot|document)(?:\s+and\s+(?:build|develop|"
    r"implement|design|deploy|maintain))?\s+(?:the\s+)?(?:"
    r"(?:data\s+|etl\s+)?(?:dashboards?|pipelines?|warehouses?|databases?)|apis?|software|code|"
    r"(?:data|ml|machine learning|statistical|predictive)\s+models?|cloud infrastructure|network devices)$", re.I)
_BROKEN_CLAUSE = re.compile(r"\b(?:be|they|that|which)\b", re.I)
_WEAK_FRAGMENT_START = re.compile(r"^(?:base|basis)(?:\s|$)", re.I)
_TECHNICAL_COMPOUND_START = re.compile(r"^(?:as-is|to-be|end-to-end|out-of-sample|in-memory)\b", re.I)
# Bounded word forms, not a stemmer: analysis/analytics and related domains stay distinct.
_SKILL_HEAD_FORMS = {
    "compute": "computing", "computations": "computation",
    "visualise": "visualization", "visualize": "visualization", "visualisation": "visualization",
    "visualisations": "visualization", "visualizations": "visualization",
    "modelling": "modeling", "modelings": "modeling", "modellings": "modeling",
    "analyse": "analysis", "analyze": "analysis", "analyses": "analysis",
    "optimise": "optimization", "optimize": "optimization", "optimisation": "optimization",
    "optimisations": "optimization", "optimizations": "optimization",
    "standards": "standards", "standard": "standards", "agreement": "agreements",
}
_SKILL_LABEL_PREFIX = re.compile(
    r"^(?:(?:advanced|basic|intermediate|expert|proficient|strong|good|excellent|solid)\s+|"
    r"(?:(?:working|practical|hands-on)\s+)?(?:knowledge|understanding|experience|proficiency|"
    r"expertise|familiarity|skills?)\s+(?:of|in|with)\s+)", re.I)
_SKILL_LABEL_SUFFIX = re.compile(r"\s+skills?$", re.I)
_SKILL_TASK = re.compile(
    r"^(build|building|built|develop|developing|create|creating|design|designing|maintain|maintaining|"
    r"enhance|enhancing|improve|improving|test|testing|deploy|deploying|configure|configuring)\s+"
    r"(?:(?:a|an|the)\s+)?((?:(?:data|etl|interactive|ml|machine learning|statistical|predictive)\s+)?"
    r"(?:dashboards?|pipelines?|databases?|apis?|models?))$", re.I)
_TASK_CAPABILITIES = {
    "build": "development", "building": "development", "built": "development",
    "develop": "development", "developing": "development", "create": "development", "creating": "development",
    "design": "design", "designing": "design", "maintain": "maintenance", "maintaining": "maintenance",
    "enhance": "improvement", "enhancing": "improvement", "improve": "improvement", "improving": "improvement",
    "test": "testing", "testing": "testing", "deploy": "deployment", "deploying": "deployment",
    "configure": "configuration", "configuring": "configuration",
}
_UNCLEAR_LIST_TAIL = re.compile(r"\b(?:etc\.?|and more|among others|and others|and related(?:\s+(?:skills?|areas?|fields?))?)$", re.I)
_SKILL_ACTIONS = {
    "ability", "skill", "skills", "experience", "knowledge", "proficiency",
    "build", "develop", "identify", "maintain", "monitor", "ensure", "perform",
    "provide", "responsible", "requirement", "requirements", "responsibilities",
    "duties", "work", "working", "remote", "hybrid", "onsite", "apply",
    "preferred", "required",
}
_GENERIC_REQUIREMENT_WORDS = _VAGUE_ONLY_WORDS | _SKILL_ACTIONS | {
    "data", "job", "jobs", "position", "positions", "employer", "employee", "employees",
    "team", "teams", "other", "additional", "general", "routine", "assigned",
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
    if words and words <= _GENERIC_REQUIREMENT_WORDS:
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
    if is_incomplete_phrase(phrase) and not _TECHNICAL_COMPOUND_START.match(phrase):
        return "Incomplete connector phrase; check the advertisement context"
    return ""


def _chart_phrase_reason(value):
    """Require identifiable competency wording; retain ambiguous evidence for review."""
    phrase = _CHART_BULLETS.sub("", normalize_text(value).translate(
        {0x200b: None, 0xfeff: None, 0x2060: None})).strip()
    if phrase in _CHART_ONLY_NON_SKILL_PHRASES:
        return _CHART_ONLY_NON_SKILL_PHRASES[phrase]
    if _LEGAL_BOILERPLATE_PHRASE.fullmatch(phrase):
        return "Equal-employment legal boilerplate; not an employer competency"
    if _ADOPTION_OUTCOME_PHRASE.fullmatch(phrase):
        return "Success-metric wording; review before treating as a competency"
    if _MODIFIER_ONLY_PHRASE.fullmatch(phrase):
        return "Modifier without a named activity; specify the skill in source context"
    if _DANGLING_ACCESS_PHRASE.fullmatch(phrase):
        return "Incomplete access wording; the object or competency is missing"
    if _UNSPECIFIED_TECH_OBJECT.fullmatch(phrase):
        return "Unspecified technology object; identify the tool or demonstrable capability in context"
    if _OUTPUT_MODIFIED_PHRASE.fullmatch(phrase):
        return "Ambiguous output-oriented wording; verify the employer competency in source context"
    if _NON_REQUIREMENT_WORDING.fullmatch(phrase):
        return "Benefit, opportunity or promotional wording; verify an actual skill requirement in source context"
    reason = _skill_phrase_reason(phrase)
    if reason:
        return reason
    candidate = _SKILL_REQUIREMENT_PREFIX.sub("", _SKILL_LEVEL_PREFIX.sub("", phrase))
    candidate = chart_skill_key(_SKILL_LEVEL_PREFIX.sub("", candidate))
    if candidate in _NAMED_SKILL_TERMS:
        return ""
    if _WEAK_FRAGMENT_START.match(phrase) or _BROKEN_CLAUSE.search(_TECHNICAL_COMPOUND_START.sub("", phrase)):
        return "Incomplete clause or advertisement fragment; clarify the competency in source context"
    words = re.findall(r"[a-z0-9+#.]+", candidate)
    if len(words) > 1 and words[-1] in _CAPABILITY_HEADS:
        return ""
    if _CONCRETE_TECH_TASK.fullmatch(phrase):
        return ""
    return _UNRECOGNIZED_SKILL_REASON

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
    phrase_reasons = {phrase: _chart_phrase_reason(chart_skill_key(phrase)) for phrase in phrases.unique()}
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


def chart_skill_key(value):
    """Group clear wording variants without changing evidence or framework identities."""
    phrase = _CHART_BULLETS.sub("", normalize_text(value).translate({0x200b: None, 0xfeff: None, 0x2060: None})).strip()
    phrase = re.sub(r"\bdatum\b", "data", phrase)
    while True:
        previous = phrase
        phrase = _skill_word_form(phrase)
        # Strip only neutral decorations with an identifiable skill core.
        core = phrase
        while True:
            stripped = _skill_word_form(_SKILL_LABEL_SUFFIX.sub("", _SKILL_LABEL_PREFIX.sub("", core)))
            if stripped == core:
                break
            core = stripped
        if _identifiable_skill_core(core):
            phrase = core
        task = _SKILL_TASK.fullmatch(phrase)
        if task:
            action, subject = task.groups()
            phrase = re.sub(r"s$", "", subject) + " " + _TASK_CAPABILITIES[action]
        else:
            core = re.sub(r"^(?:conduct|conducting|perform|performing)\s+", "", phrase)
            if core != phrase and _identifiable_skill_core(core):
                phrase = core
        phrase = _CHART_PHRASE_ALIASES.get(phrase, phrase)
        if phrase == previous:
            return phrase


def _skill_word_form(phrase):
    phrase = _CHART_PHRASE_ALIASES.get(phrase, phrase)
    words = phrase.split()
    if len(words) > 1:
        words[-1] = _SKILL_HEAD_FORMS.get(words[-1], words[-1])
        phrase = " ".join(words)
    phrase = re.sub(r"\brequirement(?= (?:elicitation|gathering|analysis|mapping|management)\b)", "requirements", phrase)
    phrase = re.sub(r"\b(dashboards|pipelines|databases|apis|models)(?= (?:development|design|maintenance|improvement|testing|deployment|configuration)\b)",
                    lambda match: match[1][:-1], phrase)
    # Only recognize hyphenated compounds when the spaced name is already known.
    spaced = re.sub(r"(?<=[a-z])[-‐‑](?=[a-z])", " ", phrase)
    parts = spaced.split()
    if len(parts) > 1:
        parts[-1] = _SKILL_HEAD_FORMS.get(parts[-1], parts[-1])
        spaced = " ".join(parts)
    if spaced in _NAMED_SKILL_TERMS:
        phrase = spaced
    return phrase


def _identifiable_skill_core(phrase):
    words = phrase.split()
    return (phrase in _NAMED_SKILL_TERMS or
            len(words) > 1 and words[-1] in _CAPABILITY_HEADS or
            bool(_SKILL_TASK.fullmatch(phrase)))


def skill_chart_tables(skills, jobs, *, allowed_phrases=None):
    """Create an auditable chart view without changing stored research evidence."""
    ids = jobs.get("source_id", pd.Series(dtype=str)).dropna().astype(str)
    ids = ids[ids.str.strip().ne("")]
    view = skills.loc[skills.get("source_id", pd.Series(index=skills.index, dtype=str)).astype(str).isin(ids)].copy()
    view["source_id"] = view.get("source_id", pd.Series(index=view.index, dtype=str))
    if "source_type" in view:
        view = view[view.source_type.isin(["jobs", "Philippine job advertisement"])].copy()
    original = view.get("normalized_phrase", pd.Series("", index=view.index)).fillna("")
    surface = view.get("original_phrase", pd.Series("", index=view.index)).fillna("")
    view["original_normalized_phrase"] = original
    phrases = original.where(original.astype(str).str.strip().ne(""), surface)
    keys = {phrase: chart_skill_key(phrase) for phrase in phrases.unique()}
    view["normalized_phrase"] = phrases.map(keys)
    view["skill_label"] = view.normalized_phrase
    reasons = {phrase: _chart_phrase_reason(phrase) for phrase in view.normalized_phrase.unique()}
    view["review_reason"] = view.normalized_phrase.map(reasons)
    categories = view.get("competency_category", pd.Series("", index=view.index)).fillna("")
    needs_category_reason = view.review_reason.isin(["", _UNRECOGNIZED_SKILL_REASON])
    view.loc[needs_category_reason & categories.map(requirement_type).eq("Credential requirement"), "review_reason"] = "Credential requirement, not a skill"
    view.loc[needs_category_reason & categories.astype(str).str.casefold().eq("irrelevant"), "review_reason"] = "Researcher or classifier marked this phrase irrelevant"
    accepted = view.get("accepted", pd.Series(True, index=view.index)).astype(str).str.casefold().eq("true")
    view.loc[~accepted & view.review_reason.eq(""), "review_reason"] = "Candidate did not meet the skill acceptance rules"
    reason = view.review_reason.fillna("").astype(str)
    review = view.loc[reason.ne("")].copy()
    eligible = view.loc[accepted & reason.eq("")].copy()
    if allowed_phrases is not None:
        eligible = eligible[eligible.original_normalized_phrase.isin(allowed_phrases)]
    types = eligible.get("skill_type", pd.Series("", index=eligible.index)).replace("", pd.NA)
    eligible["category_conflict"] = types.groupby([eligible.source_id, eligible.skill_label]).transform("nunique").gt(1)
    variant_columns = ["original_phrase", "original_normalized_phrase", "skill_label", "competency_category", "skill_type", "category_conflict"]
    variants = (eligible.reindex(columns=["source_id", *variant_columns]).fillna("")
                .groupby(variant_columns, dropna=False).source_id.nunique().rename("job_ads").reset_index())
    variants["grouping_basis"] = variants.original_normalized_phrase.eq(variants.skill_label).map(
        {True: "Same skill wording", False: "Documented skill wording normalization"})
    if "skill_type" in eligible:
        eligible.loc[eligible.category_conflict, "skill_type"] = "Other / Unclassified"
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
            "chart_skill_variants": variants,
            "chart_skill_demand": demand,
            "chart_phrase_review": review,
            "chart_skill_family_demand": family_demand,
            "chart_family_ad_counts": family_ads.sort_values(["family_ads", "job_family"],
                                                              ascending=[False, True], kind="stable").reset_index(drop=True)}


def job_market_kpis(jobs, views, reference):
    """Count the complete evidence for the overview, before chart display filters."""
    demand = views["chart_skill_demand"]
    charted = set(demand.normalized_phrase)
    withheld = set(views["chart_phrase_review"].normalized_phrase.dropna()) - charted - {""}
    role_field = next((field for field in ("job_role", "psf_job_role") if field in reference), None)
    role_count = None
    if role_field and not reference.empty:
        roles = reference[role_field].map(normalize_text).str.split(";").explode().str.strip()
        role_count = int(roles[roles.ne("")].nunique())
    ids = jobs.get("source_id", pd.Series(dtype=str)).dropna().astype(str)
    return {"ads": int(ids[ids.str.strip().ne("")].nunique()), "chartSkills": len(charted),
            "withheldPhrases": len(withheld), "referenceRoles": role_count}


def chart_mapping_rows(mapping):
    """Screen employer phrases before aggregation without rewriting framework labels."""
    if mapping.empty or "normalized_skill" not in mapping:
        return mapping
    original = mapping.normalized_skill.fillna("")
    phrases = original.map({phrase: chart_skill_key(phrase) for phrase in original.unique()})
    reasons = {phrase: _chart_phrase_reason(phrase) for phrase in phrases.unique()}
    return mapping.loc[phrases.map(reasons).eq("")].copy()


def psf_demand_tables(mapping, jobs, taxonomy, *, denominator=None):
    """Aggregate linked evidence; framework row order is presentation metadata only."""
    from .cleaning import normalize_text
    reference = taxonomy.reindex(columns=["competency_id", "competency_name", "job_role"]).fillna("").copy()
    reference["framework_order"] = range(len(reference))
    reference["psf_competency"] = reference.competency_name.map(normalize_text)
    columns = ["source_id", "psf_competency", "psf_job_role", "status"]
    linked = chart_mapping_rows(mapping).reindex(columns=columns).fillna("")
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


def unmapped_chart_counts(occurrences, alignment, *, minimum_jobs=1):
    """Count screened canonical labels; mapped variants suppress the group."""
    columns = ["normalized_skill", "skill_label", "job_ads"]
    if occurrences.empty or alignment.empty:
        return pd.DataFrame(columns=columns)
    mapped = alignment.loc[alignment.status.isin(["ALIGNED", "PARTIALLY ALIGNED"]), "normalized_skill"].map(chart_skill_key)
    unmapped = alignment.loc[alignment.status.eq("NOT MAPPED"), "normalized_skill"].map(chart_skill_key)
    keys = set(unmapped) - set(mapped)
    rows = occurrences.loc[occurrences.normalized_phrase.isin(keys)]
    counts = rows.groupby(["normalized_phrase", "skill_label"]).source_id.nunique().rename("job_ads").reset_index()
    counts = counts.rename(columns={"normalized_phrase": "normalized_skill"})
    return counts.loc[counts.job_ads.ge(minimum_jobs), columns].sort_values(
        ["job_ads", "skill_label"], ascending=[False, True], kind="stable").reset_index(drop=True)
