"""SYNTHETIC UI-state tests only; no research data or credentials are used."""

from src import action_guard
from streamlit.testing.v1 import AppTest


def test_duplicate_action_is_rejected_during_cooldown(monkeypatch):
    state = {"_fow_current_page": "Training"}
    now = [100.0]
    monkeypatch.setattr(action_guard.st, "session_state", state)
    monkeypatch.setattr(action_guard.st, "info", lambda _message: None)
    monkeypatch.setattr(action_guard.time, "monotonic", lambda: now[0])

    assert action_guard._accept("Train", "train-model", None, 2.0)
    action_guard.finish_action_run()

    now[0] += 0.1
    assert not action_guard._accept("Train", "train-model", None, 2.0)

    now[0] += 2.0
    assert action_guard._accept("Train", "train-model", None, 2.0)


def test_long_handler_starts_cooldown_after_it_finishes(monkeypatch):
    state = {"_fow_current_page": "Sign in"}
    now = [100.0]
    monkeypatch.setattr(action_guard.st, "session_state", state)
    monkeypatch.setattr(action_guard.st, "info", lambda _message: None)
    monkeypatch.setattr(action_guard.time, "monotonic", lambda: now[0])

    assert action_guard._accept("Sign in", "login", None, 3.0)
    now[0] += 45.0  # The remote authentication request took a while.
    action_guard.finish_action_run()
    now[0] += 0.1

    assert not action_guard._accept("Sign in", "login", None, 3.0)


def test_form_double_submit_is_processed_once():
    app = AppTest.from_string("""
import streamlit as st
from src.action_guard import action_form_submit_button, finish_action_run
with st.form('sign_in'):
    submitted = action_form_submit_button('Sign in', key='sign_in', cooldown=3.0)
if submitted:
    st.session_state['sign_in_count'] = st.session_state.get('sign_in_count', 0) + 1
finish_action_run()
st.write(st.session_state.get('sign_in_count', 0))
""").run()
    submit = app.button[0]
    submit.click().run()
    submit = app.button[0]
    submit.click().run()

    assert app.session_state["sign_in_count"] == 1
    assert any("just submitted" in item.value for item in app.info)
