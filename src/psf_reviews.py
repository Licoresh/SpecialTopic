"""Researcher-reviewed links scoped to a phrase occurrence in one advertisement."""
import pandas as pd
from threading import Lock
from . import storage
from .utils import digest, frame_hash, timestamp
from .validation import validate_taxonomy

REVIEW_TABLE = "psf_mapping_reviews"
REVIEW_COLUMNS = ["extraction_id", "source_id", "normalized_phrase", "competency_id",
                  "rationale", "reviewer", "timestamp", "reference_hash", "occurrence_hash", "version"]
_save_lock = Lock()


def occurrence_hash(row):
    return digest([str(row.get(key, "")) for key in
                   ("source_type", "source_id", "normalized_phrase", "original_phrase", "original_text")])


def prepare_mapping_review(occurrence, taxonomy, assignments, reviewer, context_confirmed=False,
                           unmapped_reason=""):
    """Assignments are competency ID -> context-specific rationale; empty means no match."""
    validate_taxonomy(taxonomy)
    if not str(reviewer).strip():
        raise ValueError("Enter a reviewer ID.")
    if not context_confirmed:
        raise ValueError("Confirm that you checked the source context and each selected competency.")
    if not occurrence.get("extraction_id") or not occurrence.get("source_id"):
        raise ValueError("A mapping review requires an extraction and its source advertisement.")
    allowed = set(taxonomy.competency_id.astype(str))
    if set(assignments) - allowed:
        raise ValueError("Select competencies from the active PSF-AAI reference.")
    reasons = {key: str(value).strip() for key, value in assignments.items()}
    if any(not value for value in reasons.values()):
        raise ValueError("Explain the source evidence for every selected competency.")
    if len(reasons) > 1 and len({value.casefold() for value in reasons.values()}) != len(reasons):
        raise ValueError("Provide a distinct, competency-specific rationale for each mapping.")
    if not reasons:
        if not unmapped_reason.strip():
            raise ValueError("Explain why this occurrence has no justified mapping.")
        reasons = {"": unmapped_reason.strip()}
    base = {key: str(occurrence.get(key, "")) for key in
            ("extraction_id", "source_id", "normalized_phrase")}
    base.update(reviewer=reviewer.strip(), timestamp=timestamp(), version="", reference_hash=frame_hash(taxonomy),
                occurrence_hash=occurrence_hash(occurrence))
    return pd.DataFrame([base | {"competency_id": key, "rationale": reason}
                         for key, reason in reasons.items()], columns=REVIEW_COLUMNS)


def save_mapping_review(occurrence, taxonomy, assignments, reviewer, expected_version=0, **options):
    from . import supabase_store
    if supabase_store.configured():
        reviewer = str(supabase_store.st.session_state.get("supabase_user_email", ""))
    rows = prepare_mapping_review(occurrence, taxonomy, assignments, reviewer, **options)
    rows["version"] = str(int(expected_version) + 1)
    if supabase_store.configured():
        supabase_store.save_mapping_review(rows.to_dict("records"), int(expected_version), supabase_store.get_token())
        return rows
    with _save_lock:
        previous = storage.read_frame(REVIEW_TABLE)
        saved = previous[previous.extraction_id.eq(occurrence["extraction_id"])] if not previous.empty else previous
        version = int(saved.version.iloc[0]) if not saved.empty else 0
        if version != int(expected_version):
            raise ValueError("This occurrence was reviewed since you opened it. Refresh and review the current links.")
        remaining = previous[~previous.extraction_id.eq(occurrence["extraction_id"])] if not previous.empty else previous
        storage.save_frame(REVIEW_TABLE, pd.concat([remaining, rows], ignore_index=True))
    return rows
