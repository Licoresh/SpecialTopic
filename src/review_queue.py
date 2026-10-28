"""Phrase-level manual review helpers that preserve posting-level evidence."""

import pandas as pd


def group_candidates_by_phrase(candidates):
    """Return one display row per normalized phrase with a representative source."""
    if candidates.empty:
        return candidates.copy()
    # Streamlit reruns this page when reviewers edit a cell or change a filter.
    # Keep grouping in vectorized pandas operations so a few thousand phrases do
    # not require thousands of Python-level group iterations on every rerun.
    grouped = candidates.copy()
    grouped["_group_order"] = grouped.groupby(
        "normalized_phrase", sort=False, dropna=False
    ).ngroup()
    grouped["_context"] = grouped.get(
        "original_text", pd.Series("", index=grouped.index)
    ).astype(str).str.len()
    grouped["_title"] = grouped.get(
        "job_title", pd.Series("", index=grouped.index)
    ).astype(str).str.len()

    # Match the existing rule: longest context, then longest title, then the
    # lexicographically first source ID, with stable order for any remaining tie.
    ranked = grouped.sort_values(
        ["_group_order", "_context", "_title", "source_id"],
        ascending=[True, False, False, True],
        kind="stable",
    )
    representatives = ranked.drop_duplicates("_group_order", keep="first").copy()

    source_pairs = grouped[["_group_order", "source_type", "source_id"]].copy()
    source_pairs[["source_type", "source_id"]] = source_pairs[
        ["source_type", "source_id"]
    ].astype(str).apply(lambda column: column.str.strip())
    source_pairs = source_pairs[source_pairs["source_id"].ne("")].drop_duplicates()
    source_counts = source_pairs.groupby("_group_order", sort=False).size()
    representatives["source_ads"] = (
        representatives["_group_order"].map(source_counts).fillna(0).astype(int)
    )
    representatives["normalized_phrase"] = representatives["normalized_phrase"].astype(str)
    return representatives.drop(
        columns=["_group_order", "_context", "_title"], errors="ignore"
    ).reset_index(drop=True)


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


def manual_mapping_occurrences(candidates, extracted):
    """Prefer the exact extracted evidence; retain candidates pending extraction."""
    from .utils import digest
    rows = candidates[candidates.source_id.astype(str).str.strip().ne("")].copy()
    rows = rows[rows.source_type.isin(["jobs", "Philippine job advertisement"])]
    rows["source_type"] = "jobs"
    rows["original_phrase"] = rows.phrase
    rows["extraction_id"] = [digest([row.source_id, row.normalized_phrase])[:24]
                             for row in rows.itertuples()]
    rows["pending_extraction"] = True
    if not extracted.empty:
        active = extracted[extracted.source_type.eq("jobs")].copy()
        active["pending_extraction"] = False
        # Shared extraction projections omit long ad text to keep database
        # reads small. Restore it from the exact candidate occurrence before
        # dropping the duplicate candidate row; never borrow another ad's text.
        keys = ["source_id", "normalized_phrase"]
        candidate_evidence = rows.drop_duplicates(keys, keep="last").set_index(keys)
        active_keys = pd.MultiIndex.from_frame(active[keys])
        for column in ("original_text", "job_title", "company", "source_url"):
            if column not in rows:
                continue
            evidence = candidate_evidence[column].reindex(active_keys).fillna("").to_numpy()
            if column not in active:
                active[column] = ""
            missing = active[column].fillna("").astype(str).str.strip().eq("")
            active.loc[missing, column] = evidence[missing.to_numpy()]
        rows = pd.concat([active, rows], ignore_index=True)
    return rows.drop_duplicates(["source_id", "normalized_phrase"], keep="first").fillna("")


def preserve_occurrence_references(rows, labels):
    """Category-only saves must neither erase nor spread legacy PSF references."""
    from .cleaning import normalize_text
    result = rows.copy()
    # Annotation storage normalizes surface phrases, whereas extraction can lemmatize.
    result["normalized_phrase"] = result.phrase.map(normalize_text)
    keys = ["normalized_phrase", "source_type", "source_id"]
    result["psf_competency"] = ""
    if not labels.empty and "psf_competency" in labels:
        previous = labels.drop_duplicates(keys, keep="last").set_index(keys).psf_competency
        result["psf_competency"] = pd.MultiIndex.from_frame(result[keys]).map(previous).fillna("")
    return result
