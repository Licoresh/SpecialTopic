"""Presentation and auth regressions; synthetic data and mocked services only."""
from unittest.mock import Mock
from pathlib import Path
import tomllib
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest
from src import supabase_store as backend
from src.visualization import distribution, style_chart


def login_app():
    return AppTest.from_string("from src.auth_ui import login_page\nlogin_page()").run()


def test_compact_account_menu_keeps_identity_and_signout(monkeypatch):
    monkeypatch.setattr(backend, "configured", lambda: True)
    signout = Mock()
    monkeypatch.setattr(backend, "sign_out", signout)
    app = AppTest.from_string('''
import streamlit as st
from src.auth_ui import render_account_menu
st.session_state["supabase_user_email"] = "synthetic@example.test"
st.session_state["supabase_role"] = "admin"
render_account_menu()
''').run()
    assert not app.exception
    profile = app.get("html")[0].proto.body
    assert "synthetic@example.test" in profile and "Admin" in profile
    assert "Your account</h3>" in profile
    assert 'class="account-profile-avatar"' in profile
    assert len(app.get("divider")) == 0
    app.button(key="sign_out").click().run()
    assert not app.exception
    signout.assert_called_once()


@pytest.mark.parametrize("email,password", [("", ""), ("synthetic@example.test", ""), ("invalid", "synthetic")])
def test_login_validates_without_network(monkeypatch, email, password):
    sign_in = Mock()
    monkeypatch.setattr(backend, "sign_in", sign_in)
    app = login_app()
    app.text_input[0].set_value(email)
    app.text_input[1].set_value(password)
    app.button[0].click().run()
    assert not app.exception
    assert "email address and password" in app.error[0].value
    sign_in.assert_not_called()


def test_login_failure_restores_form_and_hides_network_details(monkeypatch):
    monkeypatch.setattr(backend, "sign_in", Mock(side_effect=backend.SupabaseError("Internal network detail SYNTHETIC-SECRET")))
    app = login_app()
    app.text_input[0].set_value("synthetic@example.test")
    app.text_input[1].set_value("synthetic")
    app.button[0].click().run()
    assert not app.exception
    assert "Could not sign in" in app.error[0].value
    assert "SYNTHETIC-SECRET" not in app.error[0].value
    assert not app.button[0].disabled
    assert not any(field.disabled for field in app.text_input)
    assert "supabase_access_token" not in app.session_state


def test_busy_login_disables_all_controls():
    app = AppTest.from_string("from src.auth_ui import _login_panel\n_login_panel(busy=True)").run()
    assert not app.exception
    assert all(item.disabled for item in app.text_input)
    assert app.button[0].disabled


def test_successful_login_still_requires_membership(monkeypatch):
    session = {"access_token":"synthetic-token", "refresh_token":"synthetic-refresh",
               "user":{"email":"synthetic@example.test"}, "expires_in":3600}
    monkeypatch.setattr(backend, "sign_in", Mock(return_value=session))
    membership = Mock(return_value="reviewer")
    monkeypatch.setattr(backend, "check_connection", membership)
    app = AppTest.from_string("""
import streamlit as st
from src.auth_ui import login_page
if not st.session_state.get('supabase_access_token'):
    login_page()
else:
    st.success('Synthetic authorized workspace')
""").run()
    app.text_input[0].set_value("synthetic@example.test")
    app.text_input[1].set_value("synthetic")
    app.button[0].click().run()
    assert not app.exception and not app.error
    membership.assert_called_once_with("synthetic-token")
    assert app.session_state["supabase_role"] == "reviewer"
    assert app.session_state["supabase_refresh_token"] == "synthetic-refresh"


def test_chart_redesign_preserves_counts_and_original_categories():
    name = "A deliberately long competency name with detailed source terminology"
    frame = pd.DataFrame({"category":[name,name,"SQL",""]})
    before = frame.copy(deep=True)
    figure = distribution(frame, "category", "Synthetic demand")
    values = dict(zip(figure.data[0].y, figure.data[0].x))
    assert values == {name:2, "SQL":1}
    trace = figure.data[0].to_json()
    style_chart(figure)
    assert figure.data[0].to_json() == trace
    assert "<br>" in figure.layout.yaxis.ticktext[0]
    pd.testing.assert_frame_equal(frame, before)


