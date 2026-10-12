"""Lightweight login route. No NLP/model modules load before authorization."""
import os
import time
import streamlit as st
from . import supabase_store as backend
from .action_guard import action_button, action_form_submit_button, finish_action_run


def login_page():
    view = st.empty()
    with view.container():
        _, center, _ = st.columns([1, 1.6, 1])
        with center:
            st.caption("FUTURE OF WORK · PHILIPPINES")
            st.title("Research team sign in")
            if st.session_state.pop("_fow_signed_out_notice", False):
                st.success("You’ve been signed out. Sign in again to continue.")
            login_error = st.session_state.pop("_fow_login_error", None)
            if login_error:
                st.error(login_error)
            st.write("Review job-ad skills together in your shared research workspace.")
            with st.form("team_sign_in", clear_on_submit=False, border=True):
                email = st.text_input("Email", autocomplete="email")
                password = st.text_input("Password", type="password", autocomplete="current-password")
                submitted = action_form_submit_button(
                    "Sign in", key="team_sign_in_submit", cooldown=3.0,
                    type="primary", use_container_width=True,
                )
            st.caption("Use your individual research-team account. The project owner creates accounts and grants team access in Supabase.")

    if submitted:
        # Replace the form in place while the remote authentication checks run.
        view.empty()
        with view.container():
            _, center, _ = st.columns([1, 1.6, 1])
            with center:
                st.caption("FUTURE OF WORK · PHILIPPINES")
                st.title("Signing you in")
                with st.container(border=True):
                    st.write("Verifying your account and research-team access…")
                    with st.spinner("Connecting securely to the shared workspace…"):
                        try:
                            session = backend.sign_in(email, password)
                            role = backend.check_connection(session["access_token"])
                        except backend.SupabaseError as exc:
                            # No partially authenticated session survives a failed setup check.
                            backend.sign_out()
                            st.session_state["_fow_login_error"] = str(exc)
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


def require_workspace_access():
    if not backend.configured():
        if os.environ.get("VERCEL") == "1" or os.environ.get("VERCEL_URL"):
            st.title("Sign-in configuration required")
            st.error(
                "This deployment requires Supabase sign-in, but SUPABASE_URL or "
                "SUPABASE_PUBLISHABLE_KEY is missing. Ask the project owner to add "
                "both variables in Vercel, then redeploy."
            )
            st.stop()
        return
    try:
        token = backend.get_token()
    except backend.SupabaseError as exc:
        st.error(str(exc))
        if action_button("Retry session connection"):
            st.rerun()
        st.stop()
    if not token:
        st.navigation([st.Page(login_page, title="Sign in", default=True)], position="hidden").run()
        st.stop()
    try:
        role = backend.check_connection(token)
    except backend.SupabaseError as exc:
        if exc.status_code == 401:
            backend.sign_out()
            st.session_state["_fow_login_error"] = "Your session has expired. Sign in again to continue."
            st.navigation([st.Page(login_page, title="Sign in", default=True)], position="hidden").run()
            st.stop()
        st.title("Workspace unavailable")
        st.error(str(exc))
        if action_button("Retry connection"):
            backend.clear_read_cache()
            st.rerun()
        if action_button("Return to sign in"):
            backend.sign_out()
            st.rerun()
        st.stop()
    st.session_state["supabase_role"] = role


def render_account_menu():
    """Render account actions in a compact top-right menu on workspace pages."""
    if not backend.configured():
        return
    email = st.session_state.get("supabase_user_email")
    role = st.session_state.get("supabase_role")
    if not email:
        return

    spacer, account = st.columns([8, 1], vertical_alignment="top")
    with account:
        with st.popover("Account", icon=":material/account_circle:", use_container_width=True):
            st.caption(email)
            if role:
                st.caption(str(role).replace("_", " ").title())
            st.divider()
            if action_button(
                "Sign out",
                key="sign_out",
                cooldown=4.0,
                type="secondary",
                use_container_width=True,
            ):
                backend.sign_out()
                st.session_state["_fow_signed_out_notice"] = True
                st.rerun()
