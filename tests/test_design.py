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
