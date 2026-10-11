"""Evidence-based research readiness checks; software gates are not research approval."""
import re
import pandas as pd

_PHRASE_EDGE_CONNECTORS = {"a", "an", "and", "as", "at", "by", "for", "from", "in", "of", "on", "or", "the", "to", "with"}
MIN_SOURCE_WARNING = 20  # workflow warning only; not a sample-size calculation


def _edit_distance(left, right):
    row = list(range(len(right) + 1))
    for i, a in enumerate(left, 1):
        current = [i]
        for j, b in enumerate(right, 1):
            current.append(min(current[-1] + 1, row[j] + 1, row[j - 1] + (a != b)))
        row = current
    return row[-1]


def source_overlap(frame, metadata):
    """Return train/test posting overlap for saved source-row holdout provenance."""
    split = (metadata or {}).get("split", {})
    train_rows, test_rows = split.get("train_source_rows", []), split.get("test_source_rows", [])
    if not train_rows or not test_rows or "source_id" not in frame:
        return None
    source_ids = frame.source_id.fillna("").astype(str).tolist()

    def ids(rows):
        return {source_ids[int(row) - 2] for row in rows if str(row).isdigit() and 0 <= int(row) - 2 < len(source_ids) and source_ids[int(row) - 2].strip()}

    train_ids, test_ids = ids(train_rows), ids(test_rows)
    return train_ids & test_ids


def historical_category_disagreements(history):
    """Summarize prior labels that disagreed for a normalized phrase; never overwrite the current table."""
    columns = ["phrase", "historical_categories", "reviewer_ids", "source_ids", "history_rows"]
    if history is None or history.empty or not {"phrase", "label"}.issubset(history.columns):
        return pd.DataFrame(columns=columns)
    data = history.copy().fillna("")
    if "normalized_phrase" not in data:
        from .cleaning import normalize_text
        data["normalized_phrase"] = data.phrase.map(normalize_text)
    else:
        from .cleaning import normalize_text
        data["normalized_phrase"] = data.normalized_phrase.where(
            data.normalized_phrase.astype(str).str.strip().ne(""), data.phrase.map(normalize_text)
        )
    data = data[data.normalized_phrase.astype(str).str.strip().ne("") & data.label.astype(str).str.strip().ne("")]
    records = []
    for normalized, group in data.groupby("normalized_phrase", sort=True):
        categories = sorted(group.label.astype(str).str.strip().unique(), key=str.casefold)
        if len(categories) < 2:
            continue
        records.append({
            "phrase": str(group.phrase.iloc[0]),
            "historical_categories": " · ".join(categories),
            "reviewer_ids": " · ".join(sorted(set(group.get("reviewer", pd.Series(dtype=str)).astype(str)) - {"", "nan"})),
            "source_ids": " · ".join(sorted(set(group.get("source_id", pd.Series(dtype=str)).astype(str)) - {"", "nan"})),
            "history_rows": len(group),
        })
    return pd.DataFrame(records, columns=columns)


def research_data_profile(frame):
    """Return transparent source/reviewer coverage tables without changing annotations."""
    columns = ["source_type", "source_id", "annotation_rows", "distinct_phrases",
               "competency_phrases", "irrelevant_phrases", "reviewer_ids"]
    reviewer_columns = ["reviewer", "annotation_rows", "distinct_phrases"]
    if frame is None or frame.empty:
        return {"sources": pd.DataFrame(columns=columns),
                "reviewers": pd.DataFrame(columns=reviewer_columns),
                "top_two_source_row_share": 0.0}

    data = frame.copy()
    for column in ("phrase", "normalized_phrase", "label", "source_type", "source_id", "reviewer"):
        if column not in data:
            data[column] = ""
    data["_source_type"] = data.source_type.fillna("").astype(str).str.strip().replace("", "Unspecified")
    data["_source_id"] = data.source_id.fillna("").astype(str).str.strip().replace("", "Unspecified")
    data["_reviewer"] = data.reviewer.fillna("").astype(str).str.strip()
    data["_label"] = data.label.fillna("").astype(str).str.strip().str.casefold()
    data["_phrase"] = data.normalized_phrase.fillna("").astype(str).str.strip().str.casefold()
    empty = data["_phrase"].eq("")
    data.loc[empty, "_phrase"] = data.loc[empty, "phrase"].fillna("").astype(str).str.strip().str.casefold()

    source_rows = []
    for (source_type, source_id), group in data.groupby(["_source_type", "_source_id"], sort=True):
        source_rows.append({
            "source_type": source_type,
            "source_id": source_id,
            "annotation_rows": len(group),
            "distinct_phrases": int(group.loc[group._phrase.ne(""), "_phrase"].nunique()),
            "competency_phrases": int(group.loc[group["_label"].ne("") & group["_label"].ne("irrelevant"), "_phrase"].replace("", pd.NA).nunique()),
            "irrelevant_phrases": int(group.loc[group["_label"].eq("irrelevant"), "_phrase"].replace("", pd.NA).nunique()),
            "reviewer_ids": " · ".join(sorted({value for value in group["_reviewer"] if value})),
        })
    sources = pd.DataFrame(source_rows, columns=columns).sort_values(
        ["annotation_rows", "source_id"], ascending=[False, True], ignore_index=True
    ) if source_rows else pd.DataFrame(columns=columns)

    reviewer_rows = []
    for reviewer, group in data[data["_reviewer"].ne("")].groupby("_reviewer", sort=True):
        reviewer_rows.append({"reviewer": reviewer, "annotation_rows": len(group),
                              "distinct_phrases": int(group.loc[group._phrase.ne(""), "_phrase"].nunique())})
    reviewers = pd.DataFrame(reviewer_rows, columns=reviewer_columns).sort_values(
        ["annotation_rows", "reviewer"], ascending=[False, True], ignore_index=True
    ) if reviewer_rows else pd.DataFrame(columns=reviewer_columns)
    total_rows = int(sources.annotation_rows.sum()) if not sources.empty else 0
    top_two_share = float(sources.annotation_rows.head(2).sum() / total_rows) if total_rows else 0.0
    return {"sources": sources, "reviewers": reviewers,
            "top_two_source_row_share": top_two_share}


