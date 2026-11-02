"""Presentation and auth regressions; synthetic data and mocked services only."""
from unittest.mock import Mock
from pathlib import Path
import tomllib
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest
from src import supabase_store as backend
from src import design
from src.visualization import distribution, style_chart


def login_app():
    return AppTest.from_string("from src.auth_ui import login_page\nlogin_page()").run()


def test_single_education_metric_uses_maroon_value():
    assert '.st-key-job_market_education [data-testid="stMetricValue"] { color: #86142D; }' in design.CSS


def test_compact_account_menu_keeps_identity_and_signout(monkeypatch):
    monkeypatch.setattr(backend, "configured", lambda: True)
    signout = Mock()
    monkeypatch.setattr(backend, "sign_out", signout)
    app = AppTest.from_string('''
import streamlit as st
from src.auth_ui import render_account_menu
st.session_state["supabase_user_email"] = "synthetic@example.test"
st.session_state["supabase_role"] = "admin"
with st.container(horizontal=True, key="workspace_toolbar"):
    st.caption("Synthetic workspace")
    render_account_menu()
''').run()
    assert not app.exception
    trigger = app.get("popover")[0].proto.popover
    assert trigger.label == "Account" and not trigger.disabled
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


@pytest.mark.parametrize("status,expected", [(503, "Connection issue"), (403, "Workspace access"), (404, "Workspace setup")])
def test_unavailable_screen_keeps_error_escaped_and_offers_recovery(monkeypatch, status, expected):
    clear_cache, sign_out = Mock(), Mock()
    monkeypatch.setattr(backend, "clear_read_cache", clear_cache)
    monkeypatch.setattr(backend, "sign_out", sign_out)
    app = AppTest.from_string(
        'from src.auth_ui import _workspace_unavailable\n'
        'from src.supabase_store import SupabaseError\n'
        f'_workspace_unavailable(SupabaseError("Synthetic <script>unsafe</script> interruption", status_code={status}))'
    ).run()
    assert not app.exception
    content = " ".join(item.proto.body for item in app.get("html"))
    assert expected in content and "&lt;script&gt;unsafe&lt;/script&gt;" in content
    assert "<script>unsafe</script>" not in content
    assert app.title[0].value == "Workspace unavailable"
    assert len(app.get("image")) == 1
    assert not app.sidebar.button
    clear_cache.assert_not_called()
    sign_out.assert_not_called()


def test_unavailable_retry_and_signin_actions_do_not_approve_workspace_access(monkeypatch):
    clear_cache, sign_out = Mock(), Mock()
    monkeypatch.setattr(backend, "clear_read_cache", clear_cache)
    monkeypatch.setattr(backend, "sign_out", sign_out)
    # After either action reruns, replace the test screen to avoid repeating a click.
    app = AppTest.from_string('''
import streamlit as st
from src.auth_ui import _workspace_unavailable
from src.supabase_store import SupabaseError
if st.session_state.get('_fow_recent_actions'):
    st.info('Synthetic rerun reached; workspace remains unapproved')
else:
    _workspace_unavailable(SupabaseError('Synthetic interruption', status_code=503))
''').run()
    app.button[0].click().run()
    assert not app.exception
    clear_cache.assert_called_once()
    sign_out.assert_not_called()
    app = AppTest.from_string('''
import streamlit as st
from src.auth_ui import _workspace_unavailable
from src.supabase_store import SupabaseError
if st.session_state.get('_fow_recent_actions'):
    st.info('Synthetic rerun reached; workspace remains unapproved')
else:
    _workspace_unavailable(SupabaseError('Synthetic interruption', status_code=503))
''').run()
    app.button[1].click().run()
    assert not app.exception
    sign_out.assert_called_once()


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


