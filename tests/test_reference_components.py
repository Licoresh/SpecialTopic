"""Reference-style controls retain real metrics and route exports to Reports."""
from unittest.mock import Mock
import pandas as pd
import pytest

from src import ui
from src.visualization import ranked_bar
from test_result_views import result_app, result_tables


def test_readiness_panels_follow_current_evidence_and_keep_diagnostics_lazy(workspace, jobs, monkeypatch):
    from streamlit.testing.v1 import AppTest
    from src import storage
    from src.readiness import research_data_profile
    labels = pd.DataFrame({
        "phrase": ["Python programming", "team collaboration", "SQL queries"],
        "label": ["Technical / Digital", "Soft / Enabling", "Technical / Digital"],
        "source_id": [jobs.source_id.iloc[0], jobs.source_id.iloc[1], " "],
        "source_type": ["jobs"] * 3, "reviewer": ["Synthetic A", "Synthetic B", "Synthetic A"],
        "timestamp": ["2026-11-02T00:00:00Z"] * 3,
    })
    monkeypatch.setattr(ui, "ROOT", workspace)
    monkeypatch.setattr(ui, "load_labeled_data", lambda path: labels.copy())
    monkeypatch.setattr(ui, "read_model_metadata", lambda: None)
    storage.save_frame("cleaned_jobs", jobs)
    app = AppTest.from_string('from src.ui import research_readiness\nresearch_readiness()').run(timeout=30)
    assert not app.exception and not app.error
    metrics = {item.label: item.value for item in app.metric}
    assert metrics["Saved labels"] == "3"
    assert metrics["Distinct job-ad source IDs"] == "2"  # Blank provenance is not an ad.
    assert metrics["Reviewer ID spellings"] == "2"
    assert metrics["Cleaned job ads"] == str(len(jobs))
    assert metrics["Scope review recorded"] == "No"
    sources = next(item.value for item in app.dataframe if "competency_phrases" in item.value)
    pd.testing.assert_frame_equal(sources, research_data_profile(labels)["sources"])
    content = " ".join(item.proto.body for item in app.get("html"))
    assert "The labeled file has 2 distinct source IDs" in content
    assert "Independent annotation quality is not established by the app" in content
    assert not app.json
    labels = labels.iloc[:1].copy()
    storage.save_frame("cleaned_jobs", jobs.iloc[:1])
    storage.save_json("cleaning_jobs", {"philippine_aai_scope_reviewed": True})
    app.run(timeout=30)
    assert not app.exception and not app.error
    metrics = {item.label: item.value for item in app.metric}
    assert metrics["Saved labels"] == metrics["Distinct job-ad source IDs"] == metrics["Cleaned job ads"] == "1"
    assert metrics["Scope review recorded"] == "Yes"
    updated = " ".join(item.proto.body for item in app.get("html"))
    assert "The labeled file has 1 distinct source IDs" in updated
    assert "The labeled file has 2 distinct source IDs" not in updated
    app.session_state["readiness_diagnostics"] = True
    app.run(timeout=30)
    assert not app.exception and app.json


def test_quality_insight_updates_with_the_actual_cleaned_preview(workspace, jobs, monkeypatch):
    from streamlit.testing.v1 import AppTest
    from src import storage
    monkeypatch.setattr(ui, "ROOT", workspace)
    frame = jobs.copy()
    frame["required_skills"] = ""
    frame["preferred_skills"] = ""
    storage.save_frame("mapped_jobs", frame)
    app = AppTest.from_string('from src.ui import quality\nquality()').run(timeout=30)
    assert not app.exception and not app.error
    content = " ".join(item.proto.body for item in app.get("html"))
    assert f"This preview contains {len(frame):,} records" in content
    assert f"blank in {len(frame):,} of {len(frame):,} ads" in content
    frame = frame.iloc[:1].copy()
    frame["required_skills"] = "synthetic skill"
    storage.save_frame("mapped_jobs", frame)
    app.run(timeout=30)
    assert not app.exception and not app.error
    content = " ".join(item.proto.body for item in app.get("html"))
    assert "This preview contains 1 record" in content
    assert "blank in 0 of 1 ad" in content
    assert not any("Quality check" in item.value for item in app.dataframe)
    app.session_state["quality_report_details"] = True
    app.run(timeout=30)
    assert not app.exception
    quality = next(item.value for item in app.dataframe if "Quality check" in item.value)
    assert int(quality.loc[quality["Quality check"].eq("Total records"), "Count"].iloc[0]) == 1
    assert "Blank values across 5 core fields: 2." in content
    frame["job_title"] = ""
    storage.save_frame("mapped_jobs", frame)
    app.session_state["quality_report_details"] = True
    app.run(timeout=30)
    assert not app.exception
    updated = " ".join(item.proto.body for item in app.get("html"))
    assert "Blank values across 5 core fields: 3." in updated
    quality = next(item.value for item in app.dataframe if "Quality check" in item.value)
    assert int(quality.loc[quality["Quality check"].eq("Missing: job title"), "Count"].iloc[0]) == 1


