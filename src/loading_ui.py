"""Fast, page-shaped wireframes for authenticated workspace navigation."""

import streamlit as st


_TABLE_PAGES = {"Review data quality", "Extract skill phrases", "Review and label phrases"}
_ANALYSIS_PAGES = {
    "Overview", "Job market", "PSF mapping", "Employer–PSF alignment",
    "Unmapped and emerging skills", "Reports and downloads", "Evaluate models",
}
_FORM_PAGES = {"Upload job data", "Train classifier", "Settings", "Feedback and corrections"}


def render_workspace_page_skeleton(page_title: str) -> None:
    """Draw a lightweight wireframe shaped for the page being opened."""
    st.skeleton(height=34, width=300)
    st.skeleton(height=16, width=440)

    if page_title in _ANALYSIS_PAGES:
        metric_columns = st.columns(4)
        for column in metric_columns:
            with column:
                st.skeleton(height=88)
        st.skeleton(height=330)
        left, right = st.columns(2)
        with left:
            st.skeleton(height=220)
        with right:
            st.skeleton(height=220)
        return

    if page_title in _TABLE_PAGES:
        controls = st.columns([1, 1, 1, 2])
        for column in controls:
            with column:
                st.skeleton(height=42)
        st.skeleton(height=470)
        return

    if page_title in _FORM_PAGES:
        for _ in range(2):
            left, right = st.columns(2)
            with left:
                st.skeleton(height=48)
            with right:
                st.skeleton(height=48)
        st.skeleton(height=300)
        return

    # Methodology and readiness pages are primarily explanatory text and checks.
    st.skeleton(height=120)
    st.skeleton(height=240)
    st.skeleton(height=180)