def test_theme_primary_button_meets_text_contrast():
    theme = tomllib.loads((Path(__file__).resolve().parents[1]/".streamlit/config.toml").read_text())["theme"]
    def luminance(color):
        rgb = [int(color[index:index+2],16)/255 for index in (1,3,5)]
        rgb = [value/12.92 if value <= .04045 else ((value+.055)/1.055)**2.4 for value in rgb]
        return sum(value*weight for value,weight in zip(rgb,(.2126,.7152,.0722)))
    assert 1.05/(luminance(theme["primaryColor"])+.05) >= 4.5
    assert (luminance(theme["backgroundColor"])+.05)/(luminance(theme["textColor"])+.05) >= 4.5


def test_main_content_preserves_native_toolbar_clearance_at_all_breakpoints():
    import re
    from src.design import CSS
    rules = re.findall(r"\.stMainBlockContainer\s*\{([^}]+)\}", CSS)
    assert rules
    for rule in rules:
        assert not re.search(r"\bpadding(?:-top|-block|-block-start)?\s*:", rule)
        assert "padding-inline:" in rule


def test_review_fullscreen_styles_are_scoped_and_reversible():
    from unittest.mock import patch
    from src.design import review_workspace_style
    with patch("src.design.st.html") as html:
        review_workspace_style(True)
        expanded = html.call_args.args[0]
        assert "position: fixed" in expanded and "overflow: auto" in expanded
        assert ".st-key-manual_review_workspace" in expanded
        assert ':has(> .st-key-manual_review_actions)' in expanded
        review_workspace_style(False)
        normal = html.call_args.args[0]
        assert "position: fixed" not in normal
        assert "visibility: hidden" not in normal


@pytest.mark.parametrize("foreground,background", [
    ("#FFFFFF", "#173B38"), ("#BDE3D8", "#173B38"),
    ("#173B38", "#F1F8F5"), ("#52666B", "#F5F7F8"),
    ("#11695F", "#FFFFFF"),
])
def test_product_design_text_pairs_meet_aa_contrast(foreground, background):
    def luminance(color):
        rgb = [int(color[index:index + 2], 16) / 255 for index in (1, 3, 5)]
        linear = [value / 12.92 if value <= .04045 else ((value + .055) / 1.055) ** 2.4 for value in rgb]
        return sum(value * weight for value, weight in zip(linear, (.2126, .7152, .0722)))
    light, dark = sorted((luminance(foreground), luminance(background)), reverse=True)
    assert (light + .05) / (dark + .05) >= 4.5


def test_plotly_measurement_node_has_no_size_adding_decoration():
    import re
    from src.design import CSS
    rules = re.findall(r'\[data-testid="stPlotlyChart"\]\s*\{([^}]+)\}', CSS)
    assert rules
    assert all("padding: 0;" in rule and "border: 0;" in rule for rule in rules)
    assert "box-shadow: inset" in rules[0]


def test_overview_metric_icons_use_shared_semantic_palette():
    from unittest.mock import patch
    from src.design import CSS, apply_design
    assert ".st-key-overview_metrics [data-testid=\"stMetricIcon\"]" in CSS
    for selector in (
        ".st-key-overview_metric_1 [data-testid=\"stMetricIcon\"]",
        ".st-key-overview_metric_2 [data-testid=\"stMetricIcon\"]",
        ".st-key-overview_metric_3 [data-testid=\"stMetricIcon\"]",
        ".st-key-overview_metric_4_ready [data-testid=\"stMetricIcon\"]",
        ".st-key-overview_metric_4_pending [data-testid=\"stMetricIcon\"]",
    ):
        assert selector in CSS
    assert ".st-key-result_metric_2 [data-testid=\"stMetricIcon\"] { background: var(--fow-info-bg); color: var(--fow-info); }" in CSS
    with patch("src.design.st.html") as html:
        apply_design()
    theme_css = html.call_args_list[0].args[0]
    assert "--fow-accent-bg:#E8F4EE" in theme_css
    assert "--fow-info-bg:#EDF4FD" in theme_css
    assert "--fow-review-bg:#FFF3E8" in theme_css
    assert "--fow-framework-bg:#F2EDFA" in theme_css


