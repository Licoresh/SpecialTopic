"""Employer phrase alignment against the active PSF-AAI reference."""
import pandas as pd
from .psf_mapping import TaxonomyMatcher
from .utils import digest, frame_hash

STATUSES = ["ALIGNED", "PARTIALLY ALIGNED", "NOT MAPPED", "UNCLASSIFIED"]


def calculate_alignment(skills, taxonomy, aligned_threshold=.8, partial_threshold=.6, semantic_path="", semantic_threshold=.8):
    if not 0 <= partial_threshold < aligned_threshold <= 1:
        raise ValueError("Thresholds must satisfy 0 <= partial < aligned <= 1.")
    columns = ["alignment_id", "employer_skill", "normalized_skill", "psf_competency", "psf_job_role", "psf_category", "proficiency_level", "source_page", "source_url", "source_hash", "match_method", "similarity_score", "confidence", "status", "job_source_ids", "interpretation"]
    if skills.empty:
        return pd.DataFrame(columns=columns)
    matcher = TaxonomyMatcher(taxonomy, partial_threshold, semantic_path, semantic_threshold) if not taxonomy.empty else None
    tax_hash = frame_hash(taxonomy)
    records = []
    for phrase, group in skills.groupby("normalized_phrase", sort=True):
        match = None
        if matcher:
            reviewed = group[group.get("matching_method", pd.Series("", index=group.index)).eq("human_annotation")]
            assignments = reviewed.get("psf_competency", pd.Series(dtype=str)).replace("", pd.NA).dropna().unique()
            if len(assignments) == 1:
                match = matcher.match(assignments[0])
                if match:
                    match = match | {"matching_method": "human_annotation", "similarity_score": 1., "confidence": 1.}
            elif len(assignments) > 1:
                raise ValueError(f"Conflicting PSF assignments for {phrase}. Resolve annotations first.")
            rejected = group.get("psf_assignment_reviewed", pd.Series(False, index=group.index)).fillna(False).astype(str).str.casefold().eq("true") & group.get("psf_competency", pd.Series("", index=group.index)).eq("")
            if not match and not rejected.any():
                matches = [matcher.match(surface, phrase) for surface in group.original_phrase.unique()]
                matches = [m for m in matches if m]
                match = max(matches, key=lambda m: m["similarity_score"]) if matches else None
        score = match["similarity_score"] if match else 0. if matcher else None
        status = "UNCLASSIFIED" if matcher is None else "ALIGNED" if score >= aligned_threshold else "PARTIALLY ALIGNED" if score >= partial_threshold else "NOT MAPPED"
        record = {column: "" for column in columns}
        record.update(alignment_id=digest([phrase, sorted(group.source_id.unique()), tax_hash, aligned_threshold, partial_threshold, semantic_path, match])[:24],
                      employer_skill=group.original_phrase.iloc[0], normalized_skill=phrase, status=status,
                      similarity_score=score, confidence=match["confidence"] if match else None,
                      match_method=match["matching_method"] if match else "no_match_above_threshold" if matcher else "reference_unavailable",
                      job_source_ids=";".join(sorted(group.source_id.unique())),
                      interpretation="Not clearly mapped to PSF-AAI; review terminology, context and reference coverage." if status == "NOT MAPPED" else "PSF reference unavailable; alignment cannot be assessed." if status == "UNCLASSIFIED" else "Observed reference alignment; verify job context. This does not establish proficiency.")
        if match:
            record["suggested_psf_competency"] = match["psf_competency"]
            accepted_mapping = status in ("ALIGNED", "PARTIALLY ALIGNED")
            for column in ("psf_competency", "psf_category", "proficiency_level", "source_page", "source_url", "source_hash"):
                record[column] = match.get(column, "") if accepted_mapping else ""
            record["psf_job_role"] = match.get("job_role", "") if accepted_mapping else ""
        records.append(record)
    return pd.DataFrame(records, columns=columns)
