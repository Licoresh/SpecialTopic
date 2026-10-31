"""Synthetic audience-focused result views; no live sources or research records."""
import pandas as pd
from streamlit.testing.v1 import AppTest
from src import ui
from src.analytics import skill_chart_tables


def result_tables():
    jobs = pd.DataFrame({
        "source_id": ["A", "B", "C", "D"],
        "job_title": ["Data Analyst", "data analyst", "Engineer", "Designer"],
        "job_family": ["Analytics", "analytics", "Engineering", "Design"],
        "location": ["Manila", "MANILA", "Cebu", "Cebu"],
        "education_requirement": ["Bachelor's degree", "bachelor's degree", "", ""],
        "experience_requirement": ["2-3 years", "", "5+ years", "Relevant experience"],
        "job_description": ["Synthetic posting"] * 4,
    })
    rows = [("A", "SQL", "Technical / Digital", "Technical"),
            ("B", "sql", "Technical / Digital", "Technical"),
            ("A", "Collaboration", "Soft / Enabling", "Soft / Enabling"),
            ("A", "• COLLABORATION", "Soft / Enabling", "Soft / Enabling"),
            ("C", "C++", "Technical / Digital", "Technical"),
            ("B", "Build", "Technical / Digital", "Technical")]
    skills = pd.DataFrame([{
        "extraction_id": f"SYNTHETIC-{i}", "source_id": source, "source_type": "jobs",
        "original_phrase": phrase, "normalized_phrase": phrase,
        "competency_category": category, "human_label": category, "skill_type": kind,
    } for i, (source, phrase, category, kind) in enumerate(rows)])
    mapping = pd.DataFrame({"source_id": ["A", "B"], "psf_competency": ["Programming", "Programming"],
                            "psf_job_role": ["Analyst", "Analyst"], "status": ["ALIGNED", "NOT MAPPED"]})
    return {"cleaned_jobs": jobs, "extracted_job_skills": skills,
            "employer_skill_demand": pd.DataFrame(), "alignment_results": pd.DataFrame(),
            "psf_mapping": mapping, **skill_chart_tables(skills, jobs)}


def result_app(monkeypatch, tables, page="Job Market Analysis"):
    figures = []
    original = ui.chart
    def capture(figure):
        figures.append(figure)
        original(figure)
    monkeypatch.setattr(ui, "chart", capture)
    monkeypatch.setattr(ui, "current_analysis", lambda: True)
    monkeypatch.setattr(ui, "filtered_bundle", lambda: (tables, {"settings": {"emerging_min_jobs": 2}}))
    app = AppTest.from_string(f"from src.ui import research_page\nresearch_page({page!r})").run(timeout=30)
    assert not app.exception and not app.error
    return app, figures


def figure_with_title(figures, title):
    return next(figure for figure in reversed(figures) if figure.layout.title.text == title)


def test_job_market_hides_audience_guidance_banner(monkeypatch):
    app, _ = result_app(monkeypatch, result_tables())
    assert not any("For the chancellor:" in item.value for item in app.markdown)
    assert not any("Counts describe the selected advertisements" in item.value for item in app.caption)


