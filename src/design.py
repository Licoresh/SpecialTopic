"""Shared presentation only; native controls retain their behavior and accessibility."""
import streamlit as st
from pathlib import Path
from html import escape
from urllib.parse import quote


def apply_design():
    # Configured theme colors stay authoritative in config.toml.
    colors = {key: st.get_option(f"theme.{option}") for key, option in {
        "accent": "primaryColor", "surface": "backgroundColor",
        "soft": "secondaryBackgroundColor", "border": "borderColor",
        "info": "blueColor", "info-bg": "blueBackgroundColor",
        "review": "orangeColor", "review-bg": "orangeBackgroundColor",
        "error": "redColor",
        "framework": "violetColor", "framework-bg": "violetBackgroundColor"}.items()}
    colors.update({"accent-bg": "#F7EDEF", "gold": "#D6A33D", "gold-dark": "#A8751C",
                   "heading": "#24303D", "muted": "#647184",
                   "ink": "#4D1020"})
    tokens = ";".join(f"--fow-{key}:{value}" for key, value in colors.items() if value)
    st.html("<style>:root{" + tokens + "}" + CSS + "</style>")
    hover_script = Path(__file__).with_name("chart_hover.js").read_text(encoding="utf-8")
    st.html('<script data-fow-hover-loader="true">' + hover_script + "</script>", unsafe_allow_javascript=True)


def workspace_breadcrumb(page):
    label = "Overview" if page == "Home" else page
    st.html('<nav class="fow-breadcrumb" aria-label="Current location">'
            '<span class="fow-home-mark" aria-hidden="true"></span><span>Future of Work</span><span class="fow-crumb-separator" aria-hidden="true">›</span>'
            '<strong aria-current="page">' + escape(label) + '</strong></nav>')


def review_workspace_style(fullscreen):
    # Expand the same widgets so entering/leaving focus mode preserves drafts.
    focus = """
    .st-key-manual_review_workspace {
      position: fixed; inset: 0; z-index: 100;
      overflow: auto; overscroll-behavior: contain; padding: clamp(.75rem, 2vw, 2rem);
      background: var(--fow-surface, #fff); isolation: isolate; border-radius: 0;
      visibility: visible;
    }
    .stMainBlockContainer { visibility: hidden; }
    [data-testid="stLayoutWrapper"]:has(> .st-key-manual_review_actions) { top: 0; }
    [data-testid="stHeader"], [data-testid="stSidebar"] { display: none; }
    """ if fullscreen else ""
    st.html("<style>" + REVIEW_CSS + focus + "</style>")


REVIEW_CSS = """
/* Use workspace expansion so actions and evidence remain available. */
.st-key-manual_review_workspace button[aria-label="Fullscreen"] { display: none; }
[data-testid="stLayoutWrapper"]:has(> .st-key-manual_review_actions) {
  position: sticky; top: 3.75rem; z-index: 10;
}
.st-key-manual_review_actions {
  background: var(--fow-surface, #fff); padding: .75rem;
  border-bottom: 1px solid var(--fow-border, #ddd);
  border-radius: .75rem .75rem 0 0;
}
.st-key-manual_review_workspace { background: var(--fow-surface); border-radius: var(--fow-radius); padding: 0; }
.st-key-review_controls { gap: .75rem; }
.st-key-review_detail_tools { gap: .5rem; }
.st-key-review_detail_tools button { min-height: var(--fow-control-height); }
"""


ACCOUNT_SVG = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#78182B" stroke-width="1.7" stroke-linecap="round"><circle cx="12" cy="7" r="4"/><path d="M4 22v-2a8 8 0 0 1 16 0v2z"/></svg>'
HOME_SVG = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#78182B" stroke-width="1.7" stroke-linejoin="round"><path d="m3 11 9-8 9 8M5 10v10h5v-6h4v6h5V10"/></svg>'
BRAND_SVG = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#78182B" stroke-width="1.7" stroke-linejoin="round"><rect x="3" y="7" width="18" height="14" rx="3"/><path d="M8 7V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2M3 12q9 7 18 0M10 12h4v5h-4z"/></svg>'