def test_shared_visual_direction_is_present_in_theme_css():
    from src.design import CSS, JOB_MARKET_CSS, SIDEBAR_CSS
    root = Path(__file__).resolve().parents[1]
    theme = tomllib.loads((root/".streamlit/config.toml").read_text())["theme"]
    assert theme["primaryColor"] == "#78182B"
    assert theme["chartCategoricalColors"][:2] == ["#78182B", "#D6A33D"]
    assert theme["backgroundColor"] == "#FBF8F4"
    assert theme["orangeColor"] != theme["violetColor"]
    assert theme["orangeTextColor"] != theme["violetTextColor"]
    assert "width: 100%; max-width: none;" in CSS
    assert "--fow-control-height: 44px" in CSS
    assert "min-height: 185px" not in CSS
    assert ".st-key-job_market_heading" in JOB_MARKET_CSS
    assert ".st-key-page_heading, .st-key-overview_heading, .st-key-job_market_heading" in JOB_MARKET_CSS
    assert '[data-testid="stSidebarNavLink"][aria-current="page"]' in SIDEBAR_CSS
    assert '[role="radiogroup"] > button[aria-checked="true"]' in JOB_MARKET_CSS
    root = Path(__file__).resolve().parents[1]
    assert "MSU-IIT" not in (root / "assets" / "job_market_brand.svg").read_text(encoding="utf-8")
    entry = (root / "app.py").read_text(encoding="utf-8")
    assert entry.index("apply_design()") < entry.index("require_workspace_access()") < entry.index("from src.ui import render")
    assert "apply_sidebar_branding()" in entry
    assert 'title="Job Market Analysis"' in (root / "app.py").read_text(encoding="utf-8")
    assert "max-width: none !important" in JOB_MARKET_CSS
    assert "@media" in JOB_MARKET_CSS
    assert 'body:has(.st-key-workspace_toolbar) [data-stale="true"]' in CSS
    assert '[data-testid="stSidebar"] [data-stale="true"]' in CSS


def test_sequential_chart_palette_has_supported_number_of_steps():
    root = Path(__file__).resolve().parents[1]
    theme = tomllib.loads((root/".streamlit/config.toml").read_text())["theme"]
    assert len(theme["chartSequentialColors"]) == 10


def test_pipeline_uses_independent_stage_cards_and_keeps_all_stages_readable():
    app = AppTest.from_string("from src.ui import analysis_workflow\nanalysis_workflow()").run(timeout=30)
    assert not app.exception
    visible = " ".join(item.proto.body for item in app.get("html"))
    assert 'aria-label="Analysis pipeline"' in visible
    assert "<h2>Analysis Pipeline</h2>" in visible
    assert visible.count("<li>") == 5
    for stage in ("Select job ads", "Clean and group", "Extract and review", "Compare PSF-AAI", "Describe results"):
        assert visible.count(stage) == 1
    assert "fow-pipeline-number" not in visible
    assert "Follow the steps" not in visible


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
    ("#FFFFFF", "#4D1020"), ("#F4DFAF", "#4D1020"),
    ("#4D1020", "#FBF3E1"), ("#647184", "#FBF8F4"),
    ("#78182B", "#FFFFFF"),
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
    assert ".st-key-overview_metrics [data-testid=\"stMetricLabel\"] { display: flex; align-items: center;" in CSS
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
    assert "--fow-accent-bg:#F7EDEF" in theme_css
    assert "--fow-info-bg:#EEF4FA" in theme_css
    assert "--fow-review-bg:#FBF3E1" in theme_css
    assert "--fow-framework-bg:#FBF3E1" in theme_css


def test_narrow_horizontal_workspaces_wrap_before_clipping_content():
    from src.design import CSS
    assert "@media (max-width: 900px)" in CSS
    for key in ("overview_metrics", "result_metrics", "analysis_pipeline", "workflow_0", "workflow_3"):
        assert f".st-key-{key}" in CSS
    assert "flex-wrap: wrap" in CSS
    assert "width: auto !important; min-width: min(100%, 220px); flex: 1 1 220px;" in CSS


def test_job_market_metrics_and_result_tabs_follow_reference_layout():
    from src.design import JOB_MARKET_CSS
    assert "align-items: flex-start" in JOB_MARKET_CSS
    assert ".fow-metric-badge" not in JOB_MARKET_CSS
    assert ".fow-key-insight" in JOB_MARKET_CSS
    for icon in ("work", "person_pin_circle", "school", "layers"):
        assert f'content: "{icon}"' in JOB_MARKET_CSS


