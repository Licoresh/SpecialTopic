from io import BytesIO
from openpyxl import load_workbook
import pandas as pd
from src import storage
from src.classification import compare_models, save_model
from src.labeling import save_annotations
from src.workflow import run_extraction, analysis_bundle, input_signature, current_extractions
from src.reporting import export_excel
import pytest

def test_input_to_workbook(workspace, jobs, taxonomy, labeled):
    for kind, frame in (("jobs",jobs),("psf_aai",taxonomy)):
        storage.save_frame("cleaned_"+kind, frame)
    save_annotations(labeled, "SYNTHETIC TEST REVIEWER")
    result = compare_models(storage.read_frame("labeled_competencies"))["Logistic Regression"]
    save_model(result["model"], workspace/"models/competency_classifier.joblib")
    storage.save_json("selected_model", {"name":"Logistic Regression", "metrics":result["metrics"]})
    extracted = run_extraction()
    assert extracted.ml_category.ne("").any()
    assert extracted.psf_competency.ne("").any()
    tables, meta = analysis_bundle()
    assert not tables["employer_skill_demand"].empty
    assert {"chart_skill_demand", "chart_skill_occurrences", "chart_phrase_review", "normalized_jobs"} <= set(tables)
    assert tables["normalized_jobs"].job_title.eq(tables["normalized_jobs"].job_title.str.casefold()).all()
    pd.testing.assert_series_equal(storage.read_frame("cleaned_jobs").job_title, jobs.job_title)
    assert "original_text" not in tables["chart_skill_occurrences"]
    assert "original_text" not in tables["chart_phrase_review"]
    assert meta["chart_presentation"]["job_ad_denominator"] == len(jobs)
    assert tables["chart_skill_demand"].employer_demand_count.le(len(jobs)).all()
    assert {"psf_mapping", "alignment_results", "unmapped_skills", "emerging_skills", "verified_psf_aai", "extracted_job_skills"} <= set(tables)
    assert meta["extraction"]["signature"] == input_signature()
    snapshot = {"jobs": storage.read_frame("cleaned_jobs"),
                "taxonomy": storage.read_frame("cleaned_psf_aai"),
                "extracted": current_extractions()}
    cached_path_tables, _ = analysis_bundle(source_snapshot=snapshot)
    pd.testing.assert_frame_equal(tables["employer_skill_demand"], cached_path_tables["employer_skill_demand"])
    book = load_workbook(BytesIO(export_excel(tables, meta)))
    assert "employer_skill_demand" in book.sheetnames
    assert book["employer_skill_demand"].max_row > 1
    filtered, _ = analysis_bundle(job_filters={"job_title":["Synthetic developer"]})
    assert len(filtered["cleaned_jobs"]) == 1
    assert filtered["employer_skill_demand"].employer_demand_pct.eq(100).all()


def test_job_market_matches_public_with_private_research_inputs(workspace, taxonomy):
    from streamlit.testing.v1 import AppTest
    from src.column_mapping import suggest_column_mapping
    from src.cleaning import clean_dataset
    from src.loaders import load_data, map_columns
    from src.public_engine import analyze_upload
    from src.utils import digest
    from src.workflow import job_market_bundle

    filename = "synthetic.csv"
    content = ("job_title,job_description,source_name\nAnalyst,Python and data analysis.,Café"
               "\nAnalyst,Python and data analysis.,Café\n,,").encode("cp1252")
    dataset_id = digest(content)
    raw = load_data(content, filename, encoding="auto")
    mapping, _ = suggest_column_mapping(raw.columns, "jobs")
    jobs, _ = clean_dataset(map_columns(raw, mapping, "jobs", dataset_id), "jobs")
    storage.save_frame("cleaned_jobs", jobs)
    storage.save_frame("cleaned_psf_aai", taxonomy)
    storage.save_json("settings", {"stopwords": ["python", "analysis"], "max_candidates": 1})
    storage.save_json("uploads", {"jobs": {"hash": "pending-upload", "filename": "pending.csv"}})

    public = analyze_upload(content, filename, mapping, hosted=True)
    tables, metadata = job_market_bundle()
    demand = tables["chart_skill_demand"]
    assert len(demand) > 0
    assert public["summary"]["ads"] == tables["cleaned_jobs"].source_id.nunique() == 2
    assert metadata["quality"] == {"rows": 3, "duplicates": 1, "blank": 1}
    assert {key: public["summary"][key] for key in metadata["quality"]} == metadata["quality"]
    assert public["summary"]["chartSkills"] == len(demand)
    assert {key: public["summary"][key] for key in metadata["kpis"]} == metadata["kpis"]
    assert public["charts"]["skills"] == [
        {"label": row.employer_skill, "count": row.employer_demand_count} for row in demand.itertuples()
    ]
    assert public["datasetHash"] == metadata["dataset_id"] == dataset_id
    assert public["analysisInputHash"] == metadata["analysis_input_id"]
    assert public["model"]["version"] == metadata["classifier_version"]
    assert metadata["filename"] == ""

    storage.save_json("extraction_metadata", {"signature": "stale-private-extraction"})
    app = AppTest.from_string('from src.ui import research_page\nresearch_page("Job Market Analysis")').run(timeout=30)
    assert not app.exception and not app.error
    metrics = {metric.label: metric.value for metric in app.metric}
    assert metrics["Distinct chart skills"] == str(public["summary"]["chartSkills"])
    assert metrics["Distinct phrases withheld"] == str(public["summary"]["withheldPhrases"])
    assert any("Possible duplicate rows included: 1" in caption.value for caption in app.caption)
    assert any("Upload pending: pending.csv" in warning.value for warning in app.warning)


