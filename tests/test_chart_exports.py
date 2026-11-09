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
    fig.update_layout(paper_bgcolor="#FAF5EF", plot_bgcolor="#FAF5EF")
    before = fig.to_json()
    result = chart_exports.chart_table(fig)
    assert result.to_dict("records") == [
        {"Series": "data analyst", "Posting month": "2026-01", "Job advertisements": 2},
        {"Series": "data analyst", "Posting month": "2026-02", "Job advertisements": 3},
    ]
    html = chart_exports.chart_html(fig, "Job-title timeline")
    assert "Job-title timeline" in html and "Plotly.addFrames" in html
    assert '"paper_bgcolor":"#FAF5EF"' in html and '"plot_bgcolor":"#FAF5EF"' in html
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


def test_section_download_keeps_both_graphs_and_their_counts():
    figures = {"Location": go.Figure(go.Bar(x=[11, 2], y=["region a", "region b"], orientation="h")),
               "Skills": go.Figure(go.Bar(x=[6, 3], y=["sql", "python"], orientation="h"))}
    data = chart_exports.chart_group_data(figures)
    assert data.groupby("Graph").Value.sum().to_dict() == {"Location": 13, "Skills": 9}
    html = chart_exports.chart_group_html(figures, "Geography <selection>")
    assert html.count('class="plotly-graph-div"') == 2
    assert "Geography &lt;selection&gt;" in html


def test_chart_evidence_is_lazy_inside_card_and_tracks_filters():
    from streamlit.testing.v1 import AppTest

    source = '''
import pandas as pd
import streamlit as st
from src.ui import chart, featured_visual_chart
from src.visualization import ranked_bar
st.session_state["_fow_current_page"] = "Job Market Analysis"
selected = st.selectbox("Category selection", ["All", "python"])
rows = pd.DataFrame({"skill": ["sql", "python"], "ads": [2, 1], "job_ads_pct": [50., 25.]})
if selected != "All":
    rows = rows[rows.skill.eq(selected)]
featured_visual_chart(lambda: chart(ranked_bar(rows, "skill", "ads", "Selected skills"), key="evidence_bar"),
                      "Selected skills", [], key="evidence_demo", heading="Selected skills")
'''
    app = AppTest.from_string(source).run(timeout=30)
    assert not app.exception
    assert not app.dataframe
    card = app.get_by_key("job_market_featured_evidence_demo")
    assert any(panel.label == "View chart evidence" for panel in card.expander)
    app.session_state["chart_evidence_evidence_bar"] = True
    app.run(timeout=30)
    assert not app.exception
    table = app.get_by_key("job_market_featured_evidence_demo").dataframe[0].value
    assert table.columns.tolist() == ["Category", "Job advertisements", "Share of selected ads (%)"]
    assert table.to_dict("records") == [
        {"Category": "sql", "Job advertisements": 2, "Share of selected ads (%)": 50.},
        {"Category": "python", "Job advertisements": 1, "Share of selected ads (%)": 25.},
    ]
    app.selectbox[0].set_value("python")
    # AppTest does not serialize expander widget state on other widget events.
    app.session_state["chart_evidence_evidence_bar"] = True
    app.run(timeout=30)
    assert not app.exception
    assert app.dataframe[0].value.Category.tolist() == ["python"]
    app.session_state["chart_evidence_evidence_bar"] = False
    app.run(timeout=30)
    assert not app.exception and not app.dataframe


def test_heatmap_evidence_pages_cells_and_preserves_counts_and_shares():
    from streamlit.testing.v1 import AppTest

    source = '''
import pandas as pd
import streamlit as st
from src.ui import chart
from src.visualization import heatmap
st.session_state["_fow_current_page"] = "Job Market Analysis"
counts = pd.DataFrame(2, index=[f"Family {i}" for i in range(12)], columns=[f"Skill {i}" for i in range(10)])
counts.index.name, counts.columns.name = "family", "skill"
chart(heatmap(counts, "Skill comparison", share_matrix=counts * 10,
              row_denominators=pd.Series(10, index=counts.index),
              count_label="Job advertisements"), key="evidence_matrix")
'''
    app = AppTest.from_string(source).run(timeout=30)
    assert not app.exception and not app.dataframe
    app.session_state["chart_evidence_evidence_matrix"] = True
    app.run(timeout=30)
    assert not app.exception
    table = app.dataframe[0].value
    assert len(table) == 100
    assert table["Job advertisements"].eq(2).all()
    assert table["Share within row group (%)"].eq(20).all()
    app.number_input(key="chart_evidence_page_evidence_matrix").set_value(2)
    app.session_state["chart_evidence_evidence_matrix"] = True
    app.run(timeout=30)
    assert not app.exception and len(app.dataframe[0].value) == 20
