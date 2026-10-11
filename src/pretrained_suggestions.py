"""Optional open-weight pretrained label drafts for researcher review.

Drafts are persisted separately. Only reviewed values are written to the
researcher-labeled training table by the Manual Labeling workflow.
"""
from functools import lru_cache
from pathlib import Path
import re
import pandas as pd
from .cleaning import normalize_text
from .utils import digest, timestamp
from .storage import atomic_bytes
from .skill_extraction import GENERAL


MODEL_ID = "BAAI/bge-m3"
MODEL_REVISION = "5617a9f61b028005a4858fdac845db406aefb181"
PSF_MODEL_ID = MODEL_ID
PSF_MODEL_REVISION = MODEL_REVISION
_ENCODE_BATCH_SIZE = 8
_LEADING_FRAGMENTS = {"a", "an", "and", "as", "at", "by", "for", "from", "in", "of", "on", "or", "the", "to", "with"}
_TRAILING_FRAGMENTS = {"a", "an", "and", "as", "at", "by", "for", "from", "in", "of", "on", "or", "the", "to", "with"}

CATEGORY_DESCRIPTIONS = {
    "AI / Machine Learning": "artificial intelligence or machine learning skills, AI tools, machine learning models, or AI system design",
    "Data / Analytics": "data or analytics skills such as data analysis, SQL databases, statistics, reporting, or business intelligence",
    "Technical / Digital": "technical and digital tool skills such as programming, software, IT, website development, or design software",
    "Business / Domain": "business, marketing, operations, finance, or knowledge of a specific industry",
    "Soft / Enabling": "transferable communication and interpersonal skills, including written or spoken English, teamwork, creativity, attention to detail, organization, or time management",
    "Leadership / Management": "leading people or teams, supervising staff, directing work, or setting team goals",
    "Education / Qualification": "a required formal education credential, degree, professional certification, license, or training qualification",
    "IRRELEVANT": "not a skill or competency a candidate can demonstrate, such as an incomplete phrase, generic instruction, job title, or company name",
}

_TOKEN = re.compile(r"[a-z0-9+#.]+", re.IGNORECASE)
SUGGESTION_COLUMNS = [
    "suggestion_key", "normalized_phrase", "source_type", "source_id", "phrase",
    "category", "category_score", "category_method", "psf_competency", "psf_score",
    "category_model", "category_revision", "psf_model", "psf_revision", "generated_at",
]


@lru_cache(maxsize=1)
def load_competency_encoder():
    """Load the pinned multilingual sentence encoder used for both suggestions."""
    from sentence_transformers import SentenceTransformer

    encoder = SentenceTransformer(MODEL_ID, revision=MODEL_REVISION, device="cpu")
    # Suggestions use a phrase plus one nearby sentence, so the model's full
    # 8k-token window is unnecessary and wasteful for local CPU inference.
    encoder.max_seq_length = 512
    return encoder