def test_research_input_csv_preserves_reviewed_scope_and_rebuilds_cleaning(workspace):
    from src.cleaning import clean_dataset, duplicate_ids, job_comparison_csv
    from src.column_mapping import suggest_column_mapping
    from src.loaders import load_data, map_columns
    from src.public_engine import analyze_upload
    from src.utils import digest
    from src.workflow import job_market_bundle

    content = (b"Position,Details,Location,Posted Date\n"
               b"Analyst,<p>Python and data analysis</p>,Manila,2025-01-02\n"
               b"Analyst,<p>Python and data analysis</p>,Manila,2025-01-02\n"
               b"Engineer,SQL and data engineering,Cebu City,2025-02-03\n"
               b"Screened out,Financial management,Manila,2025-03-02")
    raw = load_data(content, "jobs.csv", encoding="auto")
    mapping, _ = suggest_column_mapping(raw.columns, "jobs")
    mapped = map_columns(raw, mapping, "jobs", digest(content)).iloc[:3]
    saved, _ = clean_dataset(mapped, "jobs", duplicate_ids(mapped))
    storage.save_frame("cleaned_jobs", saved.iloc[::-1].assign(
        cleaned_text="stale text", posting_date_parsed="1900-01-01"))
    tables, meta = job_market_bundle()
    comparison = job_comparison_csv(tables["cleaned_jobs"])
    preview = load_data(comparison, "comparison.csv", encoding="auto")
    defaults, _ = suggest_column_mapping(preview.columns, "jobs")
    public = analyze_upload(comparison, "comparison.csv", defaults, hosted=True)
    assert public["datasetHash"] != meta["dataset_id"]
    assert public["analysisInputHash"] == meta["analysis_input_id"]
    assert {key: public["summary"][key] for key in meta["kpis"]} == meta["kpis"]
    assert meta["kpis"]["ads"] == 2
    assert public["summary"]["duplicates"] == 0
    assert [row["postingMonth"] for row in public["evidence"]["rows"]] == ["2025-01", "2025-02"]
    assert set(tables["cleaned_jobs"].job_title) == {"Analyst", "Engineer"}
    assert "stale text" not in tables["cleaned_jobs"].cleaned_text.tolist()


