"""Synthetic audience-focused result views; no live sources or research records."""
from copy import deepcopy
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
        original(deepcopy(figure))
    monkeypatch.setattr(ui, "chart", capture)
    monkeypatch.setattr(ui, "current_analysis", lambda: True)
    monkeypatch.setattr(ui, "filtered_bundle", lambda: (tables, {"settings": {"emerging_min_jobs": 2}}))
    app = AppTest.from_string(f"from src.ui import research_page\nresearch_page({page!r})").run(timeout=30)
    assert not app.exception and not app.error
    return app, figures


def figure_with_title(figures, title):
    return next(figure for figure in reversed(figures) if figure.layout.title.text == title)


def html_content(app):
    return "\n".join(item.proto.body for item in app.get("html"))


def test_first_section_visits_load_once_and_revisits_reuse_prepared_data(monkeypatch):
    from unittest.mock import Mock
    from src import loading_ui
    tables = result_tables()
    wireframe = Mock(wraps=loading_ui._wireframe)
    monkeypatch.setattr(loading_ui, "_wireframe", wireframe)
    original_profile = ui.job_profile_tables
    def prepare_profile(jobs):
        assert wireframe.call_args.args == ("market_section",)
        assert wireframe.call_args.kwargs["view"] in {"Roles and locations", "Qualifications"}
        return original_profile(jobs)
    profile = Mock(side_effect=prepare_profile)
    geography = Mock(wraps=ui.location_tables)
    monkeypatch.setattr(ui, "job_profile_tables", profile)
    monkeypatch.setattr(ui, "location_tables", geography)
    app, _ = result_app(monkeypatch, tables)
    def transitions():
        return [call.kwargs["view"] for call in wireframe.call_args_list if call.args == ("market_section",)]
    assert transitions() == ["Skills"]
    for section in ("Roles and locations", "Qualifications", "PSF-AAI demand"):
        app.button_group(key="result_section").select(section).run(timeout=30)
        assert not app.exception and not app.error
        assert transitions()[-1] == section
        assert app.session_state["_fow_loading_ready"]["job_market_view_load"]
    assert transitions() == ["Skills", "Roles and locations", "Qualifications", "PSF-AAI demand"]
    before = list(transitions())
    for section in ("Skills", "Qualifications", "Roles and locations", "PSF-AAI demand", "Skills"):
        app.button_group(key="result_section").select(section).run(timeout=30)
        assert not app.exception and not app.error
        assert transitions() == before
    profile.assert_called_once()
    geography.assert_called_once()
    app.run(timeout=30)
    assert transitions() == before


def test_keyed_market_fragment_can_rerun_without_reentering_parent_data_loads(monkeypatch):
    from unittest.mock import Mock
    hashed = Mock(side_effect=AssertionError("Explicit revisions must not rehash the snapshot"))
    monkeypatch.setattr(ui, "frame_hash", hashed)
    app = AppTest.from_string('''
import streamlit as st
from src.ui import _job_market_results
from test_result_views import result_tables
st.button('Synthetic fragment refresh', on_click=lambda: st.rerun('job_market_results'))
st.session_state['synthetic_parent_loads'] = st.session_state.get('synthetic_parent_loads', 0) + 1
_job_market_results(result_tables(), {}, revision="synthetic-revision-one")
''').run(timeout=30)
    assert not app.exception and app.session_state["synthetic_parent_loads"] == 1
    next(item for item in app.button if item.label == "Synthetic fragment refresh").click().run(timeout=30)
    assert not app.exception and app.session_state["synthetic_parent_loads"] == 1
    hashed.assert_not_called()