def test_role_focus_duplicate_labels_and_unclear_phrases(monkeypatch):
    tables = result_tables()
    before = tables["extracted_job_skills"].copy(deep=True)
    app, figures = result_app(monkeypatch, tables)
    main = figure_with_title(figures, "Employer-requested skills")
    assert dict(zip(main.data[0].y, main.data[0].x)) == {"sql": 2, "c++": 1, "collaboration": 1}
    assert not any(fig.layout.title.text == "Related role groups" for fig in figures)
    app.button_group(key="result_section").select("Qualifications").run(timeout=30)
    assert any("not stated in 1" in item.value for item in app.markdown)
    app.button_group(key="result_section").select("Roles and locations").run(timeout=30)
    focused = figure_with_title(figures, "Top skills for all selected advertisements")
    assert dict(zip(focused.data[0].y, focused.data[0].x)) == {"sql": 2, "c++": 1, "collaboration": 1}
    metrics = {item.label: item.value for item in app.metric}
    assert metrics["Selected job advertisements"] == "4"
    assert metrics["Distinct phrases withheld"] == "1"
    assert not any("Experience requirement fields" == fig.layout.title.text for fig in figures)
    app.selectbox(key="result_title_view").set_value("Specific titles (alphabetical)").run(timeout=30)
    app.selectbox(key="result_specific_title").set_value("engineer").run(timeout=30)
    assert not app.exception and not app.error
    assert not any(fig.layout.title.text == "Top skills for engineer" for fig in figures)
    assert any(item.label == "c++" and item.value == "1" for item in app.metric)
    pd.testing.assert_frame_equal(tables["extracted_job_skills"], before)


def test_alphabetical_chart_order_and_linked_psf_counts(monkeypatch):
    app, figures = result_app(monkeypatch, result_tables())
    app.selectbox(key="result_chart_order").set_value("Alphabetical").run(timeout=30)
    assert not app.exception and not app.error
    labels = figure_with_title(figures, "Employer-requested skills").data[0].y.tolist()
    assert labels == sorted(labels, key=str.casefold)
    app.button_group(key="result_section").select("PSF-AAI demand").run(timeout=30)
    assert not any(fig.layout.title.text == "PSF-AAI competencies linked to employer demand" for fig in figures)
    assert any(item.label == "programming" and item.value == "1" for item in app.metric)  # Corrected NOT MAPPED row is excluded.


def test_unmapped_chart_does_not_count_aligned_format_variant(monkeypatch):
    tables = result_tables()
    skills = tables["extracted_job_skills"].iloc[:2].copy()
    skills.loc[skills.source_id.eq("A"), ["normalized_phrase", "original_phrase"]] = "•sql"
    tables.update(skill_chart_tables(skills, tables["cleaned_jobs"]))
    tables["alignment_results"] = pd.DataFrame({"normalized_skill": ["•sql", "sql"], "status": ["NOT MAPPED", "ALIGNED"]})
    tables["unmapped_skills"] = pd.DataFrame({"normalized_skill": ["•sql"], "employer_skill": ["•sql"], "employer_demand_count": [1]})
    tables["emerging_skills"] = tables["unmapped_skills"].iloc[:0]
    app, figures = result_app(monkeypatch, tables, "Unmapped / Emerging Skills")
    assert not figures  # Mixed mapped group is not shown as wholly unmapped.
    assert any("•sql" in frame.value.astype(str).to_string() for frame in app.dataframe)


def test_specific_titles_stay_alphabetical_and_grouped_view_is_auditable(monkeypatch):
    app, figures = result_app(monkeypatch, result_tables())
    assert any("Select job ads" in item.value for item in app.markdown)
    assert any("Describe results" in item.value for item in app.markdown)
    app.button_group(key="result_section").select("Roles and locations").run(timeout=30)
    common = figure_with_title(figures, "Most common job titles")
    assert common.data[0].y[0] == "data analyst"
    app.selectbox(key="result_title_view").set_value("Related role groups").run(timeout=30)
    grouped = figure_with_title(figures, "Related role groups")
    assert dict(zip(grouped.data[0].y, grouped.data[0].x))["analytics"] == 2
    app.selectbox(key="result_chart_order").set_value("Highest demand").run(timeout=30)
    app.selectbox(key="result_title_view").set_value("Specific titles (alphabetical)").run(timeout=30)
    titles = figure_with_title(figures, "Specific job titles (alphabetical)").data[0].y.tolist()
    assert titles == ["data analyst", "designer", "engineer"]
    assert app.selectbox(key="result_specific_title").options == ["All", *titles]
    assert any("grouping_basis" in frame.value.columns for frame in app.dataframe)