def source_context(phrase, original_text, window=240):
    """Return the phrase and its nearby source sentence, without the full ad."""
    phrase = str(phrase or "").strip()
    source = str(original_text or "").strip()
    if not source:
        return f"Candidate phrase: {phrase}"

    match_at = source.casefold().find(phrase.casefold()) if phrase else -1
    if match_at < 0:
        source = re.sub(r"\s+", " ", source)
        context = source[:window].strip()
    else:
        boundaries = "\n.!?;"
        start = max((source.rfind(char, 0, match_at) for char in boundaries), default=-1) + 1
        ends = [position for char in boundaries if (position := source.find(char, match_at + len(phrase))) >= 0]
        end = min(ends) if ends else len(source)
        context = re.sub(r"\s+", " ", source[start:end]).strip()
        if len(context) > window:
            left = max(0, match_at - start - window // 2)
            context = "…" + context[left:left + window].strip() + "…"
    return f"Candidate phrase: {phrase}\nPosting context: {context}"


def is_incomplete_phrase(phrase):
    """Flag common connector-led/trailing fragments for phrase editing first."""
    tokens = _TOKEN.findall(str(phrase or ""))
    return bool(tokens and (tokens[0].casefold() in _LEADING_FRAGMENTS or tokens[-1].casefold() in _TRAILING_FRAGMENTS))


@lru_cache(maxsize=1)
def _default_category_vectors(category_texts):
    return load_competency_encoder().encode(
        list(category_texts), normalize_embeddings=True, batch_size=_ENCODE_BATCH_SIZE, show_progress_bar=False
    )


def suggest_categories(records, encoder=None):
    """Rank the category descriptions against each phrase and its source context.

    `records` should contain `phrase` and may contain `original_text`. Cosine
    scores rank suggestions; they are not calibrated accuracy.
    """
    records = list(records)
    if not records:
        return []
    use_default_encoder = encoder is None
    if encoder is None:
        encoder = load_competency_encoder()
    texts = [source_context(row.get("phrase", ""), row.get("original_text", "")) for row in records]
    categories = list(CATEGORY_DESCRIPTIONS)
    category_texts = tuple(f"{category}. {CATEGORY_DESCRIPTIONS[category]}" for category in categories)
    if use_default_encoder:
        category_vectors = _default_category_vectors(category_texts)
    else:
        category_vectors = encoder.encode(list(category_texts), normalize_embeddings=True, batch_size=_ENCODE_BATCH_SIZE, show_progress_bar=False)
    text_vectors = encoder.encode(texts, normalize_embeddings=True, batch_size=_ENCODE_BATCH_SIZE, show_progress_bar=False)
    similarities = text_vectors @ category_vectors.T
    suggestions = []
    for scores in similarities:
        index = int(scores.argmax())
        suggestions.append({
            "label": categories[index],
            "score": float(scores[index]),
            "category_method": "BGE-M3 semantic similarity",
            "incomplete_phrase": False,
            "model": MODEL_ID,
            "revision": MODEL_REVISION,
        })
    for row, suggestion in zip(records, suggestions):
        exact_category = GENERAL.get(normalize_text(row.get("phrase", "")))
        if exact_category:
            # The project vocabulary is a direct, auditable rule for these
            # exact phrases. Do not preserve a contradictory embedding score.
            suggestion["label"] = exact_category
            suggestion["score"] = None
            suggestion["category_method"] = "Exact project vocabulary match"
        suggestion["incomplete_phrase"] = is_incomplete_phrase(row.get("phrase", ""))
    return suggestions


def suggestion_key(row):
    return digest([
        normalize_text(row.get("phrase", "")),
        str(row.get("source_type", "")),
        str(row.get("source_id", "")),
    ])


def _competency_text(row):
    parts = [row.get("competency_name", ""), row.get("competency_category", "")]
    for field in ("keywords", "aliases", "functional_skill", "enabling_skill", "competency_description"):
        value = str(row.get(field, "") or "").strip()
        if value:
            parts.append(value)
    return ". ".join(str(part).strip() for part in parts if str(part).strip())


@lru_cache(maxsize=4)
def _default_taxonomy_vectors(competency_texts):
    return load_competency_encoder().encode(
        list(competency_texts), normalize_embeddings=True, batch_size=_ENCODE_BATCH_SIZE, show_progress_bar=False
    )


def suggest_psf_competencies(records, taxonomy, encoder=None):
    """Rank official taxonomy entries against each phrase and source context.

    Similarity scores rank entries for review; they are not calibrated
    probabilities, evidence of equivalence, or research performance metrics.
    """
    records = list(records)
    taxonomy_rows = taxonomy.fillna("").to_dict("records") if hasattr(taxonomy, "fillna") else list(taxonomy)
    if not records or not taxonomy_rows:
        return [{"psf_competency": "", "psf_score": None} for _ in records]
    use_default_encoder = encoder is None
    if encoder is None:
        encoder = load_competency_encoder()
    competency_texts = [_competency_text(row) for row in taxonomy_rows]
    candidate_texts = [source_context(row.get("phrase", ""), row.get("original_text", "")) for row in records]
    if use_default_encoder:
        competency_vectors = _default_taxonomy_vectors(tuple(competency_texts))
    else:
        competency_vectors = encoder.encode(competency_texts, normalize_embeddings=True, batch_size=_ENCODE_BATCH_SIZE, show_progress_bar=False)
    candidate_vectors = encoder.encode(candidate_texts, normalize_embeddings=True, batch_size=_ENCODE_BATCH_SIZE, show_progress_bar=False)
    similarities = candidate_vectors @ competency_vectors.T
    suggestions = []
    for scores in similarities:
        index = int(scores.argmax())
        entry = taxonomy_rows[index]
        suggestions.append({
            "psf_competency": str(entry.get("competency_name", "")),
            "psf_score": float(scores[index]),
            "psf_model": PSF_MODEL_ID,
            "psf_revision": PSF_MODEL_REVISION,
        })
    return suggestions


def suggest_labels(records, taxonomy, encoder=None):
    """Return an AI category plus a PSF-AAI match suggestion for each phrase."""
    records = list(records)
    categories = suggest_categories(records, encoder=encoder)
    competencies = suggest_psf_competencies(records, taxonomy, encoder=encoder)
    combined = []
    for category, competency in zip(categories, competencies):
        # IRRELEVANT phrases have no competency assignment by definition.
        if category.get("label") == "IRRELEVANT":
            competency = {"psf_competency": "", "psf_score": None,
                          "psf_model": PSF_MODEL_ID, "psf_revision": PSF_MODEL_REVISION}
        combined.append({**category, **competency})
    return combined


def save_ai_suggestions(root, records, suggestions):
    """Persist predictions separately from researcher-reviewed annotations."""
    if len(records) != len(suggestions):
        raise ValueError("Each candidate needs exactly one AI suggestion record.")
    generated = timestamp()
    rows = []
    for record, suggestion in zip(records, suggestions):
        rows.append({
            "suggestion_key": suggestion_key(record),
            "normalized_phrase": str(record.get("normalized_phrase", "") or normalize_text(record.get("phrase", ""))),
            "source_type": str(record.get("source_type", "")),
            "source_id": str(record.get("source_id", "")),
            "phrase": str(record.get("phrase", "")),
            "category": str(suggestion.get("label", "")),
            "category_score": suggestion.get("score", ""),
            "category_method": str(suggestion.get("category_method", "BGE-M3 semantic similarity")),
            "psf_competency": str(suggestion.get("psf_competency", "")),
            "psf_score": suggestion.get("psf_score", ""),
            "category_model": str(suggestion.get("model", MODEL_ID)),
            "category_revision": str(suggestion.get("revision", MODEL_REVISION)),
            "psf_model": str(suggestion.get("psf_model", PSF_MODEL_ID)),
            "psf_revision": str(suggestion.get("psf_revision", PSF_MODEL_REVISION)),
            "generated_at": generated,
        })
    path = Path(root) / "data/processed/pretrained_label_suggestions.csv"
    previous = pd.read_csv(path, dtype=str, keep_default_na=False) if path.exists() else pd.DataFrame(columns=SUGGESTION_COLUMNS)
    new_rows = pd.DataFrame(rows, columns=SUGGESTION_COLUMNS)
    if not previous.empty:
        replaced = {
            (normalize_text(row.get("phrase", "")), str(row.get("source_type", "")), str(row.get("source_id", "")))
            for row in records
        }
        previous_identity = list(zip(
            previous.phrase.map(normalize_text), previous.source_type.astype(str), previous.source_id.astype(str)
        ))
        previous = previous.loc[[identity not in replaced for identity in previous_identity]]
    combined = new_rows if previous.empty else pd.concat([previous, new_rows], ignore_index=True).reindex(columns=SUGGESTION_COLUMNS)
    combined = combined.drop_duplicates("suggestion_key", keep="last")
    combined = apply_exact_vocabulary_overrides(combined)
    atomic_bytes(path, combined.to_csv(index=False).encode("utf-8-sig"))
    return combined


def apply_exact_vocabulary_overrides(frame):
    """Correct exact project-vocabulary category drafts without inventing scores."""
    frame = frame.copy()
    if "category_method" not in frame:
        frame["category_method"] = "BGE-M3 semantic similarity"
    else:
        frame["category_method"] = frame.category_method.fillna("").replace("", "BGE-M3 semantic similarity")
    if "category_score" not in frame:
        frame["category_score"] = ""
    else:
        # Exact rule matches have no embedding confidence. Keep mixed numeric/
        # blank values without pandas' incompatible-dtype assignment warning.
        frame["category_score"] = frame.category_score.astype(object)
    if "phrase" not in frame:
        return frame
    for index, phrase in frame.phrase.items():
        category = GENERAL.get(normalize_text(phrase))
        if category:
            frame.at[index, "category"] = category
            frame.at[index, "category_score"] = ""
            frame.at[index, "category_method"] = "Exact project vocabulary match"
    return frame


def refresh_saved_exact_vocabulary_overrides(root):
    """Update persisted suggestion drafts to the current deterministic rule."""
    path = Path(root) / "data/processed/pretrained_label_suggestions.csv"
    if not path.exists():
        return 0
    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    updated = apply_exact_vocabulary_overrides(frame)
    changed_mask = pd.Series(False, index=frame.index)
    for column in ("category", "category_score", "category_method"):
        old_values = frame.get(column, pd.Series("", index=frame.index)).astype(str)
        changed_mask |= old_values.ne(updated[column].astype(str))
    changed_rows = int(changed_mask.sum())
    if changed_rows:
        atomic_bytes(path, updated.to_csv(index=False).encode("utf-8-sig"))
    return changed_rows


def load_ai_suggestions(root):
    path = Path(root) / "data/processed/pretrained_label_suggestions.csv"
    if not path.exists():
        return {}
    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    required = {"category_model", "category_revision", "psf_model", "psf_revision", "suggestion_key"}
    if not required.issubset(frame.columns):
        return {}
    # Do not present drafts produced by an older encoder as BGE-M3 suggestions.
    frame = frame[
        frame.category_model.eq(MODEL_ID) & frame.category_revision.eq(MODEL_REVISION) &
        frame.psf_model.eq(PSF_MODEL_ID) & frame.psf_revision.eq(PSF_MODEL_REVISION)
    ]
    if frame.empty:
        return {}
    frame = apply_exact_vocabulary_overrides(frame)
    return frame.drop_duplicates("suggestion_key", keep="last").set_index("suggestion_key").to_dict("index")
