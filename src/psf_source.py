"""Traceable extraction of the official PSF-AAI PDF; review precedes activation."""
from pathlib import Path
import hashlib
import json
import re
import pandas as pd
from pypdf import PdfReader
from .config import FIELDS
from .storage import atomic_bytes
from .utils import timestamp

OFFICIAL_URL = "https://www.tesda.gov.ph/Uploads/File/Philippine%20Skills%20Framework/ICT/Philippine%20Skills%20Framework%20for%20Analytics%20and%20Artificial%20Intelligence.pdf"
COMPETENCY_ALIASES = {"Collaboration": "collaborate", "Research": "conduct research",
                      "Computational Modeling": "computational modelling"}
OCCUPATIONAL_FAMILIES = ("Business Intelligence & Strategy", "Data Stewardship", "Data Engineering",
                         "Data Science", "AI Engineering", "Applied Data/AI Research")


def _role_context(page_texts, page, role):
    family_match = re.search(r"Skills\s+Maps\s+(" + "|".join(map(re.escape, OCCUPATIONAL_FAMILIES)) + r")", page_texts[page - 1])
    family = family_match.group(1) if family_match else ""
    if not family:
        raise ValueError(f"No occupational family found for {role} on PDF page {page}.")
    for index in range(page - 1, max(-1, page - 6), -1):
        text = re.sub(r"\s+", " ", page_texts[index]).strip()
        if role in text and "Critical Work" in text:
            description = text.split("Critical Work", 1)[0].strip()
            description = description.removeprefix(role).removesuffix(role).strip()
            if len(description) < 100:
                continue
            return {"occupational_family": family, "role_description": description,
                    "role_source_page": index + 1}
    raise ValueError(f"No role description found for {role} before PDF page {page}.")


