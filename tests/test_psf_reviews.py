"""SYNTHETIC DATA — NOT RESEARCH DATA."""
import pandas as pd
import pytest
from src import storage, supabase_store
from src.alignment import calculate_mapping, summarize_alignment
from src.gap_analysis import calculate_gaps
from src.psf_reviews import prepare_mapping_review, save_mapping_review, REVIEW_TABLE
from src.workflow import analysis_bundle


def occurrence(identity="a", ad="ad1", phrase="Python"):
    return dict(extraction_id=identity, source_id=ad, source_type="jobs", original_phrase=phrase,
                normalized_phrase=phrase.lower(), original_text="SYNTHETIC: Python scripts query SQL databases.",
                start_char=11, end_char=17, accepted=True, competency_category="Technical / Digital")


def review(taxonomy, row=None, assignments=None):
    return prepare_mapping_review(row or occurrence(), taxonomy,
                                  assignments or {"TEST-1": "The phrase requires Python scripting.",
                                                  "TEST-2": "The context specifically requires SQL querying."},
                                  "Synthetic reviewer", context_confirmed=True)


def test_many_to_many_preserves_each_ad_and_distinct_phrase(taxonomy):
    a, b, c = occurrence(), occurrence("b", "ad2"), occurrence("c", "ad2", "Python programming")
    reviews = pd.concat([review(taxonomy, a), review(taxonomy, b, {"TEST-2": "SQL context in ad2."})])
    mapping = calculate_mapping(pd.DataFrame([a,b,c]), taxonomy, reviews=reviews)
    assert set(mapping[mapping.extraction_id.eq("a")].competency_id) == {"TEST-1", "TEST-2"}
    assert mapping[mapping.extraction_id.eq("b")].competency_id.tolist() == ["TEST-2"]
    assert mapping[mapping.extraction_id.eq("c")].competency_id.tolist() == ["TEST-1"]
    assert mapping.source_id.tolist() == ["ad1", "ad1", "ad2", "ad2"]
    assert mapping.original_text.ne("").all()


@pytest.mark.parametrize("assignments,confirmed,message", [
    ({"TEST-1": ""}, True, "every selected"),
    ({"TEST-1": "broad wording", "TEST-2": "broad wording"}, True, "distinct"),
    ({"UNKNOWN": "context"}, True, "active PSF"),
    ({"TEST-1": "context"}, False, "Confirm"),
])
def test_review_requires_evidence(taxonomy, assignments, confirmed, message):
    with pytest.raises(ValueError, match=message):
        prepare_mapping_review(occurrence(), taxonomy, assignments, "Reviewer", confirmed)


def test_no_match_overrides_automatic_match(taxonomy):
    reviews = prepare_mapping_review(occurrence(), taxonomy, {}, "Reviewer", True, "Not a work requirement in this ad.")
    result = calculate_mapping(pd.DataFrame([occurrence()]), taxonomy, reviews=reviews)
    assert result.status.tolist() == ["NOT MAPPED"]
    assert result.mapping_review_status.tolist() == ["REVIEWED"]
    assert result.competency_id.tolist() == [""]


@pytest.mark.parametrize("change", ["source", "taxonomy"])
def test_changed_evidence_requires_new_review(taxonomy, change):
    row = occurrence()
    reviews = review(taxonomy, row)
    if change == "source":
        row["original_text"] = "Changed meaning"
    else:
        taxonomy.loc[0, "competency_description"] = "Changed definition"
    result = calculate_mapping(pd.DataFrame([row]), taxonomy, reviews=reviews)
    assert result.status.tolist() == ["UNCLASSIFIED"]
    assert result.mapping_review_status.tolist() == ["STALE"]
    assert result.competency_id.tolist() == [""]


def test_save_replaces_only_selected_occurrence_and_detects_conflict(workspace, taxonomy):
    args = {"context_confirmed": True}
    save_mapping_review(occurrence(), taxonomy, {"TEST-1":"Python use", "TEST-2":"SQL queries"}, "Reviewer", **args)
    save_mapping_review(occurrence("b", "ad2"), taxonomy, {"TEST-2":"SQL use"}, "Reviewer", **args)
    save_mapping_review(occurrence(), taxonomy, {}, "Reviewer", expected_version=1,
                        unmapped_reason="No supported link", **args)
    saved = storage.read_frame(REVIEW_TABLE)
    assert len(saved) == 2
    assert saved[saved.extraction_id.eq("a")].competency_id.tolist() == [""]
    assert saved[saved.extraction_id.eq("b")].competency_id.tolist() == ["TEST-2"]
    with pytest.raises(ValueError, match="since you opened"):
        save_mapping_review(occurrence(), taxonomy, {"TEST-1":"Old decision"}, "Reviewer", expected_version=1, **args)


