"""Traceable extraction of the official PSF-AAI PDF; review precedes activation."""
from pathlib import Path
import hashlib
import re
import pandas as pd
from pypdf import PdfReader
from .config import FIELDS
from .storage import atomic_bytes
from .utils import timestamp

OFFICIAL_URL = "https://www.tesda.gov.ph/Uploads/File/Philippine%20Skills%20Framework/ICT/Philippine%20Skills%20Framework%20for%20Analytics%20and%20Artificial%20Intelligence.pdf"


def parse_framework(path):
    """Read competency heading/description blocks, not arbitrary PDF mentions.

    This adapter targets the supplied official edition. It fails closed if the
    edition's heading layout changes. Role links use literal names and levels;
    unresolved spelling variants stay absent, never guessed.
    """
    path = Path(path)
    source_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    reader = PdfReader(path)
    records, page_texts = [], []
    for number, page in enumerate(reader.pages, 1):
        spans = []
        def capture(text, cm, tm, font, size):
            if text.strip():
                spans.append((text.strip(), abs(tm[0] * size), tm[5]))
        text = page.extract_text(visitor_text=capture) or ""
        page_texts.append(text)
        functional = "FSC Code" in text and "Functional Skills and Competencies (FSC)" in text
        enabling = "ESC-" in text and "Enabling Skills and Competencies (ESC)" in text
        if not (functional or enabling):
            continue
        names = [t for t, size, y in spans if 20 <= size <= 24 and y > 650]
        description = [t for t, size, y in spans if 10.5 <= size <= 11.5 and y > 630]
        if not names or not description:
            raise ValueError(f"Unrecognized competency heading layout on PDF page {number}; review the source manually.")
        name = re.sub(r"\s+", " ", " ".join(names)).strip()
        codes = sorted(set(re.findall(r"AAI-[A-Z0-9]+-[1-6]\d{3}-[\d.]+|ESC-[A-Z]+-[BIA]\d+-\d+", text)))
        levels = sorted({"Level " + re.search(r"-([1-6])\d{3}-", code).group(1) for code in codes}) if functional else ["Basic", "Intermediate", "Advanced"]
        if not codes:
            raise ValueError(f"No official FSC/ESC code was read for {name} on PDF page {number}; review this page manually.")
        row = {column: "" for column in FIELDS["psf_aai"]}
        row.update(competency_id="; ".join(codes), competency_name=name,
                   competency_description=re.sub(r"\s+", " ", " ".join(description)).strip(),
                   competency_category="Functional Skills and Competencies" if functional else "Enabling Skills and Competencies",
                   functional_skill=name if functional else "", enabling_skill=name if enabling else "",
                   proficiency_level="; ".join(levels), source_page=str(number), source_url=OFFICIAL_URL,
                   source_hash=source_hash, review_status="Parsed — needs researcher review")
        records.append(row)
    if not records:
        raise ValueError("No PSF competency definition blocks found. Use a verified structured CSV or review this PDF edition.")
    frame = pd.DataFrame(records)
    if frame.competency_name.str.casefold().duplicated().any():
        raise ValueError("Duplicate competency definition headings detected; review the PDF layout.")
    links = []
    for page, text in enumerate(page_texts, 1):
        if "Functional Skills and Competencies Enabling Skills and Competencies" not in text:
            continue
        role = text.splitlines()[0].strip()
        if not role or "Analytics &" in role or "Skills" in role or role.startswith("Critical Work"):
            continue
        flat = re.sub(r"\s+", " ", text)
        for row in frame.itertuples():
            hit = re.search(re.escape(row.competency_name) + r"\s+(Level [1-6]|Basic|Intermediate|Advanced)\b", flat, re.I)
            if hit:
                links.append({"competency_name": row.competency_name, "job_role": role,
                              "proficiency_level": hit.group(1), "source_page": page,
                              "source_url": OFFICIAL_URL, "source_hash": source_hash})
    roles = pd.DataFrame(links, columns=["competency_name", "job_role", "proficiency_level", "source_page", "source_url", "source_hash"])
    if not roles.empty:
        grouped = roles.groupby("competency_name").job_role.agg(lambda values: "; ".join(sorted(set(values))))
        frame["job_role"] = frame.competency_name.map(grouped).fillna("")
    return frame, roles


def save_framework_draft(root, pdf_path):
    frame, roles = parse_framework(pdf_path)
    root = Path(root)
    atomic_bytes(root / "data/processed/psf_aai_draft.csv", frame.to_csv(index=False).encode("utf-8-sig"))
    atomic_bytes(root / "data/processed/psf_role_links.csv", roles.to_csv(index=False).encode("utf-8-sig"))
    return frame


def activate_framework(frame, reviewer, root):
    from .validation import validate_taxonomy
    from .psf_mapping import TaxonomyMatcher
    from .loaders import map_columns
    from .cleaning import clean_dataset
    from .utils import frame_hash
    if not reviewer.strip():
        raise ValueError("Enter the framework reviewer's name or ID.")
    frame = frame.copy().fillna("")
    validate_taxonomy(frame)
    for field in ("source_page", "source_url"):
        if field not in frame or frame[field].astype(str).str.strip().eq("").any():
            raise ValueError("Every verified competency needs a source page and source URL.")
    TaxonomyMatcher(frame)
    frame["review_status"] = "Researcher verified"
    frame["reviewer"] = reviewer.strip()
    frame["review_timestamp"] = timestamp()
    mapped = map_columns(frame, {c:c for c in FIELDS["psf_aai"] if c in frame}, "psf_aai", frame_hash(frame))
    cleaned, _ = clean_dataset(mapped, "psf_aai")
    for name, value in (("verified_psf_aai", frame), ("cleaned_psf_aai", cleaned), ("mapped_psf_aai", mapped)):
        atomic_bytes(Path(root) / f"data/processed/{name}.csv", value.to_csv(index=False).encode("utf-8-sig"))
    # The reviewed reference replaces the active raw-table selection, whose bytes
    # remain archived. This prevents stale upload hashes blocking its extraction.
    import json
    manifest_path = Path(root) / "data/processed/uploads.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest.pop("psf_aai", None)
        atomic_bytes(manifest_path, json.dumps(manifest, indent=2).encode("utf-8"))
    return frame