def test_training_insight_uses_the_displayed_distribution(workspace, monkeypatch):
    from streamlit.testing.v1 import AppTest
    from src import storage
    monkeypatch.setattr(ui, "ROOT", workspace)
    monkeypatch.setattr(ui.supabase_store, "configured", lambda: True)
    monkeypatch.setattr(ui.supabase_store, "is_admin", lambda: False)
    data = pd.DataFrame({"label": ["Data / Analytics"] * 2 + ["Technical / Digital"] * 5})
    monkeypatch.setattr(storage, "read_frame", lambda *a, **k: data.copy())
    monkeypatch.setattr(ui, "read_model_metadata", lambda: None)
    monkeypatch.setattr(ui, "training_data_changed", lambda: False)
    def validate(*a, **k):
        return data.copy(), {"total_rows": len(data), "rows_used": len(data),
                             "number_of_classes": data.label.nunique(), "warnings": [],
                             "errors": ["Synthetic incomplete review; do not train."],
                             "additional_distinct_labels_needed": 30 - len(data), "additional_classes_needed": 0}
    monkeypatch.setattr(ui, "cached_label_validation", validate)
    app = AppTest.from_string('from src.ui import training\ntraining()').run(timeout=30)
    assert not app.exception and not app.error
    content = " ".join(item.proto.body for item in app.get("html"))
    assert "7 distinct usable phrases across 2 displayed categories" in content
    assert "Data / Analytics: 2 usable phrases" in content
    assert "Technical / Digital: 5 usable phrases; below" not in content
    data = pd.DataFrame({"label": ["Data / Analytics"] * 3 + ["Technical / Digital"] * 6})
    app.run(timeout=30)
    assert not app.exception and not app.error
    content = " ".join(item.proto.body for item in app.get("html"))
    assert "9 distinct usable phrases across 2 displayed categories" in content
    assert "Data / Analytics: 3 usable phrases" in content
    assert next(item for item in app.button if item.label == "Train / Retrain Models").disabled


def test_empty_evaluation_does_not_copy_reference_example_scores(workspace, monkeypatch):
    from streamlit.testing.v1 import AppTest
    from src import storage
    monkeypatch.setattr(ui, "read_model_metadata", lambda: None)
    monkeypatch.setattr(storage, "read_frame", lambda *a, **k: pd.DataFrame())
    app = AppTest.from_string('from src.ui import evaluation\nevaluation()').run(timeout=30)
    assert not app.exception and not app.error
    assert not app.metric and not app.get("plotly_chart")
    assert any("No research model has been trained" in item.value for item in app.info)


def test_export_action_opens_reports_without_changing_research_counts(monkeypatch):
    route = Mock()
    monkeypatch.setattr(ui.st, 'switch_page', route)
    app, _ = result_app(monkeypatch, result_tables())
    before = {metric.label: metric.value for metric in app.metric}
    app.button(key='results_export').click().run(timeout=30)
    assert not app.exception and not app.error
    route.assert_called_once_with('pages/14_Reports.py')
    assert {metric.label: metric.value for metric in app.metric} == before
    assert before['Job ads in sample'] == '4'
    assert before['Distinct chart skills'] == '3'
    assert before['Distinct phrases withheld'] == '1'


