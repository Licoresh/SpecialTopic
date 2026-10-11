import html
import re
import unicodedata
from urllib.parse import urlsplit, urlunsplit
import pandas as pd
from .config import TEXT_FIELDS
from .validation import quality_report

TAGS = re.compile(r"<[^>]+>")
SPACE = re.compile(r"\s+")
EDUCATION = re.compile(r"\b(?:bachelor(?:['’]s)?(?:\s+degree)?|master(?:['’]s)?(?:\s+degree)?|doctoral(?:\s+degree)?|doctorate|ph\.?d\.?|undergraduate|associate(?:['’]s)?\s+degree|high\s+school|certification)\b", re.I)
EXPERIENCE = re.compile(r"\b\d+(?:\s*[-–]\s*\d+)?\+?\s*(?:years?|yrs?)\s+(?:(?:of|relevant|professional|work|related|prior)\s+){0,3}experience\b", re.I)

def clean_text(value):
    if value is None or pd.isna(value):
        return ""
    text = unicodedata.normalize("NFKC", html.unescape(str(value)))
    return SPACE.sub(" ", TAGS.sub(" ", text).replace("\x00", " ")).strip()

def normalize_text(value):
    return clean_text(value).casefold()

def normalize_url(value):
    value = clean_text(value)
    if not value:
        return ""
    try:
        p = urlsplit(value if "://" in value else "https://" + value)
        if p.scheme.lower() not in ("http", "https") or not p.netloc:
            return value
        return urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path, p.query, ""))
    except ValueError:
        return value

def duplicate_ids(frame):
    cols = [c for c in frame if not c.startswith("_") and c not in ("source_id", "job_id") and not c.endswith("_clean")]
    normalized = frame[cols].map(normalize_text)
    return frame.loc[normalized.duplicated(keep="first"), "source_id"].tolist()

def clean_dataset(frame, kind, confirmed_duplicates=()):
    unknown = set(confirmed_duplicates) - set(duplicate_ids(frame))
    if unknown:
        raise ValueError("Only confirmed duplicate records may be removed here.")
    out = frame.loc[~frame.source_id.isin(confirmed_duplicates)].copy().fillna("")
    for col in list(out.columns):
        if not col.startswith("_") and col != "source_id":
            out[col + "_clean"] = out[col].map(normalize_url if col in ("url", "source_url") else clean_text)
    if kind in TEXT_FIELDS:
        text_cols = [f + "_clean" for f in TEXT_FIELDS[kind] if f + "_clean" in out]
        out["original_text"] = out[[f for f in TEXT_FIELDS[kind] if f in out]].agg("\n".join, axis=1)
        out["cleaned_text"] = out[text_cols].agg("\n".join, axis=1).str.strip()
        out["empty_text"] = out.cleaned_text.eq("")
    if kind == "jobs":
        out["posting_date_parsed"] = pd.to_datetime(out.posting_date, errors="coerce", format="mixed", utc=True).dt.strftime("%Y-%m-%d").fillna("")
        out["empty_job_description"] = out.job_description_clean.eq("")
        out["education_detected"] = out.cleaned_text.map(lambda text: "; ".join(dict.fromkeys(m.group().casefold() for m in EDUCATION.finditer(text))))
        out["experience_detected"] = out.cleaned_text.map(lambda text: "; ".join(dict.fromkeys(m.group().casefold() for m in EXPERIENCE.finditer(text))))
    if kind == "psf_aai":
        out["competency_category"] = out["competency_category"].where(out["competency_category"].ne(""), out["functional_skill"].map(lambda value: "Functional Skills and Competencies" if value else ""))
        out["competency_category"] = out["competency_category"].where(out["competency_category"].ne(""), out["enabling_skill"].map(lambda value: "Enabling Skills and Competencies" if value else ""))
    return out, quality_report(out, kind)
