"""Prevent accidental repeat submissions within one Streamlit browser session."""

from __future__ import annotations

import time

import streamlit as st


DEFAULT_COOLDOWN_SECONDS = 1.5


def _identity(label: str, key: str | None, action_id: str | None) -> str:
    page = str(st.session_state.get("_fow_current_page", "workspace"))
    widget = str(action_id or key or label)
    return f"{page}:{widget}"


def _accept(label: str, key: str | None, action_id: str | None, cooldown: float) -> bool:
    identity = _identity(label, key, action_id)
    completed = st.session_state.setdefault("_fow_recent_actions", {})
    now = time.monotonic()
    last = completed.get(identity)
    if last is not None and now - last < cooldown:
        st.info("This action was just submitted. Please wait a moment before trying again.")
        return False

    # Record immediately for login/actions that trigger st.rerun(). The render
    # lifecycle refreshes this timestamp after longer handlers finish.
    completed[identity] = now
    pending = st.session_state.setdefault("_fow_pending_actions", set())
    pending.add(identity)
    return True


def action_button(label: str, *args, key: str | None = None,
                  action_id: str | None = None,
                  cooldown: float = DEFAULT_COOLDOWN_SECONDS, **kwargs) -> bool:
    """A drop-in st.button wrapper with a short same-session duplicate guard."""
    clicked = st.button(label, *args, key=key, **kwargs)
    return bool(clicked and _accept(label, key, action_id, cooldown))


def action_form_submit_button(label: str = "Submit", *args, key: str | None = None,
                              action_id: str | None = None,
                              cooldown: float = DEFAULT_COOLDOWN_SECONDS,
                              **kwargs) -> bool:
    """A duplicate-guarded form submit button."""
    clicked = st.form_submit_button(label, *args, key=key, **kwargs)
    return bool(clicked and _accept(label, key, action_id, cooldown))


def finish_action_run() -> None:
    """Start the cooldown after handlers finish, including long-running ones."""
    pending = st.session_state.get("_fow_pending_actions")
    if not pending:
        return
    now = time.monotonic()
    recent = st.session_state.setdefault("_fow_recent_actions", {})
    for identity in pending:
        recent[identity] = now
    st.session_state["_fow_pending_actions"] = set()

    # Keep session state small even in very long-lived reviewer sessions.
    stale = [key for key, timestamp in recent.items() if now - timestamp > 60]
    for key in stale:
        recent.pop(key, None)

