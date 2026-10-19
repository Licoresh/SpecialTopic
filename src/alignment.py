"""Occurrence-specific employer evidence and many-to-many PSF-AAI alignment."""
import pandas as pd
from .psf_mapping import TaxonomyMatcher
from .psf_reviews import occurrence_hash
from .utils import digest, frame_hash

STATUSES = ["ALIGNED", "PARTIALLY ALIGNED", "NOT MAPPED", "UNCLASSIFIED"]
ALIGNMENT_COLUMNS = ["alignment_id", "employer_skill", "normalized_skill", "competency_id",
                     "psf_competency", "psf_job_role", "psf_category", "proficiency_level",
                     "source_page", "source_url", "source_hash", "match_method", "similarity_score",
                     "confidence", "status", "job_source_ids", "interpretation"]
OCCURRENCE_COLUMNS = ["extraction_id", "source_id", "source_type", "original_text", "start_char", "end_char",
                      "rationale", "reviewer", "reviewed_at", "mapping_review_status"]


def calculate_mapping(skills, taxonomy, aligned_threshold=.8, partial_threshold=.6,
                      semantic_path="", semantic_threshold=.8, reviews=None):
    if not 0 <= partial_threshold < aligned_threshold <= 1:
        raise ValueError("Thresholds must satisfy 0 <= partial < aligned <= 1.")
    columns = ALIGNMENT_COLUMNS + OCCURRENCE_COLUMNS
    if skills.empty:
        return pd.DataFrame(columns=columns)
    matcher = TaxonomyMatcher(taxonomy, partial_threshold, semantic_path, semantic_threshold) if not taxonomy.empty else None
    tax_hash = frame_hash(taxonomy)
    references = {str(row["competency_id"]): row for row in taxonomy.fillna("").to_dict("records")}
    reviewed = {key: group.fillna("") for key, group in reviews.groupby("extraction_id")} if reviews is not None and not reviews.empty else {}
    records = []
    for occurrence in skills.fillna("").to_dict("records"):
        phrase = occurrence["normalized_phrase"]
        extraction_id = occurrence.get("extraction_id") or digest([occurrence["source_id"], phrase])[:24]
        review = reviewed.get(extraction_id)
        decisions = []
        stale = False
        if review is not None:
            stale = (not review.reference_hash.eq(tax_hash).all()
                     or not review.occurrence_hash.eq(occurrence_hash(occurrence)).all()
                     or not review.source_id.eq(str(occurrence["source_id"])).all()
                     or bool(set(review.competency_id) - set(references) - {""}))
            if not stale:
                for link in review.drop_duplicates("competency_id").to_dict("records"):
                    reference = references.get(link["competency_id"])
                    match = matcher.match(reference["competency_name"]) if reference and matcher else None
                    decisions.append((match, link))
        else:
            rejected = str(occurrence.get("psf_assignment_reviewed", False)).casefold() == "true"
            match = None
            if matcher:
                if occurrence.get("matching_method") == "human_annotation" and occurrence.get("psf_competency"):
                    match = matcher.match(occurrence["psf_competency"])
                    if match:
                        match = match | {"matching_method": "human_annotation"}
                elif not rejected:
                    match = matcher.match(occurrence["original_phrase"], phrase)
            decisions.append((match, {}))
        if stale:
            decisions = [(None, {})]
        for match, link in decisions:
            score = float(match["similarity_score"]) if match else 0. if matcher else None
            status = ("UNCLASSIFIED" if matcher is None or stale else
                      "ALIGNED" if score >= aligned_threshold else
                      "PARTIALLY ALIGNED" if score >= partial_threshold else "NOT MAPPED")
            accepted = status in ("ALIGNED", "PARTIALLY ALIGNED")
            evidence = match if accepted else {}
            method = ("review_required" if stale else "human_annotation" if link else
                      match["matching_method"] if match else "no_match_above_threshold" if matcher else "reference_unavailable")
            record = {key: "" for key in columns}
            record.update({key: occurrence.get(key, "") for key in OCCURRENCE_COLUMNS})
            record.update(extraction_id=extraction_id, employer_skill=occurrence["original_phrase"], normalized_skill=phrase,
                          status=status, similarity_score=score, confidence=match["confidence"] if match else None,
                          match_method=method, job_source_ids=str(occurrence["source_id"]),
                          rationale=link.get("rationale", ""), reviewer=link.get("reviewer", ""),
                          reviewed_at=link.get("timestamp", ""),
                          mapping_review_status="STALE" if stale else "REVIEWED" if link else "LEGACY REVIEW" if method == "human_annotation" else "SUGGESTED",
                          interpretation="Source or reference changed; review this occurrence again." if stale else
                          "Not clearly mapped to PSF-AAI; review terminology, context and reference coverage." if status == "NOT MAPPED" else
                          "PSF reference unavailable; alignment cannot be assessed." if status == "UNCLASSIFIED" else
                          "Observed reference alignment; verify job context. This does not establish proficiency.")
            for column in ("competency_id", "psf_competency", "psf_category", "proficiency_level", "source_page", "source_url", "source_hash"):
                record[column] = evidence.get(column, "")
            record["psf_job_role"] = evidence.get("job_role", "")
            # Group only equal evidence. Different contexts are never cross-joined by phrase.
            record["alignment_id"] = digest([phrase, record["competency_id"], status, method, score,
                                              tax_hash, aligned_threshold, partial_threshold, semantic_path])[:24]
            records.append(record)
    result = pd.DataFrame(records, columns=columns)
    # Corrections must not silently carry onto a different set of advertisements.
    for identity, group in result.groupby("alignment_id", sort=False):
        result.loc[group.index, "alignment_id"] = digest([identity, sorted(group.extraction_id.tolist()),
                                                         sorted(group.original_text.tolist())])[:24]
    return result


def summarize_alignment(mapping):
    records = []
    for _, group in mapping.groupby("alignment_id", sort=False):
        record = group.iloc[0].reindex(ALIGNMENT_COLUMNS).to_dict()
        record["job_source_ids"] = ";".join(sorted(group.source_id.astype(str).unique()))
        records.append(record)
    return pd.DataFrame(records, columns=ALIGNMENT_COLUMNS)


def calculate_alignment(skills, taxonomy, aligned_threshold=.8, partial_threshold=.6,
                        semantic_path="", semantic_threshold=.8, reviews=None):
    return summarize_alignment(calculate_mapping(skills, taxonomy, aligned_threshold, partial_threshold,
                                                semantic_path, semantic_threshold, reviews))
