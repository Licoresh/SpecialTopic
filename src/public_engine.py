"""Run anonymous public uploads through the research analysis pipeline."""

from __future__ import annotations

import json
import math
from pathlib import Path
import re
import unicodedata

import numpy as np
import pandas as pd

from .alignment import calculate_mapping, summarize_alignment
from .analytics import chart_mapping_rows, job_market_kpis, skill_chart_tables, psf_demand_tables, unmapped_chart_counts
from .category_schema import category_parent
from .cleaning import analysis_job_values, clean_dataset, duplicate_ids, normalize_text
from .config import DEFAULTS, FIELDS, ROOT
from .gap_analysis import calculate_gaps
from .geography import location_tables
from .job_profile import job_profile_tables, job_title_timeline
from .loaders import load_data, map_columns
from .psf_mapping import TaxonomyMatcher
from .skill_extraction import extract_skills
from .utils import digest, frame_hash


MAX_LOCAL_UPLOAD_BYTES = 64 * 1024 * 1024
MAX_HOSTED_UPLOAD_BYTES = 4 * 1024 * 1024
MAX_ROWS = 100_000
RESULT_SCHEMA_VERSION = 5
_MODEL_PATH = "public-web/site/model.json"
_REFERENCE_PATH = "data/reference/psf_aai_default.csv"
_TOKEN = re.compile(r"(?<!\w)(?:\.net|c\+\+|c#|[\w]+)(?!\w)", re.UNICODE)


class ClassifierUnavailable(ValueError):
    """The public analysis must not silently fall back to another classifier."""


class _ReleasedClassifier:
    """Small adapter for the explicitly released browser-model artifact."""

    def __init__(self, artifact):
        if artifact.get("schema") != 1:
            raise ClassifierUnavailable("The evaluated research classifier has not been released for public analysis yet.")
        self.name = artifact["name"]
        self.version = artifact["version"]
        self.trained_at = artifact.get("trainedAt", "")
        self.classes_ = np.asarray(artifact["classes"], dtype=object)
        self.kind = artifact["kind"]
        self.indices = {term: index for index, term in enumerate(artifact["terms"])}
        self.idf = np.asarray(artifact["idf"], dtype=float)
        self.weights = np.asarray(artifact["weights"], dtype=float)
        self.intercepts = np.asarray(artifact["intercepts"], dtype=float)
        self.casefold = artifact.get("casefold", {})
        self.release_status = artifact.get("releaseStatus", "approved")
        self.release_note = artifact.get("releaseNote", "")
        self.binary = self.kind == "logistic" and len(self.classes_) == 2
        self.research_model_name_ = self.name

    def predict_proba(self, phrases):
        output = []
        for phrase in phrases:
            normalized = unicodedata.normalize("NFKC", str(phrase))
            text = "".join(self.casefold.get(char, char.lower()) for char in normalized)
            tokens = _TOKEN.findall(text)
            counts = {}
            for index, token in enumerate(tokens):
                for term in (token, f"{tokens[index - 1]} {token}" if index else None):
                    if term in self.indices:
                        column = self.indices[term]
                        counts[column] = counts.get(column, 0) + 1
            if counts:
                columns = np.fromiter(counts, dtype=int)
                values = np.asarray([(1 + math.log(counts[column])) * self.idf[column] for column in columns])
                values /= np.linalg.norm(values)
                scores = self.weights[:, columns] @ values + self.intercepts
            else:
                scores = self.intercepts.copy()
            if self.binary:
                positive = 1 / (1 + math.exp(-float(np.clip(scores[0], -700, 700))))
                output.append(np.asarray([1 - positive, positive]))
                continue
            scores -= scores.max()
            probabilities = np.exp(scores)
            output.append(probabilities / probabilities.sum())
        return np.asarray(output)


def _model():
    artifact_path = ROOT / _MODEL_PATH
    try:
        artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ClassifierUnavailable("The approved public classifier could not be loaded.") from exc
    return _ReleasedClassifier(artifact)