def test_pipeline_and_deliverables_keep_component_alignment_and_responsive_layout():
    from src.design import JOB_MARKET_CSS, REPORTS_CSS
    assert "container: pipeline / inline-size" in JOB_MARKET_CSS
    assert ".fow-analysis-pipeline li > div { min-width: 0; }" in JOB_MARKET_CSS
    for size in (950, 620, 380):
        assert f"@container pipeline (max-width: {size}px)" in JOB_MARKET_CSS
    assert ".st-key-reports_deliverables_grid" in REPORTS_CSS
    assert "grid-auto-rows: 1fr" in REPORTS_CSS
    assert "margin-top: auto; width: 100%" in REPORTS_CSS
    assert ".st-key-report_deliverable_excel { border-color: var(--fow-accent)" in REPORTS_CSS
    assert "min-height: 44px" in REPORTS_CSS
    for size in (1200, 850, 550):
        assert f"@media (max-width: {size}px)" in REPORTS_CSS


def test_loading_shapes_are_scoped_responsive_and_respect_reduced_motion():
    from src.design import LOADING_CSS, JOB_MARKET_CSS
    for kind in ("metrics", "results", "review", "reports", "cards", "selector", "form", "document", "table"):
        assert f".fow-loading--{kind}" in LOADING_CSS
    for shape in ("line", "icon", "card", "chart", "table", "toolbar", "row", "grid", "insight", "heading", "field", "control", "document", "matrix", "cell"):
        assert f".fow-skeleton-{shape}" in LOADING_CSS
    assert ".fow-loading--reports > :is(.fow-skeleton-toolbar,.fow-skeleton-heading) { grid-column: 1 / -1; }" in LOADING_CSS
    assert "grid-auto-flow: column" in LOADING_CSS
    assert "repeat(var(--fow-skeleton-cards,4),minmax(0,1fr))" in LOADING_CSS
    assert "grid-auto-columns: minmax(100px,1fr)" in LOADING_CSS
    assert ".fow-skeleton-matrix > .fow-skeleton-row { grid-auto-columns: 38px;" in LOADING_CSS
    assert "@media (prefers-reduced-motion: reduce)" in LOADING_CSS
    assert "animation: none; opacity: 1" in LOADING_CSS
    assert "position: fixed" not in LOADING_CSS and "backdrop-filter" not in LOADING_CSS
    assert ".st-key-result_chart_note > * { grid-column: 2; min-width: 0; }" in JOB_MARKET_CSS
    assert 'font: 18px/1 "Material Symbols Rounded"' in JOB_MARKET_CSS


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
    assert figure.layout.hoverlabel.bgcolor == "#4D1020"
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
    assert list(alphabetic.data[0].marker.color) == ["#96857A", "#96857A"]
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


def test_transposed_heatmap_keeps_group_denominators_and_readable_axes():
    from src.visualization import heatmap
    counts = pd.DataFrame([[25, 75], [5, 5]], index=["Analyst", "Engineer"], columns=["SQL", "communication and stakeholder management"])
    counts.index.name = "occupational_family"
    counts.columns.name = "skill_label"
    shares = pd.DataFrame([[25, 75], [50, 50]], index=counts.index, columns=counts.columns)
    totals = pd.Series([100, 10], index=counts.index)
    figure = heatmap(counts, "Synthetic skill-family shares", share_matrix=shares,
                     row_denominators=totals, share_label="Share of family ads",
                     denominator_label="Advertisements in family", transpose=True)
    trace = figure.data[0]
    assert trace.y.tolist() == counts.columns.tolist()
    assert trace.x.tolist() == counts.index.tolist()
    assert trace.z.tolist() == [[25.0, 50.0], [75.0, 50.0]]
    assert trace.customdata[0][1] == ["SQL", "Engineer", 5, 50.0, 10]
    assert figure.layout.xaxis.tickangle == 0
    assert figure.layout.xaxis.title.text == "Occupational family"
    assert figure.layout.yaxis.title.text == "Skill label"
    assert "<br>" in figure.layout.yaxis.ticktext[1]


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