CSS = """
:root {
  --fow-radius: 10px;
  --fow-space-1: .25rem; --fow-space-2: .5rem; --fow-space-3: .75rem;
  --fow-space-4: 1rem; --fow-space-5: 1.5rem; --fow-space-6: 2rem;
  --fow-control-height: 44px; --fow-card-padding: 1rem;
  --fow-shadow: 0 2px 10px rgb(36 48 61 / .04);
}
[data-testid="stAppViewContainer"] { background: var(--fow-soft); }
[data-testid="stHeader"] { background: rgb(246 245 243 / .96); }
/* The trusted chart handler has no visible layout content. */
[data-testid="stElementContainer"]:has(> [data-testid="stHtml"] > script[data-fow-hover-loader]) { display: none; }
/* Remove only the obsolete tooltip overlay; current retained hover labels stay visible. */
svg[data-fow-sticky-tooltip="true"] { display: none !important; }
.stMainBlockContainer {
  /* Preserve Streamlit's native top clearance for its fixed toolbar. */
  max-width: 1440px; padding-inline: clamp(1rem, 3vw, 2rem); padding-bottom: 4rem;
}
h1,h2,h3 { color: var(--fow-heading); letter-spacing: -.035em; text-wrap: balance; font-weight: 700; }
h1 { max-width: 30ch; }
p,li { line-height: 1.55; }
.st-key-page_heading, .st-key-overview_heading { padding-block: .5rem 1rem; margin-bottom: .25rem; }
.st-key-page_heading h1, .st-key-overview_heading h1 { font-size: clamp(1.9rem, 3.2vw, 2.75rem); line-height: 1.15; padding-block: .2rem .45rem; max-width: 28ch; }
.st-key-page_heading p, .st-key-overview_heading p { max-width: 72ch; color: var(--fow-muted); font-size: 1rem; }
:is(.st-key-page_heading, .st-key-overview_heading) [data-testid="stCaptionContainer"] p { color: var(--fow-accent); font-size: .75rem; font-weight: 700; letter-spacing: .1em; }
[data-testid="stCaptionContainer"] { opacity: 1; }
[data-testid="stMetric"] {
  border: 1px solid var(--fow-border); border-radius: var(--fow-radius);
  background: var(--fow-surface); padding: 1rem; min-height: 112px;
  box-shadow: var(--fow-shadow);
}
[data-testid="stMetricLabel"] { font-weight: 550; color: var(--fow-muted); }
[data-testid="stMetricValue"] { color: var(--fow-heading); font-variant-numeric: tabular-nums; letter-spacing: -.04em; font-weight: 700; }
.st-key-overview_metrics { margin-bottom: .5rem; }
.st-key-overview_metrics > [data-testid="stLayoutWrapper"] { flex: 1 1 220px; }
.st-key-overview_metrics [data-testid="stMetricLabel"] { display: flex; align-items: center; gap: .5rem; min-height: 40px; }
.st-key-overview_metrics [data-testid="stMetricIcon"] { position: static !important; inset: auto !important; transform: none !important; display: grid; place-items: center; flex: 0 0 40px; width: 40px; height: 40px; margin: 0; border-radius: 11px; font-size: 22px; }
.st-key-overview_metric_1 [data-testid="stMetricIcon"],
.st-key-overview_metric_2 [data-testid="stMetricIcon"],
.st-key-overview_metric_4_ready [data-testid="stMetricIcon"],
.st-key-result_metric_1 [data-testid="stMetricIcon"] { background: var(--fow-accent-bg); color: var(--fow-accent); }
.st-key-overview_metric_3 [data-testid="stMetricIcon"] { background: var(--fow-framework-bg); color: var(--fow-framework); }
.st-key-overview_metric_4_pending [data-testid="stMetricIcon"],
.st-key-result_metric_3 [data-testid="stMetricIcon"] { background: var(--fow-review-bg); color: var(--fow-review); }
.st-key-result_metric_2 [data-testid="stMetricIcon"] { background: var(--fow-info-bg); color: var(--fow-info); }
[data-testid="stButton"] button, [data-testid="stDownloadButton"] button,
[data-testid="stFormSubmitButton"] button, [data-testid="stPopover"] button {
  min-height: var(--fow-control-height); font-weight: 600;
}
button:focus-visible, a:focus-visible, input:focus-visible, textarea:focus-visible,
[role="combobox"]:focus-visible {
  outline: 3px solid var(--fow-accent); outline-offset: 3px;
}
[data-testid="stTextInput"] input { min-height: var(--fow-control-height); }
:is([data-testid="stSelectbox"], [data-testid="stMultiSelect"]) .react-aria-ComboBox > [role="group"] { min-height: var(--fow-control-height); }
[data-testid="stNumberInput"] input { min-height: var(--fow-control-height); }
[data-testid="stTextInput"] input, [data-testid="stNumberInput"] input { background: var(--fow-surface); }
[data-testid="stForm"] { padding: var(--fow-card-padding); }
[data-testid="stDataFrame"] {
  border: 1px solid var(--fow-border); border-radius: var(--fow-radius);
}
/* Streamlit measures this node to size Plotly. Decoration must not add size. */
[data-testid="stPlotlyChart"] {
  border: 0; padding: 0; border-radius: var(--fow-radius);
  box-shadow: inset 0 0 0 1px var(--fow-border); background: var(--fow-surface);
}
[data-testid="stSidebarNav"] a { min-height: 40px; border-radius: .5rem; }
[data-testid="stSidebarNav"] a[aria-current="page"] { font-weight: 650; background: var(--fow-accent-bg); box-shadow: inset 3px 0 var(--fow-accent); }
[data-testid="stSidebarNav"] a:hover { background: #F1EDEF; }
[data-testid="stSidebarNav"] span { overflow-wrap: normal; }
.st-key-workspace_toolbar { padding-bottom: .6rem; margin-bottom: .25rem; min-height: 46px; }
.st-key-workspace_toolbar [data-testid="stCaptionContainer"] p { color: var(--fow-muted); font-size: .75rem; font-weight: 650; letter-spacing: .06em; }
/* Own the profile markup; only the popover and sign-out remain native controls. */
[data-testid="stPopoverBody"][aria-label="Account"] {
  width: 288px; min-width: 0; max-width: calc(100vw - 24px);
  padding: var(--fow-card-padding); border: 1px solid var(--fow-border); border-radius: var(--fow-radius);
  background: var(--fow-surface); box-shadow: 0 12px 28px rgb(36 48 61 / .12);
  overflow: visible;
}
[data-testid="stPopoverBody"][aria-label="Account"]::before {
  content: ""; position: absolute; top: -6px; right: 56px;
  width: 12px; height: 12px; transform: rotate(45deg); background: var(--fow-surface);
  border-top: 1px solid var(--fow-border); border-left: 1px solid var(--fow-border);
}
.st-key-account_menu { gap: var(--fow-card-padding); }
.account-profile { width: 100%; }
.account-profile h3 {
  margin: 0; padding: 0 0 var(--fow-card-padding); color: var(--fow-heading);
  font-family: inherit; font-weight: 700; font-size: 1.25rem; line-height: 1.2; letter-spacing: -.4px;
}
.account-profile-identity {
  display: flex; align-items: center; gap: var(--fow-space-4);
  padding: var(--fow-card-padding) 0; border-block: 1px solid var(--fow-border);
}
.account-profile-avatar {
  display: flex; align-items: center; justify-content: center;
  flex: 0 0 48px; height: 48px; border-radius: 50%;
  background: var(--fow-accent-bg) url("__ACCOUNT_URI__") no-repeat center / 29px; color: var(--fow-accent);
}
.account-profile-details { min-width: 0; }
.account-profile-email { color: var(--fow-ink); font: inherit; font-weight: 500; font-size: .875rem; line-height: 1.4; overflow-wrap: anywhere; }
.account-profile-role { margin-top: var(--fow-space-1); color: var(--fow-muted); font: inherit; font-size: .875rem; line-height: 1.4; }
.st-key-account_menu [data-testid="stButton"] button {
  min-height: var(--fow-control-height); border: 1px solid #D9B8BE; background: var(--fow-accent-bg);
  border-radius: 8px; color: var(--fow-ink); gap: 10px; font-weight: 600;
}
.st-key-account_menu [data-testid="stButton"] button p { font-size: 1rem; color: var(--fow-ink); }
.st-key-account_menu [data-testid="stButton"] button:hover { background: #F1EDEF; border-color: #C98E99; }
.st-key-account_trigger [data-testid="stPopoverButton"] { background: var(--fow-surface); border: 1px solid var(--fow-border); border-radius: 8px; }
.st-key-home_next { background: var(--fow-ink); color: white; border: 0; padding: clamp(1rem, 2.5vw, 1.5rem); margin-block: .5rem 1.25rem; }
.st-key-home_next h3, .st-key-home_next p { color: white; }
.st-key-home_next [data-testid="stCaptionContainer"] p { color: #F4DFAF; font-size: .75rem; letter-spacing: .1em; font-weight: 650; }
.st-key-home_next button[kind="primary"] { background: var(--fow-gold); border-color: var(--fow-gold); color: var(--fow-ink); }
.st-key-home_next button[kind="primary"] p { color: var(--fow-ink); }
.st-key-home_next button[kind="primary"]:hover { background: #E7BD68; border-color: #E7BD68; }
[class*="st-key-workflow_step_"] { background: var(--fow-surface); padding: var(--fow-card-padding); gap: .5rem; box-shadow: var(--fow-shadow); }
[class*="st-key-workflow_step_"] h4 { font-size: 1.1rem; }
[class*="st-key-workflow_step_"] [data-testid="stCaptionContainer"] p { color: var(--fow-accent); font-size: .75rem; font-weight: 650; }
[class*="st-key-workflow_step_"] [data-testid="stButton"] { margin-top: .5rem; }
[class*="st-key-workflow_step_"] > [data-testid="stElementContainer"]:has([data-testid="stMarkdownContainer"]) { min-height: 3rem; }
.st-key-readiness_summary { border-left: 3px solid var(--fow-review); background: var(--fow-review-bg); padding: 1rem; margin-top: 1rem; }
.st-key-readiness_summary h3 { font-size: 1.15rem; }
:is(.st-key-login_shell, .st-key-login_shell_busy) { padding-top: clamp(1rem, 5vh, 4rem); }
:is(.st-key-login_panel, .st-key-login_panel_busy) { padding: clamp(1.25rem, 3vw, 2rem); background: var(--fow-surface); box-shadow: 0 10px 28px rgb(36 48 61 / .08); }
:is(.st-key-login_panel, .st-key-login_panel_busy) h1 { font-size: clamp(1.65rem, 4vw, 2.1rem); }
:is(.st-key-login_status, .st-key-login_status_busy) { min-height: 76px; }
:is(.st-key-login_panel, .st-key-login_panel_busy) [data-testid="stForm"] { padding: 0; border: 0; }
.st-key-workflow_0, .st-key-workflow_3 { gap: 1rem; }
.st-key-workflow_0 > [data-testid="stLayoutWrapper"], .st-key-workflow_3 > [data-testid="stLayoutWrapper"] { flex: 1 1 280px; }
.st-key-settings_form { max-width: 880px; }
[data-testid="stAlert"] p { overflow-wrap: anywhere; }

.fow-breadcrumb { display: flex; align-items: center; gap: 1rem; color: var(--fow-muted); font-size: .85rem; min-height: 42px; }
.fow-breadcrumb strong { color: var(--fow-heading); font-weight: 650; }
.fow-home-mark { display: grid; place-items: center; width: 38px; height: 38px; background: var(--fow-accent-bg) url("__HOME_URI__") no-repeat center / 20px; border-radius: 10px; color: var(--fow-accent); }
.fow-crumb-separator { color: #9C9290; font-size: 1.4rem; }
.login-brand-mark { display: grid; place-items: center; width: 52px; height: 52px; border: 1px solid #D9B8BE; border-radius: 12px; background: var(--fow-accent-bg) url("__BRAND_URI__") no-repeat center / 27px; color: var(--fow-accent); margin-bottom: .5rem; }
:is([data-testid="stButton"], [data-testid="stDownloadButton"], [data-testid="stFormSubmitButton"]) button { border-color: var(--fow-border); border-radius: 8px; box-shadow: none; }
:is([data-testid="stButton"], [data-testid="stDownloadButton"], [data-testid="stFormSubmitButton"]) button:hover { border-color: #C98E99; box-shadow: 0 2px 7px rgb(77 16 32 / .08); }
[data-testid="stExpander"] { border: 1px solid var(--fow-border); border-radius: var(--fow-radius); background: var(--fow-surface); box-shadow: none; }
[data-testid="stExpander"] details summary { min-height: 46px; font-weight: 550; }
[data-testid="stFileUploader"] { background: var(--fow-surface); border-radius: var(--fow-radius); }
[data-testid="stFileUploaderDropzone"] { background: var(--fow-soft); border: 1px dashed #C98E99; border-radius: var(--fow-radius); }
[data-testid="stForm"], [data-testid="stVerticalBlockBorderWrapper"] { border-color: var(--fow-border); }
[data-testid="stTabs"] [role="tablist"] { background: var(--fow-surface); border: 1px solid var(--fow-border); border-radius: var(--fow-radius); padding: 4px; gap: 4px; }
[data-testid="stTabs"] [role="tab"][aria-selected="true"] { background: var(--fow-accent-bg); color: var(--fow-accent); border-radius: 7px; }
.st-key-analysis_pipeline { margin-block: 0 var(--fow-space-4); padding: .35rem; align-items: stretch; background: var(--fow-surface); }
.st-key-analysis_pipeline > [data-testid="stLayoutWrapper"] { flex: 1 1 140px; min-width: 0; }
[class*="st-key-pipeline_stage_"] { padding: var(--fow-space-2) var(--fow-space-3); border-radius: 7px; min-height: 112px; gap: .25rem; text-align: center; border: 0; background: transparent; box-shadow: none; }
[class*="st-key-pipeline_stage_"] [data-testid="stMarkdownContainer"] p { font-size: .83rem; line-height: 1.45; }
[class*="st-key-pipeline_stage_"] [data-testid="stCaptionContainer"] p { color: var(--fow-muted); font-size: .79rem; }
.st-key-result_metrics { margin-block: .8rem; }
.st-key-result_metrics > [data-testid="stLayoutWrapper"] { flex: 1 1 245px; }
[class*="st-key-result_metric_"] { background: var(--fow-surface); border: 1px solid var(--fow-border); border-radius: var(--fow-radius); padding: var(--fow-card-padding); box-shadow: var(--fow-shadow); gap: .5rem; }
[class*="st-key-result_metric_"] [data-testid="stMetric"] { border: 0; background: transparent; box-shadow: none; min-height: 0; padding: 0; }
[class*="st-key-result_metric_"] [data-testid="stMetricValue"] { font-size: 2.4rem; }
[class*="st-key-result_metric_"] [data-testid="stMetric"] { position: relative; padding-left: 68px; }
[class*="st-key-result_metric_"] [data-testid="stMetricIcon"] { position: absolute; top: 0; left: 0; display: grid; place-items: center; width: 48px; height: 48px; border-radius: 12px; font-size: 27px; }
[class*="st-key-result_single_"] [data-testid="stMetric"] { min-height: 144px; }
[class*="st-key-result_single_"] [data-testid="stMetricValue"] { font-size: clamp(2.7rem, 5vw, 3.7rem); }
.st-key-result_chart_controls { align-items: end; margin-block: .4rem 1rem; }
.st-key-result_chart_controls > [data-testid="stLayoutWrapper"] { flex: 1 1 360px; }
.st-key-result_chart_selectors > [data-testid="stLayoutWrapper"] { flex: 1 1 150px; }
.st-key-result_chart_note { min-width: 0; }
.st-key-result_chart_note [data-testid="stCaptionContainer"] p { color: var(--fow-muted); font-size: .83rem; }
.st-key-result_section_toolbar { align-items: center; justify-content: space-between; margin-top: .5rem; }
.st-key-result_section_toolbar h3 { font-size: 1.2rem; padding-bottom: .15rem; }
.st-key-result_sections [data-testid="stButtonGroup"] { background: var(--fow-surface); border: 1px solid var(--fow-border); border-radius: var(--fow-radius); }
.st-key-result_sections [data-testid="stButtonGroup"] button { min-height: var(--fow-control-height); border-radius: 8px; }
[data-testid="stSidebar"] { border-right: 1px solid var(--fow-border); }
[data-testid="stSidebarNav"] a { padding-block: .55rem; }

@media (max-width: 1100px) {
  .st-key-page_heading p, .st-key-overview_heading p { max-width: 70ch; }
}
@media (max-width: 900px) {
  [data-testid="stMetric"] { padding: .9rem; }
  .st-key-overview_metrics,
  .st-key-result_metrics,
  .st-key-analysis_pipeline,
  .st-key-workflow_0,
  .st-key-workflow_3 { flex-wrap: wrap; }
  .st-key-overview_metrics > [data-testid="stLayoutWrapper"],
  .st-key-result_metrics > [data-testid="stLayoutWrapper"],
  .st-key-workflow_0 > [data-testid="stLayoutWrapper"],
  .st-key-workflow_3 > [data-testid="stLayoutWrapper"] {
    width: auto !important; min-width: min(100%, 220px); flex: 1 1 220px;
  }
  .st-key-analysis_pipeline > [data-testid="stLayoutWrapper"] {
    width: auto !important; min-width: min(100%, 160px); flex: 1 1 160px;
  }
  [class*="st-key-pipeline_stage_"] { min-height: 100px; }
}
@media (max-width: 640px) {
  .stMainBlockContainer { padding-inline: 1rem; padding-bottom: 3rem; }
  h1 { font-size: 1.8rem; } h2 { font-size: 1.4rem; }
  .st-key-page_heading, .st-key-overview_heading { padding-block: .35rem .75rem; }
  .st-key-page_heading p, .st-key-overview_heading p { max-width: 100%; font-size: 1rem; }
  .fow-breadcrumb { gap: .5rem; font-size: .75rem; flex-wrap: wrap; }
  .fow-home-mark { width: 30px; height: 30px; }
  .st-key-analysis_pipeline { gap: var(--fow-space-3); }
  [class*="st-key-pipeline_stage_"] { min-height: 96px; }
  .st-key-workspace_toolbar { flex-wrap: wrap; }
  [data-testid="stForm"] { padding: 1rem; }
  [data-testid="stMetric"] { min-height: 96px; }
  .st-key-manual_review_workspace { padding: 0; }
  .st-key-home_next > [data-testid="stLayoutWrapper"] { width: 100%; }
  :is(.st-key-login_shell, .st-key-login_shell_busy) { padding-top: .5rem; }
  :is(.st-key-login_panel, .st-key-login_panel_busy) { padding: 1.15rem; }
  button p { overflow-wrap: anywhere; }
}
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation-duration: .01ms !important; transition-duration: .01ms !important; }
}
""".replace("__HOME_URI__", "data:image/svg+xml," + quote(HOME_SVG)).replace(
    "__BRAND_URI__", "data:image/svg+xml," + quote(BRAND_SVG)).replace(
    "__ACCOUNT_URI__", "data:image/svg+xml," + quote(ACCOUNT_SVG))