def reference_role_profiles(root, taxonomy):
    """Role context is evidence, not an additional competency or training alias."""
    path = Path(root) / "data/reference/psf_aai_role_profiles.json"
    if not path.is_file() or "source_hash" not in taxonomy:
        return []
    hashes = set(taxonomy.source_hash)
    return [row for row in json.loads(path.read_text(encoding="utf-8")) if row["source_hash"] in hashes]


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
    edition's heading layout changes. Role links use official names and levels,
    with explicit spelling variants from this edition's role cards.
    """
    path = Path(path)
    source_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    reader = PdfReader(path)
    records, page_texts, role_pages = [], [], []
    for number, page in enumerate(reader.pages, 1):
        spans = []
        def capture(text, cm, tm, font, size):
            if text.strip():
                spans.append((text.strip(), abs(tm[0] * size), tm[5]))
        text = page.extract_text(visitor_text=capture) or ""
        page_texts.append(text)
        if "Functional Skills and Competencies Enabling Skills and Competencies" in text:
            titles = [t for t, size, y in spans if 20 <= size <= 24 and 700 < y < 780]
            if len(titles) != 1:
                raise ValueError(f"Unrecognized role heading on PDF page {number}; review the source manually.")
            role_pages.append((number, titles[0], text))
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
                   proficiency_level="; ".join(levels), aliases=COMPETENCY_ALIASES.get(name, ""),
                   source_page=str(number), source_url=OFFICIAL_URL,
                   source_hash=source_hash, review_status="Parsed — needs researcher review")
        records.append(row)
    if not records:
        raise ValueError("No PSF competency definition blocks found. Use a verified structured CSV or review this PDF edition.")
    frame = pd.DataFrame(records)
    if frame.competency_name.str.casefold().duplicated().any():
        raise ValueError("Duplicate competency definition headings detected; review the PDF layout.")
    links = []
    names = {name.casefold(): name for name in frame.competency_name}
    alternatives = "|".join(re.escape(name) for name in sorted(names, key=len, reverse=True))
    role_skill = re.compile(r"(?<!\w)(" + alternatives + r")\s+(Level [1-6]|Basic|Intermediate|Advanced)\b", re.I)
    for page, role, text in role_pages:
        flat = re.sub(r"\s+", " ", text)
        # The role cards use these variants of the official profile headings.
        flat = re.sub(r"Self-Management", "Self Management", flat, flags=re.I)
        flat = re.sub(r"Computational Modelling", "Computational Modeling", flat, flags=re.I)
        context = _role_context(page_texts, page, role)
        for hit in role_skill.finditer(flat):
            links.append({"competency_name": names[hit.group(1).casefold()], "job_role": role,
                          "proficiency_level": hit.group(2), "source_page": page,
                          "source_url": OFFICIAL_URL, "source_hash": source_hash, **context})
    roles = pd.DataFrame(links, columns=["competency_name", "job_role", "proficiency_level", "source_page",
                                       "source_url", "source_hash", "occupational_family",
                                       "role_description", "role_source_page"])
    roles = roles.drop_duplicates(["competency_name", "job_role", "proficiency_level"])
    if not roles.empty:
        grouped = roles.groupby("competency_name").job_role.agg(lambda values: "; ".join(sorted(set(values))))
        frame["job_role"] = frame.competency_name.map(grouped).fillna("")
        families = roles.groupby("competency_name").occupational_family.agg(lambda values: "; ".join(sorted(set(values))))
        frame["occupational_family"] = frame.competency_name.map(families).fillna("")
    for index, row in frame.iterrows():
        profile = _profile_pages(page_texts, int(row["source_page"]))
        detail = _profile_detail(profile)
        if detail:
            frame.at[index, "competency_description"] = f"{row['competency_description']} Profile details: {detail}"
        frame.at[index, "range_of_application"] = _range_of_application(profile)
    return frame, roles


def apply_bundled_role_links(frame, root):
    """Refresh released links on rows that cite the same official competency."""
    fields = {"competency_id", "competency_name", "source_hash", "review_status", "job_role"}
    if frame.empty or not fields.issubset(frame.columns):
        return frame
    path = Path(root) / "data/reference/psf_aai_default.csv"
    if not path.is_file():
        return frame
    bundled = pd.read_csv(path, dtype=str, keep_default_na=False)
    if not fields.issubset(bundled.columns):
        return frame
    from .cleaning import normalize_text

    keys = ["competency_id", "competency_name", "source_hash"]
    official = bundled[bundled.review_status.eq("Researcher verified")].set_index(keys)
    official_roles = {normalize_text(term) for value in official.job_role for term in value.split(";") if term.strip()}
    current = frame.copy()
    alias_owners = {}
    for index, row in current.iterrows():
        for field in ("competency_name", "aliases", "keywords"):
            for term in str(row.get(field, "")).split(";"):
                if normalized := normalize_text(term):
                    alias_owners.setdefault(normalized, set()).add(index)

    for index, row in current.iterrows():
        key = tuple(row[field] for field in keys)
        if row["review_status"] != "Researcher verified" or key not in official.index or not key[-1]:
            continue
        for field in ("job_role", "aliases", "occupational_family"):
            terms = {normalize_text(term): term.strip() for term in str(row.get(field, "")).split(";") if term.strip()}
            original_terms = terms.copy()
            if field == "job_role":
                released_roles = {normalize_text(term) for term in official.loc[key, field].split(";") if term.strip()}
                terms = {key: value for key, value in terms.items() if key not in official_roles or key in released_roles}
            for term in str(official.loc[key].get(field, "")).split(";"):
                normalized = normalize_text(term)
                if normalized and (field != "aliases" or alias_owners.get(normalized, {index}) == {index}):
                    terms.setdefault(normalized, term.strip())
            if terms == original_terms:
                continue
            value = "; ".join(sorted(terms.values())) if field == "job_role" else "; ".join(terms.values())
            if field not in current:
                current[field] = ""
            current.at[index, field] = value
            if field + "_clean" in current:
                current.at[index, field + "_clean"] = value
    return current


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
