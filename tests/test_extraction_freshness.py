"""Saved result compatibility; synthetic inputs only."""
import pandas as pd
import pytest
from src import storage, workflow
from src.utils import digest


@pytest.fixture
def research_inputs(workspace, jobs, taxonomy):
    storage.save_frame("cleaned_jobs", jobs)
    storage.save_frame("cleaned_psf_aai", taxonomy)


def legacy_metadata(version="2.0.65"):
    return {"signature": digest(workflow._legacy_extraction_inputs() | {"version": version})}


@pytest.mark.parametrize("version", ["2.0.60", "2.0.61", "2.0.62", "2.0.63", "2.0.64", "2.0.65"])
def test_pre_shared_classifier_results_require_reextraction(research_inputs, version):
    metadata = legacy_metadata(version)
    signature, current = workflow.extraction_freshness(metadata)
    assert not current and signature == workflow.input_signature()
    assert metadata["signature"]


def test_ui_release_does_not_change_extraction_freshness(research_inputs, monkeypatch):
    legacy = legacy_metadata()
    signature = workflow.input_signature()
    metadata = {"signature": signature, "pipeline_version": workflow.EXTRACTION_PIPELINE_VERSION}
    monkeypatch.setattr(workflow, "VERSION", "99.0.0")
    assert workflow.input_signature() == signature
    assert workflow.extraction_freshness(metadata)[1]
    monkeypatch.setattr(workflow, "EXTRACTION_PIPELINE_VERSION", workflow.EXTRACTION_PIPELINE_VERSION + 1)
    assert not workflow.extraction_freshness(metadata)[1]
    assert not workflow.extraction_freshness(legacy)[1]


@pytest.mark.parametrize("kind", ["jobs", "taxonomy", "labels", "settings", "classifier"])
def test_real_input_changes_still_require_extraction(research_inputs, kind, monkeypatch, tmp_path):
    if kind == "classifier":
        monkeypatch.setattr(workflow, "ROOT", tmp_path)
        artifact = tmp_path / "public-web/site/model.json"
        artifact.parent.mkdir(parents=True)
        artifact.write_bytes(b"released model one")
    legacy = legacy_metadata()
    current = {"signature": workflow.input_signature(), "pipeline_version": workflow.EXTRACTION_PIPELINE_VERSION}
    if kind in ("jobs", "taxonomy", "labels"):
        name = {"jobs": "cleaned_jobs", "taxonomy": "cleaned_psf_aai", "labels": "labeled_competencies"}[kind]
        storage.save_frame(name, pd.DataFrame({"synthetic": ["Changed research input"]}))
    else:
        if kind == "settings":
            storage.save_json("settings", {"max_candidates": 100})
        else:
            artifact.write_bytes(b"released model two")
    assert not workflow.extraction_freshness(legacy)[1]
    assert not workflow.extraction_freshness(current)[1]


def test_pending_upload_and_mapping_do_not_stale_cleaned_results(research_inputs):
    current = {"signature": workflow.input_signature(), "pipeline_version": workflow.EXTRACTION_PIPELINE_VERSION}
    storage.save_json("uploads", {"jobs": {"hash": "pending-upload"}})
    storage.save_json("mapping_jobs", {"job_description": "pending column"})
    assert workflow.input_signature() == current["signature"]
    assert workflow.extraction_freshness(current)[1]


def test_existing_pipeline_result_stays_fresh_without_input_changes(research_inputs):
    old = {"signature": digest(workflow._legacy_extraction_inputs() |
                               {"pipeline_version": workflow.EXTRACTION_PIPELINE_VERSION}),
           "pipeline_version": workflow.EXTRACTION_PIPELINE_VERSION}
    assert workflow.extraction_freshness(old)[1]


def test_unknown_legacy_release_is_not_assumed_compatible(research_inputs):
    assert not workflow.extraction_freshness(legacy_metadata("1.0.0"))[1]
    assert not workflow.extraction_freshness({})[1]


def test_review_labels_are_audit_only_for_shared_classifier_output():
    extracted = pd.DataFrame({"normalized_phrase": ["Python"], "human_label": [""],
                              "model_prediction": ["Technical / Digital"],
                              "competency_category": ["Technical / Digital"],
                              "accepted": [True], "agreement": ["Not Reviewed"]})
    annotations = pd.DataFrame({"phrase": ["python"], "normalized_phrase": ["python"],
                                "label": ["IRRELEVANT"]})

    result = workflow._retain_review_labels(extracted, annotations)

    assert result.loc[0, "human_label"] == "IRRELEVANT"
    assert result.loc[0, "agreement"] == "Mismatch"
    assert result.loc[0, "competency_category"] == "Technical / Digital"
    assert bool(result.loc[0, "accepted"])
    assert extracted.loc[0, "human_label"] == ""
