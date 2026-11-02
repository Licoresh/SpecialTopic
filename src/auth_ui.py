"""Lightweight login route. No NLP/model modules load before authorization."""
import os
import time
from html import escape
from pathlib import Path
import streamlit as st
from . import supabase_store as backend
from .action_guard import action_button, action_form_submit_button, finish_action_run


def _hide_workspace_sidebar():
    guard = st.empty()
    guard.html('''<span data-fow-auth-sidebar hidden></span><style>
        body:has([data-fow-auth-sidebar]) :is(
            [data-testid="stSidebar"], [data-testid="stSidebarCollapsed"],
            [data-testid="stSidebarCollapseButton"], [data-testid="stSidebarResizeHandle"],
            [data-testid="stExpandSidebarButton"]
        ) { display: none !important; }
    </style>''')
    return guard


def _login_panel(*, busy=False, email=""):
    suffix = "_busy" if busy else ""
    with st.container(key=f"login_shell{suffix}", horizontal_alignment="center"):
        with st.container(key=f"login_panel{suffix}", width=480, border=True):
            st.html('''<div class="login-brand-mark" aria-hidden="true"></div>''')
            st.caption("FUTURE OF WORK / PHILIPPINES")
            st.title("Research team sign in")
            st.write("Your shared workspace for job-ad skills, framework mapping, and research review.")
            if st.session_state.pop("_fow_signed_out_notice", False):
                st.success("You’ve been signed out. Sign in again to continue.")
            with st.form("team_sign_in_busy" if busy else "team_sign_in", clear_on_submit=False, border=False):
                email = st.text_input("Email", value=email, type="email", autocomplete="email",
                                      placeholder="you@example.org", disabled=busy)
                password = st.text_input("Password", type="password", autocomplete="current-password", disabled=busy)
                submitted = action_form_submit_button(
                    "Signing in…" if busy else "Sign in", key="team_sign_in_busy_submit" if busy else "team_sign_in_submit", cooldown=3.0,
                    type="primary", width="stretch", disabled=busy,
                    icon=":material/progress_activity:" if busy else ":material/login:",
                )
            with st.container(key=f"login_status{suffix}"):
                status = st.empty()
            st.caption("Use your individual research-team account. For account access or password help, contact your project owner.")
    return email, password, submitted, status


def login_page():
    from .design import apply_design
    _hide_workspace_sidebar()
    apply_design()
    view = st.empty()
    with view.container():
        email, password, submitted, status = _login_panel()
    login_error = st.session_state.pop("_fow_login_error", None)
    if login_error:
        status.error(login_error)
    if not submitted:
        return
    email = email.strip()
    if not email or "@" not in email or not password:
        status.error("Enter your team email address and password.")
        return
    # Replace controls in the same footprint while preserving existing auth checks.
    view.empty()
    with view.container():
        _, _, _, status = _login_panel(busy=True, email=email)
    with status.container():
        with st.spinner("Verifying your account and team access…"):
            try:
                session = backend.sign_in(email, password)
                role = backend.check_connection(session["access_token"])
            except backend.SupabaseError as exc:
                backend.sign_out()
                message = str(exc).lower()
                messages = {
                    "incomplete": "Workspace setup is incomplete. Ask the project owner to apply the required database setup.",
                    "no active research-team membership": "Your account has no active team membership. Ask the project owner to grant access.",
                    "session has expired": "Your session has expired. Sign in again to continue.",
                }
                st.session_state["_fow_login_error"] = next(
                    (hint for term, hint in messages.items() if term in message),
                    "Could not sign in. Check your email and password, then retry. If this continues, ask the project owner to check workspace access.")
                finish_action_run()
                st.rerun()
            else:
                st.session_state.update({
                    "supabase_access_token": session["access_token"],
                    "supabase_refresh_token": session["refresh_token"],
                    "supabase_expires_at": time.time() + int(session.get("expires_in", 3600)) - 60,
                    "supabase_user_email": session["user"].get("email", email),
                    "supabase_role": role,
                })
                finish_action_run()
                st.rerun()