@pytest.mark.parametrize("page", ["Job Market Analysis", "PSF Mapping", "Employer–PSF Alignment"])
def test_compact_job_market_chart_keeps_counts_and_accessible_title(monkeypatch, page):
    frame = pd.DataFrame({"skill": [f"Synthetic skill {index}" for index in range(15)],
                          "job_ads": list(range(1, 16))})
    figure = ranked_bar(frame, "skill", "job_ads", "Synthetic demand")
    trace = figure.data[0].to_json()
    original_height = figure.layout.height
    rendered, heading = Mock(), Mock()
    session = {"_fow_current_page": page}
    monkeypatch.setattr(ui.st, "session_state", session)
    monkeypatch.setattr(ui.st, "plotly_chart", rendered)
    monkeypatch.setattr(ui.st, "subheader", heading)

    ui.chart(figure)

    assert figure.data[0].to_json() == trace
    prepared = rendered.call_args.args[0]
    assert prepared.layout.height < original_height
    assert rendered.call_args.kwargs["alt"] == "Synthetic demand"
    assert heading.call_args.args[0] == "Synthetic demand"
    assert prepared.layout.title.text == ""
    assert figure.layout.title.text == "Synthetic demand"
    session["_fow_current_page"] = "Employer–PSF alignment"
    other = ranked_bar(frame, "skill", "job_ads", "Synthetic demand")
    ui.chart(other)
    assert other.layout.height == original_height
    assert other.layout.title.text == "Synthetic demand"
    assert heading.call_count == 1


def test_long_chart_labels_reserve_their_lines_without_changing_evidence(monkeypatch):
    frame = pd.DataFrame({
        "skill": ["continuous integration and continuous deployment", "research <and> development", "SQL"],
        "job_ads": [4, 3, 2], "job_ads_pct": [40., 30., 20.],
    })
    figure = ranked_bar(frame, "skill", "job_ads", "Synthetic long labels")
    trace = figure.data[0].to_json()
    monkeypatch.setattr(ui.st, "session_state", {"_fow_current_page": "Job Market Analysis"})
    rendered = Mock()
    monkeypatch.setattr(ui.st, "plotly_chart", rendered)
    monkeypatch.setattr(ui.st, "subheader", Mock())
    ui.chart(figure)
    assert figure.data[0].to_json() == trace
    prepared = rendered.call_args.args[0]
    assert list(prepared.layout.yaxis.tickvals) == list(figure.data[0].y)
    labels = prepared.layout.yaxis.ticktext
    assert any("<br>" in label for label in labels)
    assert any("&lt;and&gt;" in label for label in labels)
    required_height = 55 + sum(max(28, 14 * (label.count("<br>") + 1) + 8) for label in labels)
    assert prepared.layout.height >= required_height
    assert prepared.layout.font.size >= 12
    assert rendered.call_args.kwargs["width"] == "stretch"


def test_wide_heatmap_scrolls_locally_with_all_cells_and_stable_identity():
    import json
    from streamlit.testing.v1 import AppTest
    app = AppTest.from_string('''
import streamlit as st
import pandas as pd
from src.ui import chart
from src.visualization import heatmap
st.session_state["_fow_current_page"] = "Job Market Analysis"
matrix = pd.DataFrame([list(range(18)), list(range(18, 36))],
                      index=["Synthetic role A", "Synthetic role B"],
                      columns=[f"Synthetic competency {index}" for index in range(18)])
chart(heatmap(matrix, "Synthetic wide matrix"))
''').run(timeout=30)
    assert not app.exception
    chart = app.get("plotly_chart")[0].proto
    spec = json.loads(chart.spec)
    assert len(spec["data"][0]["x"]) == 18 and len(spec["data"][0]["y"]) == 2
    assert "Count:" in spec["data"][0]["hovertemplate"]
    markup = " ".join(item.proto.body for item in app.get("html"))
    assert "--fow-matrix-width:1576px" in markup
    assert "Scroll horizontally to read all chart columns." in markup
    first_id = chart.id
    app.run(timeout=30)
    assert not app.exception and app.get("plotly_chart")[0].proto.id == first_id


