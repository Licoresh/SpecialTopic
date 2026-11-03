from contextlib import nullcontext
from io import BytesIO

import pandas as pd
import plotly.graph_objects as go

from src import chart_exports


def test_bar_download_uses_displayed_counts_and_hover_percentages():
    fig = go.Figure(go.Bar(x=[8, 7], y=["communication", "sql"], orientation="h",
                          customdata=[["communication", 40.0], ["sql", 35.0]],
                          hovertemplate="<b>%{customdata[0]}</b><br>Share of selected ads: %{customdata[1]:.1f}%"))
    fig.update_xaxes(title="Job advertisements")
    result = chart_exports.chart_table(fig)
    assert result.to_dict("records") == [
        {"Job advertisements": 8, "Category": "communication", "Share of selected ads": 40.0},
        {"Job advertisements": 7, "Category": "sql", "Share of selected ads": 35.0},
    ]


def test_heatmap_download_preserves_zero_cells_counts_and_denominators():
    fig = go.Figure(go.Heatmap(x=["sql", "python"], y=["analyst"], z=[[50., 0.]],
                              customdata=[[["analyst", "sql", 2, 50., 4], ["analyst", "python", 0, 0., 4]]],
                              hovertemplate="Job advertisements: %{customdata[2]}<br>Share of role ads: %{customdata[3]}<br>Role advertisements: %{customdata[4]}"))
    fig.update_xaxes(title="Skill")
    fig.update_yaxes(title="Role")
    fig.update_coloraxes(colorbar_title="Share of role ads")
    result = chart_exports.chart_table(fig)
    assert result.to_dict("records") == [
        {"Role": "analyst", "Skill": "sql", "Share of role ads": 50., "Job advertisements": 2, "Role advertisements": 4},
        {"Role": "analyst", "Skill": "python", "Share of role ads": 0., "Job advertisements": 0, "Role advertisements": 4},
    ]


def test_standalone_html_retains_line_series_frames_and_title_without_mutation():
    fig = go.Figure(go.Scatter(x=["2026-01", "2026-02"], y=[2, 3], name="data analyst"),
                    frames=[go.Frame(name="2026-01", data=[go.Scatter(x=["2026-01"], y=[2])])])
    fig.update_xaxes(title="Posting month")
    fig.update_yaxes(title="Job advertisements")
    before = fig.to_json()
    result = chart_exports.chart_table(fig)
    assert result.to_dict("records") == [
        {"Series": "data analyst", "Posting month": "2026-01", "Job advertisements": 2},
        {"Series": "data analyst", "Posting month": "2026-02", "Job advertisements": 3},
    ]
    html = chart_exports.chart_html(fig, "Job-title timeline")
    assert "Job-title timeline" in html and "Plotly.addFrames" in html
    assert '<script src="' not in html
    assert fig.to_json() == before


def test_download_buttons_generate_only_on_click_and_sanitize_csv(monkeypatch):
    downloads = []
    monkeypatch.setattr(chart_exports.st, "popover", lambda *args, **kwargs: nullcontext())
    monkeypatch.setattr(chart_exports.st, "download_button", lambda *args, **kwargs: downloads.append(kwargs))
    monkeypatch.setattr(chart_exports.st, "caption", lambda *args: None)
    fig = go.Figure(go.Bar(x=[1], y=["=formula()"], orientation="h"))
    chart_exports.chart_downloads(fig, "Example / graph", key="example")
    assert all(callable(item["data"]) and item["on_click"] == "ignore" for item in downloads)
    assert [item["file_name"] for item in downloads] == ["example-graph.csv", "example-graph.html"]
    csv = downloads[0]["data"]()
    values = pd.read_csv(BytesIO(csv))
    assert values.Category.iloc[0] == "'=formula()"


def test_pie_download_keeps_category_values():
    result = chart_exports.chart_table(go.Figure(go.Pie(labels=["one", "two"], values=[5, 3])))
    assert result.to_dict("records") == [{"Category": "one", "Value": 5}, {"Category": "two", "Value": 3}]


def test_standalone_html_escapes_script_tags_in_labels():
    label = "</script><script>alert(1)</script>"
    html = chart_exports.chart_html(go.Figure(go.Bar(x=[1], y=[label])), label)
    assert label not in html