def test_section_filters_survive_switches_and_changed_inputs_invalidate_summaries(monkeypatch):
    from unittest.mock import Mock
    from src import loading_ui
    tables = result_tables()
    profile = Mock(wraps=ui.job_profile_tables)
    geography = Mock(wraps=ui.location_tables)
    wireframe = Mock(wraps=loading_ui._wireframe)
    monkeypatch.setattr(ui, "job_profile_tables", profile)
    monkeypatch.setattr(ui, "location_tables", geography)
    monkeypatch.setattr(loading_ui, "_wireframe", wireframe)
    app, _ = result_app(monkeypatch, tables)
    app.button_group(key="result_section").select("Roles and locations").run(timeout=30)
    app.selectbox(key="result_title_view").select("Specific titles (alphabetical)").run(timeout=30)
    app.button_group(key="result_section").select("Skills").run(timeout=30)
    app.button_group(key="result_section").select("Roles and locations").run(timeout=30)
    assert app.selectbox(key="result_title_view").value == "Specific titles (alphabetical)"
    assert profile.call_count == geography.call_count == 1
    before = sum(call.args == ("market_section",) for call in wireframe.call_args_list)
    # A same-sized replacement must refresh cached summaries and readiness.
    tables["cleaned_jobs"].loc[0, "job_title"] = "Synthetic changed title"
    app.run(timeout=30)
    assert not app.exception and not app.error
    assert profile.call_count == geography.call_count == 2
    assert sum(call.args == ("market_section",) for call in wireframe.call_args_list) == before + 1
    # A reviewed mapping change also invalidates visited sections.
    tables["psf_mapping"].loc[0, "psf_competency"] = "Synthetic changed competency"
    app.button_group(key="result_section").select("PSF-AAI demand").run(timeout=30)
    assert not app.exception and not app.error
    assert app.session_state["_fow_market_loaded"]["sections"] == {"psf_aai"}


def test_job_market_hides_audience_guidance_banner(monkeypatch):
    app, _ = result_app(monkeypatch, result_tables())
    assert not any("For the chancellor:" in item.value for item in app.markdown)
    assert not any("Counts describe the selected advertisements" in item.value for item in app.caption)


def test_reference_metrics_render_selected_counts_without_extra_badges(monkeypatch):
    app, _ = result_app(monkeypatch, result_tables())
    metrics = {metric.label: metric.value for metric in app.metric}
    assert metrics["Job ads in sample"] == "4"
    assert metrics["Distinct chart skills"] == "3"
    assert metrics["Distinct phrases withheld"] == "1"
    assert metrics["PSF-AAI reference roles"] == "—"
    assert "fow-metric-badge" not in html_content(app)
    assert not any("fow-metric-badge" in item.value for item in app.markdown)
    assert app.button_group(key="result_section").options == ["Skills", "Roles and locations", "Qualifications", "PSF-AAI demand"]


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
    assert metrics["Job ads in sample"] == "4"
    assert metrics["Distinct phrases withheld"] == "1"
    assert not any("Experience requirement fields" == fig.layout.title.text for fig in figures)
    app.selectbox(key="result_title_view").set_value("Specific titles (alphabetical)").run(timeout=30)
    app.selectbox(key="result_specific_title").set_value("engineer").run(timeout=30)
    assert not app.exception and not app.error
    assert not any(fig.layout.title.text == "Top skills for engineer" for fig in figures)
    assert any(item.label == "c++" and item.value == "1" for item in app.metric)
    pd.testing.assert_frame_equal(tables["extracted_job_skills"], before)


def test_job_market_insights_and_reference_role_card_use_selected_data(monkeypatch):
    tables = result_tables()
    tables["psf_framework_order"] = pd.DataFrame({
        "competency_id": ["C1", "C2", "C3"],
        "competency_name": ["Programming", "Data Analysis", "Statistics"],
        "job_role": ["Analyst", "Data Engineer", "Analyst"],
    })
    app, _ = result_app(monkeypatch, tables)
    metrics = {item.label: item.value for item in app.metric}
    assert metrics["PSF-AAI reference roles"] == "2"
    skills_insight = html_content(app).casefold()
    assert "key insight" in skills_insight
    assert "sql has the highest displayed skill count" in skills_insight
    assert "top displayed skills" in skills_insight

    for section, insight, evidence in (
        ("Roles and locations", "title insight", "data analyst"),
        ("Qualifications", "education insight", "bachelor"),
        ("PSF-AAI demand", "key insight", "programming"),
    ):
        app.button_group(key="result_section").select(section).run(timeout=30)
        assert not app.exception and not app.error
        content = html_content(app).casefold()
        assert insight in content and evidence in content