def test_psf_heatmap_filter_clear_and_restore_keeps_real_values_and_palette():
    import json
    from streamlit.testing.v1 import AppTest
    app = AppTest.from_string('''
import pandas as pd
import streamlit as st
from src.ui import _competency_heatmap_view
st.session_state['_fow_current_page'] = 'Job Market Analysis'
cells = pd.DataFrame({'psf_job_role': ['analyst', 'analyst', 'engineer', 'engineer'],
                      'psf_competency': ['python', 'sql', 'python', 'sql'], 'job_ads': [1, 2, 2, 1]})
roles = pd.DataFrame({'psf_job_role': ['analyst', 'engineer'], 'job_ads': [20, 25]})
competence = pd.DataFrame({'psf_competency': ['python', 'sql'], 'job_ads': [3, 3]})
_competency_heatmap_view(cells, roles, competence, 15)
''').run(timeout=30)

    def specification():
        assert not app.exception and not app.error
        assert len(app.get('plotly_chart')) == 1
        chart = app.get('plotly_chart')[0].proto
        assert chart.theme == ''  # Use the figure's explicit palette on every rerun.
        spec = json.loads(chart.spec)
        assert spec['layout']['coloraxis']['cmin'] == 0
        assert spec['layout']['coloraxis']['cmax'] == 100
        return spec

    initial = specification()
    for roles in (['analyst'], ['engineer'], ['analyst', 'engineer']):
        app.multiselect(key='result_competency_heatmap_roles').set_value(roles).run(timeout=30)
        spec = specification()
        assert spec['data'][0]['x'] == roles
        assert spec['layout']['coloraxis']['colorscale'] == initial['layout']['coloraxis']['colorscale']
        if len(roles) == 1:
            assert spec['layout']['uirevision'] != initial['layout']['uirevision']
        for row in spec['data'][0]['customdata']:
            for _, role, count, share, denominator in row:
                assert denominator == {'analyst': 20, 'engineer': 25}[role]
                assert share == count / denominator * 100
    app.multiselect(key='result_competency_heatmap_competencies').set_value([]).run(timeout=30)
    assert not app.exception and not app.get('plotly_chart')
    assert any('Select at least one role and competency' in item.value for item in app.info)
    app.multiselect(key='result_competency_heatmap_competencies').set_value(['sql']).run(timeout=30)
    assert specification()['data'][0]['y'] == ['sql']
    app.multiselect(key='result_competency_heatmap_roles').set_value(['analyst']).run(timeout=30)
    assert not app.exception and not app.get('plotly_chart')
    app.multiselect(key='result_competency_heatmap_roles').set_value(['analyst', 'engineer']).run(timeout=30)
    assert specification()['data'][0]['customdata'][0][0] == ['sql', 'analyst', 2, 10.0, 20]


def test_heatmap_small_positive_shares_are_visible_without_rescaling_percentages():
    from plotly.colors import sample_colorscale
    from src.visualization import heatmap
    counts = pd.DataFrame([[0, 1, 25]], index=['synthetic role'], columns=['zero', 'rare', 'common'])
    before = counts.copy(deep=True)
    shares = counts / 500 * 100
    figure = heatmap(counts, 'Synthetic small shares', share_matrix=shares)
    assert figure.data[0].z.tolist() == [[0., .2, 5.]]
    assert figure.layout.coloraxis.cmin == 0 and figure.layout.coloraxis.cmax == 100
    colors = sample_colorscale([list(stop) for stop in figure.layout.coloraxis.colorscale], [0, .002, .05], colortype='tuple')
    assert sum(abs(a - b) for a, b in zip(colors[0], colors[1])) > .4
    assert colors[0] != colors[1] != colors[2]
    pd.testing.assert_frame_equal(counts, before)


def test_reference_role_distribution_counts_roles_not_overlapping_ad_links(monkeypatch):
    roles = pd.DataFrame({"psf_job_role": ["First role", "Second role", "Third role"],
                          "job_ads": [19, 19, 18]})
    before = roles.copy(deep=True)
    rendered = Mock()
    monkeypatch.setattr(ui.st, "html", rendered)

    ui.result_role_distribution(roles)

    content = rendered.call_args.args[0]
    assert '<strong>3</strong><small>Linked roles</small>' in content
    assert '3 linked reference roles grouped by advertisement count' in content
    assert '19 ads each' in content and '18 ads each' in content
    assert '66.7%' in content and '33.3%' in content
    assert '>56<' not in content
    pd.testing.assert_frame_equal(roles, before)


