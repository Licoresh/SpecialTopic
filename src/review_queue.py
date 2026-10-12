"""Phrase-level manual review helpers that preserve posting-level evidence."""

import pandas as pd


def group_candidates_by_phrase(candidates):
    """Return one display row per normalized phrase with a representative source."""
    if candidates.empty:
        return candidates.copy()
    rows = []
    for normalized, group in candidates.groupby("normalized_phrase", sort=False, dropna=False):
        # Prefer the most informative source row for draft suggestions and evidence.
        ranked = group.assign(
            _context=group.get("original_text", pd.Series("", index=group.index)).astype(str).str.len(),
            _title=group.get("job_title", pd.Series("", index=group.index)).astype(str).str.len(),
        ).sort_values(["_context", "_title", "source_id"], ascending=[False, False, True], kind="stable")
        representative = ranked.iloc[0].drop(labels=["_context", "_title"], errors="ignore").to_dict()
        source_pairs = group[["source_type", "source_id"]].astype(str).apply(lambda column: column.str.strip())
        source_pairs = source_pairs[source_pairs.source_id.ne("")].drop_duplicates()
        representative["source_ads"] = int(len(source_pairs))
        representative["normalized_phrase"] = str(normalized)
        rows.append(representative)
    return pd.DataFrame(rows).reset_index(drop=True)


def labels_by_phrase(labels):
    """Build unambiguous existing values for display; conflicts remain blank."""
    result = {}
    if labels.empty or "normalized_phrase" not in labels:
        return result
    for normalized, group in labels.groupby("normalized_phrase", sort=False):
        categories = group.get("label", pd.Series(dtype=str)).fillna("").astype(str).str.strip()
        categories = list(dict.fromkeys(value for value in categories if value))
        psf_values = group.get("psf_competency", pd.Series(dtype=str)).fillna("").astype(str).str.strip()
        psf_values = list(dict.fromkeys(value for value in psf_values if value))
        result[str(normalized)] = {
            "label": categories[0] if len(categories) == 1 else "",
            "psf_competency": psf_values[0] if len(psf_values) == 1 else "",
        }
    return result


def expand_phrase_annotations(rows, occurrences):
    """Copy each reviewed phrase decision to every known source-ad occurrence."""
    columns = ["phrase", "normalized_phrase", "source_type", "source_id", "label", "psf_competency"]
    if rows.empty:
        return pd.DataFrame(columns=columns)
    provenance = occurrences[["normalized_phrase", "phrase", "source_type", "source_id"]].copy()
    provenance = provenance.drop_duplicates(["normalized_phrase", "source_type", "source_id"], keep="first")
    decisions = rows.drop(columns=["phrase", "source_type", "source_id"], errors="ignore")
    expanded = decisions.merge(provenance, on="normalized_phrase", how="left")
    return expanded.reindex(columns=columns).drop_duplicates(
        ["normalized_phrase", "source_type", "source_id"], keep="last"
    ).reset_index(drop=True)
