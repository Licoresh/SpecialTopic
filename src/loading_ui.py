"""Delay a lightweight loading skeleton until a page is genuinely slow to appear."""

import streamlit as st


def run_page_with_loading(page, route: str) -> None:
    """Run a page with a delayed skeleton on its first visit in this session only."""
    loaded_routes = st.session_state.setdefault("_fow_loaded_routes", set())
    if route in loaded_routes:
        page.run()
        return

    # Streamlit delays context-manager skeletons briefly, so fast pages never flash.
    # Previously visited pages and ordinary widget reruns bypass it entirely.
    with st.skeleton(height=560):
        page.run()
    loaded_routes.add(route)
