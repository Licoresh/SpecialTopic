"""Descriptive job-title and qualification evidence from selected job ads."""

import re

import pandas as pd

from .cleaning import EDUCATION, EXPERIENCE, clean_text


def _counts(frame, column, output_name):
    if frame.empty or column not in frame:
        return pd.DataFrame(columns=[column, output_name])
    values = frame[column].map(clean_text).replace("", pd.NA).dropna()
    result = values.value_counts().rename_axis(column).reset_index(name=output_name)
    denominator = frame.source_id.nunique() if "source_id" in frame else len(frame)
    result["job_ads_pct"] = (100 * result[output_name] / denominator).round(1) if denominator else 0.0
    return result


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
        explicit_rows.append({"source_id": source_id, "requirement": explicit or "Not stated"})
        if explicit:
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
    summary = (explicit_frame.groupby("requirement", dropna=False).source_id.nunique()
               .rename("job_ads").reset_index().sort_values("job_ads", ascending=False, kind="stable"))
    denominator = jobs.source_id.nunique() if "source_id" in jobs else len(jobs)
    summary["job_ads_pct"] = (100 * summary.job_ads / denominator).round(1) if denominator else 0.0
    evidence = pd.DataFrame(evidence_rows)
    if not evidence.empty:
        evidence = evidence.drop_duplicates(["source_id", "requirement_type", "phrase", "source_field", "evidence"])
        evidence = evidence.sort_values(["requirement_type", "phrase", "job_title"], kind="stable")
    return summary, evidence


def job_profile_tables(jobs):
    """Build export-ready job-market tables using unique advertisements as units."""
    job_ads = jobs.drop_duplicates("source_id") if "source_id" in jobs else jobs.copy()
    titles = _counts(job_ads, "job_title", "job_ads")
    families = _counts(job_ads, "job_family", "job_ads")
    education, education_evidence = _requirements(job_ads, "education_requirement", (EDUCATION,))
    experience, experience_evidence = _requirements(job_ads, "experience_requirement", (EXPERIENCE,))
    evidence = pd.concat([education_evidence, experience_evidence], ignore_index=True)
    tables = {"job_title_counts": titles,
              "job_family_counts": families,
              "education_requirement_counts": education,
              "experience_requirement_counts": experience,
              "requirement_evidence": evidence}
    return tables