def test_common_title_chart_uses_canonical_role_but_specific_view_keeps_title(monkeypatch):
    tables = result_tables()
    tables["cleaned_jobs"] = pd.concat([tables["cleaned_jobs"], pd.DataFrame([{
        "source_id": "E", "job_title": "Junior Business Analyst - Banking Branch", "job_family": "Banking",
        "location": "Manila", "education_requirement": "", "experience_requirement": "",
        "job_description": "Synthetic posting",
    }])], ignore_index=True)
    app, figures = result_app(monkeypatch, tables)
    app.button_group(key="result_section").select("Roles and locations").run(timeout=30)
    common = figure_with_title(figures, "Most common job titles")
    labels = common.data[0].y.tolist()
    assert "business analyst" in labels
    assert common.data[0].x[labels.index("business analyst")] == 1
    app.selectbox(key="result_title_view").set_value("Specific titles (alphabetical)").run(timeout=30)
    assert "junior business analyst - banking branch" in app.selectbox(key="result_specific_title").options
    evidence = next(frame.value for frame in app.dataframe if "common_job_title" in frame.value.columns)
    assert evidence.loc[evidence.source_id.eq("E"), "original_job_title"].iloc[0] == "Junior Business Analyst - Banking Branch"


def test_family_title_filters_reset_and_geographical_denominators(monkeypatch):
    app, figures = result_app(monkeypatch, result_tables())
    app.button_group(key="result_section").select("Roles and locations").run(timeout=30)
    app.selectbox(key="result_family").select("analytics").run(timeout=30)
    assert app.selectbox(key="result_specific_title").options == ["All", "data analyst"]
    focused = figure_with_title(figures, "Top skills for analytics")
    assert focused.data[0].x.tolist() == [2, 1]
    assert focused.data[0].customdata[0][1] == 100
    assert any("Small group" in item.value for item in app.caption)
    app.selectbox(key="result_region").select("national capital region").run(timeout=30)
    app.selectbox(key="result_family").select("engineering").run(timeout=30)
    assert not app.exception
    assert app.selectbox(key="result_region").value == "All"
    next(button for button in app.button if button.label == "Reset exploration filters").click().run(timeout=30)
    assert not app.exception and app.selectbox(key="result_family").value == "All"


def test_skill_family_heatmap_uses_all_ads_in_each_family_as_denominator(monkeypatch):
    app, figures = result_app(monkeypatch, result_tables())
    app.button_group(key="result_section").select("Roles and locations").run(timeout=30)
    app.multiselect(key="result_skill_family_heatmap_families").set_value(["analytics"]).run(timeout=30)
    figure = figure_with_title(figures, "Top requested skills by occupational family")
    trace = figure.data[0]
    row = trace.y.tolist().index("analytics")
    column = trace.x.tolist().index("sql")
    assert trace.z[row][column] == 100.0
    assert list(trace.customdata[row][column][2:]) == [2, 100.0, 2]
    assert "Advertisements in family: %{customdata[4]:,d}" in trace.hovertemplate
    assert any("skill categories overlap" in item.value for item in app.caption)


def test_skill_family_count_table_renders_inside_its_expander(monkeypatch):
    app, _ = result_app(monkeypatch, result_tables())
    app.button_group(key="result_section").select("Roles and locations").run(timeout=30)
    app.session_state["result_all_skill_family_table"] = True
    app.run(timeout=30)
    expander = next(item for item in app.expander if item.label == "View all skill-by-family counts")
    assert expander.proto.expanded
    assert len(expander.dataframe) == 1
    assert "Occupational family" in expander.dataframe[0].value.columns
    assert "Skill" in expander.dataframe[0].value.columns