def _workspace_unavailable(error, *, retry_label="Retry connection"):
    """Keep connection recovery available without exposing the workspace."""
    message = str(error)
    if error.status_code == 403:
        issue, advice, icon = "Workspace access", "Ask the project owner to check your team access, then retry.", "lock"
    elif "incomplete" in message.lower() or error.status_code == 404:
        issue, advice, icon = "Workspace setup", "Ask the project owner to check the shared database setup, then retry.", "settings"
    else:
        issue, advice, icon = "Connection issue", "Check the internet connection and retry.", "wifi_off"
    with st.container(key="workspace_unavailable", horizontal_alignment="center", gap="large"):
        st.image(str(Path(__file__).resolve().parents[1] / "assets/workspace_unavailable.svg"),
                 width=420, alt="A laptop with an interrupted wireless connection.")
        st.title("Workspace unavailable", anchor=False)
        st.html('<p class="fow-unavailable-message">' + escape(message) + '</p>')
        st.html('<aside class="fow-unavailable-reason"><span class="material-symbols-rounded" aria-hidden="true">'
                + icon + '</span><div><h2>' + escape(issue) + '</h2><p>' + escape(advice) + '</p></div></aside>')
        with st.container(horizontal=True, horizontal_alignment="center", gap="medium", wrap=True, key="workspace_unavailable_actions"):
            if action_button(retry_label, icon=":material/refresh:", type="primary", width=230):
                backend.clear_read_cache()
                st.rerun()
            if action_button("Return to sign in", icon=":material/login:", width=230):
                backend.sign_out()
                st.rerun()


def require_workspace_access():
    from .design import apply_design
    if not backend.configured():
        if os.environ.get("VERCEL") == "1" or os.environ.get("VERCEL_URL"):
            _hide_workspace_sidebar()
            apply_design()
            st.title("Sign-in configuration required")
            st.error(
                "This deployment requires Supabase sign-in, but SUPABASE_URL or "
                "SUPABASE_PUBLISHABLE_KEY is missing. Ask the project owner to add "
                "both variables in Vercel, then redeploy."
            )
            st.stop()
        return
    known_session = (st.session_state.get("supabase_access_token")
                     and st.session_state.get("supabase_role")
                     and float(st.session_state.get("supabase_expires_at", 0)) > time.time())
    sidebar_guard = None if known_session else _hide_workspace_sidebar()
    try:
        token = backend.get_token()
    except backend.SupabaseError as exc:
        _hide_workspace_sidebar()
        apply_design()
        _workspace_unavailable(exc, retry_label="Retry session connection")
        st.stop()
    if not token:
        st.navigation([st.Page(login_page, title="Sign in", default=True)], position="hidden").run()
        st.stop()
    try:
        role = backend.check_connection(token)
    except backend.SupabaseError as exc:
        _hide_workspace_sidebar()
        if exc.status_code == 401:
            backend.sign_out()
            st.session_state["_fow_login_error"] = "Your session has expired. Sign in again to continue."
            st.navigation([st.Page(login_page, title="Sign in", default=True)], position="hidden").run()
            st.stop()
        apply_design()
        _workspace_unavailable(exc)
        st.stop()
    st.session_state["supabase_role"] = role
    if sidebar_guard is not None:
        sidebar_guard.empty()


def render_account_menu():
    """Render account actions in a compact top-right menu on workspace pages."""
    if not backend.configured():
        return
    email = st.session_state.get("supabase_user_email")
    role = st.session_state.get("supabase_role")
    if not email:
        return

    with st.container(horizontal=True, horizontal_alignment="right", width="content", key="account_trigger"):
        with st.popover("Account", icon=":material/account_circle:", width="content", key="account_popover"), st.container(key="account_menu", gap="xsmall"):
            role_text = escape(str(role).replace("_", " ").title()) if role else ""
            st.html(f'''<section class="account-profile" aria-label="Your account">
                <h3>Your account</h3>
                <div class="account-profile-identity">
                    <span class="account-profile-avatar" aria-hidden="true">
                    </span>
                    <div class="account-profile-details"><div class="account-profile-email">{escape(str(email))}</div>
                    <div class="account-profile-role">{role_text}</div></div>
                </div>
            </section>''')
            if action_button(
                "Sign out",
                icon=":material/logout:",
                key="sign_out",
                cooldown=4.0,
                type="secondary",
                width="stretch",
            ):
                _hide_workspace_sidebar()
                backend.sign_out()
                st.session_state["_fow_signed_out_notice"] = True
                st.rerun()