def test_public_results_render_family_and_psf_heatmaps():
    import json
    from pathlib import Path
    from streamlit.testing.v1 import AppTest
    from src.public_engine import analyze_upload

    content = (b"job_title,job_family,job_description\n"
               b"Data analyst,Analytics,SQL and data analysis with Python.\n"
               b"Machine learning engineer,Engineering,Machine learning and data engineering.")
    mapping = {field: field for field in ("job_title", "job_family", "job_description")}
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "public-web/streamlit_app.py")
    app.session_state["public_result"] = analyze_upload(content, "synthetic.csv", mapping, hosted=True)

    def heatmap_axes():
        assert not app.exception and not app.error
        specs = (json.loads(chart.proto.spec) for chart in app.get("plotly_chart"))
        return {spec["layout"]["xaxis"]["title"]["text"] for spec in specs
                if any(trace["type"] == "heatmap" for trace in spec["data"])}

    app.run(timeout=30)
    assert heatmap_axes() == {"Occupational family", "Reference role"}
    roles = app.selectbox(key="public_psf_role").options
    assert {"Machine Learning Engineer", "Business Analytics Manager", "Chief Technology Officer", "AI Engineer"} <= set(roles)
    reference = next(table.value for table in app.dataframe if "Framework roles" in table.value)
    assert set(reference.Competency) >= {"Collaboration", "Research", "Product Management", "Transdisciplinary Thinking"}
    families = app.multiselect(key="public_family_selection")
    chosen = families.value
    families.set_value([]).run(timeout=30)
    assert heatmap_axes() == {"Reference role"}
    assert any("Select at least one occupational family" in caption.value for caption in app.caption)
    app.multiselect(key="public_family_selection").set_value(chosen).run(timeout=30)
    assert heatmap_axes() == {"Occupational family", "Reference role"}
    app.multiselect(key="public_psf_heatmap_roles").set_value([]).run(timeout=30)
    assert heatmap_axes() == {"Occupational family"}
    assert any("Select at least one reference role" in caption.value for caption in app.caption)


def test_pending_upload_does_not_replace_saved_cleaned_jobs(workspace, jobs):
    storage.save_frame("cleaned_jobs", jobs)
    storage.save_frame("mapped_jobs", jobs)
    from src.utils import frame_hash
    storage.save_json("cleaning_jobs", {"dataset_hash": jobs._dataset_hash.iloc[0],
                                       "source_hash": frame_hash(jobs),
                                       "philippine_aai_scope_reviewed": True})
    before = input_signature()
    storage.archive_raw(b"description\nnew data", "jobs.csv", "jobs")
    assert input_signature() == before
    extracted = run_extraction()
    assert not extracted.empty
    assert set(extracted.source_id) <= set(jobs.source_id)


def test_cleaning_record_must_match_active_cleaned_jobs(workspace, jobs):
    storage.save_frame("cleaned_jobs", jobs)
    storage.save_json("cleaning_jobs", {"dataset_hash": "another-dataset",
                                       "philippine_aai_scope_reviewed": True})
    with pytest.raises(ValueError, match="cleaning record does not match"):
        run_extraction()


def test_requirement_and_missing_phrases_remain_auditable_but_never_enter_skill_or_psf_demand(workspace, jobs, taxonomy):
    from src.workflow import analysis_bundle
    source_id = jobs.source_id.iloc[0]
    extracted = pd.DataFrame([
        {"extraction_id": "SYNTHETIC-SQL", "source_id": source_id, "source_type": "jobs",
         "original_phrase": "SQL", "normalized_phrase": "sql", "accepted": True,
         "competency_category": "Data / Analytics"},
        {"extraction_id": "SYNTHETIC-MISSING", "source_id": source_id, "source_type": "jobs",
         "original_phrase": "not mentioned", "normalized_phrase": "not mentioned", "accepted": True,
         "competency_category": "Technical / Digital"},
        {"extraction_id": "SYNTHETIC-YEARS", "source_id": source_id, "source_type": "jobs",
         "original_phrase": "3+year", "normalized_phrase": "3+year", "accepted": True,
         "competency_category": "Technical / Digital"},
    ])

    tables, meta = analysis_bundle(source_snapshot={
        "jobs": jobs.iloc[:1], "taxonomy": taxonomy, "extracted": extracted,
    })

    assert tables["chart_skill_demand"].employer_skill.tolist() == ["sql"]
    assert tables["psf_mapping"].normalized_skill.tolist() == ["sql"]
    reasons = tables["chart_phrase_review"].set_index("original_phrase").review_reason
    assert reasons["not mentioned"].startswith("Not reported")
    assert reasons["3+year"] == "Experience-duration requirement, not a skill"
    assert meta["chart_presentation"]["chartable_skill_ads"] == 1
    assert meta["chart_presentation"]["ads_without_chartable_skill"] == 0