def test_timeline_education_and_family_insights_acknowledge_ties(monkeypatch):
    tables = result_tables()
    tables["cleaned_jobs"]["education_requirement"] = ["Bachelor's degree", "Master's degree"] * 2
    tables["cleaned_jobs"]["posting_date_parsed"] = ["2026-01-01", "2026-02-01"] * 2
    app, _ = result_app(monkeypatch, tables)
    app.button_group(key="result_section").select("Roles and locations").run(timeout=30)
    assert not app.exception and not app.error
    content = html_content(app)
    assert "displayed skill–family pairs tie" in content
    assert "2 displayed months tie" in content
    app.button_group(key="result_section").select("Qualifications").run(timeout=30)
    assert not app.exception and not app.error
    assert "2 classifiable levels share the highest count" in html_content(app)


def test_experience_band_table_uses_readable_labels_and_hides_sort_key(monkeypatch):
    tables = result_tables()
    tables["cleaned_jobs"]["experience_requirement"] = ["2 years", "3 years", "2 years", "3 years"]
    app, _ = result_app(monkeypatch, tables)
    app.button_group(key="result_section").select("Qualifications").run(timeout=30)
    bands = next(frame.value for frame in app.dataframe if "Experience requirement" in frame.value.columns
                 and "1–2 years" in frame.value["Experience requirement"].astype(str).tolist())
    assert bands.columns.tolist() == ["Experience requirement", "Job advertisements", "Share of selected ads (%)"]


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
    assert not app.dataframe
    app.session_state["unmapped_evidence_details"] = True
    app.run(timeout=30)
    assert not app.exception
    assert any("•sql" in frame.value.astype(str).to_string() for frame in app.dataframe)


def test_unmapped_summary_and_insights_follow_screened_counts_and_data_changes(monkeypatch):
    tables = result_tables()
    tables["alignment_results"] = pd.DataFrame({
        "normalized_skill": ["SQL", "sql", "collaboration", "c++", "build"],
        "status": ["NOT MAPPED"] * 5,
    })
    tables["unmapped_skills"] = tables["alignment_results"].assign(
        employer_skill=tables["alignment_results"].normalized_skill, employer_demand_count=1)
    tables["emerging_skills"] = tables["unmapped_skills"].iloc[:0].copy()
    app, figures = result_app(monkeypatch, tables, "Unmapped / Emerging Skills")
    metrics = {item.label: item.value for item in app.metric}
    assert metrics["Unmapped skill labels"] == "3"
    assert metrics["Recurring labels for review"] == "1"
    bars = figure_with_title(figures, "Unmapped skill evidence").data[0]
    assert dict(zip(bars.y, bars.x)) == {"sql": 2, "c++": 1, "collaboration": 1}
    content = html_content(app)
    assert "Evidence Insight" in content and "Review Insight" in content
    assert "sql has the highest displayed unmapped skill count" in content
    assert "50.0% of 4 selected ads" in content
    assert "build" not in bars.y
    # Raw evidence survives screening; current charts update when mapping evidence changes.
    assert not app.dataframe
    app.session_state["unmapped_evidence_details"] = True
    app.session_state["unmapped_recurring_details"] = True
    app.run(timeout=30)
    assert not app.exception and len(app.dataframe) == 2
    assert any("build" in frame.value.astype(str).to_string() for frame in app.dataframe)
    recurring = app.dataframe[1].value
    assert set(recurring.normalized_skill.str.casefold()) == {"sql"}
    app.session_state["unmapped_evidence_details"] = False
    app.session_state["unmapped_recurring_details"] = False
    app.run(timeout=30)
    assert not app.exception and not app.dataframe
    tables["alignment_results"].loc[tables["alignment_results"].normalized_skill.str.casefold().eq("sql"), "status"] = "ALIGNED"
    figures.clear()
    app.run(timeout=30)
    assert not app.exception and not app.error
    metrics = {item.label: item.value for item in app.metric}
    assert metrics["Unmapped skill labels"] == "2" and metrics["Recurring labels for review"] == "0"
    bars = figure_with_title(figures, "Unmapped skill evidence").data[0]
    assert set(bars.y) == {"c++", "collaboration"}
    assert "sql has the highest" not in html_content(app)


