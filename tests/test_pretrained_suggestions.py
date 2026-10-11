"""Synthetic unit checks for the optional pretrained suggestion adapter."""
import numpy as np
import pandas as pd
from src.pretrained_suggestions import (
    CATEGORY_DESCRIPTIONS,
    MODEL_ID,
    MODEL_REVISION,
    PSF_MODEL_ID,
    PSF_MODEL_REVISION,
    is_incomplete_phrase,
    load_ai_suggestions,
    refresh_saved_exact_vocabulary_overrides,
    save_ai_suggestions,
    source_context,
    suggest_categories,
    suggest_psf_competencies,
)


def test_source_context_uses_nearby_original_posting_text():
    context = source_context("with strong", "A role requires clear communication with strong written and spoken English skills.")
    assert "Candidate phrase: with strong" in context
    assert "written and spoken English" in context
    assert len(context) < 400


def test_embedding_ranking_maps_categories_without_loading_model():
    observed = {}

    class FakeEncoder:
        def encode(self, texts, **kwargs):
            observed["texts"] = texts
            return np.asarray([
                [1.0, 0.0] if text.startswith("Soft / Enabling") or "spoken English" in text else
                [0.0, 1.0] if text.startswith("IRRELEVANT") or "with strong" in text else
                [0.0, 0.0]
                for text in texts
            ])

    suggestions = suggest_categories([
        {"phrase": "spoken English", "original_text": "Requirements include spoken English."},
        {"phrase": "with strong", "original_text": "with strong written skills"},
    ], encoder=FakeEncoder())

    assert [item["label"] for item in suggestions] == ["Soft / Enabling", "IRRELEVANT"]
    assert suggestions[0]["score"] == 1.0
    assert suggestions[0]["model"] == MODEL_ID
    assert suggestions[0]["revision"] == MODEL_REVISION
    assert "written skills" in observed["texts"][-1]
    assert suggestions[1]["incomplete_phrase"] is True


def test_common_candidate_fragments_are_held_for_editing():
    for phrase in ("with strong", "written and", "and spoken", "Creative with", "a keen", "eye for"):
        assert is_incomplete_phrase(phrase)
    assert not is_incomplete_phrase("spoken English")
    assert not is_incomplete_phrase("time management")


def test_category_ranking_supports_a_single_result():
    class FakeEncoder:
        def encode(self, texts, **kwargs):
            return np.asarray([[1.0, 0.0] if text.startswith("Data / Analytics") or "data analysis" in text else [0.0, 0.0] for text in texts])

    output = suggest_categories(
        [{"phrase": "data analysis"}],
        encoder=FakeEncoder(),
    )
    assert output[0]["label"] == "Data / Analytics"


def test_exact_research_vocabulary_overrides_conflicting_embedding_without_score():
    class FakeEncoder:
        def encode(self, texts, **kwargs):
            return np.asarray([[0.0, 1.0] if "IRRELEVANT" in text else [0.0, 0.0] for text in texts])

    result = suggest_categories([{"phrase": "Python"}], encoder=FakeEncoder())[0]
    assert result["label"] == "Technical / Digital"
    assert result["score"] is None
    assert result["category_method"] == "Exact project vocabulary match"


def test_pretrained_psf_ranking_uses_taxonomy_text_and_records_similarity():
    observed = {}

    class FakeEncoder:
        def encode(self, texts, **kwargs):
            observed.setdefault("inputs", []).extend(texts)
            return np.asarray([[1.0, 0.0] if "communication" in text.casefold() else [0.0, 1.0] for text in texts])

    taxonomy = pd.DataFrame([
        {"competency_name": "Communication", "competency_description": "Communicate with teams"},
        {"competency_name": "Data analysis", "competency_description": "Analyze data"},
    ])
    result = suggest_psf_competencies(
        [{"phrase": "communication", "original_text": "Strong communication skills with teams."}],
        taxonomy,
        encoder=FakeEncoder(),
    )[0]
    assert result["psf_competency"] == "Communication"
    assert result["psf_score"] == 1.0
    assert result["psf_model"] == PSF_MODEL_ID
    assert result["psf_revision"] == PSF_MODEL_REVISION
    assert "Analyze data" in " ".join(observed["inputs"])


def test_ai_suggestions_persist_separately_from_reviewed_labels(tmp_path):
    records = [{"phrase": "SQL", "source_type": "Synthetic job", "source_id": "SYNTHETIC-1"}]
    predictions = [{"label": "Data / Analytics", "score": 0.8, "psf_competency": "SQL", "psf_score": 0.7}]
    save_ai_suggestions(tmp_path, records, predictions)
    revised = [{"label": "Technical / Digital", "score": 0.81, "psf_competency": "SQL", "psf_score": 0.72}]
    saved = save_ai_suggestions(tmp_path, records, revised)
    loaded = load_ai_suggestions(tmp_path)
    assert len(saved) == 1
    suggestion = next(iter(loaded.values()))
    assert suggestion["category"] == "Technical / Digital"
    assert suggestion["psf_competency"] == "SQL"
    assert suggestion["category_method"] == "Exact project vocabulary match"
    assert suggestion["category_score"] == ""
    assert suggestion["category_model"] == MODEL_ID
    assert suggestion["psf_model"] == PSF_MODEL_ID
    assert (tmp_path / "data/processed/pretrained_label_suggestions.csv").exists()


def test_refresh_corrects_old_exact_vocabulary_drafts_without_touching_labels(tmp_path):
    records = [{"phrase": "Python", "source_type": "Synthetic job", "source_id": "SYNTHETIC-3"}]
    save_ai_suggestions(tmp_path, records, [{"label": "IRRELEVANT", "score": 0.9}])
    path = tmp_path / "data/processed/pretrained_label_suggestions.csv"
    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    frame.loc[0, "category"] = "IRRELEVANT"
    frame.loc[0, "category_score"] = "0.9"
    frame.loc[0, "category_method"] = "BGE-M3 semantic similarity"
    frame.to_csv(path, index=False)
    label_path = tmp_path / "train/labeled_competencies.csv"
    label_path.parent.mkdir(parents=True)
    label_path.write_text("phrase,normalized_phrase,label,psf_competency,reviewer,timestamp\n", encoding="utf-8")

    assert refresh_saved_exact_vocabulary_overrides(tmp_path) == 1
    updated = pd.read_csv(path, dtype=str, keep_default_na=False).iloc[0]
    assert updated.category == "Technical / Digital"
    assert updated.category_score == ""
    assert updated.category_method == "Exact project vocabulary match"
    assert label_path.read_text(encoding="utf-8").count("\n") == 1

def test_suggestions_from_a_previous_encoder_are_not_shown_as_current(tmp_path):
    records = [{"phrase": "SQL", "source_type": "Synthetic job", "source_id": "SYNTHETIC-2"}]
    save_ai_suggestions(tmp_path, records, [{"label": "Data / Analytics", "psf_competency": "SQL"}])
    path = tmp_path / "data/processed/pretrained_label_suggestions.csv"
    old = pd.read_csv(path, dtype=str, keep_default_na=False)
    old.loc[0, "category_model"] = "sentence-transformers/all-MiniLM-L6-v2"
    old.loc[0, "category_revision"] = "old-revision"
    old.loc[0, "psf_model"] = "sentence-transformers/all-MiniLM-L6-v2"
    old.loc[0, "psf_revision"] = "old-revision"
    old.to_csv(path, index=False)

    assert load_ai_suggestions(tmp_path) == {}