def test_alignment_reference_view_preserves_supplied_rates_counts_and_basis(monkeypatch):
    from streamlit.testing.v1 import AppTest
    tables = result_tables()
    tables["alignment_results"] = pd.DataFrame({
        "alignment_id": ["S1", "S2", "S3", "S4"],
        "employer_skill": ["sql", "python", "communication", "new tool"],
        "psf_competency": ["Data Engineering", "Data Engineering", "Communication", ""],
        "status": ["ALIGNED", "PARTIALLY ALIGNED", "PARTIALLY ALIGNED", "NOT MAPPED"],
    })
    tables["employer_skill_demand"] = pd.DataFrame({
        "employer_skill": ["sql", "python"], "employer_demand_count": [3, 2],
    })
    before = tables["alignment_results"].copy(deep=True)
    metadata = {"rates_before_status_display_filter": {
        "alignment_rate": 50., "partially_aligned_rate": 50., "unmapped_rate": 25.,
    }, "denominators": "Synthetic basis: assessed and mapped phrase denominators differ."}
    figures = []
    monkeypatch.setattr(ui, "current_analysis", lambda: True)
    monkeypatch.setattr(ui, "filtered_bundle", lambda: (tables, metadata))
    monkeypatch.setattr(ui.storage, "read_frame", lambda name: pd.DataFrame({"range_of_application": ["SQL"]}))
    monkeypatch.setattr(ui, "chart", figures.append)
    app = AppTest.from_string('from src.ui import research_page\nresearch_page("Employer–PSF Alignment")').run(timeout=30)
    assert not app.exception and not app.error
    assert {metric.label: metric.value for metric in app.metric} == {
        "Alignment Rate": "50.0%", "Partially Aligned Rate": "50.0%", "Unmapped Rate": "25.0%",
    }
    assert dict(zip(figures[0].data[0].y, figures[0].data[0].x)) == {
        "partially aligned": 2, "aligned": 1, "not mapped": 1,
    }
    assert figures[0].data[0].texttemplate == "%{x:,d}"
    assert any(item.value == metadata["denominators"] for item in app.info)
    assert any("verified Range of Application" in item.value for item in app.caption)
    assert not app.dataframe
    app.session_state["employer_psf_evidence"] = True
    app.run(timeout=30)
    assert not app.exception and len(app.dataframe) == 2
    insight = next(item.proto.body for item in app.get("html") if 'aria-label="Alignment Insight"' in item.proto.body)
    assert "partially aligned: 2 (50.0%)" in insight
    assert "aligned: 1 (25.0%)" in insight and "not mapped: 1 (25.0%)" in insight
    assert "4 displayed phrase–competency evidence groups" in insight
    pd.testing.assert_frame_equal(tables["alignment_results"], before)


@pytest.mark.parametrize("order", ["Framework order", "Highest demand", "Alphabetical"])
def test_psf_mapping_maximum_ties_keep_reference_colors_in_every_order(monkeypatch, order):
    frame = pd.DataFrame({"psf_competency": ["Third", "First", "Second"],
                          "job_ads": [7, 8, 8], "framework_order": [0, 1, 2]})
    before = frame.copy(deep=True)
    figures = []
    monkeypatch.setattr(ui, "chart", figures.append)
    ui.result_count_chart(frame, "psf_competency", "job_ads", "PSF-AAI competency demand",
                          order=order, highlight_max=True)
    trace = figures[0].data[0]
    assert dict(zip(trace.y, trace.marker.color)) == {
        "Third": "#958277", "First": "#99043B", "Second": "#99043B",
    }
    assert dict(zip(trace.y, trace.x)) == {"Third": 7, "First": 8, "Second": 8}
    pd.testing.assert_frame_equal(frame, before)