def test_unmapped_insight_uses_alphabetical_visible_subset_and_ties(monkeypatch):
    tables = result_tables()
    tables["alignment_results"] = pd.DataFrame({
        "normalized_skill": ["sql", "collaboration", "c++"], "status": ["NOT MAPPED"] * 3})
    tables["unmapped_skills"] = tables["alignment_results"].assign(
        employer_skill=tables["alignment_results"].normalized_skill, employer_demand_count=1)
    tables["emerging_skills"] = pd.DataFrame()
    monkeypatch.setattr(ui, "result_chart_options", lambda **kwargs: ("Alphabetical", 2))
    app, figures = result_app(monkeypatch, tables, "Unmapped / Emerging Skills")
    bars = figure_with_title(figures, "Unmapped skill evidence").data[0]
    assert list(bars.y) == ["c++", "collaboration"]
    content = html_content(app)
    assert "2 unmapped skills tie for the highest displayed count at 1 ad each" in content
    assert "sql has the highest" not in content


def test_psf_tab_has_isolated_body_and_reuses_prepared_all_role_summaries(monkeypatch):
    from unittest.mock import Mock
    from src.analytics import psf_demand_tables
    from src import loading_ui
    tables = result_tables()
    tables.update(psf_demand_tables(tables["psf_mapping"], tables["cleaned_jobs"], pd.DataFrame()))
    builder = Mock(side_effect=AssertionError("All-role summaries are already available"))
    monkeypatch.setattr(ui, "psf_demand_tables", builder)
    wireframe = Mock(wraps=loading_ui._wireframe)
    monkeypatch.setattr(loading_ui, "_wireframe", wireframe)
    app, _ = result_app(monkeypatch, tables)
    app.button_group(key="result_section").select("PSF-AAI demand").run(timeout=30)
    assert not app.exception and not app.error
    content = html_content(app)
    assert "st-key-job_market_section_psf_aai{display:flex!important}" in content
    assert '[class*="st-key-job_market_section_"]{display:none!important}' in content
    assert 'data-fow-psf-ready="true"' in content
    assert sum(call.args[0] == "psf_charts" for call in wireframe.call_args_list) == 1
    builder.assert_not_called()
    app.run(timeout=30)
    assert sum(call.args[0] == "psf_charts" for call in wireframe.call_args_list) == 1


def test_psf_chart_summary_does_not_hash_or_copy_repeated_source_text(monkeypatch):
    tables = result_tables()
    tables["psf_mapping"]["original_text"] = ["Synthetic source evidence " * 1000] * 2
    original = ui.frame_hash
    columns = []
    def check(frame):
        columns.append(set(frame.columns))
        assert "original_text" not in frame.columns
        return original(frame)
    monkeypatch.setattr(ui, "frame_hash", check)
    app, _ = result_app(monkeypatch, tables)
    app.button_group(key="result_section").select("PSF-AAI demand").run(timeout=30)
    assert not app.exception and not app.error
    assert {"source_id", "psf_competency", "psf_job_role", "status"} in columns
    assert any(item.label == "programming" and item.value == "1" for item in app.metric)
    assert "original_text" in tables["psf_mapping"]