def _records(frame):
    if frame is None or frame.empty:
        return []
    return json.loads(frame.to_json(orient="records", date_format="iso", double_precision=4))


def _counts(frame, label, value, *, sort=True):
    if frame is None or frame.empty or label not in frame or value not in frame:
        return []
    rows = frame[[label, value]].copy().fillna("")
    rows = rows[rows[label].astype(str).str.strip().ne("")]
    if sort:
        rows = rows.sort_values([value, label], ascending=[False, True], kind="stable")
    return [{"label": str(label_value), "count": int(count_value)}
            for label_value, count_value in rows[[label, value]].itertuples(index=False, name=None)]


def _taxonomy():
    path = ROOT / _REFERENCE_PATH
    taxonomy = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    if "review_status" in taxonomy:
        taxonomy = taxonomy[taxonomy.review_status.eq("Researcher verified")].copy()
    if taxonomy.empty:
        raise ValueError("The verified PSF-AAI reference is unavailable on this server.")
    return taxonomy.reset_index(drop=True)


def automatic_asset_revision():
    return [digest((ROOT / path).read_bytes()) for path in (_MODEL_PATH, _REFERENCE_PATH)]


def automatic_job_scope(jobs):
    """Use rows with job text and retain possible duplicates for review."""
    if jobs.empty:
        return jobs, {"rows": 0, "blank": 0, "duplicates": 0}, ""
    included = jobs.loc[jobs.cleaned_text.fillna("").str.strip().ne("")]
    duplicates = duplicate_ids(included.reindex(columns=["source_id", *FIELDS["jobs"]]))
    quality = {"rows": len(jobs), "blank": len(jobs) - len(included), "duplicates": len(duplicates)}
    return included, quality, frame_hash(analysis_job_values(included))


def automatic_job_analysis(jobs, model, progress=None):
    """Use the released analysis preset for both public and researcher charts."""
    taxonomy = _taxonomy()
    settings = DEFAULTS
    matcher = TaxonomyMatcher(taxonomy, settings["fuzzy_threshold"], settings["semantic_model"], settings["semantic_threshold"])
    extracted, _ = extract_skills(jobs, "jobs", matcher, model, None,
                                  stopwords=settings["stopwords"], batch_size=settings["batch_size"],
                                  max_candidates=settings["max_candidates"], progress=progress)
    views = skill_chart_tables(extracted, jobs)
    mapping = calculate_mapping(views["chart_skill_occurrences"], taxonomy,
                                settings["aligned_threshold"], settings["partial_threshold"],
                                settings["semantic_model"], settings["semantic_threshold"])
    return extracted, views, taxonomy, mapping, summarize_alignment(mapping)


