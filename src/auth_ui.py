"""Lightweight login route. No NLP/model modules load before authorization."""
import time
import streamlit as st
from . import supabase_store as backend
from .action_guard import action_button, action_form_submit_button, finish_action_run


def login_page():
    _, center, _ = st.columns([1, 1.6, 1])
    with center:
        st.caption("FUTURE OF WORK · PHILIPPINES")
        st.title("Research team sign in")
        if st.session_state.pop("_fow_signed_out_notice", False):
            st.success("You’ve been signed out. Sign in again to continue.")
        st.write("Review job-ad skills together in your shared research workspace.")
        with st.form("team_sign_in", clear_on_submit=False, border=True):
            email = st.text_input("Email", autocomplete="email")
            password = st.text_input("Password", type="password", autocomplete="current-password")
            submitted = action_form_submit_button(
                "Sign in", key="team_sign_in_submit", cooldown=3.0,
                type="primary", use_container_width=True,
            )
        if submitted:
            try:
                with st.spinner("Signing in and checking your research-team access…"):
                    session = backend.sign_in(email, password)
                    role = backend.check_connection(session["access_token"])
            except backend.SupabaseError as exc:
                # No partially authenticated session survives a failed setup check.
                backend.sign_out()
                st.error(str(exc))
            else:
                st.session_state.update({
                    "supabase_access_token": session["access_token"],
                    "supabase_refresh_token": session["refresh_token"],
                    "supabase_expires_at": time.time() + int(session.get("expires_in", 3600)) - 60,
                    "supabase_user_email": session["user"].get("email", email),
                    "supabase_role": role,
                })
                st.rerun()
            finally:
                finish_action_run()
        st.caption("Use your individual research-team account. The project owner creates accounts and grants team access in Supabase.")


def require_workspace_access():
    if not backend.configured():
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


def render_account_controls():
    """Render account actions after page navigation, in the sidebar footer."""
    if not backend.configured():
        return
    email = st.session_state.get("supabase_user_email")
    role = st.session_state.get("supabase_role")
    if not email:
        return

    with st.sidebar.container(border=True):
        st.caption("ACCOUNT")
        st.write(email)
        if role:
            st.caption(str(role).replace("_", " ").title())
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
