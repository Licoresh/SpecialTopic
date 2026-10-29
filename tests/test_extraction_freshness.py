"""Saved result compatibility; synthetic inputs only."""
from copy import deepcopy
import pandas as pd
import pytest
from src import storage, workflow
from src.utils import digest


@pytest.fixture
def research_inputs(workspace, jobs, taxonomy):
    storage.save_frame("cleaned_jobs", jobs)
    storage.save_frame("cleaned_psf_aai", taxonomy)


def legacy_metadata(version="2.0.65"):
    return {"signature": digest(workflow._extraction_inputs() | {"version": version})}


@pytest.mark.parametrize("version", ["2.0.60", "2.0.61", "2.0.62", "2.0.63", "2.0.64", "2.0.65"])
def test_compatible_legacy_results_do_not_require_reextraction(research_inputs, version):
    metadata = legacy_metadata(version)
    before = deepcopy(metadata)
    signature, current = workflow.extraction_freshness(metadata)
    assert current and signature == workflow.input_signature()
    assert metadata == before


def test_ui_release_does_not_change_extraction_freshness(research_inputs, monkeypatch):
    legacy = legacy_metadata()
    signature = workflow.input_signature()
    metadata = {"signature": signature, "pipeline_version": workflow.EXTRACTION_PIPELINE_VERSION}
    monkeypatch.setattr(workflow, "VERSION", "99.0.0")
    assert workflow.input_signature() == signature
    assert workflow.extraction_freshness(metadata)[1]
    monkeypatch.setattr(workflow, "EXTRACTION_PIPELINE_VERSION", 2)
    assert not workflow.extraction_freshness(metadata)[1]
    assert not workflow.extraction_freshness(legacy)[1]


@pytest.mark.parametrize("kind", ["jobs", "taxonomy", "labels", "upload", "mapping", "settings", "model"])
def test_real_input_changes_still_require_extraction(research_inputs, kind):
    legacy = legacy_metadata()
    current = {"signature": workflow.input_signature(), "pipeline_version": workflow.EXTRACTION_PIPELINE_VERSION}
    if kind in ("jobs", "taxonomy", "labels"):
        name = {"jobs": "cleaned_jobs", "taxonomy": "cleaned_psf_aai", "labels": "labeled_competencies"}[kind]
        storage.save_frame(name, pd.DataFrame({"synthetic": ["Changed research input"]}))
    else:
        name, value = {
            "upload": ("uploads", {"jobs": {"hash": "Changed upload"}}),
            "mapping": ("mapping_jobs", {"job_description": "changed column"}),
            "settings": ("settings", {"max_candidates": 100}),
            "model": ("selected_model", {"name": "Changed model"}),
        }[kind]
        storage.save_json(name, value)
    assert not workflow.extraction_freshness(legacy)[1]
    assert not workflow.extraction_freshness(current)[1]


def test_unknown_legacy_release_is_not_assumed_compatible(research_inputs):
    assert not workflow.extraction_freshness(legacy_metadata("1.0.0"))[1]
    assert not workflow.extraction_freshness({})[1]