def _build_charts(jobs, extracted, chart_views, profile, geography, monthly, date_evidence, mapping, alignment,
                  taxonomy, unmapped, threshold):
    occurrences = chart_views["chart_skill_occurrences"]
    chartable = occurrences
    demand = chart_views["chart_skill_demand"]
    categories = occurrences.groupby("competency_category").source_id.nunique().rename("job_ads").reset_index()
    parents = occurrences.assign(category_group=occurrences.competency_category.map(category_parent)
                                 .replace("Not applicable", "Category needs review"))
    if "category_conflict" in parents:
        parents.loc[parents.category_conflict.eq(True), "category_group"] = "Category needs review"
    broad = parents.groupby("category_group").source_id.nunique().rename("job_ads").reset_index()
    technical = occurrences[occurrences.skill_type.eq("Technical")].groupby("skill_label").source_id.nunique().rename("job_ads").reset_index()
    enabling = occurrences[occurrences.skill_type.eq("Soft / Enabling")].groupby("skill_label").source_id.nunique().rename("job_ads").reset_index()

    locations = geography["location_evidence"]
    region_counts = locations[locations.region.ne("")].groupby("region").source_id.nunique().rename("job_ads").reset_index()
    city_counts = locations[locations.locality.ne("")].groupby(["region", "locality"]).source_id.nunique().rename("job_ads").reset_index()
    region_skills = (chartable.merge(locations[["source_id", "region"]], on="source_id", how="inner")
                     .loc[lambda frame: frame.region.ne("")]
                     .groupby(["region", "skill_label"]).source_id.nunique().rename("job_ads").reset_index())
    city_skills = (chartable.merge(locations[["source_id", "region", "locality"]], on="source_id", how="inner")
                   .loc[lambda frame: frame.locality.ne("")]
                   .groupby(["region", "locality", "skill_label"]).source_id.nunique().rename("job_ads").reset_index())
    title_source = profile["job_title_source_evidence"].reindex(columns=["source_id", "job_family", "job_title"])
    title_skills = (chartable.merge(title_source, on="source_id", how="inner")
                    .groupby(["job_family", "job_title", "skill_label"]).source_id.nunique().rename("job_ads").reset_index())

    alignment_status = alignment.assign(status=alignment.status.fillna("").astype(str).str.casefold())
    alignment_counts = alignment_status.groupby("status").size().rename("evidence_groups").reset_index()
    alignment_counts = alignment_counts.rename(columns={"status": "label", "evidence_groups": "count"})

    linked = chart_mapping_rows(mapping)
    linked = linked.loc[linked.status.isin(["ALIGNED", "PARTIALLY ALIGNED"]) &
                        linked.psf_competency.fillna("").ne("")].copy()
    role_rows = linked.assign(psf_job_role=linked.psf_job_role.fillna("").astype(str).str.casefold().str.split("; ")).explode("psf_job_role")
    role_rows = role_rows[role_rows.psf_job_role.ne("")]
    role_counts = role_rows.groupby("psf_job_role").source_id.nunique().rename("job_ads").reset_index()
    psf_tables = psf_demand_tables(linked, jobs, taxonomy)
    psf_demand = psf_tables["psf_chart_demand"].copy()
    psf_roles = role_counts.rename(columns={"psf_job_role": "label", "job_ads": "count"})
    references = taxonomy.reindex(columns=["competency_name", "competency_description", "range_of_application",
                                            "source_page", "source_url"]).fillna("").copy()
    references["psf_competency"] = references.competency_name.map(normalize_text)
    references = references.drop_duplicates("psf_competency")
    methods = (linked.groupby("psf_competency").match_method.apply(lambda values: sorted(set(map(str, values)))).to_dict()
               if not linked.empty and "match_method" in linked else {})
    psf_references = psf_demand.merge(references, on="psf_competency", how="left")
    psf_references["methods"] = psf_references.psf_competency.map(methods).apply(lambda value: value or [])
    education = profile["education_level_counts"].copy()
    education["education_level"] = education.education_level.replace({
        "undergraduate / college level": "College / undergraduate", "associate degree": "College / undergraduate",
        "bachelor's degree": "College / undergraduate", "postgraduate degree": "Postgraduate",
        "master's degree": "Postgraduate", "doctoral degree": "Postgraduate",
    })
    education = education.groupby("education_level", as_index=False, sort=False).agg(
        job_ads=("job_ads", "sum"), job_ads_pct=("job_ads_pct", "sum"), level_order=("level_order", "min"))
    education = education.sort_values("level_order", kind="stable")
    title_options = profile["job_title_source_evidence"].drop_duplicates("source_id")
    title_counts = title_options.groupby("job_title").source_id.nunique().rename("job_ads").reset_index()
    title_counts = title_counts[title_counts.job_title.astype(str).str.strip().ne("")]

    return {
        "skills": _counts(demand, "employer_skill", "employer_demand_count"),
        "technicalSkills": _counts(technical, "skill_label", "job_ads"),
        "enablingSkills": _counts(enabling, "skill_label", "job_ads"),
        "broadAreas": _counts(broad, "category_group", "job_ads"),
        "titles": _counts(profile["common_job_title_counts"], "common_job_title", "job_ads"),
        "roleGroups": _counts(profile["job_role_group_counts"], "job_role_group", "job_ads"),
        "sourceTitles": _counts(title_counts, "job_title", "job_ads"),
        "titleFamilies": _records(profile["job_title_family_counts"]),
        "families": _counts(profile["job_family_counts"], "job_family", "job_ads"),
        "locations": _counts(region_counts, "region", "job_ads"),
        "cities": [{"region": str(row.region), "label": str(row.locality), "count": int(row.job_ads)}
                   for row in city_counts.itertuples(index=False)],
        "timeline": [{"label": str(row.month), "count": int(row.job_ads)}
                     for row in monthly.groupby("month").job_ads.sum().reset_index().itertuples(index=False)] if not monthly.empty else [],
        "timelineByTitle": [{"label": str(row.job_title), "month": str(row.month), "count": int(row.job_ads)}
                            for row in monthly.itertuples(index=False)],
        "timelineCoverage": [{"label": str(row.job_title), "dated": int(row.dated), "undated": int(row.undated)}
                             for row in date_evidence.assign(dated=date_evidence.date_status.eq("Dated").astype(int),
                                                             undated=date_evidence.date_status.ne("Dated").astype(int))
                             .groupby("job_title", as_index=False)[["dated", "undated"]].sum().itertuples(index=False)],
        "education": _records(education),
        "experience": _counts(profile["experience_duration_counts"], "requirement", "job_ads"),
        "psf": [{"label": str(row.psf_competency), "count": int(row.job_ads), "percent": float(row.job_ads_pct)}
                for row in psf_demand.sort_values(["job_ads", "psf_competency"], ascending=[False, True], kind="stable").itertuples(index=False)],
        "psfEvidence": [{"label": str(row.psf_competency), "count": int(row.job_ads),
                         "methods": row.methods, "description": str(row.competency_description),
                         "range": str(row.range_of_application), "sourcePage": str(row.source_page),
                         "sourceUrl": str(row.source_url)}
                        for row in psf_references.itertuples(index=False)],
        "psfRoles": _counts(psf_roles, "label", "count"),
        "psfHeatmap": [{"role": str(row.psf_job_role), "competency": str(row.psf_competency), "count": int(row.job_ads)}
                       for row in psf_tables["psf_role_competency_demand"].itertuples(index=False)],
        "alignment": [{"label": str(row.label), "count": int(row.count)} for row in
                      alignment_counts.sort_values(["count", "label"], ascending=[False, True]).itertuples(index=False)],
        "unmapped": _counts(unmapped, "skill_label", "job_ads"),
        "recurring": _counts(unmapped[unmapped.job_ads.ge(threshold)], "skill_label", "job_ads"),
        "familySkillDemand": _records(chart_views["chart_skill_family_demand"]),
        "familyAdCounts": _records(chart_views["chart_family_ad_counts"]),
        "titleSkillDemand": _records(title_skills),
        "regionSkillDemand": _records(region_skills),
        "citySkillDemand": _records(city_skills),
        "roleCompetencyDemand": _records(psf_tables["psf_role_competency_demand"]),
        "referenceEvidence": _records(psf_references),
    }


