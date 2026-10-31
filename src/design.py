"""Shared presentation only; native controls retain their behavior and accessibility."""
import streamlit as st
from pathlib import Path
from html import escape
from urllib.parse import quote


def apply_design():
    # Configured theme colors stay authoritative in config.toml.
    colors = {key: st.get_option(f"theme.{option}") for key, option in {
        "accent": "primaryColor", "accent-bg": "greenBackgroundColor", "surface": "backgroundColor",
        "soft": "secondaryBackgroundColor", "border": "borderColor",
        "info": "blueColor", "info-bg": "blueBackgroundColor",
        "review": "orangeColor", "review-bg": "orangeBackgroundColor",
        "error": "redColor", "framework": "violetColor", "framework-bg": "violetBackgroundColor"}.items()}
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
.st-key-manual_review_workspace { background: var(--fow-surface); border-radius: 1rem; padding: 0; }
.st-key-review_controls { gap: .75rem; }
.st-key-review_detail_tools { gap: .5rem; }
.st-key-review_detail_tools button { min-height: 36px; }
"""


ACCOUNT_SVG = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#2F6B5D" stroke-width="1.7" stroke-linecap="round"><circle cx="12" cy="7" r="4"/><path d="M4 22v-2a8 8 0 0 1 16 0v2z"/></svg>'
HOME_SVG = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#344F60" stroke-width="1.7" stroke-linejoin="round"><path d="m3 11 9-8 9 8M5 10v10h5v-6h4v6h5V10"/></svg>'
BRAND_SVG = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#2F6B5D" stroke-width="1.7" stroke-linejoin="round"><rect x="3" y="7" width="18" height="14" rx="3"/><path d="M8 7V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2M3 12q9 7 18 0M10 12h4v5h-4z"/></svg>'
HERO_SVG = '<svg xmlns="http://www.w3.org/2000/svg" width="470" height="210" viewBox="0 0 470 210"><defs><pattern id="g" width="20" height="20" patternUnits="userSpaceOnUse"><path d="M20 0H0V20" fill="none" stroke="#B6D4D0" stroke-opacity=".2"/></pattern></defs><ellipse cx="265" cy="147" rx="198" ry="106" fill="#EAF3F2"/><circle cx="144" cy="128" r="83" fill="#EDF5F3"/><path d="M15 187Q93 129 173 170T350 128T470 154V210H15Z" fill="#DFEEEA" opacity=".5"/><path fill="url(#g)" d="M60 47h370v160H60z"/><g fill="#BED8D5"><circle cx="193" cy="16" r="2"/><circle cx="207" cy="16" r="2"/><circle cx="221" cy="16" r="2"/><circle cx="235" cy="16" r="2"/><circle cx="249" cy="16" r="2"/><circle cx="193" cy="29" r="2"/><circle cx="207" cy="29" r="2"/><circle cx="221" cy="29" r="2"/><circle cx="235" cy="29" r="2"/></g><g transform="translate(100 68) skewX(-8)"><rect width="232" height="134" rx="14" fill="#FDFEFE" stroke="#E4EFEB"/><path d="M25 31h48M25 48h35M25 65h43" stroke="#D5E6E2" stroke-width="7" stroke-linecap="round"/><path d="m102 77 24-26 22 8 30-30 22 8" fill="none" stroke="#BCCFAD" stroke-width="2"/><g fill="#8DB9AE"><rect x="104" y="87" width="15" height="25" rx="3"/><rect x="130" y="67" width="15" height="45" rx="3"/><rect x="156" y="51" width="15" height="61" rx="3"/><rect x="182" y="31" width="15" height="81" rx="3" fill="#568D7E"/></g></g><g transform="translate(331 69)"><path d="m35 72 51 58" stroke="#2D625B" stroke-width="18" stroke-linecap="round"/><circle r="51" fill="#628F87"/><circle r="43" fill="#FAFDFC" stroke="#376C63" stroke-width="3"/><g fill="none" stroke="#32685E" stroke-width="3" stroke-linejoin="round"><rect x="-22" y="-12" width="44" height="34" rx="4"/><path d="M-9-12v-7a3 3 0 0 1 3-3H6a3 3 0 0 1 3 3v7M-22-1q22 15 44 0M-3 3h6v8h-6z"/></g></g></svg>'


CSS = """
:root {
  --fow-radius: 14px;
  --fow-space-1: .25rem; --fow-space-2: .5rem; --fow-space-3: .75rem;
  --fow-space-4: 1rem; --fow-space-5: 1.5rem; --fow-space-6: 2rem;
  --fow-control-height: 44px; --fow-card-padding: 1.25rem;
  --fow-shadow: 0 3px 16px rgb(27 52 65 / .035);
  --fow-muted: #526478;
  --fow-heading: #0B1826;
  --fow-ink: #173B38;
}
[data-testid="stAppViewContainer"] { background: #F7F9FB; }
[data-testid="stHeader"] { background: rgb(247 249 251 / .96); }
/* The trusted chart handler has no visible layout content. */
[data-testid="stElementContainer"]:has(> [data-testid="stHtml"] > script[data-fow-hover-loader]) { display: none; }
.stMainBlockContainer {
  /* Preserve Streamlit's native top clearance for its fixed toolbar. */
  max-width: 1640px; padding-inline: clamp(1rem, 3vw, 3rem); padding-bottom: 4rem;
}
h1,h2,h3 { color: var(--fow-heading); letter-spacing: -.035em; text-wrap: balance; font-weight: 700; }
h1 { max-width: 30ch; }
p,li { line-height: 1.55; }
.st-key-page_heading, .st-key-overview_heading { position: relative; isolation: isolate; min-height: 185px; padding-block: .9rem 1.5rem; margin-bottom: .5rem; background: url("__HERO_URI__") no-repeat right center / 430px 195px; }
.st-key-page_heading h1, .st-key-overview_heading h1 { font-size: clamp(2rem, 3.5vw, 3.25rem); line-height: 1.12; padding-block: .35rem .6rem; max-width: 23ch; }
.st-key-page_heading p, .st-key-overview_heading p { max-width: min(70ch, 72%); color: var(--fow-muted); font-size: 1.05rem; }
.st-key-overview_heading h1 { font-size: clamp(2rem, 3.6vw, 3.2rem); line-height: 1.12; max-width: 23ch; }
:is(.st-key-page_heading, .st-key-overview_heading) [data-testid="stCaptionContainer"] p { color: var(--fow-accent, #2F6B5D); font-size: .75rem; font-weight: 700; letter-spacing: .12em; }
[data-testid="stCaptionContainer"] { opacity: 1; }
[data-testid="stMetric"] {
  border: 1px solid var(--fow-border); border-radius: var(--fow-radius);
  background: var(--fow-surface); padding: 1.15rem 1.25rem; min-height: 120px;
  box-shadow: var(--fow-shadow);
}
[data-testid="stMetricLabel"] { font-weight: 550; color: var(--fow-muted); }
[data-testid="stMetricValue"] { color: var(--fow-heading); font-variant-numeric: tabular-nums; letter-spacing: -.04em; font-weight: 700; }
.st-key-overview_metrics { margin-bottom: .5rem; }
.st-key-overview_metrics > [data-testid="stLayoutWrapper"] { flex: 1 1 220px; }
.st-key-overview_metrics [data-testid="stMetricIcon"] { display: grid; place-items: center; flex: 0 0 48px; width: 48px; height: 48px; margin-right: .55rem; border-radius: 15px; font-size: 27px; }
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
[data-testid="stSidebarNav"] a[aria-current="page"] { font-weight: 650; background: #E3EFEC; box-shadow: inset 3px 0 var(--fow-accent, #2F6B5D); }
[data-testid="stSidebarNav"] a:hover { background: #EAF0F1; }
[data-testid="stSidebarNav"] span { overflow-wrap: normal; }
.st-key-workspace_toolbar { padding-bottom: .6rem; margin-bottom: .25rem; min-height: 46px; }
.st-key-workspace_toolbar [data-testid="stCaptionContainer"] p { color: #52666B; font-size: .75rem; font-weight: 650; letter-spacing: .06em; }
/* Own the profile markup; only the popover and sign-out remain native controls. */
[data-testid="stPopoverBody"][aria-label="Account"] {
  width: 288px; min-width: 0; max-width: calc(100vw - 24px);
  padding: var(--fow-card-padding); border: 1px solid #EDF1F7; border-radius: var(--fow-radius);
  background: #fff; box-shadow: 0 14px 35px rgb(44 70 102 / .16);
  overflow: visible;
}
[data-testid="stPopoverBody"][aria-label="Account"]::before {
  content: ""; position: absolute; top: -6px; right: 56px;
  width: 12px; height: 12px; transform: rotate(45deg); background: #fff;
  border-top: 1px solid #EDF1F7; border-left: 1px solid #EDF1F7;
}
.st-key-account_menu { gap: var(--fow-card-padding); }
.account-profile { width: 100%; }
.account-profile h3 {
  margin: 0; padding: 0 0 var(--fow-card-padding); color: #142335;
  font-family: inherit; font-weight: 700; font-size: 1.25rem; line-height: 1.2; letter-spacing: -.4px;
}
.account-profile-identity {
  display: flex; align-items: center; gap: var(--fow-space-4);
  padding: var(--fow-card-padding) 0; border-block: 1px solid #E7EDF5;
}
.account-profile-avatar {
  display: flex; align-items: center; justify-content: center;
  flex: 0 0 48px; height: 48px; border-radius: 50%;
  background: #E0F0E9 url("__ACCOUNT_URI__") no-repeat center / 29px; color: #2F6B5D;
}
.account-profile-details { min-width: 0; }
.account-profile-email { color: #246450; font: inherit; font-weight: 500; font-size: .875rem; line-height: 1.4; overflow-wrap: anywhere; }
.account-profile-role { margin-top: var(--fow-space-1); color: #61778B; font: inherit; font-size: .875rem; line-height: 1.4; }
.st-key-account_menu [data-testid="stButton"] button {
  min-height: var(--fow-control-height); border: 1px solid #C8DED5; background: #EFF7F3;
  border-radius: 8px; color: #2D5147; gap: 10px; font-weight: 600;
}
.st-key-account_menu [data-testid="stButton"] button p { font-size: 1rem; color: #2D5147; }
.st-key-account_menu [data-testid="stButton"] button:hover { background: #E0F0E9; border-color: #A7CCBD; }
.st-key-account_trigger [data-testid="stPopoverButton"] { background: #FFFFFF; border: 1px solid #E0E7EF; border-radius: 8px; }
.st-key-home_next { background: var(--fow-ink); color: white; border: 0; padding: clamp(1.25rem, 3vw, 2rem); margin-block: .5rem 1.25rem; }
.st-key-home_next h3, .st-key-home_next p { color: white; }
.st-key-home_next [data-testid="stCaptionContainer"] p { color: #BDE3D8; font-size: .75rem; letter-spacing: .12em; font-weight: 650; }
.st-key-home_next button[kind="primary"] { background: #F1F8F5; border-color: #F1F8F5; color: #173B38; }
.st-key-home_next button[kind="primary"] p { color: #173B38; }
.st-key-home_next button[kind="primary"]:hover { background: #D9EEE6; border-color: #D9EEE6; }
[class*="st-key-workflow_step_"] { background: white; padding: 1.25rem; gap: .5rem; box-shadow: var(--fow-shadow); }
[class*="st-key-workflow_step_"] h4 { font-size: 1.1rem; }
[class*="st-key-workflow_step_"] [data-testid="stCaptionContainer"] p { color: var(--fow-accent, #2F6B5D); font-size: .75rem; font-weight: 650; }
[class*="st-key-workflow_step_"] [data-testid="stButton"] { margin-top: .5rem; }
[class*="st-key-workflow_step_"] > [data-testid="stElementContainer"]:has([data-testid="stMarkdownContainer"]) { min-height: 3rem; }
.st-key-readiness_summary { border-left: 3px solid var(--fow-review, #A65A24); background: #FFFDF7; padding: 1.25rem; margin-top: 1rem; }
.st-key-readiness_summary h3 { font-size: 1.15rem; }
:is(.st-key-login_shell, .st-key-login_shell_busy) { padding-top: clamp(1rem, 5vh, 4rem); }
:is(.st-key-login_panel, .st-key-login_panel_busy) { padding: clamp(1.25rem, 3vw, 2.25rem); background: #fff; box-shadow: 0 12px 45px rgb(24 51 44 / .06); }
:is(.st-key-login_panel, .st-key-login_panel_busy) h1 { font-size: clamp(1.65rem, 4vw, 2.1rem); }
:is(.st-key-login_status, .st-key-login_status_busy) { min-height: 76px; }
:is(.st-key-login_panel, .st-key-login_panel_busy) [data-testid="stForm"] { padding: 0; border: 0; }
.st-key-workflow_0, .st-key-workflow_3 { gap: 1rem; }
.st-key-workflow_0 > [data-testid="stLayoutWrapper"], .st-key-workflow_3 > [data-testid="stLayoutWrapper"] { flex: 1 1 280px; }
.st-key-settings_form { max-width: 880px; }
[data-testid="stAlert"] p { overflow-wrap: anywhere; }

.fow-breadcrumb { display: flex; align-items: center; gap: 1rem; color: #4F6073; font-size: .85rem; min-height: 42px; }
.fow-breadcrumb strong { color: #152B3B; font-weight: 650; }
.fow-home-mark { display: grid; place-items: center; width: 38px; height: 38px; background: #EAF0F5 url("__HOME_URI__") no-repeat center / 20px; border-radius: 11px; color: #344F60; }
.fow-crumb-separator { color: #93A1AF; font-size: 1.4rem; }
.login-brand-mark { display: grid; place-items: center; width: 56px; height: 56px; border: 1px solid #D9EAE3; border-radius: 17px; background: #EAF5EF url("__BRAND_URI__") no-repeat center / 28px; color: #2F6B5D; margin-bottom: .5rem; }
:is([data-testid="stButton"], [data-testid="stDownloadButton"], [data-testid="stFormSubmitButton"]) button { border-color: #DAE3EA; border-radius: 9px; box-shadow: 0 1px 2px rgb(20 40 50 / .025); }
:is([data-testid="stButton"], [data-testid="stDownloadButton"], [data-testid="stFormSubmitButton"]) button:hover { border-color: #87AF9E; box-shadow: 0 3px 9px rgb(20 60 45 / .06); }
[data-testid="stExpander"] { border: 1px solid #E0E7EF; border-radius: 12px; background: rgb(255 255 255 / .8); box-shadow: 0 1px 5px rgb(20 40 50 / .02); }
[data-testid="stExpander"] details summary { min-height: 46px; font-weight: 550; }
[data-testid="stFileUploader"] { background: #fff; border-radius: 14px; }
[data-testid="stFileUploaderDropzone"] { background: #F5F9F7; border: 1px dashed #B3CFC2; border-radius: 12px; }
[data-testid="stForm"], [data-testid="stVerticalBlockBorderWrapper"] { border-color: var(--fow-border); }
[data-testid="stTabs"] [role="tablist"] { background: #FFF; border: 1px solid #E0E7EF; border-radius: 10px; padding: 4px; gap: 4px; }
[data-testid="stTabs"] [role="tab"][aria-selected="true"] { background: #E5F1EB; color: #245E4F; border-radius: 7px; }
.st-key-analysis_pipeline { margin-block: 0 var(--fow-space-4); align-items: stretch; }
.st-key-analysis_pipeline > [data-testid="stLayoutWrapper"] { flex: 1 1 140px; }
[class*="st-key-pipeline_stage_"] { padding: var(--fow-space-4); border-radius: 11px; min-height: 158px; gap: .35rem; text-align: center; border: 1px solid var(--stage-border); background: var(--stage-bg); }
[class*="st-key-pipeline_stage_"] [data-testid="stMarkdownContainer"] p { font-size: .83rem; line-height: 1.45; }
[class*="st-key-pipeline_stage_"] [data-testid="stCaptionContainer"] p { color: #33495B; font-size: .79rem; }
.st-key-pipeline_stage_1 { --stage-bg: #F3FBF7; --stage-border: #CAEADF; color: #1D6D4E; }
.st-key-pipeline_stage_2 { --stage-bg: #F4F9FF; --stage-border: #CBDEF3; color: #23649A; }
.st-key-pipeline_stage_3 { --stage-bg: #FFF9F3; --stage-border: #F3DFCD; color: #9B5319; }
.st-key-pipeline_stage_4 { --stage-bg: #F8F6FF; --stage-border: #E0D9F6; color: #634494; }
.st-key-pipeline_stage_5 { --stage-bg: #FFF6F6; --stage-border: #F0DADC; color: #9F3B43; }
.st-key-result_metrics { margin-block: .8rem; }
.st-key-result_metrics > [data-testid="stLayoutWrapper"] { flex: 1 1 245px; }
[class*="st-key-result_metric_"] { background: #fff; border: 1px solid #E0E7EF; border-radius: 14px; padding: var(--fow-card-padding); box-shadow: var(--fow-shadow); gap: .5rem; }
[class*="st-key-result_metric_"] [data-testid="stMetric"] { border: 0; background: transparent; box-shadow: none; min-height: 0; padding: 0; }
[class*="st-key-result_metric_"] [data-testid="stMetricValue"] { font-size: 2.4rem; }
[class*="st-key-result_metric_"] [data-testid="stMetric"] { position: relative; padding-left: 68px; }
[class*="st-key-result_metric_"] [data-testid="stMetricIcon"] { position: absolute; top: 0; left: 0; display: grid; place-items: center; width: 48px; height: 48px; border-radius: 15px; font-size: 27px; }
[class*="st-key-result_single_"] [data-testid="stMetric"] { min-height: 144px; }
[class*="st-key-result_single_"] [data-testid="stMetricValue"] { font-size: clamp(2.7rem, 5vw, 3.7rem); }
.st-key-result_chart_controls { align-items: end; margin-block: .4rem 1rem; }
.st-key-result_chart_controls > [data-testid="stLayoutWrapper"] { flex: 1 1 360px; }
.st-key-result_chart_selectors > [data-testid="stLayoutWrapper"] { flex: 1 1 150px; }
.st-key-result_chart_note { min-width: 0; }
.st-key-result_chart_note [data-testid="stCaptionContainer"] p { color: #4C617A; font-size: .83rem; }
.st-key-result_section_toolbar { align-items: center; justify-content: space-between; margin-top: .5rem; }
.st-key-result_section_toolbar h3 { font-size: 1.2rem; padding-bottom: .15rem; }
.st-key-result_sections [data-testid="stButtonGroup"] { background: #FFF; border: 1px solid #DCE5EC; border-radius: 10px; }
.st-key-result_sections [data-testid="stButtonGroup"] button { min-height: 44px; border-radius: 9px; }
[data-testid="stSidebar"] { border-right: 1px solid #E2E9ED; }
[data-testid="stSidebarNav"] a { padding-block: .55rem; }

@media (max-width: 1100px) {
  .st-key-page_heading, .st-key-overview_heading { background-image: none; }
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
    width: auto !important; min-width: min(100%, 170px); flex: 1 1 170px;
  }
}
@media (max-width: 640px) {
  .stMainBlockContainer { padding-inline: 1rem; padding-bottom: 3rem; }
  h1 { font-size: 1.8rem; } h2 { font-size: 1.4rem; }
  .st-key-page_heading, .st-key-overview_heading { background-image: none; min-height: 0; padding-block: .5rem 1rem; }
  .st-key-page_heading p, .st-key-overview_heading p { max-width: 100%; font-size: 1rem; }
  .fow-breadcrumb { gap: .5rem; font-size: .75rem; flex-wrap: wrap; }
  .fow-home-mark { width: 30px; height: 30px; }
  .st-key-analysis_pipeline { gap: var(--fow-space-3); }
  [class*="st-key-pipeline_stage_"] { min-height: 130px; }
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
""".replace("__HERO_URI__", "data:image/svg+xml," + quote(HERO_SVG)).replace(
    "__HOME_URI__", "data:image/svg+xml," + quote(HOME_SVG)).replace(
    "__BRAND_URI__", "data:image/svg+xml," + quote(BRAND_SVG)).replace(
    "__ACCOUNT_URI__", "data:image/svg+xml," + quote(ACCOUNT_SVG))
