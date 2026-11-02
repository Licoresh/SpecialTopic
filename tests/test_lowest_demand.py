"""Lowest-demand ordering uses isolated synthetic counts only."""
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from src.ui import ordered_result_table
from src import ui
from src.visualization import distribution, ranked_bar
from test_result_views import figure_with_title, result_app, result_tables


@pytest.mark.parametrize("percentage", ["job_ads_pct", "employer_demand_pct"])
def test_lowest_ranked_bars_select_smallest_counts_before_limit_and_keep_evidence(percentage):
    frame = pd.DataFrame({"skill": ["Most", "zulu", "Beta", "alpha", "Zero"],
                          "job_ads": [8, 2, 2, 2, 0], percentage: [80., 20., 20., 20., 0.]})
    original = frame.copy(deep=True)
    figure = ranked_bar(frame, "skill", "job_ads", "Synthetic demand", order="Lowest demand", limit=3)
    trace = figure.data[0]
    assert list(trace.y) == ["Zero", "alpha", "Beta"]
    assert list(trace.x) == [0, 2, 2]
    assert [float(row[1]) for row in trace.customdata] == [0., 20., 20.]
    assert "%{customdata[1]:.1f}%" in trace.hovertemplate
    assert "%{x:,d}" in trace.hovertemplate
    assert figure.layout.yaxis.autorange == "reversed"
    pd.testing.assert_frame_equal(frame, original)


def test_lowest_distribution_orders_actual_counts_and_breaks_ties_alphabetically():
    frame = pd.DataFrame({"skill": ["Most"] * 8 + ["zulu"] * 2 + ["Beta"] * 2 + ["alpha"] * 2})
    original = frame.copy(deep=True)
    figure = distribution(frame, "skill", "Synthetic frequency", order="Lowest demand", limit=2)
    trace = figure.data[0]
    assert list(trace.y) == ["alpha", "Beta"]
    assert list(trace.x) == [2, 2]
    assert [row[0] for row in trace.customdata] == ["alpha", "Beta"]
    assert "%{x:,d}" in trace.hovertemplate
    pd.testing.assert_frame_equal(frame, original)


def test_lowest_status_distribution_keeps_status_color_identity():
    frame = pd.DataFrame({"status": ["ALIGNED"] * 4 + ["PARTIALLY ALIGNED"] * 2 + ["NOT MAPPED"]})
    ascending = distribution(frame, "status", "Synthetic status", order="Lowest demand")
    descending = distribution(frame, "status", "Synthetic status", order="Highest demand")
    assert list(ascending.data[0].y) == ["NOT MAPPED", "PARTIALLY ALIGNED", "ALIGNED"]
    assert list(ascending.data[0].x) == [1, 2, 4]
    assert dict(zip(ascending.data[0].y, ascending.data[0].marker.color)) == dict(
        zip(descending.data[0].y, descending.data[0].marker.color))


def test_lowest_evidence_table_uses_numeric_counts_and_stable_label_ties():
    frame = pd.DataFrame({"skill": ["Most", "zulu", "Beta", "alpha", "Zero"],
                          "job_ads": [12, 2, 2, 2, 0], "source_note": ["SYNTHETIC"] * 5})
    original = frame.copy(deep=True)
    ordered = ordered_result_table(frame, "skill", "Lowest demand", "job_ads")
    assert ordered.skill.tolist() == ["Zero", "alpha", "Beta", "zulu", "Most"]
    assert ordered.job_ads.tolist() == [0, 2, 2, 2, 12]
    assert ordered.columns.tolist() == frame.columns.tolist()
    pd.testing.assert_frame_equal(frame, original)


def test_shared_chart_order_exposes_lowest_without_changing_default():
    app = AppTest.from_string("from src.ui import result_chart_options\nresult_chart_options()").run()
    assert not app.exception
    selector = app.selectbox(key="result_chart_order")
    assert selector.value == "Highest demand"
    assert set(selector.options) == {"Alphabetical", "Highest demand", "Lowest demand"}
    selector.set_value("Lowest demand").run()
    assert not app.exception
    assert app.selectbox(key="result_chart_order").value == "Lowest demand"
    assert not any("Alphabetical order supports label lookup" in item.value for item in app.caption)