def test_narrow_horizontal_workspaces_wrap_before_clipping_content():
    from src.design import CSS
    assert "@media (max-width: 900px)" in CSS
    for key in ("overview_metrics", "result_metrics", "analysis_pipeline", "workflow_0", "workflow_3"):
        assert f".st-key-{key}" in CSS
    assert "flex-wrap: wrap" in CSS
    assert "width: auto !important; min-width: min(100%, 220px); flex: 1 1 220px;" in CSS


def test_result_hover_is_explicit_readable_wrapped_and_preserves_counts():
    from src.visualization import bar
    label = "Senior Business Intelligence and Data Visualization Analyst <Research & Test>"
    frame = pd.DataFrame({"job_title": [label], "job_ads": [1]})
    before = frame.copy(deep=True)
    figure = style_chart(bar(frame, "job_title", "job_ads", "Synthetic job titles"))
    assert figure.data[0].x.tolist() == [label]
    assert figure.data[0].y.tolist() == [1]
    hover = figure.data[0].customdata[0][0]
    assert "<br>" in hover and "&lt;Research &amp; Test&gt;" in hover
    assert "%{y:,d}" in figure.data[0].hovertemplate
    assert figure.layout.hoverlabel.bgcolor == "#173B38"
    assert figure.layout.hoverlabel.font.color == "#FFFFFF"
    assert figure.layout.hovermode == "closest"
    pd.testing.assert_frame_equal(frame, before)
    horizontal = distribution(frame, "job_title", "Synthetic titles")
    assert horizontal.data[0].x.tolist() == [1]
    assert horizontal.data[0].y.tolist() == [label]
    assert "%{x:,d}" in horizontal.data[0].hovertemplate


def test_grouped_hover_labels_stay_with_their_trace_values():
    from src.visualization import bar
    frame = pd.DataFrame({"model": ["First", "Second", "First"], "score": [.5, .75, .9],
                          "metric": ["accuracy", "macro_f1", "macro_f1"]})
    figure = bar(frame, "model", "score", "Synthetic scores", "metric")
    for trace in figure.data:
        for model, score, custom in zip(trace.x, trace.y, trace.customdata):
            assert custom[0] == model and custom[1] == trace.name
            assert score == frame.loc[frame.model.eq(model) & frame.metric.eq(trace.name), "score"].item()
        assert "%{y:,d}" not in trace.hovertemplate


@pytest.mark.parametrize("total", [0, 1, 2, 5, 500])
def test_count_axes_have_integer_intervals_and_preserve_values(total):
    from src.visualization import bar, heatmap, count_axis
    frame = pd.DataFrame({"job_title": ["Synthetic role"], "job_ads": [total]})
    vertical = bar(frame, "job_title", "job_ads", "Synthetic jobs")
    horizontal = distribution(pd.DataFrame({"skill": ["SQL"] * max(1, total)}), "skill", "Synthetic skill counts")
    matrix = pd.DataFrame([[total]], index=["SQL"], columns=["Synthetic role"])
    heat = heatmap(matrix, "Synthetic count matrix")
    for axis in (vertical.layout.yaxis, horizontal.layout.xaxis, heat.layout.coloraxis.colorbar):
        assert axis.tickmode == "linear" and axis.tick0 == 0
        assert axis.dtick >= 1 and float(axis.dtick).is_integer()
        assert axis.tickformat == ",d"
    assert vertical.data[0].y.tolist() == [total]
    assert heat.data[0].z[0][0] == total
    assert count_axis(total)["dtick"] >= 1
    scores = bar(pd.DataFrame({"model": ["Synthetic"], "score": [.5]}), "model", "score", "Scores")
    assert scores.layout.yaxis.dtick is None