def test_selected_title_starts_with_top_ten_and_offers_full_searchable_table(monkeypatch):
    tables = result_tables()
    skills = tables["extracted_job_skills"].copy()
    extra = pd.DataFrame([{"extraction_id": f"SYNTHETIC-EXTRA-{index}", "source_id": "A", "source_type": "jobs",
                           "original_phrase": f"specialized skill {index}", "normalized_phrase": f"specialized skill {index}",
                           "competency_category": "Technical / Digital", "human_label": "Technical / Digital"}
                          for index in range(11)])
    tables["extracted_job_skills"] = pd.concat([skills, extra], ignore_index=True)
    tables.update(skill_chart_tables(tables["extracted_job_skills"], tables["cleaned_jobs"]))
    app, figures = result_app(monkeypatch, tables)
    app.button_group(key="result_section").select("Roles and locations").run(timeout=30)
    app.selectbox(key="result_family").select("analytics").run(timeout=30)
    app.selectbox(key="result_specific_title").select("data analyst").run(timeout=30)
    figure = figure_with_title(figures, "Top skills for data analyst")
    assert len(figure.data[0].y) == 10
    assert any("Selected group: data analyst · 2 advertisements" in item.value for item in app.caption)
    assert any(item.label == "View all skills for this selection" for item in app.expander)


def test_location_charts_separate_region_and_city_levels_and_warn_against_rates(monkeypatch):
    tables = result_tables()
    tables["cleaned_jobs"]["location"] = ["Manila City, Philippines", "Quezon City, Philippines",
                                           "Cebu City, Philippines", "Cebu City, Philippines"]
    app, figures = result_app(monkeypatch, tables)
    app.button_group(key="result_section").select("Roles and locations").run(timeout=30)
    regional = figure_with_title(figures, "Advertisements by Philippine region")
    assert set(regional.data[0].y) == {"national capital region", "central visayas"}
    assert any("not population- or labor-force-adjusted" in item.value for item in app.caption)
    app.selectbox(key="result_region").select("central visayas").run(timeout=30)
    assert any(item.label == "cebu city" and item.value == "2" for item in app.metric)
    assert any("2 advertisements are associated with central visayas" in item.value for item in app.caption)


def test_experience_summary_uses_only_exact_single_value_requirements(monkeypatch):
    tables = result_tables()
    tables["cleaned_jobs"]["experience_requirement"] = ["2 years", "4 years", "2–3 years", "At least 5 years"]
    app, _ = result_app(monkeypatch, tables)
    app.button_group(key="result_section").select("Qualifications").run(timeout=30)
    assert any("median 3 years (observed range 2–4)" in item.value and "2 of 4 selected ads" in item.value for item in app.caption)
    assert any("Ranges and open-ended wording are excluded" in item.value for item in app.caption)
    assert any("Not specified describes the advertisement text" in item.value for item in app.caption)

def test_psf_role_filter_limits_multi_role_links_and_heatmap(monkeypatch):
    tables = result_tables()
    tables['psf_mapping'].loc[0,'psf_job_role'] = 'analyst; scientist'
    tables['verified_psf_aai'] = pd.DataFrame({'competency_name':['Programming']})
    app, figures = result_app(monkeypatch,tables)
    app.button_group(key='result_section').select('PSF-AAI demand').run(timeout=30)
    figures.clear()
    app.selectbox(key='result_psf_role').select('analyst').run(timeout=30)
    assert not app.exception and not app.error
    assert not any(fig.layout.title.text in ('Related PSF-AAI reference roles', 'Reviewed PSF-AAI competencies across reference roles') for fig in figures)
    assert any(item.label == 'analyst' and item.value == '1' for item in app.metric)
    assert any(item.label == 'analyst · programming' and item.value == '1' for item in app.metric)
    assert any("100.0% of 1 job ad in this reference role" in item.value for item in app.caption)