def test_psf_insight_and_highlights_follow_visible_bars_not_hidden_maximum(monkeypatch):
    frame = pd.DataFrame({"psf_competency": ["Lower", "Leader A", "Leader B", "Hidden"],
                          "job_ads": [3, 8, 8, 99], "framework_order": [0, 1, 2, 3]})
    monkeypatch.setattr(ui, "chart", Mock())
    rendered = Mock()
    monkeypatch.setattr(ui.st, "html", rendered)
    figure = ui.result_count_chart(frame, "psf_competency", "job_ads", "PSF demand",
                                   order="Framework order", limit=3, highlight_max=True)
    assert list(figure.data[0].marker.color) == ["#958277", "#99043B", "#99043B"]
    ui.psf_competency_demand_insight(figure, 4)
    content = rendered.call_args.args[0]
    assert "Leader A, Leader B" in content and "8 distinct advertisements" in content
    assert "3 of 4 competencies" in content
    assert "Lowest shown: Lower (3 ads each)" in content
    assert "Hidden" not in content and "99" not in content
    changed = frame.assign(job_ads=[6, 2, 2, 99])
    figure = ui.result_count_chart(changed, "psf_competency", "job_ads", "PSF demand",
                                   order="Framework order", limit=3, highlight_max=True)
    ui.psf_competency_demand_insight(figure, 4)
    updated = rendered.call_args.args[0]
    assert "Lower has the highest displayed count" in updated and "6 distinct advertisements" in updated
    assert updated != content


def test_psf_insight_reports_equal_counts_without_claiming_a_leader(monkeypatch):
    frame = pd.DataFrame({"name": ["A", "B"], "ads": [4, 4]})
    figure = ranked_bar(frame, "name", "ads", "Synthetic demand")
    rendered = Mock()
    monkeypatch.setattr(ui.st, "html", rendered)
    ui.psf_competency_demand_insight(figure, 2)
    assert "All 2 displayed competencies have the same count: 4" in rendered.call_args.args[0]


@pytest.mark.parametrize("statuses,expected", [
    (["partially aligned"] * 3 + ["aligned"], "Partially aligned has the highest displayed count: 3 evidence groups (75.0%)"),
    (["not mapped"] * 2 + ["aligned"], "Not mapped has the highest displayed count: 2 evidence groups (66.7%)"),
    (["aligned", "not mapped"], "All 2 displayed statuses are tied at 1 evidence group each"),
    (["aligned"], "Only one status is displayed: aligned (1 evidence group)"),
])
def test_alignment_insight_tracks_status_counts_and_ties(monkeypatch, statuses, expected):
    from src.visualization import distribution
    figure = distribution(pd.DataFrame({"status": statuses}), "status", "Synthetic status")
    before = figure.to_json()
    rendered = Mock()
    monkeypatch.setattr(ui.st, "html", rendered)
    ui.alignment_status_insight(figure)
    content = rendered.call_args.args[0]
    assert expected in content
    assert "do not use distinct job advertisements" in content
    assert figure.to_json() == before


def test_alignment_insight_empty_data_has_no_invented_summary(monkeypatch):
    from src.visualization import distribution
    rendered, caption = Mock(), Mock()
    monkeypatch.setattr(ui.st, "html", rendered)
    monkeypatch.setattr(ui.st, "caption", caption)
    figure = distribution(pd.DataFrame({"status": []}), "status", "Empty status")
    ui.alignment_status_insight(figure)
    rendered.assert_not_called()
    assert "No alignment evidence groups" in caption.call_args.args[0]


def test_featured_insight_uses_visible_bars_and_changes_with_their_data():
    from streamlit.testing.v1 import AppTest
    app = AppTest.from_string('''
import streamlit as st
import pandas as pd
from src.ui import featured_result_chart, result_count_chart
frame = pd.DataFrame({"skill": ["Alpha", "Beta", "Hidden"],
                      "ads": st.session_state.get("counts", [3, 2, 99])})
featured_result_chart("skill", "ads", "Top requested skills", 100,
    lambda: result_count_chart(frame, "skill", "ads", "Synthetic demand", order="Alphabetical", limit=2),
    key="synthetic_visible")
''').run(timeout=30)
    assert not app.exception
    content = "\n".join(item.proto.body for item in app.get("html"))
    assert "Alpha has the highest displayed skill count" in content
    assert "Hidden" not in content and "99" not in content
    app.session_state["counts"] = [1, 4, 99]
    app.run(timeout=30)
    updated = "\n".join(item.proto.body for item in app.get("html"))
    assert "Beta has the highest displayed skill count" in updated
    assert "4 ads" in updated and "Hidden" not in updated


