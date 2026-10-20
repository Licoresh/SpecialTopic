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


def _range_of_application(page_text):
    text = re.sub(r"\s+", " ", page_text or "")
    match = re.search(
        r"Range\s+of\s+Application\s*:?(.*?)(?=Analytics\s*&\s*Artifical\s+Intelligence|"
        r"Analytics\s*&\s*Artificial\s+Intelligence|Functional\s+Skills\s+and\s+Competencies\s*\(FSC\)|"
        r"Enabling\s+Skills\s+and\s+Competencies\s*\(ESC\)|$)",
        text, re.I,
    )
    return re.sub(r"\s+", " ", match.group(1)).strip(" •\t") if match else ""


def _profile_pages(page_texts, page_number):
    """Join a competency's continuation pages through its Range of Application."""
    parts = [page_texts[page_number - 1]]
    index = page_number
    while index < len(page_texts) and "Range of Application" not in parts[-1]:
        following = page_texts[index]
        first_line = next((line.strip() for line in following.splitlines() if line.strip()), "")
        continues = ("Continue to next page" in parts[-1] or
                     re.match(r"(?:FSC|ESC)\s+Proficiency\s+Level\b", first_line, re.I))
        if not continues:
            break
        parts.append(following)
        index += 1
    return "\n".join(parts)


def _profile_detail(text):
    match = re.search(r"(?:FSC|ESC)\s+Proficiency\s+Description", text, re.I)
    if not match:
        return ""
    detail = re.split(r"Range\s+of\s+Application", text[match.start():], maxsplit=1, flags=re.I)[0]
    detail = re.sub(r"Continue to next page", "", detail, flags=re.I)
    detail = re.sub(r"Analytics\s*&\s*Artifical\s+Intelligence\s+\d+", "", detail, flags=re.I)
    detail = re.sub(r"(?:Functional|Enabling) Skills and Competencies\s*\((?:FSC|ESC)\)", "", detail, flags=re.I)
    return re.sub(r"\s+", " ", detail).strip(" •\t")


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
        summary = re.sub(r"\s+", " ", " ".join(description)).strip()
        row.update(competency_id="; ".join(codes), competency_name=name,
                   competency_description=summary,
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
    for index, row in frame.iterrows():
        profile = _profile_pages(page_texts, int(row["source_page"]))
        detail = _profile_detail(profile)
        if detail:
            frame.at[index, "competency_description"] = f"{row['competency_description']} Profile details: {detail}"
        frame.at[index, "range_of_application"] = _range_of_application(profile)
    return frame, roles


def enrich_verified_profiles(frame, pdf_path):
    """Refresh profile text only when the reviewed rows cite this exact PDF edition."""
    pdf_path = Path(pdf_path)
    source_hash = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
    if frame.empty or "source_hash" not in frame or not frame.source_hash.eq(source_hash).all():
        return frame.copy(), False
    if "competency_description" in frame and frame.competency_description.astype(str).str.contains("Profile details:", regex=False).all():
        return frame.copy(), False
    parsed, _ = parse_framework(pdf_path)
    if set(frame.competency_name) != set(parsed.competency_name):
        raise ValueError("The reviewed PSF-AAI competency list differs from the cited PDF; review the new edition before replacing it.")
    indexed = parsed.set_index("competency_name")
    refreshed = frame.copy()
    for column in ("competency_id", "competency_description", "range_of_application"):
        if column not in refreshed:
            refreshed[column] = ""
        values = refreshed.competency_name.map(indexed[column]).fillna("")
        if column == "competency_id" and not refreshed[column].eq(values).all():
            raise ValueError("The reviewed PSF-AAI competency codes differ from the cited PDF; review them before replacing the reference.")
        refreshed[column] = values
    changed = not refreshed["competency_description"].equals(frame.get("competency_description", pd.Series(index=frame.index, dtype=str))) or not refreshed["range_of_application"].equals(frame.get("range_of_application", pd.Series(index=frame.index, dtype=str)))
    return refreshed, changed


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