def test_ranked_bars_sort_aggregate_counts_after_selection_and_preserve_inputs():
    from src.visualization import ranked_bar
    frame = pd.DataFrame({"skill": ["zebra", "Beta", "alpha"], "job_ads": [1, 4, 4], "job_ads_pct": [10., 40., 40.]})
    before = frame.copy(deep=True)
    figure = ranked_bar(frame, "skill", "job_ads", "Synthetic demand", limit=2)
    assert figure.data[0].y.tolist() == ["alpha", "Beta"]
    assert figure.data[0].x.tolist() == [4, 4]
    from src.visualization import st
    assert list(figure.data[0].marker.color) == [st.get_option("theme.primaryColor")] * 2
    assert figure.data[0].texttemplate == "%{x:,d}"
    assert figure.layout.xaxis.title.text == "Job advertisements"
    assert figure.layout.xaxis.tickformat == ",d"
    assert "%{customdata[1]:.1f}%" in figure.data[0].hovertemplate
    alphabetic = ranked_bar(frame, "skill", "job_ads", "Synthetic alphabetical", order="Alphabetical", limit=2)
    assert alphabetic.data[0].y.tolist() == ["alpha", "Beta"]
    assert list(alphabetic.data[0].marker.color) == ["#71A89E", "#71A89E"]
    pd.testing.assert_frame_equal(frame, before)


def test_ranked_bars_wrap_labels_without_truncating_or_inventing_denominators():
    from src.visualization import ranked_bar
    label = "A very long skill label needing complete display <Research & Test>"
    frame = pd.DataFrame({"skill": [label], "job_ads": [1]})
    figure = ranked_bar(frame, "skill", "job_ads", "Synthetic evidence")
    assert figure.data[0].y.tolist() == [label]
    assert "&lt;Research &amp; Test&gt;" in figure.data[0].customdata[0][0]
    assert "<br>" in figure.layout.yaxis.ticktext[0]
    assert "…" not in figure.layout.yaxis.ticktext[0]
    assert "Share of selected ads" not in figure.data[0].hovertemplate
    assert figure.data[0].cliponaxis is False


@pytest.mark.parametrize("counts", [[.5], [-1], [float("nan")], [float("inf")]])
def test_ranked_bars_reject_values_that_are_not_advertisement_counts(counts):
    from src.visualization import ranked_bar
    with pytest.raises(ValueError, match="nonnegative whole numbers"):
        ranked_bar(pd.DataFrame({"skill": ["Synthetic"], "job_ads": counts}), "skill", "job_ads", "Synthetic")


def test_heatmap_labels_and_units_are_readable_without_losing_cells():
    from src.visualization import heatmap
    matrix = pd.DataFrame([[1, 2], [3, 4]], index=["SQL", "communication"], columns=["Analyst", "Engineer"])
    matrix.index.name = "skill_phrase"
    matrix.columns.name = "job_title"
    before = matrix.copy(deep=True)
    figure = heatmap(matrix, "Synthetic role skills", count_label="Job advertisements")
    assert figure.data[0].z.tolist() == [[1, 2], [3, 4]]
    assert figure.layout.xaxis.title.text == "Job title"
    assert figure.layout.yaxis.title.text == "Skill phrase"
    assert "Job advertisements: %{z:,d}" in figure.data[0].hovertemplate
    assert figure.layout.coloraxis.colorbar.title.text == "Job advertisements"
    assert figure.layout.xaxis.type == "category" and figure.layout.yaxis.type == "category"
    pd.testing.assert_frame_equal(matrix, before)


def test_heatmap_title_and_long_category_labels_have_separate_space():
    from src.visualization import heatmap, style_chart
    columns = ["A long requested skill label " + str(index) for index in range(12)]
    matrix = pd.DataFrame([[index for index in range(12)] for _ in range(5)],
                          index=[f"family {index}" for index in range(5)], columns=columns)
    before = matrix.copy(deep=True)
    figure = style_chart(heatmap(matrix, "Top requested skills by occupational family"))
    assert figure.layout.xaxis.side == "bottom"
    assert figure.layout.xaxis.tickangle == -45
    assert figure.layout.margin.t >= 65 and figure.layout.margin.b >= 135
    assert figure.layout.height >= 440
    pd.testing.assert_frame_equal(matrix, before)