def test_report_cards_keep_downloads_deferred_and_save_a_complete_snapshot(workspace, monkeypatch):
    import json
    from streamlit.testing.v1 import AppTest
    monkeypatch.setattr(ui, "ROOT", workspace)
    excel = Mock(return_value=b"synthetic workbook")
    report = Mock(return_value=b"synthetic report draft")
    summary = Mock(return_value=b"synthetic HTML summary")
    monkeypatch.setattr(ui, "export_excel", excel)
    monkeypatch.setattr(ui, "export_research_report", report)
    monkeypatch.setattr(ui, "export_html", summary)
    downloads = Mock(wraps=ui.st.download_button)
    monkeypatch.setattr(ui.st, "download_button", downloads)
    app = AppTest.from_string('''
import pandas as pd
from src.ui import report_deliverables
report_deliverables({"cleaned_jobs": pd.DataFrame({"source_id": ["SYNTHETIC-A"]})},
                    {"research_sample": {"source_ids": ["SYNTHETIC-A"]}})
''').run(timeout=30)
    assert not app.exception
    content = "\n".join(item.proto.body for item in app.get("html"))
    assert content.count('class="fow-deliverable-icon"') == 5
    assert len(app.get("download_button")) == 4
    assert all(callable(call.args[1]) for call in downloads.call_args_list)
    assert all(call.kwargs["on_click"] == "ignore" for call in downloads.call_args_list)
    excel.assert_not_called()
    report.assert_not_called()
    summary.assert_not_called()
    app.button(key="save_report_snapshot").click().run(timeout=30)
    assert not app.exception and not app.error
    folders = list((workspace / "outputs/reports").iterdir())
    assert len(folders) == 1
    assert {path.name for path in folders[0].iterdir()} == {
        "research_results.xlsx", "philippine_job_ads_psf_aai_report.md",
        "research_summary.html", "analysis_metadata.json", "cleaned_jobs.csv",
    }
    assert (folders[0] / "research_results.xlsx").read_bytes() == b"synthetic workbook"
    assert json.loads((folders[0] / "analysis_metadata.json").read_text())["research_sample"]["source_ids"] == ["SYNTHETIC-A"]
    assert excel.call_count == report.call_count == summary.call_count == 1

def test_mapping_uses_one_chart_order_control_for_chart_and_table(monkeypatch):
    from streamlit.testing.v1 import AppTest
    tables = result_tables()
    tables['psf_competency_demand'] = pd.DataFrame({
        'psf_competency': ['Alpha', 'Zulu', 'Middle'], 'job_ad_count': [1, 3, 2]})
    tables['psf_chart_demand'] = pd.DataFrame({
        'psf_competency': ['Alpha', 'Zulu', 'Middle'], 'job_ads': [1, 3, 2],
        'framework_order': [0, 1, 2]})
    tables['psf_mapping_reviews'] = pd.DataFrame()
    figures = []
    monkeypatch.setattr(ui, 'current_analysis', lambda: True)
    monkeypatch.setattr(ui, 'filtered_bundle', lambda: (tables, {}))
    monkeypatch.setattr(ui, 'psf_mapping_review', lambda *args: None)
    monkeypatch.setattr(ui.storage, 'read_frame', lambda *args: pd.DataFrame())
    monkeypatch.setattr(ui, 'chart', figures.append)
    app = AppTest.from_string('from src.ui import research_page\nresearch_page("PSF Mapping")').run(timeout=30)
    for order, expected in [('Highest demand', ['Zulu', 'Middle', 'Alpha']),
                            ('Alphabetical', ['Alpha', 'Middle', 'Zulu'])]:
        app.selectbox(key='mapping_chart_order').set_value(order).run(timeout=30)
        assert not app.exception and not app.error
        assert sum(item.label == 'Chart order' for item in app.selectbox) == 1
        assert not any(item.label == 'Competency order' for item in app.selectbox)
        assert list(figures[-1].data[0].y) == expected
        table = next(item.value for item in app.dataframe if 'job_ad_count' in item.value)
        assert table.psf_competency.tolist() == expected