def test_job_market_lowest_selection_changes_the_display_not_the_source(monkeypatch):
    tables = result_tables()
    original = tables["chart_skill_demand"].copy(deep=True)
    app, figures = result_app(monkeypatch, tables)
    app.selectbox(key="result_chart_order").set_value("Lowest demand").run(timeout=30)
    assert not app.exception and not app.error
    trace = figure_with_title(figures, "Employer-requested skills").data[0]
    assert list(trace.y) == ["c++", "collaboration", "sql"]
    assert list(trace.x) == [1, 1, 2]
    pd.testing.assert_frame_equal(tables["chart_skill_demand"], original)


@pytest.mark.parametrize("page,expected", [
    ("PSF Mapping", [1, 2, 3]),
    ("Employer–PSF Alignment", [1, 2, 3]),
    ("Unmapped / Emerging Skills", [1, 1, 2]),
])
def test_other_results_pages_apply_the_shared_lowest_order(monkeypatch, page, expected):
    tables = result_tables()
    tables["psf_competency_demand"] = pd.DataFrame({"psf_competency": ["Largest", "Smallest", "Middle"],
                                                   "job_ad_count": [3, 1, 2]})
    tables["psf_chart_demand"] = pd.DataFrame({"psf_competency": ["Largest", "Smallest", "Middle"],
                                              "job_ads": [3, 1, 2], "framework_order": [0, 1, 2]})
    tables["psf_mapping_reviews"] = pd.DataFrame()
    if page == "Employer–PSF Alignment":
        tables["alignment_results"] = pd.DataFrame({"status": ["ALIGNED"] * 3 + ["PARTIALLY ALIGNED"] * 2 + ["NOT MAPPED"]})
    else:
        tables["alignment_results"] = pd.DataFrame({"normalized_skill": ["sql", "collaboration", "c++"],
                                                    "status": ["NOT MAPPED"] * 3})
    tables["unmapped_skills"] = pd.DataFrame()
    metadata = {"settings": {"emerging_min_jobs": 2}, "rates_before_status_display_filter": {},
                "denominators": "Synthetic test evidence only"}
    figures = []
    monkeypatch.setattr(ui, "chart", figures.append)
    monkeypatch.setattr(ui, "current_analysis", lambda: True)
    monkeypatch.setattr(ui, "filtered_bundle", lambda: (tables, metadata))
    monkeypatch.setattr(ui, "psf_mapping_review", lambda *args: None)
    monkeypatch.setattr(ui.storage, "read_frame", lambda *args: pd.DataFrame())
    app = AppTest.from_string(f"from src.ui import research_page\nresearch_page({page!r})").run(timeout=30)
    assert not app.exception and not app.error
    app.selectbox(key="result_chart_order").set_value("Lowest demand").run(timeout=30)
    assert not app.exception and not app.error
    assert list(figures[-1].data[0].x) == expected

def test_psf_lowest_highlight_and_insight_follow_displayed_minimum(monkeypatch):
    from unittest.mock import Mock
    from src import ui
    frame = pd.DataFrame({'psf_competency': ['Most', 'Zulu', 'Beta', 'Alpha'],
                          'job_ads': [9, 1, 1, 3]})
    monkeypatch.setattr(ui, 'chart', Mock())
    rendered = Mock()
    monkeypatch.setattr(ui.st, 'html', rendered)
    figure = ui.result_count_chart(frame, 'psf_competency', 'job_ads', 'PSF demand',
                                   order='Lowest demand', limit=3, highlight_max=True)
    trace = figure.data[0]
    assert list(trace.y) == ['Beta', 'Zulu', 'Alpha']
    assert list(trace.marker.color) == ['#99043B', '#99043B', '#958277']
    ui.psf_competency_demand_insight(figure, 4, order='Lowest demand')
    content = rendered.call_args.args[0]
    assert 'Maroon marks the lowest displayed count' in content
    assert 'Highest shown: Alpha (3 ads each)' in content
    assert 'Lowest shown: Beta, Zulu (1 ads each)' in content
    assert 'Most' not in content
