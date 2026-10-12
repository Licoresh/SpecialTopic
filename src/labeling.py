import pandas as pd
from .cleaning import normalize_text
from .utils import timestamp
from .storage import read_frame, save_frame, atomic_bytes
from .config import ROOT
from .training_sources import ANNOTATION_COLUMNS, training_taxonomy


def _usable_annotation_rows(rows):
    """Return rows with a phrase and category, using the same normalization as saving."""
    if rows is None:
        return pd.DataFrame(columns=["phrase", "normalized_phrase", "label"])
    rows = rows.copy().fillna("")
    if not {"phrase", "label"}.issubset(rows):
        return pd.DataFrame(columns=["phrase", "normalized_phrase", "label"])
    rows = rows[rows.phrase.map(lambda value: isinstance(value, str) and bool(value.strip())) &
                rows.label.map(lambda value: isinstance(value, str) and bool(value.strip()))].copy()
    if rows.empty:
        return rows
    rows["normalized_phrase"] = rows.phrase.map(normalize_text)
    rows["label"] = rows.label.str.strip()
    rows.loc[rows.label.str.casefold().eq("irrelevant"), "label"] = "IRRELEVANT"
    return rows


def annotation_conflicts(rows, previous=None):
    """Find normalized phrases assigned multiple categories in this batch or saved data."""
    prepared = [_usable_annotation_rows(rows)]
    if previous is not None and not previous.empty:
        prepared.append(_usable_annotation_rows(previous))
    usable = pd.concat(prepared, ignore_index=True)
    if usable.empty:
        return {}
    conflicts = {}
    for normalized, group in usable.groupby("normalized_phrase", sort=True):
        categories = sorted(group.label.dropna().astype(str).unique(), key=str.casefold)
        if normalized and len(categories) > 1:
            conflicts[normalized] = {"phrase": group.phrase.iloc[0], "labels": categories}
    return conflicts


def save_annotations(rows, reviewer, conflict_resolutions=None, preserve_row_provenance=False, expected_versions=None):
    from . import supabase_store
    shared = supabase_store.configured()
    if shared:
        if preserve_row_provenance:
            raise ValueError("Review imported labels in the shared table first. A CSV upload cannot verify another researcher's decisions.")
        reviewer = str(supabase_store.st.session_state.get("supabase_user_email", ""))
    if not reviewer.strip():
        raise ValueError("Enter a reviewer name or research ID.")
    rows = rows.copy().fillna("")
    if not {"phrase", "label"}.issubset(rows):
        raise ValueError("Annotations need phrase and label columns.")
    rows = _usable_annotation_rows(rows)
    if "normalized_phrase" not in rows:
        rows["normalized_phrase"] = ""
    if preserve_row_provenance:
        provenance_fields = {"source_type", "source_id", "reviewer", "timestamp"}
        missing_columns = provenance_fields - set(rows.columns)
        if missing_columns:
            raise ValueError("Team annotation files must include source_type, source_id, reviewer, and timestamp columns.")
        missing_values = [field for field in sorted(provenance_fields) if rows[field].astype(str).str.strip().eq("").any()]
        if missing_values:
            raise ValueError("Team annotation rows are missing " + ", ".join(missing_values) + ". Export the reviewed file again from each teammate's app.")
    previous = read_frame("labeled_competencies")
    if shared and expected_versions is None:
        expected_versions = {r.normalized_phrase: int(r.version) for r in previous.itertuples()}
    resolved_previous = pd.DataFrame()
    resolved_import = pd.DataFrame()
    # Conflicts are a dataset-wide invariant: expose old conflicts even when the
    # current page contains different phrases, and require explicit decisions.
    conflicts = annotation_conflicts(rows, previous)
    for normalized, item in annotation_conflicts(pd.DataFrame(columns=["phrase", "label"]), previous).items():
        if normalized not in conflicts:
            conflicts[normalized] = item
        else:
            labels = set(conflicts[normalized]["labels"]) | set(item["labels"])
            conflicts[normalized]["labels"] = sorted(labels, key=str.casefold)
    if conflicts:
        resolutions = conflict_resolutions or {}
        missing = [phrase for phrase in conflicts if phrase not in resolutions]
        invalid = [phrase for phrase, label in resolutions.items()
                   if phrase in conflicts and label not in conflicts[phrase]["labels"]]
        if missing or invalid:
            raise ValueError("Resolve each conflicting phrase by choosing one of its existing categories before saving.")
        for normalized, resolution in resolutions.items():
            if normalized not in conflicts:
                continue
            current_mask = rows.normalized_phrase.eq(normalized)
            if preserve_row_provenance and (rows.loc[current_mask, "label"] != resolution).any():
                resolved_import = pd.concat([resolved_import, rows.loc[current_mask].copy()], ignore_index=True)
                rows.loc[current_mask, "label"] = resolution
                rows.loc[current_mask, "reviewer"] = reviewer.strip()
                rows.loc[current_mask, "timestamp"] = timestamp()
            else:
                rows.loc[current_mask, "label"] = resolution
            if not previous.empty:
                previous = previous.copy().fillna("")
                if "normalized_phrase" not in previous:
                    previous["normalized_phrase"] = previous.phrase.map(normalize_text)
                else:
                    previous["normalized_phrase"] = previous.normalized_phrase.where(
                        previous.normalized_phrase.astype(str).str.strip().ne(""),
                        previous.phrase.map(normalize_text),
                    )
                previous.loc[previous.normalized_phrase.eq(normalized), "label"] = resolution
                previous.loc[previous.normalized_phrase.eq(normalized), "reviewer"] = reviewer.strip()
                previous.loc[previous.normalized_phrase.eq(normalized), "timestamp"] = timestamp()
                resolved_previous = pd.concat(
                    [resolved_previous, previous[previous.normalized_phrase.eq(normalized)]], ignore_index=True
                )
    if rows.empty and resolved_previous.empty:
        if conflicts:
            raise ValueError("Resolve each conflicting phrase by choosing one of its existing categories before saving.")
        raise ValueError("Enter at least one phrase and category.")
    rows["psf_competency"] = rows.get("psf_competency", "")
    taxonomy = training_taxonomy(ROOT)
    allowed = set(taxonomy.competency_name) if not taxonomy.empty else set()
    invalid = set(rows.psf_competency) - allowed - {""}
    if invalid:
        raise ValueError("PSF assignments must exactly match a competency in the active taxonomy: " + ", ".join(sorted(invalid)))
    if preserve_row_provenance:
        rows["reviewer"] = rows.reviewer.astype(str).str.strip()
        rows["timestamp"] = rows.timestamp.astype(str).str.strip()
    else:
        rows["reviewer"] = reviewer.strip()
        rows["timestamp"] = timestamp()
    for column in ANNOTATION_COLUMNS:
        if column not in rows:
            rows[column] = ""
    rows = rows[ANNOTATION_COLUMNS]
    combined = pd.concat([previous, rows], ignore_index=True)
    remaining_conflicts = annotation_conflicts(pd.DataFrame(columns=["phrase", "label"]), combined)
    if remaining_conflicts:
        phrases = ", ".join(item["phrase"] for item in list(remaining_conflicts.values())[:5])
        raise ValueError("The saved dataset still has conflicting categories for normalized phrases: " + phrases)
    if shared:
        # Submit only the explicit edits. The RPC applies category reconciliation
        # and records the authenticated identity in one database transaction.
        supabase_store.save_reviewed_annotations(rows.to_dict("records"), supabase_store.get_token(),
                                                expected_versions, conflict_resolutions)
        current = read_frame("labeled_competencies")
        try:
            atomic_bytes(ROOT / "data/processed/shared_labeled_competencies.csv", current[ANNOTATION_COLUMNS].to_csv(index=False).encode("utf-8-sig"))
        except OSError:
            # The database commit succeeded. Do not misreport it as a failed save.
            supabase_store.st.session_state["backup_warning"] = "Labels saved in Supabase, but the local CSV backup could not be written. Download reviewed data to retain a backup."
        return current
    audit = ROOT / "data/feedback/annotation_history.csv"
    history = pd.read_csv(audit, keep_default_na=False) if audit.exists() else pd.DataFrame()
    atomic_bytes(audit, pd.concat([history, resolved_previous, resolved_import, rows], ignore_index=True).to_csv(index=False).encode("utf-8-sig"))
    current = combined.drop_duplicates(["normalized_phrase", "source_type", "source_id"], keep="last")
    save_frame("labeled_competencies", current)
    return current