def analyze_upload(content, filename, mapping, *, hosted=False, progress=None):
    """Analyze one uploaded CSV without persisting its contents or results."""
    maximum = MAX_HOSTED_UPLOAD_BYTES if hosted else MAX_LOCAL_UPLOAD_BYTES
    if not content:
        raise ValueError("Choose a nonempty CSV file.")
    if len(content) > maximum:
        raise ValueError(f"This analysis server accepts CSV files up to {maximum // (1024 * 1024)} MB.")
    if Path(filename).suffix.lower() != ".csv":
        raise ValueError("Use a CSV file for public analysis.")
    encoding = "utf-16" if content.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig"
    raw = load_data(content, Path(filename).name, encoding=encoding)
    if len(raw) > MAX_ROWS:
        raise ValueError("This public analysis is limited to 100,000 rows per upload.")

    header_aliases = {}
    for column in raw.columns:
        if column.startswith("unnamed_column_"):
            header_aliases[f"Column {column.rsplit('_', 1)[-1]}"] = column
        else:
            duplicate = re.fullmatch(r"(.*)__([2-9]\d*)", column)
            if duplicate:
                header_aliases[f"{duplicate.group(1)} [{duplicate.group(2)}]"] = column
    selected = {}
    for field in FIELDS["jobs"]:
        header = str(mapping.get(field) or "")
        selected[field] = header if header in raw.columns else header_aliases.get(header, "")
    selected.pop("source_id", None)
    if not selected.get("job_title") or not any(selected.get(field) for field in ("job_description", "required_skills", "preferred_skills", "qualifications")):
        raise ValueError("Map Job title and at least one description, skills, or qualifications column.")

    dataset_hash = digest(content)
    mapped = map_columns(raw, selected, "jobs", dataset_hash)
    jobs, _ = clean_dataset(mapped, "jobs")
    jobs, quality, analysis_id = automatic_job_scope(jobs)
    if jobs.empty:
        raise ValueError("The mapped CSV has no job advertisement text.")
    settings = DEFAULTS
    model = _model()
    extracted, views, taxonomy, mapping_rows, alignment = automatic_job_analysis(jobs, model, progress)
    chartable = views["chart_skill_occurrences"]
    _, _, _, rates = calculate_gaps(views["chart_skill_occurrences"], jobs, alignment, settings["emerging_min_jobs"])
    unmapped = unmapped_chart_counts(chartable, alignment, minimum_jobs=1)
    profile = job_profile_tables(jobs)
    geography = location_tables(jobs)
    monthly, date_evidence = job_title_timeline(jobs)
    charts = _build_charts(jobs, extracted, views, profile, geography, monthly, date_evidence,
                           mapping_rows, alignment, taxonomy, unmapped, settings["emerging_min_jobs"])

    evidence = []
    skills_by_id = {source_id: group.skill_label.astype(str).tolist()
                    for source_id, group in chartable.groupby("source_id", sort=False)} if not chartable.empty else {}
    psf_by_id = {source_id: group.psf_competency.astype(str).dropna().unique().tolist()
                 for source_id, group in mapping_rows.loc[mapping_rows.psf_competency.fillna("").ne("")].groupby("source_id", sort=False)} if not mapping_rows.empty else {}
    location_by_id = geography["location_evidence"].set_index("source_id") if not geography["location_evidence"].empty else pd.DataFrame()
    for _, row in jobs.head(100).iterrows():
        source_id = str(row["source_id"])
        geo = location_by_id.loc[source_id] if not location_by_id.empty and source_id in location_by_id.index else {}
        evidence.append({"sourceRow": int(row["_raw_row"]), "sourceId": source_id, "jobId": str(row["job_id"]),
                         "title": str(row["job_title"]), "company": str(row["company"]), "location": str(row["location"]),
                         "region": str(geo.get("region", "")), "postingMonth": str(row["posting_date_parsed"])[:7] if str(row["posting_date_parsed"]) else "",
                         "skills": skills_by_id.get(source_id, []), "psf": psf_by_id.get(source_id, []),
                         "url": str(row["url"]), "source": str(row["source"]),
                         "descriptionExcerpt": str(row["job_description"])[:450]})

    kpis = job_market_kpis(jobs, views, taxonomy)
    ads = kpis["ads"]
    experience_evidence = profile["experience_analysis_year_evidence"]
    experience_status = experience_evidence.parse_status.fillna("").astype(str)
    exact_year_rows = experience_evidence.loc[experience_status.eq("Parsed stated years")].drop_duplicates("source_id")
    exact_years = pd.to_numeric(exact_year_rows.min_years, errors="coerce").dropna()
    dated_ads = int(monthly.job_ads.sum()) if not monthly.empty else 0
    metrics = {
        **kpis, **quality,
        "withLocation": int(geography["location_evidence"].loc[geography["location_evidence"].region.ne(""), "source_id"].nunique()),
        "withEducation": int(profile["requirement_field_coverage"].loc[profile["requirement_field_coverage"].source_field.eq("education_requirement"), "stated_job_ads"].sum()),
        "withExperience": int(experience_evidence.loc[experience_status.str.startswith("Parsed") | experience_status.eq("Needs review"), "source_id"].nunique()),
        "withDate": dated_ads,
        "experienceExactCount": int(len(exact_years)),
        "experienceExactMedian": float(exact_years.median()) if not exact_years.empty else None,
        "experienceExactMin": float(exact_years.min()) if not exact_years.empty else None,
        "experienceExactMax": float(exact_years.max()) if not exact_years.empty else None,
        "educationNeedsReview": int(profile["education_level_evidence"].loc[profile["education_level_evidence"].parse_status.eq("Needs review"), "source_id"].nunique()),
        "notStatedEducation": int(profile["requirement_field_coverage"].loc[profile["requirement_field_coverage"].source_field.eq("education_requirement"), "not_stated_job_ads"].sum()),
        "notStatedLocation": int(geography["location_evidence"].loc[geography["location_evidence"].location_status.eq("not stated"), "source_id"].nunique()),
        "unresolvedLocation": int(geography["location_evidence"].loc[geography["location_evidence"].region.eq("") & geography["location_evidence"].location_status.ne("not stated"), "source_id"].nunique()),
        "withPsf": int(mapping_rows.loc[mapping_rows.psf_competency.fillna("").ne(""), "source_id"].nunique()) if not mapping_rows.empty else 0,
        "alignmentGroups": int(len(alignment)),
    }
    return {
        "schemaVersion": RESULT_SCHEMA_VERSION,
        "filename": Path(filename).name,
        "mapping": selected,
        "summary": metrics,
        "charts": charts,
        "model": {"version": model.version, "name": model.name, "trainedAt": model.trained_at,
                  "releaseStatus": getattr(model, "release_status", "approved"),
                  "releaseNote": getattr(model, "release_note", "")},
        "reference": {"sourceUrl": str(taxonomy.source_url.iloc[0]) if "source_url" in taxonomy and not taxonomy.empty else "",
                      "sourceHash": str(taxonomy.source_hash.iloc[0]) if "source_hash" in taxonomy and not taxonomy.empty else "",
                      "competencies": len(taxonomy)},
        "evidence": {"limit": len(evidence), "total": ads, "rows": evidence},
        "alignmentRates": rates,
        "datasetHash": dataset_hash,
        "analysisInputHash": analysis_id,
        "processing": {"engine": "research", "classifier": model.name, "researcherReviewsApplied": False,
                       "stored": False},
    }


def analyze_request(content, filename, mapping):
    """Vercel entry point: use only an explicitly released public model."""
    return analyze_upload(content, filename, mapping, hosted=True)


def health(*, hosted=False):
    maximum = MAX_HOSTED_UPLOAD_BYTES if hosted else MAX_LOCAL_UPLOAD_BYTES
    try:
        artifact = json.loads((ROOT / _MODEL_PATH).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        artifact = {}
    available = artifact.get("schema") == 1
    return {"maxUploadBytes": maximum, "classifierAvailable": available,
            "classifierStatus": artifact.get("releaseStatus", "approved") if available else "unavailable",
            "classifierNotice": artifact.get("releaseNote", ""),
            "engine": "research", "stored": False}