def test_unreviewed_job_provenance_blocks_extraction(workspace, jobs):
    from src.workflow import run_extraction
    from src.utils import frame_hash
    storage.archive_raw(b"job_title,job_description\\nSynthetic,SQL", "jobs.csv", "jobs")
    upload = storage.read_json("uploads")["jobs"]
    jobs["_dataset_hash"] = upload["hash"]
    storage.save_frame("cleaned_jobs", jobs)
    storage.save_frame("mapped_jobs", jobs)
    storage.save_json("cleaning_jobs", {"source_hash": frame_hash(jobs)})
    with pytest.raises(ValueError, match="Philippine provenance"):
        run_extraction()


def test_fragment_screen_applies_to_results_and_exports_without_changing_evidence(workspace, jobs, taxonomy):
    phrases = ["SQL", "long and successful", "accept usage", "activity", "tool and service"]
    extracted = pd.DataFrame([
        {"extraction_id": f"SYNTHETIC-SCREEN-{index}", "source_id": jobs.source_id.iloc[index % 3],
         "source_type": "jobs", "original_phrase": phrase, "normalized_phrase": phrase.lower(),
         "original_text": "SYNTHETIC SOURCE EVIDENCE", "accepted": True,
         "human_label": "Technical / Digital", "competency_category": "Technical / Digital"}
        for index, phrase in enumerate(phrases)])
    original = extracted.copy(deep=True)

    tables, meta = analysis_bundle(source_snapshot={
        "jobs": jobs, "taxonomy": taxonomy, "extracted": extracted,
    })

    for name, column in (("extracted_job_skills", "normalized_phrase"),
                         ("psf_mapping", "normalized_skill"),
                         ("alignment_results", "normalized_skill"),
                         ("employer_skill_demand", "normalized_skill"),
                         ("chart_skill_demand", "normalized_phrase")):
        assert tables[name][column].str.casefold().tolist() == ["sql"]
    assert tables["unmapped_skills"].empty
    assert tables["emerging_skills"].empty
    assert tables["psf_competency_demand"].psf_competency.tolist() == ["SQL"]
    assert tables["psf_chart_demand"].job_ads.tolist() == [1]
    assert meta["chart_presentation"]["job_ad_denominator"] == 3
    assert meta["chart_presentation"]["chartable_skill_ads"] == 1
    assert meta["chart_presentation"]["ads_without_chartable_skill"] == 2
    assert meta["chart_presentation"]["unclear_occurrences"] == 4
    assert set(tables["chart_phrase_review"].extraction_id) == set(extracted.extraction_id.iloc[1:])
    assert tables["chart_phrase_review"].human_label.eq("Technical / Digital").all()
    pd.testing.assert_frame_equal(tables["all_candidates"], original)
    pd.testing.assert_frame_equal(extracted, original)
    book = load_workbook(BytesIO(export_excel(tables, meta)))
    assert book["all_candidates"].max_row == len(phrases) + 1
    assert book["chart_phrase_review"].max_row == 5
    assert book["psf_mapping"].max_row == 2


def test_research_exports_exclude_external_training_sources(workspace, jobs, taxonomy):
    storage.save_frame("cleaned_jobs", jobs)
    storage.save_frame("cleaned_psf_aai", taxonomy)
    selected_id = jobs.source_id.iloc[0]
    storage.save_frame("labeled_competencies", pd.DataFrame([
        {"phrase": "SQL", "normalized_phrase": "sql", "label": "Data / Analytics", "source_type": "jobs", "source_id": selected_id},
        {"phrase": "external skill", "normalized_phrase": "external skill", "label": "Technical / Digital", "source_type": "jobs", "source_id": "EXTERNAL-TRAINING-ONLY"},
    ]))
    tables, metadata = analysis_bundle(source_snapshot={"jobs": jobs.iloc[:1], "taxonomy": taxonomy, "extracted": pd.DataFrame()})
    assert tables["labeled_competencies"].source_id.tolist() == [selected_id]
    assert len(storage.read_frame("labeled_competencies")) == 2
    assert "test_predictions" not in tables
    assert "model_metrics" not in tables
    assert metadata["research_sample"]["source_ids"] == [selected_id]
    book = load_workbook(BytesIO(export_excel(tables, metadata)))
    assert "test_predictions" not in book.sheetnames
    assert book["labeled_competencies"].max_row == 2
