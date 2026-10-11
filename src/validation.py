import pandas as pd

def validate_mapping(frame, mapping, kind):
    used = [v for v in mapping.values() if v]
    if len(used) != len(set(used)):
        raise ValueError("Each source column may be mapped only once.")
    if any(v not in frame.columns for v in used):
        raise ValueError("A mapped column is missing from this file.")
    if kind == "psf_aai" and not mapping.get("competency_name"):
        raise ValueError("Map a competency name column for PSF-AAI.")
    required = {"jobs": ["job_description", "required_skills", "qualifications", "job_title"]}
    if kind in required and not any(mapping.get(c) for c in required[kind]):
        raise ValueError("Map at least one text field for analysis.")

def validate_taxonomy(frame):
    if "competency_name" not in frame or frame.empty:
        raise ValueError("Upload a researcher-verified PSF-AAI taxonomy with competency_name.")
    if frame.competency_name.str.strip().eq("").any():
        raise ValueError("Every taxonomy row needs a competency name.")
    if "competency_id" in frame and frame.competency_id.duplicated().any():
        raise ValueError("Taxonomy IDs must be unique; combine roles/aliases with semicolons.")
    if frame.competency_name.str.casefold().duplicated().any():
        raise ValueError("Taxonomy names must be unique; combine roles/levels with semicolons.")

def quality_report(frame, kind):
    rows = [{"check": "records", "count": len(frame)}]
    comparison = [c for c in frame if not c.startswith("_") and c not in ("source_id", "job_id")]
    rows.append({"check": "potential_duplicate_rows", "count": int(frame.duplicated(subset=comparison).sum()) if comparison else 0})
    for col in frame:
        if col.startswith("_"):
            continue
        rows.append({"check": f"missing: {col}", "count": int(frame[col].fillna("").astype(str).str.strip().eq("").sum())})
    if kind == "jobs" and "posting_date" in frame:
        dates = pd.to_datetime(frame.posting_date, errors="coerce", format="mixed", utc=True)
        rows.append({"check": "invalid_posting_dates", "count": int((frame.posting_date.ne("") & dates.isna()).sum())})
    return pd.DataFrame(rows)