def test_preparation_content_and_sidebar_controls_share_workspace_geometry():
    from src.design import WORKSPACE_CONTENT_CSS, JOB_MARKET_CSS
    assert '[class*="st-key-workspace_page_"]' in WORKSPACE_CONTENT_CSS
    assert '.st-key-upload_file_panel' in WORKSPACE_CONTENT_CSS
    assert '.st-key-training_options_panel' in WORKSPACE_CONTENT_CSS
    assert '[data-testid="stExpandSidebarButton"]' in WORKSPACE_CONTENT_CSS
    assert 'padding-left: 54px' in WORKSPACE_CONTENT_CSS
    assert 'grid-template-columns: minmax(0,1fr) 44px' in WORKSPACE_CONTENT_CSS
    assert 'data-fow-psf-ready' not in WORKSPACE_CONTENT_CSS
    assert '.st-key-job_market_psf_charts:has(.fow-loading) .st-key-job_market_psf_charts_body' in JOB_MARKET_CSS
    assert '[class*="st-key-workspace_page_"] h3 [data-testid="stIconMaterial"] { color: #8B1630;' in WORKSPACE_CONTENT_CSS


def test_content_card_insets_cover_captions_and_blocks_without_double_padding_readiness():
    from src.design import STUDY_CONTENT_CSS
    children = '[class*="st-key-content_panel_"] > :is([data-testid="stLayoutWrapper"],[data-testid="stElementContainer"])'
    assert children + ':not(:first-child) { margin-inline: 1rem; width: calc(100% - 2rem)' in STUDY_CONTENT_CSS
    assert children + ':not(:first-child) { margin-inline: .8rem; width: calc(100% - 1.6rem)' in STUDY_CONTENT_CSS
    assert children + ':last-child { margin-bottom: 1rem; }' in STUDY_CONTENT_CSS
    readiness = '.st-key-workspace_page_readiness ' + children + ':nth-child(n) { margin: 0; width: 100% !important; }'
    assert STUDY_CONTENT_CSS.count(readiness) == 2
    assert '[class*="st-key-content_panel_"] { padding: 1.2rem 1.35rem !important;' in STUDY_CONTENT_CSS
    assert '[class*="st-key-content_panel_"] { padding: 1rem !important;' in STUDY_CONTENT_CSS


def test_responsive_rules_win_the_cascade_and_focus_mode_keeps_viewport_positioning(monkeypatch):
    from src import design
    from src.design import RESPONSIVE_CSS
    rendered = Mock()
    monkeypatch.setattr(design.st, "html", rendered)
    design.apply_design()
    design.review_workspace_style(True)
    markup = [call.args[0] for call in rendered.call_args_list]
    assert markup[0].endswith(RESPONSIVE_CSS + "</style>")
    assert "container: workspace / inline-size" in markup[0]
    assert "visibility: hidden; container-type: normal" in markup[-1]
    for size in (1100, 760, 480):
        assert f"@container workspace (max-width: {size}px)" in RESPONSIVE_CSS
    assert "overflow-x: auto" in RESPONSIVE_CSS
    assert 'body { overflow' not in RESPONSIVE_CSS
    assert 'font-size: 16px' in RESPONSIVE_CSS


def test_reference_content_redesign_does_not_target_workspace_chrome():
    from src.design import STUDY_CONTENT_CSS
    for selector in ('[data-testid="stHeader"]', '[data-testid="stSidebar"]',
                     '.st-key-workspace_toolbar', '.st-key-account_trigger'):
        assert selector not in STUDY_CONTENT_CSS


