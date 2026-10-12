import streamlit as st
from src.auth_ui import require_workspace_access

st.set_page_config(page_title="Future of Work | Philippines", page_icon="🇵🇭", layout="wide")

require_workspace_access()

from src.ui import render

pages = {
    "Workspace": [
        st.Page(lambda: render("Home"), title="Overview", icon=":material/dashboard:", default=True),
    ],
    "Prepare data": [
        st.Page("pages/01_Data_Upload.py", title="Upload job data", icon=":material/upload_file:"),
        st.Page("pages/02_Data_Quality.py", title="Review data quality", icon=":material/fact_check:"),
        st.Page("pages/05_Competency_Extraction.py", title="Extract skill phrases", icon=":material/psychology:"),
        st.Page("pages/06_Manual_Labeling.py", title="Review and label phrases", icon=":material/rate_review:"),
    ],
    "Train models": [
        st.Page("pages/07_ML_Training.py", title="Train classifier", icon=":material/model_training:"),
        st.Page("pages/08_Model_Evaluation.py", title="Evaluate models", icon=":material/monitoring:"),
    ],
    "Research results": [
        st.Page("pages/03_Job_Market.py", title="Job market", icon=":material/insights:"),
        st.Page("pages/09_PSF_Mapping.py", title="PSF mapping", icon=":material/account_tree:"),
        st.Page("pages/10_Alignment.py", title="Employer–PSF alignment", icon=":material/compare_arrows:"),
        st.Page("pages/11_Skills_Gap.py", title="Unmapped and emerging skills", icon=":material/trending_up:"),
        st.Page("pages/14_Reports.py", title="Reports and downloads", icon=":material/download:"),
    ],
    "Study tools": [
        st.Page("pages/18_Research_Readiness.py", title="Research readiness", icon=":material/verified:"),
        st.Page("pages/16_Methodology.py", title="Methodology", icon=":material/menu_book:"),
        st.Page("pages/15_Feedback.py", title="Feedback and corrections", icon=":material/rate_review:"),
        st.Page("pages/17_Settings.py", title="Settings", icon=":material/settings:"),
    ],
}
page = st.navigation(pages, position="sidebar", expanded=True)
page.run()