def test_extra_links_do_not_inflate_phrase_rates(taxonomy):
    skills = pd.DataFrame([occurrence(), occurrence("b", "ad2", "zzzzzzz")])
    mapping = calculate_mapping(skills, taxonomy, reviews=review(taxonomy))
    *_, rates = calculate_gaps(skills, pd.DataFrame({"source_id":["ad1","ad2"]}), summarize_alignment(mapping))
    assert rates["employer_competencies"] == 2
    assert rates["mapped_competencies"] == 1
    assert rates["unmapped_rate"] == 50


def test_bundle_provenance_counts_and_filters(workspace, taxonomy):
    skills = pd.DataFrame([occurrence(), occurrence("b", "ad2"), occurrence("c", "ad2", "Python programming")])
    jobs = pd.DataFrame({"source_id":["ad1", "ad2"], "job_title":["One", "Two"],
                         "url":["https://example.test/ad1", "https://example.test/ad2"]})
    snapshot = dict(jobs=jobs, taxonomy=taxonomy, extracted=skills, mapping_reviews=review(taxonomy))
    tables, _ = analysis_bundle(source_snapshot=snapshot)
    counts = tables["psf_competency_demand"].set_index("competency_id")
    assert counts.loc["TEST-1", ["job_ad_count", "skill_phrase_count", "occurrence_count"]].tolist() == [2,2,3]
    assert counts.loc["TEST-2", "job_ad_count"] == 1
    assert set(tables["psf_mapping"].job_source_url) == set(jobs.url)
    assert "source_url" in tables["psf_mapping"]  # Framework URL remains separate.
    filtered, _ = analysis_bundle(job_filters={"job_title":["Two"]}, source_snapshot=snapshot)
    assert set(filtered["psf_mapping"].source_id) == {"ad2"}
    assert "TEST-2" not in set(filtered["psf_mapping"].competency_id)
    assert filtered["psf_mapping_reviews"].empty


def test_shared_review_uses_atomic_rpc_and_authenticated_reviewer(monkeypatch, taxonomy):
    calls = []
    monkeypatch.setattr(supabase_store, "configured", lambda: True)
    monkeypatch.setattr(supabase_store, "get_token", lambda: "synthetic-token")
    monkeypatch.setitem(supabase_store.st.session_state, "supabase_user_email", "synthetic@example.test")
    monkeypatch.setattr(supabase_store, "save_mapping_review", lambda *args: calls.append(args))
    save_mapping_review(occurrence(), taxonomy, {"TEST-1":"Context"}, "untrusted identity", context_confirmed=True)
    rows, version, token = calls[0]
    assert version == 0 and token == "synthetic-token"
    assert rows[0]["reviewer"] == "synthetic@example.test"


def test_shared_review_read_flattens_complete_decisions(monkeypatch):
    monkeypatch.setattr(supabase_store, "_request", lambda *args, **kwargs:
                        [{"records":[{"extraction_id":"a", "competency_id":"TEST-1"},
                                     {"extraction_id":"a", "competency_id":"TEST-2"}], "version":2}])
    rows = supabase_store.read_mapping_reviews.__wrapped__("synthetic")
    assert len(rows) == 2 and all(row["version"] == "2" for row in rows)


@pytest.mark.parametrize("response", [None, {}, "1", True, 2])
def test_shared_mapping_save_requires_confirmed_version(monkeypatch, response):
    monkeypatch.setattr(supabase_store, "_request", lambda *args, **kwargs: response)
    monkeypatch.setattr(supabase_store, "clear_read_cache", lambda: None)
    with pytest.raises(supabase_store.SupabaseError, match="could not be confirmed"):
        supabase_store.save_mapping_review([{"extraction_id": "SYNTHETIC"}], 0, "synthetic-token")


def test_shared_mapping_save_accepts_confirmed_version(monkeypatch):
    monkeypatch.setattr(supabase_store, "_request", lambda *args, **kwargs: 2)
    monkeypatch.setattr(supabase_store, "clear_read_cache", lambda: None)
    assert supabase_store.save_mapping_review([{"extraction_id": "SYNTHETIC"}], 1, "synthetic-token") == 2