def test_html_hover_tracks_each_chart_without_copying_svg_or_scanning_hover_mutations():
    import shutil
    import subprocess
    from pathlib import Path
    import pytest
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required for the tooltip migration runtime test")
    script = r'''
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('src/chart_hover.js', 'utf8');
let cleaned = 0, scans = 0, measures = 0;
class Element {
  constructor() {
    this.nodeType = 1; this.namespaceURI = 'http://www.w3.org/1999/xhtml';
    this.children = []; this.dataset = {}; this.style = {}; this.attributes = {};
    this.isConnected = true; this.events = new Map();
  }
  setAttribute(key, value) {this.attributes[key] = value;}
  appendChild(node) {this.children.push(node); node.parent = this;}
  replaceChildren(...nodes) {this.children = nodes;}
  remove() {this.isConnected = false;}
  contains(node) {return node === this || this.children.some(child => child.contains?.(node));}
  matches() {return this instanceof Plot;}
  closest() {return this.chart || (this.plots ? this : null);}
  querySelectorAll() {scans += 1; return this.plots || [];}
  addEventListener(name, handler) {this.events.set(name, handler);}
  removeEventListener(name, handler) {if (this.events.get(name) === handler) this.events.delete(name);}
  getBoundingClientRect() {measures += 1; return {width: 220, height: 80};}
  set innerHTML(value) {throw Error('Tooltip content must be plain text');}
}
class Plot extends Element {
  constructor(lines) {super(); this.lines = lines; this.listeners = new Map();}
  on(name, handler) {
    if (!this.listeners.has(name)) this.listeners.set(name, new Set());
    this.listeners.get(name).add(handler);
  }
  removeListener(name, handler) {this.listeners.get(name)?.delete(handler);}
  emit(name, event) {for (const handler of this.listeners.get(name) || []) handler(event);}
  querySelectorAll(selector) {
    assert(selector.includes('.hoverlayer:not([data-fow-retained-hover])'));
    const text = {textContent: this.lines.join(''), querySelectorAll: () => this.lines.map(textContent => ({textContent}))};
    return this.lines.length ? [{querySelector: name => name === 'text.nums' ? text : null}] : [];
  }
}
const first = new Plot(['SQL', 'Job advertisements: 3', 'Share of selected ads: 75.0%']);
const second = new Plot(['Python', 'Job advertisements: 1', 'Share of selected ads: 25.0%']);
const body = new Element();
const win = new Element();
win.innerWidth = 1000; win.innerHeight = 800;
const doc = new Element();
doc.body = body;
doc.createElement = () => new Element();
const legacy = [{removed: false, remove() {this.removed = true;}},
                {removed: false, remove() {this.removed = true;}}];
doc.querySelectorAll = selector => selector.includes('.js-plotly-plot')
  ? [first, second] : legacy.filter(node => !node.removed);
const retiredHandler = () => {};
const unrelatedHandler = () => {};
first.on('plotly_hover', retiredHandler);
first.on('plotly_hover', unrelatedHandler);
win.__fowChartHoverCleanup = () => {
  first.off?.('plotly_hover', retiredHandler);
  cleaned += 1;
};
const observers = [];
class Observer {
  constructor(callback) {this.callback = callback; observers.push(this);}
  observe() {}
  disconnect() {this.disconnected = true;}
}
const context = {
  window: win, document: doc, MutationObserver: Observer
};
vm.runInNewContext(source, context);
vm.runInNewContext(source, context); // An ordinary app rerun stays harmless.
assert.equal(cleaned, 1);
assert(legacy.every(node => node.removed));
assert.equal(body.children.length, 1);
assert.equal(observers.length, 1);
const tooltip = body.children[0];
const shown = () => tooltip.children.map(row => row.textContent);
assert.equal(tooltip.attributes.role, 'tooltip');
assert(tooltip.hidden);
first.emit('plotly_hover', {event: {clientX: 100, clientY: 200}});
assert.deepEqual(shown(), first.lines);
assert.equal(first.dataset.fowHtmlHover, 'true');
assert.equal(tooltip.style.left, '114px');
assert.equal(tooltip.style.top, '214px');
assert.equal(measures, 1);
first.events.get('pointermove')({clientX: 990, clientY: 790});
assert.equal(tooltip.style.left, '768px');
assert.equal(tooltip.style.top, '696px');
assert.equal(measures, 1); // Pointer movement does not repeatedly measure layout.
first.lines = ['Collaboration', 'Job advertisements: 2', 'Share of selected ads: 50.0%'];
first.emit('plotly_hover', {event: {clientX: 120, clientY: 220}});
assert.deepEqual(shown(), first.lines);
second.emit('plotly_hover', {event: {clientX: 300, clientY: 400}});
assert.deepEqual(shown(), second.lines);
assert.equal(shown().filter(line => line.startsWith('Share of selected ads:')).length, 1);
first.emit('plotly_unhover'); // A late event from another chart cannot close this one.
assert(!tooltip.hidden);
second.emit('plotly_unhover');
assert(tooltip.hidden);
second.lines = ['<img src=x onerror=alert(1)>', 'Count: 1'];
second.emit('plotly_hover', {event: {clientX: 300, clientY: 400}});
assert.equal(shown()[0], '<img src=x onerror=alert(1)>');
doc.events.get('keydown')({key: 'Escape'});
assert(tooltip.hidden);
second.emit('plotly_hover', {event: {clientX: 300, clientY: 400}});
win.events.get('scroll')();
assert(tooltip.hidden);
second.lines = [];
second.emit('plotly_hover', {event: {clientX: 300, clientY: 400}});
assert.equal(second.dataset.fowHtmlHover, undefined); // Native fallback stays available.
const before = scans;
observers[0].callback([{target: {namespaceURI: 'http://www.w3.org/2000/svg'}, addedNodes: [], removedNodes: []}]);
assert.equal(scans, before);
const late = new Plot(['Data analysis', 'Job advertisements: 4']);
const chart = new Element(); chart.plots = [late];
late.chart = chart;
late.on = undefined; // Plotly's lazy-loaded graph API is not ready yet.
observers[0].callback([{target: chart, addedNodes: [late], removedNodes: []}]);
assert.equal(late.listeners.size, 0);
late.on = Plot.prototype.on;
observers[0].callback([{target: chart, addedNodes: [late], removedNodes: []}]);
assert.equal(late.listeners.get('plotly_hover').size, 1);
late.emit('plotly_hover', {event: {clientX: 0, clientY: 0}});
assert.deepEqual(shown(), late.lines);
late.on = undefined; late.removeListener = undefined; // Match Plotly.purge.
observers[0].callback([{target: chart, addedNodes: [], removedNodes: []}]);
assert.equal(late.listeners.get('plotly_hover').size, 0);
assert(tooltip.hidden);
late.on = function(...args) {return Plot.prototype.on.apply(this, args);};
late.removeListener = Plot.prototype.removeListener;
observers[0].callback([{target: chart, addedNodes: [], removedNodes: []}]);
assert.equal(late.listeners.get('plotly_hover').size, 1);
late.emit('plotly_hover', {event: {clientX: 0, clientY: 0}});
assert.deepEqual(shown(), late.lines);
late.on = undefined; late.removeListener = undefined;
late.isConnected = false;
observers[0].callback([{target: body, addedNodes: [], removedNodes: [late]}]);
assert.equal(late.listeners.get('plotly_hover').size, 0);
assert(tooltip.hidden);
assert(first.listeners.get('plotly_hover').has(unrelatedHandler));
assert(!first.listeners.get('plotly_hover').has(retiredHandler));
win.__fowChartHoverCleanup();
assert(observers[0].disconnected && !tooltip.isConnected);
assert.equal(first.listeners.get('plotly_hover').size, 1); // Preserve unrelated listeners.
assert.equal(second.listeners.get('plotly_hover').size, 0);
assert.equal(first.events.size, 0);
assert.equal(win.events.size, 0);
assert.equal(doc.events.size, 0);
assert.equal(first.off, undefined);
assert(!source.includes('cloneNode') && !source.includes('requestAnimationFrame'));
'''
    result = subprocess.run([node, "-e", script], cwd=Path(__file__).resolve().parents[1],
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr


def test_account_menu_uses_a_native_compact_anchor_and_no_detached_arrow():
    from src.design import CSS, WORKSPACE_CONTENT_CSS
    assert '.st-key-account_trigger { flex: 0 0 auto;' in WORKSPACE_CONTENT_CSS
    assert 'min-height: 44px' in WORKSPACE_CONTENT_CSS
    assert '[data-testid="stPopoverBody"]:has(.st-key-account_menu)' in CSS
    assert '[aria-label="Account"]::before' not in CSS
    assert 'width: min(320px, calc(100vw - 24px))' in CSS
    assert '[data-fow-retained-hover]' in CSS
    assert '.hoverlayer .hovertext { pointer-events: none !important; }' in CSS


def test_html_hover_hides_svg_only_after_a_successful_replacement():
    from src.design import CSS
    assert '[data-fow-html-hover="true"] .hoverlayer { opacity: 0 !important; }' in CSS
    assert '[data-fow-html-hover="true"] .hoverlayer * { pointer-events: none !important; }' in CSS
    assert '.fow-chart-tooltip[hidden] { display: none; }' in CSS
    tooltip = CSS.split('.fow-chart-tooltip {', 1)[1].split('}', 1)[0]
    assert 'position: fixed' in tooltip and 'pointer-events: none' in tooltip
    assert 'max-width: min(380px, calc(100vw - 24px))' in tooltip


def test_design_bootstraps_the_hover_controller_with_the_current_release():
    from src.config import VERSION
    app = AppTest.from_string('from src.design import apply_design\napply_design()').run()
    assert not app.exception
    script = next(item.proto.body for item in app.get("html") if 'data-fow-hover-loader' in item.proto.body)
    assert f'const version = "{VERSION}"' in script
    assert '__FOW_APP_VERSION__' not in script


def test_transparent_header_passes_workspace_clicks_but_keeps_native_controls():
    from src.design import WORKSPACE_CONTENT_CSS
    assert 'body:has(.st-key-workspace_toolbar) :is([data-testid="stHeader"], [data-testid="stToolbar"]) { pointer-events: none; }' in WORKSPACE_CONTENT_CSS
    assert 'body:has(.st-key-workspace_toolbar) [data-testid="stHeader"] :is(button, a, [role="button"]) { pointer-events: auto; }' in WORKSPACE_CONTENT_CSS


def test_chart_upgrade_replaces_old_widget_without_changing_its_values(monkeypatch):
    import json
    from src import visualization
    app = AppTest.from_string('''
import streamlit as st
import pandas as pd
from src.visualization import ranked_bar, style_chart
data = pd.DataFrame({"skill": ["SQL", "Python"], "job_ads": [3, 1], "job_ads_pct": [75., 25.]})
st.plotly_chart(style_chart(ranked_bar(data, "skill", "job_ads", "Synthetic upgrade")))
''')
    monkeypatch.setattr(visualization, "VERSION", "synthetic-before")
    app.run()
    before = app.get("plotly_chart")[0].proto
    old_id, old_spec = before.id, json.loads(before.spec)
    app.run()
    assert app.get("plotly_chart")[0].proto.id == old_id
    monkeypatch.setattr(visualization, "VERSION", "synthetic-after")
    app.run()
    assert not app.exception
    after = app.get("plotly_chart")[0].proto
    new_spec = json.loads(after.spec)
    assert after.id != old_id
    assert old_spec["layout"].pop("uirevision") == "fow-synthetic-before"
    assert new_spec["layout"].pop("uirevision") == "fow-synthetic-after"
    assert old_spec == new_spec


def test_ranked_hover_has_one_share_for_each_bar_with_its_own_value():
    from src.visualization import ranked_bar
    frame = pd.DataFrame({"skill": ["SQL", "Python"], "job_ads": [3, 1], "job_ads_pct": [75., 25.]})
    before = frame.copy(deep=True)
    figure = ranked_bar(frame, "skill", "job_ads", "Synthetic demand")
    trace = figure.data[0]
    assert trace.hovertemplate.count("Share of selected ads:") == 1
    assert trace.hovertemplate.count("Job advertisements:") == 1
    assert trace.hovertemplate.endswith("<extra></extra>")
    assert list(zip(trace.y, trace.x, trace.customdata[:, 1])) == [("SQL", 3, 75.), ("Python", 1, 25.)]
    pd.testing.assert_frame_equal(frame, before)

def test_market_section_transition_is_short_nonblocking_and_respects_reduced_motion():
    from src.design import JOB_MARKET_CSS
    assert 'fow-section-cover 180ms ease-out both' in JOB_MARKET_CSS
    assert 'fow-section-reveal 180ms steps(1,end) both' in JOB_MARKET_CSS
    assert '.fow-section-transition[data-fow-cached="true"]' in JOB_MARKET_CSS
    assert 'animation-duration: 100ms;' in JOB_MARKET_CSS
    assert 'fow-loading[role="status"]' in JOB_MARKET_CSS
    assert 'pointer-events: none; overflow: clip;' in JOB_MARKET_CSS
    assert '@media (prefers-reduced-motion: reduce)' in JOB_MARKET_CSS
    assert '.fow-section-transition { animation: none; visibility: hidden; }' in JOB_MARKET_CSS