def test_psf_heatmap_compares_reviewed_competencies_with_role_denominators(monkeypatch):
    tables = result_tables()
    tables["psf_mapping"] = pd.DataFrame({
        "source_id": ["A", "A", "B", "B", "C"],
        "psf_competency": ["SQL", "Visualization", "SQL", "Programming", "SQL"],
        "psf_job_role": ["analyst; scientist", "analyst; scientist", "analyst", "analyst", "scientist"],
        "status": ["ALIGNED"] * 5,
    })
    tables["verified_psf_aai"] = pd.DataFrame({"competency_name": ["SQL", "Visualization", "Programming"]})
    app, figures = result_app(monkeypatch, tables)
    app.button_group(key="result_section").select("PSF-AAI demand").run(timeout=30)
    figure = figure_with_title(figures, "Reviewed PSF-AAI competencies across reference roles")
    trace = figure.data[0]
    analyst = trace.y.tolist().index("analyst")
    sql = trace.x.tolist().index("sql")
    visualization = trace.x.tolist().index("visualization")
    assert trace.z[analyst][sql] == 100.0
    assert trace.z[analyst][visualization] == 50.0
    assert list(trace.customdata[analyst][visualization][2:]) == [1, 50.0, 2]
    assert any("An ad can support several competencies" in item.value for item in app.caption)
    figures.clear()
    app.selectbox(key="result_psf_role").select("scientist").run(timeout=30)
    focused = figure_with_title(figures, "Reviewed PSF-AAI competencies across reference roles")
    assert focused.data[0].y.tolist() == ["scientist"]
    assert all("analyst" not in str(value) for value in focused.data[0].y)


def test_single_category_uses_headline_metric_with_scope(monkeypatch):
    tables = result_tables()
    tables["extracted_job_skills"] = tables["extracted_job_skills"].iloc[[0]].copy()
    tables.update(skill_chart_tables(tables["extracted_job_skills"], tables["cleaned_jobs"]))
    app, figures = result_app(monkeypatch, tables)
    assert not any(fig.layout.title.text == "Employer-requested skills" for fig in figures)
    assert any(item.label == "sql" and item.value == "1" for item in app.metric)
    assert any("25.0% of selected job advertisements" in item.value for item in app.caption)


def test_single_posting_month_is_a_metric_not_a_trend(monkeypatch):
    tables = result_tables()
    tables["cleaned_jobs"]["posting_date_parsed"] = ["2026-02-01", "2026-02-04", "2026-02-11", "2026-02-18"]
    app, figures = result_app(monkeypatch, tables)
    app.button_group(key="result_section").select("Roles and locations").run(timeout=30)
    assert not any(fig.layout.title.text == "Posting months represented in the dataset" for fig in figures)
    assert any(item.label == "2026-02" and item.value == "4" for item in app.metric)
    assert any("One month is present; this is coverage, not a time trend." in item.value for item in app.caption)




def test_missing_and_experience_phrases_are_reported_below_skill_charts(monkeypatch):
    tables = result_tables()
    skills = tables["extracted_job_skills"].copy()
    skills = pd.concat([skills, pd.DataFrame([
        {"extraction_id": "SYNTHETIC-MISSING", "source_id": "D", "source_type": "jobs",
         "original_phrase": "not mentioned", "normalized_phrase": "not mentioned",
         "competency_category": "Technical / Digital", "human_label": "Technical / Digital"},
        {"extraction_id": "SYNTHETIC-YEARS", "source_id": "C", "source_type": "jobs",
         "original_phrase": "3+year", "normalized_phrase": "3+year",
         "competency_category": "Technical / Digital", "human_label": "Technical / Digital"},
    ])], ignore_index=True)
    tables["extracted_job_skills"] = skills
    tables.update(skill_chart_tables(skills, tables["cleaned_jobs"]))

    app, figures = result_app(monkeypatch, tables)

    chart_figure = figure_with_title(figures, "Employer-requested skills")
    assert not {"not mentioned", "3+year"} & set(chart_figure.data[0].y)
    captions = [item.value for item in app.caption]
    assert any("Missing / not-mentioned placeholders: 1 ads" in value for value in captions)
    assert any("Experience/year wording: 1 ads" in value and "excluded from skills and PSF-AAI demand" in value for value in captions)
    assert any("No chartable skill evidence, regardless of PSF status: 1 of 4 ads" in value for value in captions)