def assess_research_readiness(frame, metadata=None, validation=None):
    """Assess only observable dataset/evaluation risks; never infer that labels are human-correct."""
    data = frame.copy() if frame is not None else pd.DataFrame()
    findings = []
    reviewers = data.get("reviewer", pd.Series(dtype=str)).fillna("").astype(str).str.strip()
    reviewer_ids = sorted({value for value in reviewers if value})
    if reviewer_ids:
        normalized = {name: re.sub(r"[^a-z0-9]", "", name.casefold()) for name in reviewer_ids}
        aliases = []
        for index, left in enumerate(reviewer_ids):
            for right in reviewer_ids[index + 1:]:
                if _edit_distance(normalized[left], normalized[right]) <= 2:
                    aliases.append((left, right))
        if aliases:
            findings.append({"status": "needs review", "title": "Reviewer IDs need reconciliation",
                             "detail": f"{len(reviewer_ids)} distinct reviewer IDs contain near-duplicates. Confirm which are separate people and standardize IDs before reporting rater counts."})
    if not data.empty and "source_id" in data:
        sources = data.source_id.fillna("").astype(str).str.strip()
        counts = sources[sources.ne("")].value_counts()
        if len(counts) < MIN_SOURCE_WARNING:
            findings.append({"status": "blocking", "title": "Too few independent job-ad sources for a broad claim",
                             "detail": f"The labeled file has {len(counts)} distinct source IDs. The app flags fewer than {MIN_SOURCE_WARNING} sources as a workflow warning; this is not a statistically calculated sample-size requirement, and reaching it would not by itself establish representativeness. Phrase rows from the same posting are correlated and do not count as independent job ads."})
        if len(counts) >= 2 and counts.iloc[:2].sum() / counts.sum() >= .8:
            findings.append({"status": "blocking", "title": "Labels are concentrated in two postings",
                             "detail": f"The two most represented source IDs contribute {counts.iloc[:2].sum():,} of {counts.sum():,} provenance-tagged rows ({counts.iloc[:2].sum()/counts.sum():.0%}). Expand labeling across the sampled job ads."})
    if not data.empty and "phrase" in data:
        token_rows = data.phrase.fillna("").astype(str).str.casefold().str.findall(r"[a-z0-9+#.]+")
        fragments = token_rows.map(lambda tokens: bool(tokens and (tokens[0] in _PHRASE_EDGE_CONNECTORS or tokens[-1] in _PHRASE_EDGE_CONNECTORS)))
        fragment_share = float(fragments.mean())
        if fragment_share >= .1:
            findings.append({"status": "needs review", "title": "Some saved phrases end at a connector",
                             "detail": f"{int(fragments.sum()):,} of {len(fragments):,} rows ({fragment_share:.0%}) start or end with a common connector. The review page can hide these obvious fragments by default; inspect source context and edit or mark them irrelevant as appropriate."})
    overlap = source_overlap(data, metadata or {})
    if overlap:
        findings.append({"status": "blocking", "title": "Saved evaluation leaks job-ad sources across partitions",
                         "detail": f"{len(overlap)} source ID(s) occur in both training and holdout rows. Phrase-level scores from this split are not suitable as generalization estimates."})
    elif metadata and (metadata.get("split", {}).get("strategy", "").startswith("stratified phrase-level")):
        findings.append({"status": "blocking", "title": "Evaluation was split by phrase, not job ad",
                         "detail": "A phrase-level holdout can put wording from one ad in both training and test data. Re-evaluate with job-ad source groups."})
    if metadata:
        split = metadata.get("split", {})
        test_sources = set(split.get("test_source_ids", []))
        if split.get("strategy", "").startswith("source-disjoint") and len(test_sources) < 2:
            findings.append({"status": "blocking", "title": "Holdout contains fewer than two independent job ads",
                             "detail": f"Only {len(test_sources)} distinct source ID(s) are in the test partition. This can describe a single ad but cannot show how the classifier generalizes across job ads."})
    findings.append({"status": "needs review", "title": "Independent annotation quality is not established by the app",
                     "detail": "Reviewer IDs and timestamps document saved rows, but they do not verify that every label was independently checked against its original job ad. Resolve disagreements and document the review protocol."})
    findings.append({"status": "needs review", "title": "Study scope and sampling frame need researcher sign-off",
                     "detail": "Confirm that the selected job ads match the study population, time window, roles, geography, and collection method; app validation cannot certify representativeness."})
    if validation and validation.get("errors"):
        findings.append({"status": "blocking", "title": "Training-data software checks fail", "detail": " ".join(validation["errors"])})
    if not findings:
        findings.append({"status": "needs review", "title": "Researcher sign-off remains required",
                         "detail": "Passing technical checks does not establish construct validity, sampling quality, or independent validation."})
    return {"ready": not findings, "findings": findings, "reviewer_ids": reviewer_ids}