def test_role_family_heatmap_uses_within_role_share_and_keeps_counts():
    from src.visualization import heatmap
    counts = pd.DataFrame([[25, 75], [5, 5]], index=["Analyst", "Engineer"], columns=["Analytics", "Engineering"])
    shares = pd.DataFrame([[25, 75], [50, 50]], index=counts.index, columns=counts.columns)
    totals = pd.Series([100, 10], index=counts.index)
    figure = heatmap(counts, "Synthetic role-family shares", count_label="Job advertisements",
                     share_matrix=shares, row_denominators=totals, share_label="Share within role",
                     denominator_label="All-family role total")
    trace = figure.data[0]
    colorbar = figure.layout.coloraxis.colorbar
    assert trace.z.tolist() == [[25, 75], [50, 50]]
    assert trace.customdata[0][0] == ["Analyst", "Analytics", 25, 25.0, 100]
    assert "Job advertisements: %{customdata[2]:,d}" in trace.hovertemplate
    assert "Share within role: %{customdata[3]:.1f}%" in trace.hovertemplate
    assert "All-family role total: %{customdata[4]:,d}" in trace.hovertemplate
    assert colorbar.title.text == "Share within role"
    assert colorbar.tickmode == "linear" and colorbar.tick0 == 0 and colorbar.dtick == 20
    assert colorbar.ticksuffix == "%" and figure.layout.coloraxis.cmin == 0 and figure.layout.coloraxis.cmax == 100


def test_heatmap_default_units_do_not_mislabel_model_evaluation_as_job_ads():
    from src.visualization import heatmap
    matrix = pd.DataFrame([[1]], index=["<actual>"], columns=["<predicted>"])
    figure = heatmap(matrix, "Synthetic confusion matrix")
    assert figure.layout.coloraxis.colorbar.title.text == "Count"
    assert "Job advertisements" not in figure.data[0].hovertemplate
    assert figure.data[0].customdata[0][0][0] == "&lt;actual&gt;"
    assert figure.data[0].customdata[0][0][1] == "&lt;predicted&gt;"


def test_education_chart_is_horizontal_and_preserves_natural_progression():
    from src.visualization import education_bar
    frame = pd.DataFrame({"education_level": ["bachelor's degree", "high school", "master's degree"],
                          "job_ads": [12, 4, 2], "job_ads_pct": [60., 20., 10.],
                          "level_order": [4, 0, 5]})
    figure = education_bar(frame)
    assert figure.data[0].orientation == "h"
    assert figure.data[0].y.tolist() == ["high school", "bachelor's degree", "master's degree"]
    assert figure.data[0].x.tolist() == [4, 12, 2]
    assert figure.layout.xaxis.title.text == "Job advertisements"


def test_ranked_bars_allow_room_for_full_multiline_labels_without_grid_clutter():
    from src.visualization import ranked_bar
    short = pd.DataFrame({"skill": [f"Skill {index}" for index in range(5)], "job_ads": [1] * 5})
    long = short.copy()
    long.loc[0, "skill"] = "An intentionally extensive competency statement with several clauses requiring more than three complete wrapped label lines for readable presentation"
    ordinary = ranked_bar(short, "skill", "job_ads", "Synthetic compact labels")
    expanded = ranked_bar(long, "skill", "job_ads", "Synthetic full labels")
    max_lines = max(value.count("<br>") + 1 for value in expanded.layout.yaxis.ticktext)
    assert max_lines > 3
    assert expanded.layout.height >= 115 + (18 * max_lines + 16) * len(long)
    assert expanded.layout.height > ordinary.layout.height
    assert expanded.layout.xaxis.showgrid is False and expanded.layout.yaxis.showgrid is False
    assert expanded.layout.xaxis.showticklabels is not False
    assert expanded.data[0].x.tolist() == [1] * 5
    assert set(expanded.data[0].y) == set(long.skill)


def test_distribution_order_is_deterministic_before_limiting_and_keeps_label_case():
    frame = pd.DataFrame({"category": ["Zebra", "Beta", "alpha", "Zebra", "Beta", "alpha", "Zulu"]})
    before = frame.copy(deep=True)
    ranked = distribution(frame, "category", "Synthetic ranked", limit=2)
    assert ranked.data[0].y.tolist() == ["alpha", "Beta"]
    assert ranked.data[0].x.tolist() == [2, 2]
    alphabetical = distribution(frame, "category", "Synthetic alphabetical", limit=3, order="Alphabetical")
    assert alphabetical.data[0].y.tolist() == ["alpha", "Beta", "Zebra"]
    assert alphabetical.layout.xaxis.tickformat == ",d"
    assert ranked.layout.yaxis.autorange == "reversed"
    pd.testing.assert_frame_equal(frame, before)
