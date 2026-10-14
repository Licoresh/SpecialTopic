import requests
from src import ollama_review as review


def test_optional_and_ambiguous_only(monkeypatch):
    monkeypatch.delenv("FOW_OLLAMA_MODEL", raising=False)
    drafts = [{"label": "Soft / Enabling", "score": .2, "category_method": "BGE-M3 semantic similarity"}]
    assert review.review_ambiguous([{"phrase": "ability"}], drafts) == drafts
    monkeypatch.setenv("FOW_OLLAMA_MODEL", "test-local")
    monkeypatch.setattr(review, "_review", lambda *args: {"supported": False, "reason": "Incomplete phrase"})
    result = review.review_ambiguous([{"phrase": "ability"}], drafts)
    assert result[0]["context_review"] == "Needs researcher review"
    assert result[0]["label"] == "Soft / Enabling"


def test_outage_does_not_repeat_per_row(monkeypatch):
    monkeypatch.setenv("FOW_OLLAMA_MODEL", "test-local")
    calls = []
    def fail(*args):
        calls.append(1)
        raise requests.ConnectionError()
    monkeypatch.setattr(review, "_review", fail)
    drafts = [{"score": .1, "category_method": "BGE-M3 semantic similarity"} for _ in range(5)]
    result = review.review_ambiguous([{"phrase": "ability"}] * 5, drafts)
    assert len(calls) == 1
    assert all("Unavailable" in row["context_review"] for row in result)
