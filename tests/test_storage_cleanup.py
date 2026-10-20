"""SYNTHETIC DATA — NOT RESEARCH DATA."""
import gzip

from src import storage, supabase_store


def test_clear_extractions_archives_outputs_and_preserves_research_inputs(workspace, monkeypatch):
    monkeypatch.setattr(supabase_store.st, "session_state", {})
    (workspace / "data/processed/extractions_original.csv").write_text("phrase\nSYNTHETIC SQL\n", encoding="utf-8")
    (workspace / "data/processed/nlp_processed.csv").write_text("source_id\nSYNTHETIC-1\n", encoding="utf-8")
    (workspace / "data/processed/extraction_metadata.json").write_text("{}", encoding="utf-8")
    (workspace / "data/processed/extractions_original.csv.tmp").write_text("partial", encoding="utf-8")
    kept = [workspace / "data/processed/cleaned_jobs.csv", workspace / "data/processed/psf_mapping_reviews.csv"]
    for path in kept:
        path.write_text("preserve", encoding="utf-8")

    archive = storage.clear_extraction_data()

    assert not (workspace / "data/processed/extractions_original.csv").exists()
    assert not (workspace / "data/processed/nlp_processed.csv").exists()
    assert not (workspace / "data/processed/extraction_metadata.json").exists()
    assert not (workspace / "data/processed/extractions_original.csv.tmp").exists()
    assert all(path.read_text(encoding="utf-8") == "preserve" for path in kept)
    with gzip.open(archive / "extractions_original.csv.gz", "rt", encoding="utf-8") as backup:
        assert backup.read() == "phrase\nSYNTHETIC SQL\n"
    with gzip.open(archive / "extraction_metadata.json.gz", "rt", encoding="utf-8") as backup:
        assert backup.read() == "{}"


def test_remove_misfiled_psf_upload_keeps_reference_and_study_jobs(workspace):
    source = b"competency_name,range_of_application\nSYNTHETIC,Python"
    storage.archive_raw(source, "psf_aai_range_review_draft.csv", "jobs")
    storage.archive_raw(source, "psf_aai_range_review_draft.csv", "psf_aai")
    jobs_path = storage.raw_upload_path(storage.read_json("uploads")["jobs"], "jobs")
    psf_path = storage.raw_upload_path(storage.read_json("uploads")["psf_aai"], "psf_aai")
    jobs_path.unlink()

    storage.remove_misfiled_psf_range_upload()

    assert not jobs_path.exists()
    assert psf_path.read_bytes() == source
    assert "jobs" not in storage.read_json("uploads")
    assert "psf_aai" in storage.read_json("uploads")