def test_incomplete_psf_chart_group_never_gets_a_ready_marker_and_can_retry(monkeypatch, tmp_path):
    from src import storage
    monkeypatch.setattr(storage, "ROOT", tmp_path)
    tables = result_tables()
    tables["psf_mapping"] = pd.DataFrame({
        "source_id": ["A", "B"], "psf_competency": ["SQL", "Python"],
        "psf_job_role": ["analyst", "scientist"], "status": ["ALIGNED", "ALIGNED"],
    })
    monkeypatch.setattr(ui, "current_analysis", lambda: True)
    monkeypatch.setattr(ui, "filtered_bundle", lambda: (tables, {}))
    original = ui.chart
    fail = [True]
    def draw(figure):
        if figure.layout.title.text == "PSF-AAI competencies linked to employer demand" and fail[0]:
            raise ValueError("Synthetic chart rendering interruption")
        return original(figure)
    monkeypatch.setattr(ui, "chart", draw)
    app = AppTest.from_string("from src.ui import render\nrender('Job Market Analysis')").run(timeout=30)
    app.button_group(key="result_section").select("PSF-AAI demand").run(timeout=30)
    assert not app.exception
    assert any("Synthetic chart rendering interruption" in item.value for item in app.error)
    assert 'data-fow-psf-ready="true"' not in html_content(app)
    assert not app.session_state["_fow_loading_ready"].get("job_market_psf_charts")
    fail[0] = False
    app.run(timeout=30)
    assert not app.exception and not app.error
    assert 'data-fow-psf-ready="true"' in html_content(app)
    assert app.session_state["_fow_loading_ready"]["job_market_psf_charts"]


def test_specific_titles_stay_alphabetical_and_grouped_view_is_auditable(monkeypatch):
    app, figures = result_app(monkeypatch, result_tables())
    assert "Select job ads" in html_content(app)
    assert "Describe results" in html_content(app)
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
    column = trace.x.tolist().index("analytics")
    row = trace.y.tolist().index("sql")
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
                           "original_phrase": f"Synthetic technique {index} analysis", "normalized_phrase": f"synthetic technique {index} analysis",
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
    analyst = trace.x.tolist().index("analyst")
    sql = trace.y.tolist().index("sql")
    visualization = trace.y.tolist().index("visualization")
    assert trace.z[sql][analyst] == 100.0
    assert trace.z[visualization][analyst] == 50.0
    assert list(trace.customdata[visualization][analyst][2:]) == [1, 50.0, 2]
    assert any("An ad can support several competencies" in item.value for item in app.caption)
    figures.clear()
    app.selectbox(key="result_psf_role").select("scientist").run(timeout=30)
    focused = figure_with_title(figures, "Reviewed PSF-AAI competencies across reference roles")
    assert focused.data[0].x.tolist() == ["scientist"]
    assert all("analyst" not in str(value) for value in focused.data[0].x)


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


def test_multiple_posting_months_use_chronological_count_bars(monkeypatch):
    tables = result_tables()
    tables["cleaned_jobs"]["posting_date_parsed"] = ["2026-03-01", "2026-01-04", "2026-03-14", "2026-02-12"]
    app, figures = result_app(monkeypatch, tables)
    app.button_group(key="result_section").select("Roles and locations").run(timeout=30)
    figure = figure_with_title(figures, "Posting months represented in the dataset")
    assert figure.data[0].type == "bar"
    assert figure.data[0].x.tolist() == ["2026-01", "2026-02", "2026-03"]
    assert figure.data[0].y.tolist() == [1, 1, 2]
    assert figure.layout.yaxis.tickformat == ",d"
    assert any("This shows collection coverage, not market growth." in item.value for item in app.caption)




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

def test_location_counts_render_inside_their_expander_only_when_open(monkeypatch):
    tables = result_tables()
    app, _ = result_app(monkeypatch, tables)
    app.button_group(key='result_section').select('Roles and locations').run(timeout=30)
    def regional_tables(elements):
        return [item for item in elements if 'Share of comparison group (%)' in item.value]
    assert not app.exception
    assert not regional_tables(app.dataframe)
    app.session_state['result_all_location_counts'] = True
    app.run(timeout=30)
    assert not app.exception
    expander = next(item for item in app.expander if item.label == 'View all regional or city counts')
    nested = regional_tables(expander.dataframe)
    assert len(nested) == 1
    assert nested[0].value['Job advertisements'].sum() == 4
    assert len(regional_tables(app.dataframe)) == 1
    app.session_state['result_all_location_counts'] = False
    app.run(timeout=30)
    assert not app.exception
    assert not regional_tables(app.dataframe)