def save_correction(table, row_id, field, original, corrected, reviewer, comment=""):
    if not reviewer.strip():
        raise ValueError("Enter a reviewer name or research ID.")
    path = ROOT / "data/feedback/corrections.csv"
    history = pd.read_csv(path, dtype=str, keep_default_na=False) if path.exists() else pd.DataFrame()
    row = {"table": table, "row_id": row_id, "field": field, "original_prediction": str(original),
           "corrected_prediction": str(corrected), "reviewer": reviewer, "comment": comment, "timestamp": timestamp()}
    atomic_bytes(path, pd.concat([history, pd.DataFrame([row])], ignore_index=True).to_csv(index=False).encode("utf-8-sig"))

def corrections():
    path = ROOT / "data/feedback/corrections.csv"
    return pd.read_csv(path, dtype=str, keep_default_na=False) if path.exists() else pd.DataFrame()

def apply_corrections(frame, table, key):
    out = frame.copy()
    history = corrections()
    if history.empty or out.empty:
        return out
    for row in history[history.table.eq(table)].itertuples():
        if row.field in out:
            mask = out[key].astype(str).eq(row.row_id)
            out.loc[mask, row.field] = row.corrected_prediction
            if table == "extraction" and row.field == "competency_category" and "human_label" in out:
                out.loc[mask, "human_label"] = row.corrected_prediction
                if "model_prediction" in out:
                    predicted = out.loc[mask, "model_prediction"]
                    out.loc[mask, "agreement"] = predicted.map(lambda value: "Match" if value == row.corrected_prediction else "Mismatch" if value else "")
            if table == "extraction" and row.field == "psf_competency":
                out.loc[mask, "matching_method"] = "human_annotation"
                out.loc[mask, "psf_assignment_reviewed"] = True
            if mask.any():
                if "human_corrected" not in out:
                    out["human_corrected"] = False
                out.loc[mask, "human_corrected"] = True
    return out
