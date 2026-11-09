"""Shared presentation only; native controls retain their behavior and accessibility."""
import streamlit as st
from pathlib import Path
from html import escape
from urllib.parse import quote
from .config import VERSION
from contextlib import contextmanager


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
    hero = quote((Path(__file__).parents[1] / "assets" / "job_market_hero.svg").read_text(encoding="utf-8"), safe="")
    market_css = JOB_MARKET_CSS.replace("__JOB_MARKET_HERO_URI__", "data:image/svg+xml," + hero)
    st.html("<style>:root{" + tokens + "}" + CSS + SIDEBAR_CSS.replace("__JOB_MARKET_HERO_URI__", "data:image/svg+xml," + hero) + market_css + PSF_MAPPING_CSS + ALIGNMENT_CSS + REPORTS_CSS + LOADING_CSS + UNMAPPED_CSS + WORKSPACE_CONTENT_CSS + STUDY_CONTENT_CSS + UNAVAILABLE_CSS + RESPONSIVE_CSS + "</style>")
    hover_script = Path(__file__).with_name("chart_hover.js").read_text(encoding="utf-8").replace("__FOW_APP_VERSION__", VERSION)
    st.html('<script data-fow-hover-loader="true">' + hover_script + "</script>", unsafe_allow_javascript=True)


def apply_sidebar_branding():
    root = Path(__file__).parents[1] / "assets"
    st.logo(str(root / "job_market_brand.svg"), size="large",
            icon_image=str(root / "job_market_mark.svg"))


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
    .stMainBlockContainer { visibility: hidden; container-type: normal; }
    [data-testid="stLayoutWrapper"]:has(> .st-key-manual_review_actions) { top: 0; }
    [data-testid="stHeader"], [data-testid="stSidebar"] { display: none; }
    """ if fullscreen else ""
    st.html("<style>" + REVIEW_CSS + focus + "</style>")


@contextmanager
def content_section(title, icon, key):
    with st.container(key=f"content_panel_{key}") as panel:
        st.html('<div class="fow-content-section-heading">'
                f'<span class="material-symbols-rounded" aria-hidden="true">{escape(icon)}</span>'
                f'<h3>{escape(title)}</h3></div>')
        yield panel


def content_metrics(items, key):
    with st.container(horizontal=True, key=f"content_metrics_{key}", gap="medium", wrap=True):
        for index, (label, value, icon) in enumerate(items):
            with st.container(key=f"content_metric_{key}_{index}", width="stretch"):
                st.metric(label, value, icon=f":material/{icon}:")


def content_note(title, text, *, items=(), icon="lightbulb"):
    details = "".join(f"<li>{escape(str(item))}</li>" for item in items)
    st.html('<aside class="fow-content-note">'
            f'<h4><span class="material-symbols-rounded" aria-hidden="true">{escape(icon)}</span>{escape(title)}</h4>'
            f'<p>{escape(text)}</p>' + (f'<ul>{details}</ul>' if details else '') + '</aside>')


def section_heading(title, icon, description):
    st.html('<div class="fow-section-heading">'
            f'<span class="material-symbols-rounded" aria-hidden="true">{escape(icon)}</span>'
            f'<h3>{escape(title)}</h3><p>{escape(description)}</p></div>')


UNAVAILABLE_CSS = """
body:has(.st-key-workspace_unavailable) [data-testid="stAppViewContainer"] { background: #FBF8F6 url("__UNAVAILABLE_WAVES__") no-repeat center bottom / 100% 170px; }
body:has(.st-key-workspace_unavailable) .stMainBlockContainer { width: 100%; max-width: none; padding: 2.5rem 1.5rem 6rem; }
.st-key-workspace_unavailable { width: 100%; max-width: 960px; margin: 0 auto; gap: 1.5rem; text-align: center; }
.st-key-workspace_unavailable [data-testid="stImage"] { margin-inline: auto; max-width: 100%; }
.st-key-workspace_unavailable [data-testid="stHeading"] { display: block; width: 100%; text-align: center; }
.st-key-workspace_unavailable h1 { display: block; width: 100%; max-width: none; text-align: center; color: #78182B; font-size: clamp(2rem,3.5vw,3rem); letter-spacing: -.035em; line-height: 1.15; margin: 0 auto; padding: .4rem 0 0; }
.fow-unavailable-message { margin: 0 auto .6rem; max-width: 78ch; color: #24303D; font-size: 1.05rem; line-height: 1.6; overflow-wrap: anywhere; }
.fow-unavailable-reason { display: grid; grid-template-columns: 70px minmax(0,1fr); align-items: center; gap: 1.5rem; box-sizing: border-box; width: min(100%,760px); margin: .5rem auto; padding: 1.25rem 1.5rem; border-radius: 18px; background: #F8E9ED; text-align: left; }
.fow-unavailable-reason > span { color: #9B2547; font-size: 42px; text-align: center; }
.fow-unavailable-reason > div { border-left: 1px solid #E5C7D0; padding-left: 1.5rem; }
.fow-unavailable-reason h2 { margin: 0 0 .3rem; padding: 0; color: #78182B; font-size: 1.25rem; line-height: 1.3; letter-spacing: -.02em; }
.fow-unavailable-reason p { margin: 0; color: #24303D; font-size: 1rem; line-height: 1.5; }
.st-key-workspace_unavailable_actions { justify-content: center; margin-top: .75rem; gap: 1rem; }
.st-key-workspace_unavailable_actions button { min-height: 50px; border-radius: 10px; }
.st-key-workspace_unavailable_actions button[kind="primary"] { background: #86142D; border-color: #86142D; }
.st-key-workspace_unavailable_actions button[kind="secondary"] { background: #fff; border-color: #DFD2CF; color: #24303D; }
@media (max-width: 600px) {
 body:has(.st-key-workspace_unavailable) .stMainBlockContainer { padding: 1.5rem 1rem 4rem; }
 .st-key-workspace_unavailable { gap: 1.2rem; }
 .fow-unavailable-reason { grid-template-columns: 38px minmax(0,1fr); gap: .8rem; padding: 1rem; }
 .fow-unavailable-reason > span { font-size: 32px; }
 .fow-unavailable-reason > div { padding-left: .8rem; }
 .fow-unavailable-message,.fow-unavailable-reason p { font-size: .95rem; }
 .st-key-workspace_unavailable_actions > [data-testid="stLayoutWrapper"] { width: 100% !important; }
 .st-key-workspace_unavailable_actions button { width: 100%; }
}
""".replace("__UNAVAILABLE_WAVES__", "data:image/svg+xml," + quote(
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1800 170" preserveAspectRatio="none">'
    '<path d="M0 60C170 30 170 130 360 140L650 170H0Z" fill="#F3E1E7"/>'
    '<path d="M0 115C150 110 160 160 310 170H0Z" fill="#E5BFCB"/>'
    '<path d="M1300 170C1530 170 1540 25 1800 0V170Z" fill="#F7E8ED"/>'
    '<path d="M1430 170C1570 150 1640 130 1800 58V170Z" fill="#D6A33D"/>'
    '<path d="M1350 170C1550 180 1600 140 1800 65V170Z" fill="#B56A80"/>'
    '</svg>', safe=""))


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
/* Suppress old copies and the native SVG popup only when HTML hover is active. */
[data-testid="stPlotlyChart"] [data-fow-retained-hover],
svg[data-fow-sticky-tooltip="true"] { display: none !important; }
[data-testid="stPlotlyChart"] .hoverlayer,
[data-testid="stPlotlyChart"] .hoverlayer .hovertext { pointer-events: none !important; }
[data-testid="stPlotlyChart"] [data-fow-html-hover="true"] .hoverlayer { opacity: 0 !important; }
[data-testid="stPlotlyChart"] [data-fow-html-hover="true"] .hoverlayer * { pointer-events: none !important; }
.fow-chart-tooltip { position: fixed; z-index: 1000; width: max-content; max-width: min(380px, calc(100vw - 24px)); box-sizing: border-box; padding: .6rem .75rem; border: 1px solid #4D1020; border-radius: 7px; background: #4D1020; color: #fff; box-shadow: 0 4px 16px #24101A24; pointer-events: none; font: 13px/1.45 Arial, sans-serif; overflow-wrap: anywhere; }
.fow-chart-tooltip[hidden] { display: none; }
.fow-chart-tooltip > div:first-child { font-weight: 700; }
.stMainBlockContainer {
  /* Preserve Streamlit's native top clearance for its fixed toolbar. */
  width: 100%; max-width: none; padding-inline: clamp(1rem, 3vw, 2rem); padding-bottom: 4rem;
}
body:has(.st-key-workspace_toolbar) [data-stale="true"], [data-testid="stSidebar"] [data-stale="true"] { opacity: 1 !important; filter: none !important; transition: none !important; }
/* Retained sign-in page elements must not occupy the loading workspace. */
body:has(.st-key-workspace_toolbar) :is(.st-key-login_shell, .st-key-login_shell_busy) { display: none !important; }
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
.st-key-overview_metric_1 [data-testid="stMetricIcon"],
.st-key-overview_metric_2 [data-testid="stMetricIcon"],
.st-key-overview_metric_4_ready [data-testid="stMetricIcon"],
.st-key-result_metric_1 [data-testid="stMetricIcon"] { background: var(--fow-accent-bg); color: var(--fow-accent); }
.st-key-overview_metric_3 [data-testid="stMetricIcon"] { background: var(--fow-framework-bg); color: var(--fow-framework); }
.st-key-overview_metric_4_pending [data-testid="stMetricIcon"],
.st-key-result_metric_3 [data-testid="stMetricIcon"] { background: var(--fow-review-bg); color: var(--fow-review); }
.st-key-result_metric_2 [data-testid="stMetricIcon"] { background: var(--fow-info-bg); color: var(--fow-info); }
.st-key-result_metric_4 [data-testid="stMetricIcon"] { background: var(--fow-framework-bg); color: var(--fow-framework); }
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
.st-key-workspace_toolbar { padding-bottom: .6rem; margin-bottom: .25rem; min-height: 46px; }
.st-key-workspace_toolbar [data-testid="stCaptionContainer"] p { color: var(--fow-muted); font-size: .75rem; font-weight: 650; letter-spacing: .06em; }
/* Own the profile markup; only the popover and sign-out remain native controls. */
[data-testid="stPopoverBody"]:has(.st-key-account_menu) {
  box-sizing: border-box; width: min(320px, calc(100vw - 24px)); min-width: 0;
  max-height: calc(100dvh - 80px); overflow-y: auto;
  padding: var(--fow-card-padding); border: 1px solid var(--fow-border); border-radius: var(--fow-radius);
  background: var(--fow-surface); box-shadow: 0 12px 28px rgb(36 48 61 / .12);
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
/* Native input wrappers draw the focus border around both the email icon and text. */
:is(.st-key-login_panel, .st-key-login_panel_busy) [data-testid="stTextInput"] input:focus-visible {
  outline: none; outline-offset: 0;
}
.st-key-workflow_0, .st-key-workflow_3 { gap: 1rem; }
.st-key-workflow_0 > [data-testid="stLayoutWrapper"], .st-key-workflow_3 > [data-testid="stLayoutWrapper"] { flex: 1 1 280px; }
.st-key-settings_form { width: 100%; max-width: none; }
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
[data-testid="stExpander"]:has([class*="st-key-chart_evidence_"]) { margin-top: .6rem; border: 0; border-top: 1px solid var(--fow-border); border-radius: 0; background: transparent; }
[data-testid="stExpander"]:has([class*="st-key-chart_evidence_"]) details summary { min-height: 44px; padding-inline: .35rem; color: var(--fow-accent); }
.fow-chart-evidence-mobile-hint { display: none; }
@media (max-width: 640px) { .fow-chart-evidence-mobile-hint { display: block; color: var(--fow-muted); font-size: .75rem; } }
[data-testid="stFileUploader"] { background: var(--fow-surface); border-radius: var(--fow-radius); }
[data-testid="stFileUploaderDropzone"] { background: var(--fow-soft); border: 1px dashed #C98E99; border-radius: var(--fow-radius); }
[data-testid="stForm"], [data-testid="stVerticalBlockBorderWrapper"] { border-color: var(--fow-border); }
[data-testid="stTabs"] [role="tablist"] { background: var(--fow-surface); border: 1px solid var(--fow-border); border-radius: var(--fow-radius); padding: 4px; gap: 4px; }
[data-testid="stTabs"] [role="tab"][aria-selected="true"] { background: var(--fow-accent-bg); color: var(--fow-accent); border-radius: 7px; }
  .st-key-analysis_pipeline { margin-block: 0 var(--fow-space-4); padding: 0; align-items: stretch; background: transparent; }
.st-key-analysis_pipeline > [data-testid="stLayoutWrapper"] { flex: 1 1 140px; min-width: 0; }
  :is(.st-key-pipeline_stage_1, .st-key-pipeline_stage_2, .st-key-pipeline_stage_3, .st-key-pipeline_stage_4, .st-key-pipeline_stage_5) { position: relative; padding: var(--fow-space-2) var(--fow-space-3); border: 1px solid var(--fow-border); border-radius: 9px; min-height: 76px; gap: .25rem; text-align: left; background: var(--fow-surface); box-shadow: var(--fow-shadow); }
  :is(.st-key-pipeline_stage_1, .st-key-pipeline_stage_2, .st-key-pipeline_stage_3, .st-key-pipeline_stage_4):after { content: "›"; position: absolute; right: -.9rem; top: 50%; z-index: 2; transform: translate(50%,-50%); color: var(--fow-muted); font-size: 1.25rem; font-weight: 700; }
.fow-pipeline-card { display: flex; flex-direction: column; gap: .18rem; min-height: 4.6rem; text-align: left; }
.fow-pipeline-visual { display: flex; align-items: center; gap: .45rem; min-height: 1.45rem; margin-bottom: .08rem; }
.fow-pipeline-number { display: grid; place-items: center; flex: 0 0 1.35rem; width: 1.35rem; height: 1.35rem; border-radius: 50%; font-size: .7rem; font-weight: 800; }
.fow-pipeline-icon { display: grid; place-items: center; width: 1.5rem; height: 1.5rem; border-radius: 6px; font-family: "Material Symbols Rounded"; font-size: 1.15rem; line-height: 1; font-variation-settings: "FILL" 0, "wght" 500, "GRAD" 0, "opsz" 20; }
.fow-pipeline-stage-1 { --stage-color: #168260; --stage-tint: #E7F4EE; }
.fow-pipeline-stage-2 { --stage-color: #2876B7; --stage-tint: #EAF3FB; }
.fow-pipeline-stage-3 { --stage-color: #C96819; --stage-tint: #FFF1E5; }
.fow-pipeline-stage-4 { --stage-color: #6946B5; --stage-tint: #F1EDFA; }
.fow-pipeline-stage-5 { --stage-color: #BD3F43; --stage-tint: #FBECEE; }
.fow-pipeline-card .fow-pipeline-number { color: var(--stage-color); background: var(--stage-tint); }
.fow-pipeline-card .fow-pipeline-icon { color: var(--stage-color); background: var(--stage-tint); }
.fow-pipeline-card strong { display: block; color: var(--fow-ink); font-size: .8rem; line-height: 1.2; }
.fow-pipeline-detail { display: block; color: var(--fow-muted); font-size: .69rem; line-height: 1.25; }
.st-key-result_metrics { margin-block: .8rem; }
.st-key-result_metrics > [data-testid="stLayoutWrapper"] { flex: 1 1 245px; }
[class*="st-key-result_metric_"] { background: var(--fow-surface); border: 1px solid var(--fow-border); border-radius: var(--fow-radius); padding: var(--fow-card-padding); box-shadow: var(--fow-shadow); gap: .5rem; }
[class*="st-key-result_metric_"] [data-testid="stMetric"] { border: 0; background: transparent; box-shadow: none; min-height: 0; padding: 0; }
[class*="st-key-result_metric_"] [data-testid="stMetricValue"] { font-size: 2.4rem; }
[class*="st-key-result_metric_"] [data-testid="stMetric"] { position: relative; padding-left: 68px; }
[class*="st-key-result_metric_"] [data-testid="stMetricIcon"] { position: absolute; top: 0; left: 0; display: grid; place-items: center; width: 48px; height: 48px; border-radius: 12px; font-size: 27px; }
[class*="st-key-result_single_"] [data-testid="stMetric"] { min-height: 144px; }
[class*="st-key-result_single_"] [data-testid="stMetricValue"] { font-size: clamp(2.7rem, 5vw, 3.7rem); }
.st-key-job_market_education [data-testid="stMetricValue"] { color: #86142D; }
[class*="st-key-result_chart_controls_"] { align-items: end; margin-block: .4rem 1rem; }
[class*="st-key-result_chart_controls_"] > [data-testid="stLayoutWrapper"] { flex: 1 1 360px; }
[class*="st-key-result_chart_selectors_"] > [data-testid="stLayoutWrapper"] { flex: 1 1 150px; }
[class*="st-key-result_chart_note_"] { min-width: 0; }
[class*="st-key-result_chart_note_"] [data-testid="stCaptionContainer"] p { color: var(--fow-muted); font-size: .83rem; }
.st-key-result_section_toolbar { align-items: center; justify-content: space-between; margin-top: .5rem; }
.st-key-result_section_toolbar h3 { font-size: 1.2rem; padding-bottom: .15rem; }
  [data-testid="stSidebar"] { border-right: 1px solid var(--fow-border); }

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
  :is(.st-key-pipeline_stage_1, .st-key-pipeline_stage_2, .st-key-pipeline_stage_3, .st-key-pipeline_stage_4, .st-key-pipeline_stage_5) { min-height: 80px; }
}
@media (max-width: 640px) {
  .stMainBlockContainer { padding-inline: 1rem; padding-bottom: 3rem; }
  h1 { font-size: 1.8rem; } h2 { font-size: 1.4rem; }
  .st-key-page_heading, .st-key-overview_heading { padding-block: .35rem .75rem; }
  .st-key-page_heading p, .st-key-overview_heading p { max-width: 100%; font-size: 1rem; }
  .fow-breadcrumb { gap: .5rem; font-size: .75rem; flex-wrap: wrap; }
  .fow-home-mark { width: 30px; height: 30px; }
  .st-key-analysis_pipeline { gap: var(--fow-space-3); }
  :is(.st-key-pipeline_stage_1, .st-key-pipeline_stage_2, .st-key-pipeline_stage_3, .st-key-pipeline_stage_4, .st-key-pipeline_stage_5) { min-height: 82px; }
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


SIDEBAR_CSS = """
[data-testid="stSidebar"] { width: 232px !important; min-width: 232px !important; max-width: 232px !important; flex: 0 0 232px !important; background: #FBF8F6; border-right: 1px solid #E3D9D7; }
[data-testid="stSidebarContent"] { padding: 0 .75rem 1rem; }
[data-testid="stSidebarHeader"] { position: relative; padding: .75rem .35rem 1.7rem; margin-bottom: .35rem; }
[data-testid="stSidebarHeader"] { display: flex; align-items: center; gap: .4rem; }
[data-testid="stSidebarHeader"] > div:first-child { flex: 1 1 auto; min-width: 0; }
[data-testid="stSidebarHeader"] img { width: 100% !important; height: auto !important; max-width: 174px !important; max-height: 56px !important; object-fit: contain; }
[data-testid="stSidebarCollapseButton"] { flex: 0 0 28px; position: static; margin: 0; }
[data-testid="stSidebarResizeHandle"], [data-testid="stSidebar"] div:has(> [data-testid="stSidebarResizeHandle"]) { display: none; }
[data-testid="stSidebarHeader"]::after { content: ""; position: absolute; inset: auto -.8rem 0; height: 24px; background: linear-gradient(157deg,#78182B 0 29%,#D6A33D 29.5% 42%,transparent 42.5%); pointer-events: none; }
[data-testid="stSidebarNav"] { margin: 0; padding: 0; }
[data-testid="stSidebarNavItems"] { padding: 0; gap: 0 !important; }
[data-testid="stSidebarNavItems"] > div { border-bottom: 1px solid #E4DAD7; padding-block: .55rem .65rem; margin: 0 !important; }
[data-testid="stNavSectionHeader"] { min-height: 30px; margin: 0 0 .15rem !important; padding: .2rem .5rem; }
[data-testid="stNavSectionHeader"] > span, [data-testid="stNavSectionHeader"] [data-testid="stMarkdownContainer"] { white-space: normal; overflow: visible; }
[data-testid="stNavSectionHeader"] p { color: #78182B; font-size: .82rem; font-weight: 700; line-height: 1.3; margin: 0; }
[data-testid="stSidebarNavItems"] li, [data-testid="stSidebarNavLinkContainer"] { margin: 0 !important; padding: 0 !important; }
[data-testid="stSidebarNav"] [data-testid="stSidebarNavLink"] { box-sizing: border-box; display: grid !important; grid-template-columns: 24px minmax(0,1fr); align-items: center !important; gap: .6rem; min-height: 40px; width: 100%; padding: .45rem .5rem !important; margin: 2px 0; border: 1px solid transparent; border-radius: 7px; box-shadow: none; text-decoration: none; color: #24303D; transition: background-color .14s ease,color .14s ease; }
[data-testid="stSidebarNavLink"] > span:first-child { display: inline-flex !important; align-items: center; justify-content: center; flex: none; width: 24px; height: 24px; margin: 0; line-height: 1; }
[data-testid="stSidebarNavLink"] > span:first-child > span { display: inline-flex; align-items: center; justify-content: center; line-height: 1; }
[data-testid="stSidebarNavLink"] [data-testid="stIconMaterial"] { display: block; width: 24px; height: 24px; font-size: 22px; font-weight: 400 !important; line-height: 24px; color: inherit; }
[data-testid="stSidebarNavLink"] > span:last-child { display: block; min-width: 0; align-self: center; margin: 0; padding: 0; white-space: normal; overflow: visible; font-size: .8rem; line-height: 1.3; }
[data-testid="stSidebarNav"] [data-testid="stSidebarNavLink"] > span, [data-testid="stSidebarNav"] [data-testid="stSidebarNavLink"] > span:first-child span { color: inherit !important; }
[data-testid="stSidebarNav"] [data-testid="stSidebarNavLink"] p { font-size: .8rem; line-height: 1.3; font-weight: 500; color: inherit; margin: 0; white-space: normal; }
[data-testid="stSidebarNav"] [data-testid="stSidebarNavLink"]:hover:not([aria-current="page"]) { color: #78182B !important; background: #F4E7E9; border-color: #EBD4DA; }
[data-testid="stSidebarNav"] [data-testid="stSidebarNavLink"][aria-current="page"], [data-testid="stSidebarNav"] [data-testid="stSidebarNavLink"][aria-current="page"]:hover { color: #fff !important; background: #78182B; border-color: #78182B; box-shadow: none; }
[data-testid="stSidebarNavLink"][aria-current="page"] p { font-weight: 650 !important; }
[data-testid="stSidebarNavLink"][aria-current="page"] [data-testid="stIconMaterial"] { color: #fff !important; }
[data-testid="stSidebarNav"] [data-testid="stSidebarNavLink"]:focus-visible { outline: 2px solid #A8751C; outline-offset: 2px; }
[data-testid="stSidebar"] [data-testid="stCaptionContainer"] p { font-size: .75rem; color: #62585D; line-height: 1.4; }
[data-testid="stSidebar"] [data-testid="stExpander"] { border-color: #D9CFCC; border-radius: 8px; background: #FBF8F6; }
[data-testid="stSidebar"] [data-testid="stExpander"] details summary { min-height: 44px; padding: .5rem; }
[data-testid="stSidebar"] [data-testid="stExpander"] details summary p { font-size: .8rem; font-weight: 600; }
[data-testid="stSidebar"] [data-testid="stButton"] button { min-height: 44px; font-size: .8rem; }
[data-testid="stSidebarUserContent"]::after { content: ""; display: block; height: 150px; margin: 2rem -.75rem -1rem; background: url("__JOB_MARKET_HERO_URI__") no-repeat right bottom / auto 150px; opacity: .65; pointer-events: none; }
"""


JOB_MARKET_CSS = """
.material-symbols-rounded { font-family: "Material Symbols Rounded"; font-weight: 400; font-style: normal; line-height: 1; letter-spacing: normal; text-transform: none; white-space: nowrap; font-feature-settings: "liga"; -webkit-font-smoothing: antialiased; }
body:has(:is(.st-key-page_heading, .st-key-overview_heading, .st-key-job_market_heading, .st-key-psf_mapping_heading, .st-key-employer_psf_heading)) [data-testid="stHeader"] { background: transparent; }
body:has(:is(.st-key-page_heading, .st-key-overview_heading, .st-key-job_market_heading, .st-key-psf_mapping_heading, .st-key-employer_psf_heading)) [data-testid="stToolbar"] { margin-right: 135px; }
body:has(:is(.st-key-page_heading, .st-key-overview_heading, .st-key-job_market_heading, .st-key-psf_mapping_heading, .st-key-employer_psf_heading)) [data-testid="stAppViewContainer"] { background: #FBF8F6; }
.stMainBlockContainer:has(:is(.st-key-page_heading, .st-key-overview_heading, .st-key-job_market_heading, .st-key-psf_mapping_heading, .st-key-employer_psf_heading)) { width: 100% !important; max-width: none !important; margin: 0 !important; padding: .5rem 1.35rem 2rem !important; font-size: .875rem; color: #171923; }
.stMainBlockContainer:has(:is(.st-key-page_heading, .st-key-overview_heading, .st-key-job_market_heading, .st-key-psf_mapping_heading, .st-key-employer_psf_heading)) > [data-testid="stVerticalBlock"] { gap: .7rem; }
body:has(:is(.st-key-page_heading, .st-key-overview_heading, .st-key-job_market_heading, .st-key-psf_mapping_heading, .st-key-employer_psf_heading)) .fow-breadcrumb { min-height: 36px; gap: .65rem; color: #171923; font-size: .76rem; }
body:has(:is(.st-key-page_heading, .st-key-overview_heading, .st-key-job_market_heading, .st-key-psf_mapping_heading, .st-key-employer_psf_heading)) .fow-home-mark { width: 25px; height: 25px; border-radius: 0; background-color: transparent; background-size: 18px; }
.st-key-workspace_toolbar { min-height: 36px; padding: 0; margin: 0; }
.stMainBlockContainer:has(:is(.st-key-page_heading, .st-key-overview_heading, .st-key-job_market_heading, .st-key-psf_mapping_heading, .st-key-employer_psf_heading)) [data-testid="stLayoutWrapper"]:has(> .st-key-workspace_toolbar) { position: sticky; top: 0; z-index: 50; background: #FBF8F6; }
.st-key-account_trigger button { min-height: 36px; padding-block: .25rem; }
:is(.st-key-page_heading, .st-key-overview_heading, .st-key-job_market_heading, .st-key-psf_mapping_heading, .st-key-employer_psf_heading) { position: relative; isolation: isolate; min-height: 104px; margin: 0 -1.35rem .05rem; padding: .3rem 1.35rem .7rem; overflow: hidden; border-bottom: 1px solid #E7DEDB; }
:is(.st-key-page_heading, .st-key-overview_heading, .st-key-job_market_heading, .st-key-psf_mapping_heading, .st-key-employer_psf_heading)::before { content: ""; position: absolute; z-index: -1; inset: -2.5rem 0 0; background: url("__JOB_MARKET_HERO_URI__") no-repeat right bottom / auto 130px; pointer-events: none; }
:is(.st-key-page_heading, .st-key-overview_heading, .st-key-job_market_heading, .st-key-psf_mapping_heading, .st-key-employer_psf_heading) h1 { max-width: 100%; color: #78182B; background: none; -webkit-text-fill-color: #78182B; font-size: clamp(1.9rem, 2.8vw, 2.5rem); line-height: 1.12; letter-spacing: -.035em; margin: 0; padding: .05rem 0 .25rem; font-weight: 800; }
:is(.st-key-page_heading, .st-key-overview_heading, .st-key-job_market_heading, .st-key-psf_mapping_heading, .st-key-employer_psf_heading) [data-testid="stCaptionContainer"] p { color: #78182B; font-size: .7rem; font-weight: 750; letter-spacing: .08em; }
:is(.st-key-page_heading, .st-key-overview_heading, .st-key-job_market_heading, .st-key-psf_mapping_heading, .st-key-employer_psf_heading) [data-testid="stMarkdownContainer"] p { color: #171923; font-size: .8rem; max-width: 78ch; line-height: 1.35; }
.fow-analysis-pipeline { box-sizing: border-box; width: 100%; min-width: 0; container: pipeline / inline-size; margin: .25rem 0 .5rem; }
.fow-analysis-pipeline h2 { font-size: 1rem; letter-spacing: -.02em; color: #171923; margin: 0 0 .65rem; padding: 0; }
.fow-analysis-pipeline ol { display: grid; grid-template-columns: repeat(5,minmax(0,1fr)); gap: 1.1rem; align-items: stretch; list-style: none; padding: 0; margin: 0; }
.fow-analysis-pipeline li { position: relative; display: flex; align-items: center; gap: .65rem; box-sizing: border-box; min-width: 0; min-height: 88px; padding: .75rem .7rem; border: 1px solid #E2DAD7; border-radius: 10px; background: #FCF9F7; box-shadow: 0 1px 1px #4D102009; }
.fow-analysis-pipeline li + li::before { content: "›"; position: absolute; left: -.95rem; top: 50%; transform: translateY(-50%); color: #78182B; font-size: 1.45rem; }
.fow-analysis-pipeline li > span { flex: 0 0 28px; width: 28px; color: #8B1630; font-size: 28px; line-height: 1; }
.fow-analysis-pipeline li > div { min-width: 0; }
.fow-analysis-pipeline strong { display: block; font-size: .79rem; color: #171923; line-height: 1.25; margin-bottom: .3rem; overflow-wrap: anywhere; }
.fow-analysis-pipeline p { font-size: .71rem; line-height: 1.4; margin: 0; color: #394150; overflow-wrap: anywhere; }
@container pipeline (max-width: 950px) { .fow-analysis-pipeline ol { grid-template-columns: repeat(3,minmax(0,1fr)); gap: .65rem; } .fow-analysis-pipeline li::before { display: none; } }
@container pipeline (max-width: 620px) { .fow-analysis-pipeline ol { grid-template-columns: repeat(2,minmax(0,1fr)); } }
@container pipeline (max-width: 380px) { .fow-analysis-pipeline ol { grid-template-columns: minmax(0,1fr); } }
.st-key-result_metrics { gap: .9rem; margin: .35rem 0 .1rem; flex-wrap: nowrap !important; }
.st-key-result_metrics > [data-testid="stLayoutWrapper"] { min-width: 0 !important; width: auto !important; flex: 1 1 0 !important; }
[class*="st-key-result_metric_"] { box-sizing: border-box; min-height: 60px; padding: .3rem .65rem !important; border: 1px solid #DCD2D0; border-radius: 10px; background: linear-gradient(125deg,#FEFCFA,#F8F0EC); box-shadow: 0 2px 2px #4D102010; }
[class*="st-key-result_metric_"] [data-testid="stMetric"] { border: 0; padding: 0; background: transparent; min-height: 0; box-shadow: none; }
[class*="st-key-result_metric_"] [data-testid="stMetric"] > div { display: flex; flex-direction: column; align-items: flex-start; justify-content: center; position: relative; padding-left: 53px; min-height: 48px; }
[class*="st-key-result_metric_"] [data-testid="stMetricValue"] { order: -1; font-size: 1.85rem; font-weight: 800; line-height: 1.1; color: #86142D; margin: 0; }
[class*="st-key-result_metric_"] [data-testid="stMetricLabel"] { width: 100%; min-height: 0; margin: .15rem 0 0; display: block; }
[class*="st-key-result_metric_"] [data-testid="stMetricLabel"] > div { justify-content: flex-start !important; }
[class*="st-key-result_metric_"] [data-testid="stMetricLabel"] > div > span { position: absolute; inset: 0; pointer-events: none; }
[class*="st-key-result_metric_"] [data-testid="stMetricLabel"] p { font-size: .68rem; color: #171923; line-height: 1.25; margin: 0; }
[class*="st-key-result_metric_"] [data-testid="stMetricIcon"] { position: absolute; top: 50%; left: 1px; transform: translateY(-50%); display: grid; place-items: center; width: 37px; height: 46px; background: none; color: #8B1630; font-size: 30px; border-radius: 8px; }
.st-key-result_metric_1 [data-testid="stMetricIcon"] { width: 52px; height: 60px; left: -.65rem; color: #fff; background: #86142D; border-radius: 9px; }
[class*="st-key-result_chart_controls_"] { gap: .8rem; margin: 0; align-items: end; }
[class*="st-key-result_chart_controls_"] > [data-testid="stLayoutWrapper"] { min-width: 0; flex: 1 1 0; }
[class*="st-key-result_chart_controls_"] > [data-testid="stLayoutWrapper"]:has([class*="st-key-result_chart_selectors_"]) { flex: 1.25 1 0; }
[class*="st-key-result_chart_selectors_"] { gap: .8rem; }
[class*="st-key-result_chart_selectors_"] > [data-testid="stElementContainer"] { min-width: 0; flex: 1 1 0; width: auto !important; }
[class*="st-key-result_chart_controls_"] label p { font-size: .74rem; color: #171923; }
[class*="st-key-result_chart_note_"] { display: grid !important; grid-template-columns: 18px minmax(0,1fr); column-gap: .5rem; align-items: start; padding: .35rem 0; }
[class*="st-key-result_chart_note_"]::before { content: "info"; grid-column: 1; grid-row: 1; display: block; width: 18px; height: 18px; margin-top: .05rem; font: 18px/1 "Material Symbols Rounded"; color: #8B1630; }
[class*="st-key-result_chart_note_"] > * { grid-column: 2; min-width: 0; }
[class*="st-key-result_chart_note_"] [data-testid="stCaptionContainer"] p { margin: 0; color: #394150; font-size: .78rem; line-height: 1.45; }
.st-key-result_title_exploration_filters > [data-testid="stElementContainer"], .st-key-result_psf_controls > [data-testid="stElementContainer"] { width: auto !important; min-width: 0; flex: 1 1 0; }
.st-key-result_psf_controls { width: 100%; max-width: none; margin: 0; gap: .7rem; flex-wrap: wrap; }
.st-key-result_psf_controls > [data-testid="stLayoutWrapper"] { min-width: min(100%, 220px); flex: 1 1 220px; max-width: 420px; }
.st-key-result_sections > div > [role="tablist"] > [role="tab"] { display: flex; flex: 1 1 0; align-items: center; justify-content: center; min-height: var(--fow-control-height); gap: .5rem; border-radius: 7px; text-align: center; }
.st-key-result_sections > div > [role="tablist"] > [role="tab"] > div { display: flex; align-items: center; justify-content: center; }
.st-key-result_sections > div > [role="tablist"] > [role="tab"]::before { display: inline-flex; flex: 0 0 21px; align-items: center; justify-content: center; width: 21px; height: 21px; font: 21px/1 "Material Symbols Rounded"; }
.st-key-result_sections > div > [role="tablist"] > [role="tab"]:nth-of-type(1)::before { content: "work"; }
.st-key-result_sections > div > [role="tablist"] > [role="tab"]:nth-of-type(2)::before { content: "person_pin_circle"; }
.st-key-result_sections > div > [role="tablist"] > [role="tab"]:nth-of-type(3)::before { content: "school"; }
.st-key-result_sections > div > [role="tablist"] > [role="tab"]:nth-of-type(4)::before { content: "layers"; }
.st-key-result_sections > div > [role="tablist"] > [role="tab"][aria-selected="true"] { background: var(--fow-accent); color: #fff; }
.st-key-job_market_section_psf_aai { min-width: 0; width: 100%; }
.st-key-job_market_section_psf_aai [data-testid="stColumn"] { min-width: 0; }
.st-key-job_market_section_psf_aai [data-testid="stPlotlyChart"] { max-width: 100%; }
.st-key-research_results_content:has(.fow-loading[role="status"]) .st-key-research_results_content_body { visibility: hidden; height: 0; overflow: hidden; }
body:has(.st-key-job_market_heading) [data-testid="stHeading"] h3 { display: flex; align-items: center; column-gap: .6rem; line-height: 1.35; padding-block: .2rem .45rem; }
body:has(.st-key-job_market_heading) [data-testid="stHeadingIconWrapper"] { display: inline-flex; align-items: center; justify-content: center; flex: 0 0 28px; width: 28px; height: 30px; margin: 0; overflow: visible; }
body:has(.st-key-job_market_heading) [data-testid="stHeadingIcon"] { width: 28px; height: 28px; font-size: 25px; line-height: 28px; }
body:has(:is(.st-key-page_heading, .st-key-overview_heading, .st-key-job_market_heading, .st-key-psf_mapping_heading, .st-key-employer_psf_heading)) h3 { font-size: 1.02rem; letter-spacing: -.025em; color: #171923; padding-block: .05rem .25rem; }
body:has(:is(.st-key-page_heading, .st-key-overview_heading, .st-key-job_market_heading, .st-key-psf_mapping_heading, .st-key-employer_psf_heading)) h3 [data-testid="stIconMaterial"] { color: #8B1630; font-size: 25px; }
.stMain [data-testid="stHeadingIcon"] { color: #86142D; font-size: 25px; }
:is([data-testid="stMain"], [data-testid="stSidebar"]) [data-testid="stExpander"] details > summary :is([data-testid="stExpanderIcon"], [data-testid="stIconMaterial"]) { color: #86142D !important; }
[class*="st-key-job_market_featured_"], .st-key-job_market_title_overview, .st-key-job_market_family_section, .st-key-job_market_title_section { padding: 1rem 1.15rem !important; border: 1px solid #D9CFCC; border-radius: 11px; background: #FCF9F7; }
[class*="st-key-job_market_embedded_"] [data-testid="stPlotlyChart"] { box-shadow: none; background: transparent; }
.st-key-job_market_qualification_summary { padding: 1rem 1.15rem !important; border: 1px solid #D9CFCC; border-radius: 11px; background: #FCF9F7; box-shadow: 0 1px 2px #4D102008; margin: 0; }
[class*="st-key-job_market_featured_"] [data-testid="stPlotlyChart"] { background: transparent; box-shadow: none; }
[class*="st-key-job_market_featured_"] [data-testid="stHorizontalBlock"] { gap: 1rem; }
.fow-key-insight { min-width: 0; padding: .8rem; border: 1px solid #E2D6D1; border-radius: 10px; background: #F9F2EE; color: #171923; }
.fow-key-insight h3 { display: flex; align-items: center; gap: .5rem; margin: 0 0 .65rem; color: #86142D !important; font-size: 1rem; }
.fow-key-insight h3 > span { display: inline-flex; align-items: center; justify-content: center; flex: 0 0 28px; width: 28px; height: 28px; font-size: 24px; line-height: 1; color: #8B1630; }
.fow-key-insight p { margin: .2rem 0; font-size: .82rem; line-height: 1.35; overflow-wrap: anywhere; }
.fow-key-insight h4 { margin: .8rem 0 .5rem; padding-top: .65rem; border-top: 1px solid #DDCECA; color: #86142D; font-size: .92rem; }
.fow-key-insight ol { list-style: none; counter-reset: rank; padding: 0; margin: 0; }
.fow-key-insight li { counter-increment: rank; display: grid; grid-template-columns: 1.3rem minmax(0,1fr) auto; gap: .4rem; align-items: center; padding: .25rem 0; font-size: .7rem; line-height: 1.3; }
.fow-key-insight li::before { content: counter(rank); display: grid; place-items: center; width: 1.25rem; height: 1.25rem; border-radius: 50%; background: #86142D; color: #fff; font-size: .66rem; font-weight: 700; }
.fow-key-insight li strong { font-weight: 500; white-space: nowrap; }
.fow-role-distribution { display: flex; align-items: center; justify-content: center; gap: .8rem; margin-top: .8rem; flex-wrap: wrap; }
.fow-role-donut { display: grid; place-items: center; flex: 0 0 116px; width: 116px; height: 116px; border-radius: 50%; }
.fow-role-donut > span { display: flex; flex-direction: column; align-items: center; justify-content: center; width: 76px; height: 76px; border-radius: 50%; background: #FCF9F7; }
.fow-role-donut strong { font-size: 1.7rem; line-height: 1; font-weight: 800; }
.fow-role-donut small { font-size: .65rem; margin-top: .3rem; }
.fow-role-distribution ul { list-style: none; padding: 0; margin: 0; }
.fow-role-distribution li { display: flex; gap: .4rem; font-size: .7rem; padding: .25rem 0; }
.fow-role-distribution li::before { display: none; }
.fow-role-distribution i { flex: 0 0 11px; width: 11px; height: 11px; margin-top: .15rem; }
.fow-role-distribution li small { display: block; font-size: .65rem; }
.st-key-job_market_title_overview, .st-key-job_market_family_section, .st-key-job_market_title_section { padding: .65rem !important; border: 1px solid #D9CFCC; border-radius: 11px; background: #FCF9F7; }
[class*="st-key-job_market_embedded_"] [data-testid="stPlotlyChart"] { box-shadow: none; background: transparent; }
.st-key-job_market_qualification_summary { padding: .9rem 1rem !important; }
.st-key-job_market_qualification_summary p { margin-bottom: .25rem; }
.st-key-result_education_highlight [data-testid="stMetric"] { position: relative; border: 0; box-shadow: none; border-radius: 13px; background: #FFF2DF; padding: 1.1rem 1rem 1.1rem 5.4rem; }
.st-key-result_education_highlight [data-testid="stMetric"]::before { content: "school"; position: absolute; left: 1.2rem; top: 50%; transform: translateY(-50%); font: 42px "Material Symbols Rounded"; color: #86142D; }
.st-key-result_education_highlight [data-testid="stMetricLabel"] p { font-weight: 700; color: #171923; }
.st-key-result_education_highlight [data-testid="stMetricValue"] { font-size: 3rem; color: #86142D; }
.fow-experience-empty { text-align: center; padding: 1.3rem 1rem .5rem; }
.fow-experience-empty > span { display: grid; place-items: center; width: 85px; height: 85px; margin: 0 auto 1rem; border-radius: 50%; color: #86142D; background: #F6E2E8; font-size: 50px; }
.fow-experience-empty h4 { max-width: 40ch; margin: auto; color: #86142D; font-size: 1.25rem; line-height: 1.35; }
body:has(:is(.st-key-page_heading, .st-key-overview_heading, .st-key-job_market_heading, .st-key-psf_mapping_heading, .st-key-employer_psf_heading)) [data-testid="stExpander"] details summary { min-height: 40px; padding-block: .4rem; }
body:has(:is(.st-key-page_heading, .st-key-overview_heading, .st-key-job_market_heading, .st-key-psf_mapping_heading, .st-key-employer_psf_heading)) [data-testid="stExpander"] details summary p { font-size: .78rem; font-weight: 600; }
body:has(:is(.st-key-page_heading, .st-key-overview_heading, .st-key-job_market_heading, .st-key-psf_mapping_heading, .st-key-employer_psf_heading)) [data-testid="stCaptionContainer"] p { line-height: 1.4; }
@media (max-width: 1100px) { [class*="st-key-result_chart_controls_"] { flex-wrap: wrap; } [class*="st-key-result_chart_note_"] { min-width: 150px; } }
@media (max-width: 760px) { .st-key-result_metrics { flex-wrap: wrap !important; } .st-key-result_metrics > [data-testid="stLayoutWrapper"] { flex: 1 1 calc(50% - 1rem) !important; } [class*="st-key-job_market_featured_"] [data-testid="stHorizontalBlock"] { flex-wrap: wrap; } [class*="st-key-job_market_featured_"] [data-testid="stColumn"] { width: 100% !important; flex: 1 1 100% !important; } :is(.st-key-page_heading, .st-key-overview_heading, .st-key-job_market_heading, .st-key-psf_mapping_heading, .st-key-employer_psf_heading)::before { opacity: .3; } [class*="st-key-result_chart_controls_"] > [data-testid="stLayoutWrapper"] { flex: 1 1 100%; } [class*="st-key-result_chart_note_"] { padding-block: .2rem; } }
@media (max-width: 640px) { .stMainBlockContainer:has(:is(.st-key-page_heading, .st-key-overview_heading, .st-key-job_market_heading, .st-key-psf_mapping_heading, .st-key-employer_psf_heading)) { padding: .5rem 1rem 2rem !important; } :is(.st-key-page_heading, .st-key-overview_heading, .st-key-job_market_heading, .st-key-psf_mapping_heading, .st-key-employer_psf_heading) { margin-inline: -1rem; padding-inline: 1rem; } :is(.st-key-page_heading, .st-key-overview_heading, .st-key-job_market_heading, .st-key-psf_mapping_heading, .st-key-employer_psf_heading) h1 { font-size: 1.9rem; } }
"""


PSF_MAPPING_CSS = """
.st-key-psf_mapping_heading { min-height: 82px; }
.st-key-psf_mapping_review_panel, .st-key-psf_mapping_demand_panel, .st-key-psf_mapping_evidence_panel {
  padding: .8rem 1rem !important; margin: 0; border: 1px solid #DDCFD0; border-radius: 12px;
  background: #FCF9F7; box-shadow: 0 1px 2px #4D102008;
}
.st-key-psf_mapping_review_panel { gap: .4rem; }
.fow-section-heading { display: grid; grid-template-columns: 28px minmax(0,1fr); column-gap: .65rem; row-gap: .2rem; align-items: center; }
.fow-section-heading > .material-symbols-rounded { grid-column: 1; grid-row: 1; color: #86142D; font-size: 27px; line-height: 28px; }
:is(.st-key-psf_mapping_review_heading, .st-key-psf_mapping_demand_heading) .fow-section-heading > h3 { grid-column: 2; grid-row: 1; display: block; min-width: 0; margin: 0; padding: 0; line-height: 1.35; text-wrap: wrap; }
.fow-section-heading > p { grid-column: 2; grid-row: 2; min-width: 0; margin: 0; color: #34303B; font-size: .77rem; line-height: 1.4; }
.st-key-psf_mapping_demand_panel, .st-key-psf_mapping_evidence_panel { gap: .6rem; }
:is(.st-key-psf_mapping_review_panel, .st-key-psf_mapping_demand_panel, .st-key-psf_mapping_evidence_panel) h3 {
  display: flex; align-items: center; gap: .5rem; font-size: 1.13rem;
  font-weight: 750; margin: 0; padding: 0 0 .15rem; color: #171923;
}
:is(.st-key-psf_mapping_review_panel, .st-key-psf_mapping_demand_panel, .st-key-psf_mapping_evidence_panel) h3 [data-testid="stIconMaterial"] { color: #86142D; font-size: 27px; }
.st-key-psf_mapping_review_panel [data-testid="stCaptionContainer"] p, .st-key-psf_mapping_demand_panel [data-testid="stCaptionContainer"] p { font-size: .77rem; line-height: 1.4; color: #34303B; }
body:has(.st-key-psf_mapping_heading) [data-testid="stWidgetLabel"] p { font-size: .8rem; font-weight: 600; line-height: 1.3; color: #171923; }
.st-key-psf_mapping_review_panel [data-testid="stForm"] { padding: .65rem .8rem; border: 1px solid #E1D7D2; border-radius: 11px; background: #FCF8F5; }
.st-key-psf_mapping_review_panel [data-testid="stForm"] [data-testid="stVerticalBlock"] { gap: .45rem; }
.st-key-psf_mapping_review_panel [data-testid="stAlert"] { padding: .55rem .75rem; border-radius: 8px; }
.st-key-psf_mapping_review_panel [data-testid="stAlert"] p { font-size: .8rem; line-height: 1.35; margin: 0; }
.st-key-psf_mapping_review_panel [data-testid="stAlert"] [data-testid="stIconMaterial"] { font-size: 20px; }
.st-key-psf_mapping_review_panel [data-testid="stExpander"] { border-color: #DDD1CD; background: transparent; }
.st-key-psf_mapping_review_panel [data-testid="stExpander"] details summary { min-height: 40px; padding: .4rem .6rem; }
.st-key-psf_mapping_review_panel [data-testid="stExpander"] details summary p { font-size: .8rem; font-weight: 650; }
.st-key-psf_mapping_review_panel textarea { min-height: 90px; background: #FFFDFC; font-size: .85rem; }
.st-key-psf_mapping_review_panel [data-testid="stFormSubmitButton"] button { padding-inline: 1.2rem; }
.st-key-psf_mapping_demand_panel [class*="st-key-result_chart_controls_"] > [data-testid="stLayoutWrapper"]:has([class*="st-key-result_chart_selectors_"]) { flex: 2 1 0; }
.st-key-psf_mapping_demand_panel [class*="st-key-result_chart_note_"] { min-width: 0; }
.fow-competency-demand-insight { padding: 1rem; background: #FFF8F6; border-color: #EED8D8; box-shadow: 0 3px 0 #F0DFDF; }
.fow-competency-demand-insight h3 { color: #86142D !important; font-size: 1.1rem; line-height: 1.3; }
.fow-competency-demand-insight h4 { display: flex; align-items: center; gap: .4rem; font-size: 1rem; }
.fow-competency-demand-insight h4::before { content: "lightbulb"; font: 22px "Material Symbols Rounded"; }
.fow-competency-demand-insight ul { list-style: none; padding: 0; margin: .3rem 0; }
.fow-competency-demand-insight li { display: block; position: relative; padding: .4rem 0 .4rem 1.7rem; font-size: .8rem; line-height: 1.4; }
.fow-competency-demand-insight li::before { content: "check"; position: absolute; left: 0; top: .45rem; display: grid; place-items: center; width: 1.2rem; height: 1.2rem; border-radius: 50%; color: #fff; background: #86142D; font: 15px "Material Symbols Rounded"; }
.fow-competency-demand-insight .fow-insight-scope { font-size: .73rem; color: #62585D; margin-top: .8rem; }
body:has(.st-key-psf_mapping_heading) [data-testid="stDataFrame"] { border-color: #E2D0D4; border-radius: 9px; }
@media (max-width: 760px) {
  :is(.st-key-psf_mapping_review_panel, .st-key-psf_mapping_demand_panel, .st-key-psf_mapping_evidence_panel) { padding: .75rem !important; }
  .st-key-psf_mapping_demand_panel [class*="st-key-result_chart_controls_"] > [data-testid="stLayoutWrapper"] { flex: 1 1 100% !important; }
}
"""


ALIGNMENT_CSS = """
.st-key-employer_psf_heading { min-height: 100px; }
.st-key-alignment_metrics { gap: .9rem; margin: .3rem 0 .2rem; }
.st-key-alignment_metrics > [data-testid="stLayoutWrapper"] { width: auto !important; min-width: min(100%, 200px); flex: 1 1 200px; }
[class*="st-key-alignment_metric_"] [data-testid="stMetric"] { position: relative; box-sizing: border-box; min-height: 105px; padding: 1rem 4rem 1rem 1rem; border: 1px solid #E0D4D2; border-radius: 12px; background: #FFFCFA; box-shadow: 0 2px 4px #4D102008; }
[class*="st-key-alignment_metric_"] [data-testid="stMetricLabel"] { display: block; margin: 0 0 .25rem; min-height: 0; }
[class*="st-key-alignment_metric_"] [data-testid="stMetricLabel"] > div { justify-content: flex-start; }
[class*="st-key-alignment_metric_"] [data-testid="stMetricLabel"] > div > span { position: absolute; inset: 0; pointer-events: none; }
[class*="st-key-alignment_metric_"] [data-testid="stMetricLabel"] p { font-size: .88rem; color: #505062; font-weight: 600; margin: 0; }
[class*="st-key-alignment_metric_"] [data-testid="stMetricValue"] { font-size: 2.25rem; line-height: 1.1; color: #111B30; margin: 0; font-weight: 800; }
[class*="st-key-alignment_metric_"] [data-testid="stMetricIcon"] { position: absolute; right: 1rem; top: 50%; transform: translateY(-50%); display: grid; place-items: center; width: 44px; height: 44px; font-size: 29px; color: #961735; background: #FBECEF; border-radius: 12px; }
.st-key-employer_psf_status_panel, .st-key-employer_psf_evidence_panel { border: 1px solid #DDCFD0; border-radius: 13px; background: #FCF9F7; padding: 1rem !important; box-shadow: 0 1px 2px #4D102008; }
.st-key-employer_psf_status_panel h3, .st-key-employer_psf_evidence_panel h3 { display: flex; align-items: center; gap: .6rem; font-size: 1.15rem; color: #111B30; margin: 0 0 .4rem; padding: 0; font-weight: 750; }
.st-key-employer_psf_status_panel h3 [data-testid="stIconMaterial"], .st-key-employer_psf_evidence_panel h3 [data-testid="stIconMaterial"] { font-size: 28px; color: #86142D; }
.st-key-employer_psf_status_panel [data-testid="stPlotlyChart"] { background: transparent; box-shadow: none; }
.st-key-alignment_chart_and_insight > [data-testid="stLayoutWrapper"] { min-width: 0; flex: 2.6 1 420px; }
.st-key-alignment_chart_and_insight > [data-testid="stLayoutWrapper"]:has(.st-key-alignment_status_insight) { flex: 1 1 280px; }
.st-key-employer_psf_evidence_panel [data-testid="stDataFrame"] { border-radius: 10px; border-color: #E2D0D4; }
.st-key-employer_psf_evidence_panel [data-testid="stWidgetLabel"] p { font-size: .8rem; color: #171923; font-weight: 600; }
.st-key-employer_psf_denominators [data-testid="stAlert"] { border: 1px solid #DEE5EE; border-radius: 12px; padding: .8rem 1rem; }
.st-key-employer_psf_denominators [data-testid="stAlert"] p { font-size: .8rem; line-height: 1.45; }
@media (max-width: 760px) {
  .st-key-alignment_metrics { flex-wrap: wrap; }
  .st-key-alignment_metrics > [data-testid="stLayoutWrapper"] { flex: 1 1 100%; }
  .st-key-employer_psf_status_panel, .st-key-employer_psf_evidence_panel { padding: .75rem !important; }
}
"""


REPORTS_CSS = """
.st-key-reports_deliverables_heading { margin-block: .6rem .65rem; min-width: 0; }
.fow-deliverables-heading { display: grid; grid-template-columns: 32px minmax(0,1fr); column-gap: .65rem; row-gap: .35rem; align-items: start; }
.fow-deliverables-heading > .material-symbols-rounded { grid-column: 1; grid-row: 1 / 3; color: var(--fow-accent); font-size: 30px; line-height: 1; margin-top: .1rem; }
.fow-deliverables-heading > h3 { grid-column: 2; min-width: 0; margin: 0; padding: 0; font-size: 1.25rem; line-height: 1.3; }
.fow-deliverables-heading > p { grid-column: 2; min-width: 0; margin: 0; color: #62585D; font-size: .83rem; line-height: 1.5; overflow-wrap: anywhere; }
.st-key-reports_deliverables_grid { display: grid !important; grid-template-columns: repeat(5,minmax(0,1fr)); grid-auto-rows: 1fr; gap: 1rem; align-items: stretch; }
.st-key-reports_deliverables_grid > [data-testid="stLayoutWrapper"] { display: flex; width: 100% !important; min-width: 0; align-self: stretch; }
[class*="st-key-report_deliverable_"] { box-sizing: border-box; min-width: 0; min-height: 270px; height: 100%; padding: 1.1rem !important; gap: .65rem; border: 1px solid #DFD2CF; border-radius: 12px; background: #FFFCF8; box-shadow: 0 2px 4px #4D102008; }
[class*="st-key-report_deliverable_"] > :last-child { margin-top: auto; width: 100%; }
[class*="st-key-report_deliverable_"] h4 { margin: 0; padding: 0; color: #24303D; font-size: .96rem; line-height: 1.3; letter-spacing: -.02em; overflow-wrap: anywhere; }
[class*="st-key-report_deliverable_"] [data-testid="stMarkdownContainer"] p { color: #62585D; font-size: .8rem; line-height: 1.45; }
[class*="st-key-report_deliverable_"] button { width: 100%; min-height: 44px; border-radius: 8px; }
[class*="st-key-report_deliverable_"] button[kind="secondary"] { border-color: #CDBCB9; color: #78182B; background: #FFFCF8; }
[class*="st-key-report_deliverable_"] button[kind="secondary"]:hover { border-color: #B47C89; background: #F7EDEF; }
[class*="st-key-report_deliverable_"] button p { font-size: .78rem !important; line-height: 1.25; color: inherit !important; }
.st-key-report_deliverable_excel { border-color: var(--fow-accent); box-shadow: 0 2px 5px #78182B15; }
.fow-deliverable-icon { display: grid; place-items: center; width: 48px; height: 48px; border: 1px solid #ECD4DA; border-radius: 12px; background: #F8E8ED; color: #86142D; }
.fow-deliverable-icon .material-symbols-rounded { font-size: 28px; }
@media (max-width: 1200px) { .st-key-reports_deliverables_grid { grid-template-columns: repeat(3,minmax(0,1fr)); } }
@media (max-width: 850px) { .st-key-reports_deliverables_grid { grid-template-columns: repeat(2,minmax(0,1fr)); } }
@media (max-width: 550px) { .st-key-reports_deliverables_grid { grid-template-columns: minmax(0,1fr); } [class*="st-key-report_deliverable_"] { min-height: 235px; padding: 1rem !important; } }
"""


LOADING_CSS = """
.fow-loading { position: relative; isolation: isolate; overflow: hidden; box-sizing: border-box; display: grid; gap: 1rem; width: 100%; min-width: 0; margin: .25rem 0; pointer-events: none; }
.fow-loading::after { content: ""; position: absolute; z-index: 1; inset: 0; background: linear-gradient(100deg,transparent 20%,#FFFFFF90 48%,transparent 75%); transform: translateX(-100%); animation: fow-skeleton-shimmer 1.8s linear infinite; pointer-events: none; }
.fow-loading--metrics,.fow-loading--cards { grid-template-columns: repeat(var(--fow-skeleton-cards,4),minmax(0,1fr)); }
.fow-loading--reports { grid-template-columns: repeat(5,minmax(0,1fr)); }
.fow-loading--reports > :is(.fow-skeleton-toolbar,.fow-skeleton-heading) { grid-column: 1 / -1; }
.fow-loading--reports > .fow-skeleton-toolbar > .fow-skeleton-line { max-width: none; }
.fow-skeleton-heading { display: flex; align-items: center; gap: .65rem; min-width: 0; min-height: 30px; }
.fow-skeleton-heading > .fow-skeleton-icon { width: 25px; height: 25px; border-radius: 5px; }
.fow-skeleton-heading > .fow-skeleton-line:first-child { width: 30%; height: 1rem; }
.fow-skeleton-heading > .fow-skeleton-line:last-child { width: 65%; }
.fow-loading--results, .fow-loading--review { grid-template-columns: minmax(0,1fr); }
.fow-loading--market,.fow-loading--alignment,.fow-loading--mapping,.fow-loading--evaluation,.fow-loading--unmapped { grid-template-columns: minmax(0,1fr); }
.fow-skeleton-summary { display: grid; grid-template-columns: repeat(var(--fow-skeleton-cards,3),minmax(0,1fr)); gap: 1rem; }
.fow-skeleton-panel { display: grid; gap: .9rem; min-width: 0; padding: 1rem; border: 1px solid #E2D6D1; border-radius: 12px; background: #FFFCFA; }
.fow-skeleton-tabs { display: grid; grid-template-columns: repeat(4,minmax(0,1fr)); gap: .25rem; }
.fow-skeleton-tabs > .fow-skeleton-line { height: 44px; border: 1px solid #E2D6D1; border-radius: 7px; background: #F0EAE7; }
.fow-skeleton-disclosure { display: flex; align-items: center; box-sizing: border-box; gap: .7rem; min-width: 0; min-height: 44px; padding: .7rem 1rem; border: 1px solid #E2D6D1; border-radius: 8px; background: #FFFCFA; }
.fow-skeleton-disclosure::before { content: ""; flex: none; width: 6px; height: 6px; border: solid #C3B8B5; border-width: 0 2px 2px 0; transform: rotate(-45deg); }
.fow-skeleton-disclosure > .fow-skeleton-line { width: min(45%,320px); }
.fow-skeleton-notice { display: grid; grid-template-columns: 24px minmax(0,1fr); align-items: center; gap: .7rem; min-width: 0; padding: .8rem 1rem; border-radius: 9px; background: #F1ECE8; }
.fow-skeleton-notice > .fow-skeleton-icon { width: 24px; height: 24px; border-radius: 50%; }
.fow-skeleton-notice > div { display: grid; gap: .55rem; }
.fow-skeleton-notice .fow-skeleton-line:last-child { width: 65%; }
.fow-loading--workspace_status > .fow-skeleton-summary { grid-template-columns: repeat(2,minmax(0,1fr)); }
.fow-skeleton-callout { display: grid; grid-template-columns: 48px minmax(0,1fr) 220px; align-items: center; gap: 1.25rem; padding: 1.2rem; border: 1px solid #E2D6D1; border-radius: 12px; background: #F1E8E6; }
.fow-skeleton-callout > div { display: grid; gap: .65rem; }
.fow-skeleton-callout .fow-skeleton-line { width: 70%; }
.fow-skeleton-workflow { display: grid; grid-template-columns: repeat(3,minmax(0,1fr)); gap: 1rem; }
.fow-skeleton-workflow-card { display: grid; grid-template-columns: 48px minmax(0,1fr); gap: .8rem; padding: 1rem; min-width: 0; border: 1px solid #E2D6D1; border-radius: 12px; background: #FFFAF8; }
.fow-skeleton-workflow-card > div { display: grid; gap: .7rem; }
.fow-skeleton-workflow-card > .fow-skeleton-control { grid-column: 1 / -1; }
@media (max-width: 950px) { .fow-skeleton-workflow { grid-template-columns: repeat(2,minmax(0,1fr)); } }
@media (max-width: 550px) { .fow-skeleton-workflow,.fow-skeleton-callout { grid-template-columns: minmax(0,1fr); } .fow-skeleton-callout > .fow-skeleton-icon { display: none; } }
.fow-loading--study_metrics .fow-skeleton-card { padding: .4rem; min-height: 60px; border: 0; box-shadow: none; background: transparent; display: block; }
.fow-loading--study_metrics .fow-skeleton-card > .fow-skeleton-icon { display: none; }
.fow-skeleton-study-strip { display: grid; grid-template-columns: 220px minmax(0,1fr); align-items: center; gap: 1rem; padding: 1rem 1.25rem; border: 1px solid #E2D6D1; border-radius: 12px; background: #FCF6F4; }
.fow-skeleton-study-strip .fow-skeleton-summary { grid-template-columns: repeat(4,minmax(0,1fr)); }
.fow-skeleton-study-strip .fow-skeleton-card { border-left: 1px solid #DFD2CF; border-radius: 0; padding-left: 1rem; }
@media (max-width: 760px) { .fow-skeleton-study-strip { grid-template-columns: minmax(0,1fr); } .fow-skeleton-study-strip .fow-skeleton-summary { grid-template-columns: repeat(2,minmax(0,1fr)); } }
.fow-loading--selector,.fow-loading--form,.fow-loading--document,.fow-loading--table { grid-template-columns: minmax(0,1fr); }
.fow-skeleton-field { display: grid; gap: .45rem; min-width: 0; }
.fow-skeleton-field > .fow-skeleton-line { width: min(30%,180px); min-width: 70px; }
.fow-skeleton-control { display: block; box-sizing: border-box; width: 100%; height: 44px; border: 1px solid #DFD2CF; border-radius: 8px; background: #EEE5E2; }
.fow-skeleton-document { display: grid; gap: .8rem; min-width: 0; }
.fow-skeleton-document > .fow-skeleton-line:nth-child(5n) { width: 72%; margin-bottom: .6rem; }
.fow-skeleton-grid { display: grid; grid-template-columns: minmax(0,3fr) minmax(200px,1fr); gap: 1rem; min-width: 0; }
.fow-skeleton-card { box-sizing: border-box; display: grid; grid-template-columns: 46px minmax(0,1fr); align-items: center; gap: 1rem; min-width: 0; min-height: 100px; padding: 1rem; border: 1px solid #E2D6D1; border-radius: 12px; background: #FFFAF8; }
.fow-skeleton-insight { box-sizing: border-box; display: grid; align-content: start; gap: .8rem; min-width: 0; padding: 1rem; border: 1px solid #E2D6D1; border-radius: 10px; background: #F9F2EE; }
.fow-skeleton-metric-text { display: grid; gap: .8rem; min-width: 0; }
.fow-skeleton-metric-text > .fow-skeleton-line:first-child { width: 75%; height: .7rem; }
.fow-skeleton-metric-text > .fow-skeleton-line:last-child { width: 35%; min-width: 35px; height: 1.65rem; }
.fow-loading--market .fow-skeleton-card { min-height: 60px; grid-template-columns: 36px minmax(0,1fr); padding: .65rem; gap: .65rem; }
.fow-loading--market .fow-skeleton-icon { width: 36px; height: 44px; }
.fow-loading--market .fow-skeleton-metric-text { gap: .4rem; }
.fow-loading--market .fow-skeleton-metric-text > .fow-skeleton-line:first-child { width: 35%; height: 1.5rem; }
.fow-loading--market .fow-skeleton-metric-text > .fow-skeleton-line:last-child { width: 75%; height: .65rem; }
.fow-skeleton-insight-list { display: grid; gap: 1rem; margin-top: .4rem; padding-top: .8rem; border-top: 1px solid #E2D6D1; }
.fow-skeleton-insight-list > .fow-skeleton-line { height: 1rem; width: 80%; }
.fow-skeleton-line, .fow-skeleton-icon { display: block; flex: none; border-radius: 4px; background: #E7DDDA; }
.fow-skeleton-line { width: 100%; height: .65rem; }
.fow-skeleton-icon { width: 46px; height: 48px; border-radius: 11px; }
.fow-skeleton-card > .fow-skeleton-icon + .fow-skeleton-line { width: 70%; height: .9rem; }
.fow-loading--metrics .fow-skeleton-card > .fow-skeleton-line:last-child { width: 40%; height: 1.7rem; }
.fow-loading--reports .fow-skeleton-card { display: flex; flex-direction: column; align-items: flex-start; gap: .8rem; min-height: 270px; padding: 1.1rem; }
.fow-loading--reports .fow-skeleton-card > .fow-skeleton-control { height: 44px; margin-top: auto; }
.fow-skeleton-toolbar { display: flex; flex-wrap: wrap; align-items: center; gap: .75rem; min-width: 0; }
.fow-skeleton-toolbar > .fow-skeleton-line { flex: 1 1 150px; max-width: 300px; height: 44px; border: 1px solid #DFD2CF; background: #F1EAE6; }
.fow-skeleton-toolbar > .fow-skeleton-disclosure { width: 100%; }
.fow-skeleton-chart { box-sizing: border-box; display: grid; align-content: center; gap: .65rem; min-width: 0; min-height: 250px; padding: 1rem .8rem 2rem .5rem; background: #FBF8F6; }
.fow-skeleton-grid > .fow-skeleton-insight { align-self: center; }
.fow-skeleton-bar { display: grid; grid-template-columns: minmax(65px,22%) minmax(0,1fr); align-items: center; gap: .8rem; }
.fow-skeleton-bar > .fow-skeleton-line:first-child { height: .5rem; width: 85%; justify-self: end; }
.fow-skeleton-bar > .fow-skeleton-line:last-child { height: .9rem; width: 90%; }
.fow-skeleton-chart > .fow-skeleton-line { height: 1.1rem; }
.fow-skeleton-chart > .fow-skeleton-line:nth-child(2n) { width: 72%; }
.fow-skeleton-chart > .fow-skeleton-line:nth-child(3n) { width: 52%; }
.fow-skeleton-table { min-width: 0; overflow-x: auto; overflow-y: hidden; border: 1px solid #E2D6D1; border-radius: 10px; background: #FFFCF8; }
.fow-skeleton-row { box-sizing: border-box; display: grid; grid-auto-flow: column; grid-auto-columns: minmax(100px,1fr); width: max-content; min-width: 100%; gap: 1.2rem; align-items: center; min-height: 42px; padding: .65rem 1rem; border-bottom: 1px solid #EEE6E2; }
.fow-skeleton-row:first-child { background: #F5ECEE; }
.fow-skeleton-row:last-child { border-bottom: 0; }
.fow-skeleton-matrix { display: grid; align-content: start; justify-items: start; gap: 3px; min-width: 0; overflow-x: auto; padding: 1rem; border: 1px solid #E2D6D1; border-radius: 10px; background: #FFFCF8; }
.fow-skeleton-matrix > .fow-skeleton-row { grid-auto-columns: 38px; gap: 3px; min-width: 0; min-height: 38px; padding: 0; border: 0; background: transparent; }
.fow-skeleton-cell { display: block; width: 38px; height: 38px; border-radius: 3px; background: #E7DDDA; }
@keyframes fow-skeleton-shimmer { from { transform: translateX(-100%); } to { transform: translateX(100%); } }
@media (max-width: 1200px) { .fow-loading--reports { grid-template-columns: repeat(3,minmax(0,1fr)); } }
@media (max-width: 950px) { .fow-loading--metrics,.fow-loading--cards,.fow-skeleton-summary { grid-template-columns: repeat(2,minmax(0,1fr)); } .fow-skeleton-grid { grid-template-columns: minmax(0,1fr); } }
@media (max-width: 850px) { .fow-loading--reports { grid-template-columns: repeat(2,minmax(0,1fr)); } }
@media (max-width: 550px) { .fow-loading--metrics,.fow-loading--cards,.fow-loading--reports { grid-template-columns: minmax(0,1fr); } .fow-skeleton-row { gap: .65rem; padding-inline: .75rem; } .fow-loading--reports .fow-skeleton-card { min-height: 235px; padding: 1rem; } }
@media (max-width: 550px) { .fow-skeleton-summary,.fow-loading--workspace_status > .fow-skeleton-summary { grid-template-columns: minmax(0,1fr); } .fow-skeleton-tabs { grid-template-columns: repeat(2,minmax(0,1fr)); } }
@media (prefers-reduced-motion: reduce) { .fow-loading { animation: none; opacity: 1; } .fow-loading::after { animation: none; opacity: 0; } }
"""


UNMAPPED_CSS = """
.st-key-unmapped_summary { gap: 1rem; margin: .3rem 0 .6rem; }
.st-key-unmapped_summary > [data-testid="stLayoutWrapper"] { width: auto !important; min-width: min(100%, 220px); flex: 1 1 220px; }
[class*="st-key-unmapped_metric_"] [data-testid="stMetric"], .st-key-unmapped_review_status { box-sizing: border-box; min-height: 112px; border: 1px solid #DFD2CF; border-radius: 10px; background: #FFFCF8; box-shadow: 0 2px 4px #4D102008; }
[class*="st-key-unmapped_metric_"] [data-testid="stMetric"] { padding: .8rem 1rem; }
[class*="st-key-unmapped_metric_"] [data-testid="stMetricLabel"] p { color: #62585D; font-size: .82rem; }
[class*="st-key-unmapped_metric_"] [data-testid="stMetricValue"] { color: #86142D; font-size: 2rem; }
[class*="st-key-unmapped_metric_"] [data-testid="stMetricIcon"] { font-size: 25px; color: #8B1630; }
.st-key-unmapped_review_status { padding: 1rem !important; display: flex; justify-content: center; }
.fow-unmapped-status { display: flex; align-items: center; gap: .8rem; }
.fow-unmapped-status > span { display: grid; place-items: center; flex: 0 0 44px; width: 44px; height: 44px; color: #8B1630; background: var(--fow-accent-bg); border-radius: 10px; font-size: 26px; }
.fow-unmapped-status strong { color: #78182B; font-size: .85rem; }
.fow-unmapped-status p { color: #62585D; font-size: .76rem; line-height: 1.4; margin: .25rem 0 0; }
.st-key-unmapped_evidence_panel, .st-key-unmapped_recurring_panel { padding: 1rem !important; border: 1px solid #DFD2CF; border-radius: 12px; background: #FCF9F7; box-shadow: 0 2px 4px #4D102008; }
:is(.st-key-unmapped_evidence_panel,.st-key-unmapped_recurring_panel) h3 { display: flex; align-items: center; gap: .5rem; margin: 0 0 .4rem; }
:is(.st-key-unmapped_evidence_panel,.st-key-unmapped_recurring_panel) h3 [data-testid="stIconMaterial"] { color: #8B1630; font-size: 25px; }
:is(.st-key-unmapped_evidence_panel,.st-key-unmapped_recurring_panel) [data-testid="stColumn"] { min-width: 0; }
:is(.st-key-unmapped_evidence_panel,.st-key-unmapped_recurring_panel) [data-testid="stPlotlyChart"] { background: transparent; box-shadow: none; }
:is(.st-key-unmapped_evidence_panel,.st-key-unmapped_recurring_panel) [data-testid="stDataFrame"] { border-radius: 9px; }
@media (max-width: 760px) { .st-key-unmapped_summary { flex-wrap: wrap; } .st-key-unmapped_summary > [data-testid="stLayoutWrapper"] { flex: 1 1 100%; } .st-key-unmapped_evidence_panel,.st-key-unmapped_recurring_panel { padding: .75rem !important; } }
"""


# Unmapped loading follows the same control row and three summary cards.
UNMAPPED_CSS += """
.fow-loading--unmapped .fow-skeleton-summary { display: grid; grid-template-columns: repeat(3,minmax(0,1fr)); gap: 1rem; }
@media (max-width: 760px) { .fow-loading--unmapped .fow-skeleton-summary { grid-template-columns: minmax(0,1fr); } }
"""


WORKSPACE_CONTENT_CSS = """
[data-testid="stSidebarHeader"] { display: grid; grid-template-columns: minmax(0,1fr) 44px; }
[data-testid="stSidebarHeader"] > :first-child { min-width: 0; }

/* A shared content language for preparation, review and study tools. */
[class*="st-key-workspace_page_"] { width: 100%; min-width: 0; gap: 1rem; }
[class*="st-key-workspace_page_"] h3 { display: flex; align-items: center; gap: .55rem; font-size: 1.02rem; color: #171923; margin-bottom: .3rem; }
[class*="st-key-workspace_page_"] h3 [data-testid="stIconMaterial"] { color: #8B1630; font-size: 25px; }
[class*="st-key-workspace_page_"] [data-testid="stWidgetLabel"] p { font-size: .83rem; font-weight: 550; color: #24303D; line-height: 1.4; }
[class*="st-key-workspace_page_"] [data-testid="stCaptionContainer"] p { line-height: 1.45; }
[class*="st-key-workspace_page_"] :is([data-testid="stForm"], [data-testid="stExpander"]) { background: #FFFCFA; border-color: #DFD2CF; }
[class*="st-key-workspace_page_"] [data-testid="stForm"] { border-radius: 12px; padding: 1rem; }
[class*="st-key-workspace_page_"] [data-testid="stMetricIcon"] { color: #8B1630; font-size: 25px; }
:is(.st-key-upload_file_panel,.st-key-upload_preview_body,.st-key-upload_sources_body,.st-key-training_options_panel,.st-key-feedback_records_body,.st-key-feedback_correction_history_body,.st-key-feedback_usability_results_body,.st-key-feedback_stakeholders_body,.st-key-training_saved_model_body) {
  min-width: 0; padding: 1rem !important; border: 1px solid #DFD2CF; border-radius: 12px; background: #FCF9F7; box-shadow: 0 2px 4px #4D102008;
}
.st-key-upload_file_panel [data-testid="stFileUploaderDropzone"] { min-height: 112px; background: #FFFCFA; }
.st-key-upload_preview_body [data-testid="stDataFrame"], .st-key-upload_sources_body [data-testid="stDataFrame"] { border-radius: 9px; }
.st-key-workspace_page_review .st-key-manual_review_workspace { background: #FFFCFA; border-radius: 12px; }
.st-key-workspace_page_review .st-key-manual_review_actions { border-radius: 12px 12px 0 0; }
.st-key-workspace_page_review .st-key-review_controls { gap: 1rem; padding-block: .3rem; }
.st-key-extraction_actions { flex-wrap: wrap; margin: .25rem 0 .5rem; }
.st-key-extraction_actions button { min-width: 180px; }
.st-key-training_options_panel > [data-testid="stLayoutWrapper"] { min-width: 0; }
.st-key-settings_form h3 { border-bottom: 1px solid #E9DEDA; padding-bottom: .65rem; margin-top: .4rem; }
[class*="st-key-settings_fields_"] { flex-wrap: wrap; margin-bottom: .7rem; }
[class*="st-key-settings_fields_"] > [data-testid="stLayoutWrapper"] { min-width: min(100%, 260px); flex: 0 1 calc(50% - .5rem); }
[class*="st-key-settings_fields_"] > [data-testid="stLayoutWrapper"]:has(:is(.st-key-setting_input_semantic_model,.st-key-setting_input_stopwords)) { flex: 1 1 100%; }
.st-key-methodology_sections > [data-testid="stLayoutWrapper"] { min-width: 0; }
.st-key-methodology_sections [data-testid="stExpander"] details summary { color: #78182B; min-height: 48px; }
.st-key-methodology_sections [data-testid="stExpanderDetails"] { padding: 1rem; }
.st-key-methodology_sections [data-testid="stExpanderDetails"] p { max-width: 100ch; }
/* Collapsed navigation reserves its own header slot; it cannot cover breadcrumbs. */
[data-testid="stSidebarCollapseButton"] { visibility: visible; flex: 0 0 44px; min-width: 44px; }
[data-testid="stSidebarCollapseButton"] button { display: grid; place-items: center; min-width: 44px; min-height: 44px; border-radius: 8px; color: #78182B; }
[data-testid="stExpandSidebarButton"] { position: fixed !important; left: .6rem; top: .25rem; z-index: 100; display: grid; place-items: center; width: 44px; height: 44px; min-width: 44px; border: 1px solid #DFD2CF; border-radius: 8px; color: #78182B; background: #FFFCFA; }
[data-testid="stExpandSidebarButton"]:hover { color: #78182B; background: #F4E7E9; }
[data-testid="stHeader"]:has([data-testid="stExpandSidebarButton"]) :is([data-testid="stLogo"],[data-testid="stSidebarLogo"]) { display: none; }
body:has([data-testid="stExpandSidebarButton"]) .st-key-workspace_toolbar { box-sizing: border-box; min-height: 48px; padding-left: 54px; }
body:has([data-testid="stExpandSidebarButton"]) .st-key-workspace_toolbar .fow-breadcrumb { min-height: 44px; }
/* Wireframes use known control kinds, never representative observations. */
.fow-loading--job_metrics { grid-template-columns: repeat(var(--fow-skeleton-cards,4),minmax(0,1fr)); gap: .9rem; }
.fow-loading--job_metrics .fow-skeleton-card { display: grid; grid-template-columns: 40px 1fr; align-items: center; min-height: 60px; padding: .65rem; gap: .25rem .7rem; }
.fow-loading--job_metrics .fow-skeleton-icon { grid-row: 1 / 4; width: 36px; height: 44px; }
.fow-loading--job_metrics .fow-skeleton-line:first-of-type { height: 1.4rem; width: 35%; }
.fow-skeleton-pending { display: grid; grid-template-columns: 24px minmax(0,1fr); align-items: center; gap: .7rem; width: 100%; padding: .65rem 0; }
.fow-skeleton-pending > .fow-skeleton-icon { width: 24px; height: 24px; border-radius: 50%; }
.fow-skeleton-pending > div { display: grid; gap: .55rem; }
.fow-skeleton-pending .fow-skeleton-line:last-child { width: 60%; }
.fow-skeleton-form { display: grid; grid-template-columns: repeat(var(--fow-field-columns,1),minmax(0,1fr)); gap: 1rem; }
.fow-skeleton-form-heading { grid-column: 1 / -1; padding-block: .6rem; border-bottom: 1px solid #E9DEDA; }
.fow-skeleton-form-heading > .fow-skeleton-line { width: 28%; height: 1rem; }
.fow-skeleton-field--slider .fow-skeleton-control { position: relative; height: 6px; margin-block: 19px; border: 0; border-radius: 99px; }
.fow-skeleton-field--slider .fow-skeleton-control::after { content: ""; position: absolute; width: 14px; height: 14px; left: 35%; top: -4px; border-radius: 50%; background: #CFC3BF; }
.fow-skeleton-field--select .fow-skeleton-control::after { content: ""; display: block; width: 6px; height: 6px; margin: 16px 16px 0 auto; border: solid #C3B8B5; border-width: 0 2px 2px 0; transform: rotate(45deg); }
.fow-loading--form[data-view="usability"] .fow-skeleton-form { grid-template-columns: minmax(0,1fr) minmax(0,2.5fr); }
.fow-loading--form[data-view="usability"] .fow-skeleton-field:first-child { grid-column: 1; grid-row: 1 / 7; align-content: start; }
.fow-loading--form[data-view="usability"] .fow-skeleton-field--slider { grid-column: 2; }
@media (max-width: 760px) { .fow-loading--form[data-view="usability"] .fow-skeleton-form { grid-template-columns: minmax(0,1fr); } .fow-loading--form[data-view="usability"] .fow-skeleton-field:first-child { grid-row: auto; } .fow-loading--form[data-view="usability"] .fow-skeleton-field--slider { grid-column: 1; } }
.fow-skeleton-field--textarea,.fow-skeleton-field--text,.fow-skeleton-field--button { grid-column: 1 / -1; }
.fow-skeleton-field--textarea .fow-skeleton-control { height: 110px; }
.fow-skeleton-field--button { width: min(100%,170px); }
.fow-skeleton-field--button > .fow-skeleton-line { display: none; }
@media (max-width: 760px) {
  [class*="st-key-settings_fields_"] > [data-testid="stLayoutWrapper"] { flex-basis: 100%; }
  .fow-skeleton-form { grid-template-columns: minmax(0,1fr); }
  .fow-loading--job_metrics { grid-template-columns: repeat(2,minmax(0,1fr)); }
  .st-key-workspace_toolbar .fow-breadcrumb { gap: .4rem; font-size: .7rem; }
}
"""

WORKSPACE_CONTENT_CSS += """
:is([data-testid="stExpandSidebarButton"],[data-testid="stSidebarCollapseButton"]) [data-testid="stIconMaterial"] { color: #78182B !important; font-size: 24px; }
"""


WORKSPACE_CONTENT_CSS += """
/* Transparent native header wrappers must not intercept workspace clicks. */
body:has(.st-key-workspace_toolbar) :is([data-testid="stHeader"], [data-testid="stToolbar"]) { pointer-events: none; }
body:has(.st-key-workspace_toolbar) [data-testid="stHeader"] :is(button, a, [role="button"]) { pointer-events: auto; }
/* The account trigger occupies one native content-sized toolbar slot. */
.st-key-account_trigger { flex: 0 0 auto; min-width: 0; width: max-content !important; align-self: center; }
.st-key-workspace_toolbar > [data-testid="stLayoutWrapper"]:has(> .st-key-account_trigger) { flex: 0 0 auto; width: max-content !important; align-self: center; }
.st-key-account_trigger [data-testid="stPopoverButton"] { box-sizing: border-box; display: flex; align-items: center; justify-content: center; gap: .45rem; min-height: 44px; padding: .5rem .8rem; border: 1px solid #DFD2CF; border-radius: 8px; background: #FFFCFA; color: #24303D; }
.st-key-account_trigger [data-testid="stPopoverButton"] p { margin: 0; font-size: .82rem; font-weight: 600; line-height: 1.3; white-space: nowrap; color: inherit; }
.st-key-account_trigger [data-testid="stIconMaterial"] { color: #78182B; font-size: 22px; line-height: 1; }
.st-key-account_trigger [data-testid="stPopoverButton"]:hover { border-color: #C98E99; background: #F7EDEF; }
.st-key-account_trigger [data-testid="stPopoverButton"][aria-expanded="true"] { border-color: #78182B; background: #F7EDEF; }
.st-key-account_menu .account-profile h3 { font-size: 1.05rem; padding-bottom: .7rem; }
@media (max-width: 640px) { .st-key-workspace_toolbar { column-gap: .5rem; row-gap: .35rem; } .st-key-account_trigger [data-testid="stPopoverButton"] { padding-inline: .6rem; } }
"""


STUDY_CONTENT_CSS = """
/* Content only: retain the shared header, account control and navigation. */
[class*="st-key-content_panel_"] { min-width: 0; padding: 0 !important; gap: .85rem; border: 1px solid var(--fow-border); border-radius: 12px; background: #FFFCFA; box-shadow: var(--fow-shadow); }
[class*="st-key-content_panel_"] > :is([data-testid="stLayoutWrapper"],[data-testid="stElementContainer"]):not(:first-child) { margin-inline: 1rem; width: calc(100% - 2rem) !important; min-width: 0; }
[class*="st-key-content_panel_"] > :is([data-testid="stLayoutWrapper"],[data-testid="stElementContainer"]):last-child { margin-bottom: 1rem; }
.fow-content-section-heading { display: flex; align-items: center; gap: .65rem; min-height: 48px; padding: .8rem 1rem .25rem; background: transparent; color: #171923; }
.fow-content-section-heading > .material-symbols-rounded { flex: none; color: #86142D; font-size: 25px; line-height: 1; }
.fow-content-section-heading > h3 { display: block !important; margin: 0 !important; padding: 0 !important; color: #171923 !important; font-size: 1.05rem !important; line-height: 1.35; letter-spacing: -.02em; }
[class*="st-key-content_metrics_"] { flex-wrap: wrap; gap: 1rem; }
[class*="st-key-content_metrics_"] > [data-testid="stLayoutWrapper"] { flex: 1 1 210px; min-width: min(100%,210px); }
:is([class*="st-key-content_metric_"],[class*="st-key-overview_metric_"]) [data-testid="stMetric"] { position: relative; min-width: 0; min-height: 100px; padding: 1rem 1rem 1rem 5rem; border-radius: 12px; background: #FFFAF8; }
:is([class*="st-key-content_metric_"],[class*="st-key-overview_metric_"]) [data-testid="stMetricLabel"] { position: static; }
:is([class*="st-key-content_metric_"],[class*="st-key-overview_metric_"]) [data-testid="stMetricLabel"] > div > span { position: absolute; inset: 0; pointer-events: none; }
:is([class*="st-key-content_metric_"],[class*="st-key-overview_metric_"]) [data-testid="stMetricIcon"] { position: absolute; left: 1rem; top: 50%; transform: translateY(-50%); display: grid; place-items: center; width: 46px; height: 48px; border-radius: 11px; background: #F6E4E8; color: #86142D; font-size: 27px; }
:is([class*="st-key-content_metric_"],[class*="st-key-overview_metric_"]) [data-testid="stMetricLabel"] p { font-size: .8rem; font-weight: 650; color: #62585D; }
:is([class*="st-key-content_metric_"],[class*="st-key-overview_metric_"]) [data-testid="stMetricValue"] { font-size: 1.65rem; line-height: 1.2; color: #78182B; white-space: normal; overflow-wrap: anywhere; }
.st-key-content_metric_review_3 [data-testid="stMetricValue"], .st-key-content_metric_feedback_3 [data-testid="stMetricValue"] { font-size: .9rem; white-space: normal; }
.st-key-readiness_study_metrics { flex-wrap: wrap; gap: 0; padding: 1rem 1.25rem !important; border: 1px solid #E2D6D1; border-radius: 12px; background: #FCF6F4; box-shadow: var(--fow-shadow); }
.st-key-readiness_study_metrics > [data-testid="stLayoutWrapper"] { flex: 1 1 135px; min-width: min(100%,135px); }
.st-key-readiness_study_metrics > [data-testid="stLayoutWrapper"]:first-child { flex: 1.35 1 220px; }
.st-key-workspace_page_readiness .st-key-readiness_study_title h3 { font-size: .92rem; margin: 0; padding: 0; }
[class*="st-key-readiness_study_metric_"] { padding-left: 1.1rem; border-left: 1px solid #DFD2CF; }
.st-key-readiness_study_metrics [data-testid="stMetric"] { min-height: 0; padding: 0; border: 0; background: transparent; box-shadow: none; }
.st-key-readiness_study_metrics [data-testid="stMetricLabel"] p { font-size: .8rem; font-weight: 600; }
.st-key-readiness_study_metrics [data-testid="stMetricValue"] { font-size: 1.6rem; }
:is(.st-key-readiness_study_metric_3_yes,.st-key-readiness_study_metric_3_no) [data-testid="stMetricValue"] { display: inline-flex; align-items: center; gap: .35rem; margin-top: .25rem; padding: .12rem .6rem; border: 1px solid #B9D7C3; border-radius: 99px; background: #EAF6ED; color: #246442; font-size: .85rem; letter-spacing: normal; }
.st-key-readiness_study_metric_3_yes [data-testid="stMetricValue"]::before { content: "check"; font: 18px "Material Symbols Rounded"; }
.st-key-readiness_study_metric_3_no [data-testid="stMetricValue"] { background: #FFF4DF; border-color: #E4CC9D; color: #805A1B; }
.st-key-readiness_study_metric_3_no [data-testid="stMetricValue"]::before { content: "remove"; font: 18px "Material Symbols Rounded"; }
@media (max-width: 760px) { .st-key-readiness_study_metrics { gap: 1rem; padding: 1rem !important; } .st-key-readiness_study_metrics > [data-testid="stLayoutWrapper"]:first-child { flex-basis: 100%; } [class*="st-key-readiness_study_metric_"] { padding-left: .8rem; } }
.st-key-readiness_label_profiles > [data-testid="stLayoutWrapper"] { flex: 1 1 380px; min-width: min(100%,380px); }
.fow-readiness-findings { display: grid; gap: .65rem; padding: 0; margin: 0; list-style: none; }
.fow-readiness-findings li { display: grid; grid-template-columns: 30px minmax(0,1fr); align-items: start; gap: .75rem; padding: .9rem 1rem; border-radius: 9px; background: var(--fow-review-bg); }
.fow-readiness-findings li > span { color: #86142D; font-size: 26px; line-height: 1; }
.fow-readiness-findings strong { display: block; color: #78182B; font-size: .9rem; line-height: 1.35; }
.fow-readiness-findings p { margin: .3rem 0 0; color: #34303B; font-size: .84rem; line-height: 1.5; }
.st-key-content_panel_readiness_actions li { padding-left: .2rem; margin-block: .5rem; font-size: .86rem; line-height: 1.5; }
.st-key-workspace_page_readiness [class*="st-key-content_panel_"] { padding: 1.2rem 1.35rem !important; gap: 1rem; }
.st-key-workspace_page_readiness [class*="st-key-content_panel_"] > :is([data-testid="stLayoutWrapper"],[data-testid="stElementContainer"]):nth-child(n) { margin: 0; width: 100% !important; }
.st-key-workspace_page_readiness .fow-content-section-heading { min-height: 32px; padding: 0 0 .35rem; }
.st-key-workspace_page_readiness .fow-readiness-findings { gap: .8rem; }
@media (max-width: 760px) {
 .st-key-workspace_page_readiness [class*="st-key-content_panel_"] { padding: 1rem !important; }
 .st-key-workspace_page_readiness [class*="st-key-content_panel_"] > :is([data-testid="stLayoutWrapper"],[data-testid="stElementContainer"]):nth-child(n) { margin: 0; width: 100% !important; }
 .st-key-workspace_page_readiness .fow-content-section-heading { padding: 0 0 .35rem; }
}
.fow-content-note { box-sizing: border-box; min-width: 0; padding: 1rem; border: 1px solid #EAD7DC; border-radius: 11px; background: #FBF1F2; }
.fow-content-note h4 { display: flex; align-items: center; gap: .55rem; margin: 0 0 .65rem; padding: 0; color: #78182B; font-size: 1rem; line-height: 1.35; }
.fow-content-note h4 > span { flex: none; font-size: 24px; line-height: 1; }
.fow-content-note p, .fow-content-note li { margin: 0; color: #24303D; font-size: .86rem; line-height: 1.55; }
.fow-content-note ul { margin: .7rem 0 0; padding-left: 1.2rem; }
.fow-content-note li + li { margin-top: .35rem; }
.st-key-home_next { position: relative; padding: 1.25rem 1.4rem 1.25rem 5.5rem !important; border-color: #78182B; border-radius: 12px; background: #78182B; }
.st-key-home_next::before { content: "memory"; position: absolute; left: 1.2rem; top: 50%; transform: translateY(-50%); display: grid; place-items: center; width: 48px; height: 48px; color: #fff; background: #FFFFFF12; border-radius: 11px; font: 30px "Material Symbols Rounded"; }
.st-key-home_next :is(h3,p) { color: #fff !important; }
.st-key-home_next h3 { margin: 0; font-size: 1.3rem; }
.st-key-home_next button p { color: #4D1020 !important; }
:is(.st-key-workflow_0,.st-key-workflow_3) > [data-testid="stLayoutWrapper"] { flex: 1 1 290px; min-width: min(100%,290px); }
[class*="st-key-workflow_step_"] { height: 100%; padding: 1rem !important; gap: .8rem; border-color: var(--fow-border); border-radius: 12px; background: #FFFCFA; box-shadow: var(--fow-shadow); }
[class*="st-key-workflow_step_"] > :last-child { margin-top: auto; }
.fow-workflow-card { display: grid; grid-template-columns: 48px minmax(0,1fr); gap: .8rem; }
.fow-workflow-card > span { display: grid; place-items: center; width: 48px; height: 50px; border-radius: 11px; background: #F6E4E8; color: #86142D; font-size: 29px; }
.fow-workflow-card small { color: #78182B; font-size: .72rem; font-weight: 700; }
.fow-workflow-card h4 { padding: .15rem 0; margin: 0; font-size: 1.05rem; color: #171923; }
.fow-workflow-card p { margin: 0; font-size: .83rem; color: #24303D; line-height: 1.45; }
.st-key-readiness_summary { padding: 1rem 1.2rem !important; border-color: #E5BD76; border-left: 4px solid #D6A33D; background: #FFF7E9; }
.st-key-readiness_summary h3 { color: #78182B; }
.st-key-review_controls { border: 1px solid var(--fow-border); border-radius: 12px; padding: 1rem !important; background: #FFFCFA; }
.st-key-review_tools { gap: .65rem; flex-wrap: wrap; }
.st-key-manual_review_workspace { border: 1px solid var(--fow-border); border-radius: 12px; }
.st-key-manual_review_actions { padding: .75rem 1rem; }
.st-key-settings_form, .st-key-usability { padding: 0 !important; border: 0 !important; background: transparent !important; }
.st-key-settings_form [class*="st-key-content_panel_"] { margin-bottom: .5rem; }
.st-key-settings_form [class*="st-key-settings_fields_"] { margin-bottom: 0; }
[class*="st-key-content_panel_"] [data-testid="stDataFrame"] { border-color: #E8D7DC; border-radius: 9px; }
[class*="st-key-content_panel_"] [data-testid="stPlotlyChart"] { box-shadow: none; background: transparent; }
/* The content panels own the only card border; loading hosts remain neutral. */
.st-key-manual_review_workspace { border: 0; background: transparent; }
.st-key-review_controls { border: 0; padding: 0 !important; background: transparent; }
:is(.st-key-feedback_records_body,.st-key-feedback_correction_history_body,.st-key-feedback_usability_results_body,.st-key-training_saved_model_body) { padding: 0 !important; border: 0; box-shadow: none; background: transparent; }
[class*="st-key-content_panel_"] .fow-content-note { border: 0; }
:is(.st-key-quality_dataset_selector,.st-key-quality_duplicate_selector) { padding: .8rem 1rem !important; border: 1px solid var(--fow-border); border-radius: 11px; background: #FFFCFA; }
.st-key-settings_maintenance > [data-testid="stLayoutWrapper"] { flex: 1 1 340px; min-width: min(100%,340px); }
:is(.st-key-settings_fields_aligned_threshold,.st-key-settings_fields_stopwords,.st-key-settings_fields_likert_min) { display: grid !important; gap: 1rem; }
.st-key-settings_fields_aligned_threshold { grid-template-columns: minmax(0,1.5fr) minmax(240px,1fr); align-items: start; }
.st-key-settings_fields_aligned_threshold > [data-testid="stLayoutWrapper"]:not(:has(.st-key-setting_input_semantic_model)) { grid-column: 1; }
.st-key-settings_fields_aligned_threshold > [data-testid="stLayoutWrapper"]:has(.st-key-setting_input_semantic_model) { grid-column: 2; grid-row: 1 / 5; border-left: 1px solid var(--fow-border); padding-left: 1rem; }
.st-key-setting_input_semantic_model { gap: 1.1rem; }
.st-key-settings_fields_stopwords { grid-template-columns: repeat(3,minmax(0,1fr)); }
.st-key-settings_fields_stopwords > [data-testid="stLayoutWrapper"]:has(.st-key-setting_input_stopwords) { grid-column: 1 / -1; }
.st-key-settings_fields_likert_min { grid-template-columns: 1.25fr 1fr 1fr; align-items: start; }
:is(.st-key-settings_fields_aligned_threshold,.st-key-settings_fields_stopwords,.st-key-settings_fields_likert_min) > [data-testid="stLayoutWrapper"] { min-width: 0; width: 100% !important; }
@media (max-width: 760px) {
 [class*="st-key-content_metrics_"] > [data-testid="stLayoutWrapper"] { flex-basis: calc(50% - .5rem); min-width: min(100%,160px); }
 .st-key-home_next { padding-left: 1rem !important; }
 .st-key-home_next::before { display: none; }
 .fow-content-section-heading { padding: .65rem .8rem; }
 [class*="st-key-content_panel_"] > :is([data-testid="stLayoutWrapper"],[data-testid="stElementContainer"]):not(:first-child) { margin-inline: .8rem; width: calc(100% - 1.6rem) !important; }
}
@media (max-width: 760px) {
 :is(.st-key-settings_fields_aligned_threshold,.st-key-settings_fields_stopwords,.st-key-settings_fields_likert_min) { grid-template-columns: minmax(0,1fr); }
 .st-key-settings_fields_aligned_threshold > [data-testid="stLayoutWrapper"]:has(.st-key-setting_input_semantic_model) { grid-column: 1; grid-row: auto; border-left: 0; padding-left: 0; }
}
@media (max-width: 480px) { [class*="st-key-content_metrics_"] > [data-testid="stLayoutWrapper"] { flex-basis: 100%; } }

.st-key-extraction_setup_and_run > [data-testid="stLayoutWrapper"] { flex: 1 1 390px; min-width: min(100%,390px); }
:is(.st-key-content_panel_extraction_setup,.st-key-content_panel_extraction_run) { height: 100%; }
.st-key-content_panel_extraction_run .st-key-extraction_actions { padding-block: .3rem; }
.fow-loading--settings { gap: 1rem; }
.fow-skeleton-settings-section { border: 1px solid #E2D6D1; border-radius: 12px; overflow: hidden; }
.fow-skeleton-settings-section > .fow-skeleton-heading { padding: 1rem; background: transparent; }
.fow-skeleton-settings-fields { display: grid; gap: 1rem; padding: 1rem; }
.fow-skeleton-settings-fields--0 { grid-template-columns: minmax(0,1.5fr) minmax(240px,1fr); }
.fow-skeleton-settings-fields--0 > .fow-skeleton-field--slider { grid-column: 1; }
.fow-skeleton-settings-fields--0 > .fow-skeleton-field--text { grid-column: 2; grid-row: 1 / 5; }
.fow-skeleton-settings-fields--1 { grid-template-columns: repeat(3,minmax(0,1fr)); }
.fow-skeleton-settings-fields--2 { grid-template-columns: 1.25fr 1fr 1fr; }
.fow-skeleton-settings-note { display: grid; align-content: start; gap: .65rem; padding: 1rem; border-radius: 10px; background: #F2E8E6; }
.fow-skeleton-settings-note > .fow-skeleton-line:last-child { width: 75%; }
.fow-skeleton-settings-fields--0 .fow-skeleton-field--text > .fow-skeleton-settings-note { margin-bottom: .7rem; }
@media (max-width: 760px) {
 .fow-skeleton-settings-fields { grid-template-columns: minmax(0,1fr); }
 .fow-skeleton-settings-fields--0 > .fow-skeleton-field--text { grid-column: 1; grid-row: auto; }
}
"""


RESPONSIVE_CSS = """
/* Measure usable content width, including sidebar and browser zoom changes. */
.stMainBlockContainer { container: workspace / inline-size; --fow-page-gutter: clamp(1rem,2.5vw,1.5rem); }
.stMainBlockContainer:has(.st-key-workspace_toolbar) { padding-inline: var(--fow-page-gutter) !important; }
:is(.st-key-page_heading,.st-key-overview_heading,.st-key-job_market_heading,.st-key-psf_mapping_heading,.st-key-employer_psf_heading) { margin-inline: calc(-1 * var(--fow-page-gutter)); padding-inline: var(--fow-page-gutter); }
.stMain :is([data-testid="stVerticalBlock"],[data-testid="stHorizontalBlock"],[data-testid="stColumn"],[data-testid="stLayoutWrapper"],[data-testid="stElementContainer"]) { min-width: 0; max-width: 100%; box-sizing: border-box; }
.stMain :is([data-testid="stMarkdownContainer"],[data-testid="stCaptionContainer"]) :is(p,li,h1,h2,h3,h4) { overflow-wrap: anywhere; }
.stMain [data-testid="stWidgetLabel"] { min-width: 0; height: auto; }
.stMain [data-testid="stWidgetLabel"] p { white-space: normal; overflow: visible; text-overflow: clip; }
.stMain :is([data-testid="stButton"],[data-testid="stDownloadButton"],[data-testid="stFormSubmitButton"],[data-testid="stPopover"]) button { max-width: 100%; min-height: 44px; height: auto; padding-block: .6rem; }
.stMain button p { white-space: normal; overflow-wrap: anywhere; line-height: 1.35; }
.stMain button [data-testid="stMarkdownContainer"] { white-space: normal; overflow: visible; text-overflow: clip; }
.stMain [data-testid="stNumberInput"] button { min-width: 44px; min-height: 44px; }
.stMain :is([data-testid="stCheckbox"],[data-testid="stToggle"]) label { min-height: 44px; align-items: center; }
.stMain [data-testid="stExpander"] summary { min-height: 44px; align-items: center; }
.stMain [data-testid="stExpander"] summary p { white-space: normal; overflow-wrap: anywhere; }
.stMain [data-testid="stHeading"] h3 { display: flex; align-items: center; gap: .6rem; line-height: 1.4; }
.stMain [data-testid="stHeadingIconWrapper"] { flex: 0 0 28px; width: 28px; height: 30px; margin-inline-end: 0; overflow: visible; }
.stMain [data-testid="stHeadingIcon"] { width: 28px; height: 28px; line-height: 28px; }
.stMain [data-testid="stMetricLabel"] p { white-space: normal; overflow: visible; text-overflow: clip; overflow-wrap: anywhere; }
.stMain [data-testid="stMetricValue"] { max-width: 100%; }
.stMain [data-testid="stMetricValue"] > div { white-space: normal; overflow-wrap: anywhere; line-height: 1.2; }
.stMain :is([data-testid="stDataFrame"],[data-testid="stDataEditor"],[data-testid="stPlotlyChart"]) { max-width: 100%; min-width: 0; }
.stMain [data-testid="stTable"], .stMain [data-testid="stMarkdownContainer"] table { max-width: 100%; overflow-x: auto; }
.stMain [data-testid="stMarkdownContainer"] table { display: block; }
[data-testid="stPopoverBody"] { box-sizing: border-box; max-width: calc(100vw - 24px); max-height: calc(100dvh - 24px); overflow-y: auto; }
[data-testid="stSidebarNav"] [data-testid="stSidebarNavLink"] { min-height: 44px; }
.fow-breadcrumb { min-width: 0; }
.fow-breadcrumb strong { min-width: 0; overflow-wrap: anywhere; }
.fow-home-mark { flex-shrink: 0; }
.fow-key-insight :is(h3,h4,p,li), .fow-content-note :is(h4,p,li) { overflow-wrap: anywhere; }
.fow-key-insight ol li { gap: .65rem; }
.fow-key-insight ol li > :last-child { flex-shrink: 0; }
:is(.st-key-login_panel,.st-key-login_panel_busy) { width: min(100%,480px) !important; }
:is(.st-key-overview_metrics,.st-key-result_metrics) { display: grid !important; grid-template-columns: repeat(4,minmax(0,1fr)); gap: 1rem; }
:is(.st-key-overview_metrics,.st-key-result_metrics) > [data-testid="stLayoutWrapper"] { width: 100% !important; min-width: 0 !important; }
[class*="st-key-result_metric_"] { padding: .75rem .9rem !important; }
.st-key-result_metric_1 [data-testid="stMetricIcon"] { left: 0; width: 38px; height: 46px; border-radius: 8px; }
[class*="st-key-result_metric_"] [data-testid="stMetricLabel"] p { font-size: .78rem; line-height: 1.4; }
:is(.st-key-reports_deliverables_grid,.fow-loading--reports) { grid-template-columns: repeat(5,minmax(0,1fr)); }
.st-key-review_controls { display: grid !important; grid-template-columns: 1.1fr 1.4fr .6fr 1fr; align-items: end; gap: 1rem; }
.st-key-review_controls > [data-testid="stElementContainer"] { width: 100% !important; min-width: 0; }
:is(.st-key-review_tools,.st-key-manual_review_actions,.st-key-extraction_actions) { flex-wrap: wrap; gap: .75rem; }
:is(.st-key-feedback_identity,.st-key-result_title_exploration_filters,.st-key-result_psf_controls) > [data-testid="stElementContainer"] { flex: 1 1 240px; width: auto !important; min-width: min(100%,240px); }
.st-key-feedback_identity { gap: 1rem; flex-wrap: wrap; }
[class*="st-key-result_chart_selectors_"] { flex-wrap: wrap; }
[class*="st-key-result_chart_selectors_"] > [data-testid="stElementContainer"] { flex: 1 1 180px; min-width: min(100%,180px); }
.st-key-readiness_study_metrics { row-gap: 1.25rem; }
/* Only dense two-dimensional plots scroll; ordinary charts keep fitting their card. */
[class*="st-key-matrix_viewport_"] { container: matrix / inline-size; overflow-x: auto; overscroll-behavior-x: contain; }
[class*="st-key-matrix_viewport_"] > [data-testid="stElementContainer"]:has([data-testid="stPlotlyChart"]) { min-width: var(--fow-matrix-width); max-width: none; width: max(100%,var(--fow-matrix-width)) !important; }
.fow-matrix-scroll-hint { display: none; margin: .1rem 0 .5rem; color: #62585D; font-size: .8rem; }
@container matrix (max-width: 760px) { .fow-matrix-scroll-hint { display: block; } }
@container workspace (max-width: 1250px) { :is(.st-key-reports_deliverables_grid,.fow-loading--reports) { grid-template-columns: repeat(3,minmax(0,1fr)); } }
@container workspace (max-width: 850px) { :is(.st-key-reports_deliverables_grid,.fow-loading--reports) { grid-template-columns: repeat(2,minmax(0,1fr)); } }
@container workspace (max-width: 540px) { :is(.st-key-reports_deliverables_grid,.fow-loading--reports) { grid-template-columns: minmax(0,1fr); } }
@container workspace (max-width: 1100px) {
 :is(.st-key-overview_metrics,.st-key-result_metrics) { grid-template-columns: repeat(2,minmax(0,1fr)); }
 :is([class*="st-key-job_market_featured_"],[class*="st-key-job_market_embedded_"],.st-key-job_market_geography,.st-key-content_panel_training_distribution,.st-key-content_panel_evaluation_results) [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"]) { flex-wrap: wrap; gap: 1.25rem; }
 :is([class*="st-key-job_market_featured_"],[class*="st-key-job_market_embedded_"],.st-key-job_market_geography,.st-key-content_panel_training_distribution,.st-key-content_panel_evaluation_results) [data-testid="stColumn"] { flex: 1 1 100% !important; width: 100% !important; }
 .st-key-review_controls { grid-template-columns: repeat(2,minmax(0,1fr)); }
 [class*="st-key-result_chart_controls_"] { flex-wrap: wrap; }
 [class*="st-key-result_chart_controls_"] > [data-testid="stLayoutWrapper"] { flex: 1 1 240px; }
 [class*="st-key-result_chart_controls_"] > [data-testid="stLayoutWrapper"]:has([class*="st-key-result_chart_selectors_"]) { flex: 1 1 100%; }
 .fow-skeleton-grid { grid-template-columns: minmax(0,1fr); }
 .fow-loading--job_metrics { grid-template-columns: repeat(2,minmax(0,1fr)); }
 :is(.fow-loading--overview,.fow-loading--market) > .fow-skeleton-summary { grid-template-columns: repeat(2,minmax(0,1fr)); }
}
@container workspace (max-width: 760px) {
 [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"]) { flex-wrap: wrap; gap: 1rem; }
 [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] { flex: 1 1 100% !important; width: 100% !important; }
 :is(.st-key-psf_mapping_chart_and_insight,.st-key-alignment_chart_and_insight) > [data-testid="stLayoutWrapper"] { flex: 1 1 100%; }
 :is(.st-key-settings_fields_aligned_threshold,.st-key-settings_fields_stopwords,.st-key-settings_fields_likert_min,.fow-skeleton-settings-fields,.fow-skeleton-form) { grid-template-columns: minmax(0,1fr); }
 .st-key-settings_fields_aligned_threshold > [data-testid="stLayoutWrapper"]:has(.st-key-setting_input_semantic_model) { grid-column: 1; grid-row: auto; border-left: 0; padding-left: 0; }
 .fow-skeleton-settings-fields--0 > .fow-skeleton-field--text { grid-column: 1; grid-row: auto; }
 .fow-loading--form[data-view="usability"] .fow-skeleton-form { grid-template-columns: minmax(0,1fr); }
 .fow-loading--form[data-view="usability"] .fow-skeleton-field:first-child { grid-row: auto; }
 .fow-loading--form[data-view="usability"] .fow-skeleton-field--slider { grid-column: 1; }
 .st-key-readiness_study_metrics > [data-testid="stLayoutWrapper"]:first-child { flex-basis: 100%; }
 .fow-skeleton-tabs { grid-template-columns: repeat(2,minmax(0,1fr)); }
 .st-key-home_next { padding-left: 1rem !important; }
 .st-key-home_next::before { display: none; }
 .st-key-home_next > [data-testid="stHorizontalBlock"], .st-key-readiness_summary > [data-testid="stHorizontalBlock"] { flex-wrap: wrap; }
 .st-key-home_next [data-testid="stHorizontalBlock"] > [data-testid="stLayoutWrapper"], .st-key-readiness_summary [data-testid="stHorizontalBlock"] > [data-testid="stLayoutWrapper"] { flex: 1 1 100%; width: 100% !important; }
 .fow-matrix-scroll-hint { display: block; }
}
@container workspace (max-width: 480px) {
 :is(.st-key-overview_metrics,.st-key-result_metrics,.st-key-review_controls,.fow-loading--metrics,.fow-loading--cards,.fow-loading--job_metrics,.fow-skeleton-summary) { grid-template-columns: minmax(0,1fr); }
 :is(.fow-loading--overview,.fow-loading--market) > .fow-skeleton-summary { grid-template-columns: minmax(0,1fr); }
 :is(.st-key-review_tools,.st-key-manual_review_actions,.st-key-extraction_actions) > [data-testid="stElementContainer"] { width: 100% !important; flex: 1 1 100%; }
 :is(.st-key-review_tools,.st-key-manual_review_actions,.st-key-extraction_actions) button { width: 100%; }
 .st-key-extraction_actions button { min-width: 0; }
 .st-key-workspace_toolbar .fow-breadcrumb > span:nth-child(2) { display: none; }
 .st-key-workspace_toolbar .fow-breadcrumb { flex-wrap: nowrap; gap: .35rem; }
 [class*="st-key-content_metrics_"] > [data-testid="stLayoutWrapper"] { flex-basis: 100%; }
 .st-key-unmapped_summary > [data-testid="stLayoutWrapper"], .st-key-alignment_metrics > [data-testid="stLayoutWrapper"] { flex-basis: 100%; }
}
@media (max-width: 640px) {
 body:has(.st-key-workspace_toolbar) .stMainBlockContainer { padding-top: 3.5rem !important; padding-bottom: max(2rem,env(safe-area-inset-bottom)) !important; }
 body:has([data-testid="stExpandSidebarButton"]) .st-key-workspace_toolbar { padding-left: 0; }
 .st-key-workspace_toolbar { flex-wrap: nowrap; gap: .5rem; }
 .st-key-workspace_toolbar > [data-testid="stLayoutWrapper"]:first-child { flex: 1 1 0; min-width: 0; }
 .stMain :is([data-testid="stTextInput"],[data-testid="stNumberInput"],[data-testid="stTextArea"]) :is(input,textarea), .stMain [role="combobox"] { font-size: 16px; }
 .stMain [data-testid="stWidgetLabel"] p { font-size: .9rem; }
 .stMain [data-testid="stCaptionContainer"] p { font-size: .8rem; }
 .stMain :is(.fow-key-insight,.fow-content-note) :is(p,li) { font-size: .9rem; }
 .stMain :is(.fow-key-insight,.fow-content-note) { padding: 1rem; }
 .stMain [class*="st-key-job_market_featured_"] { padding: 1rem !important; }
}
[data-testid="stPlotlyChart"] .modebar { top: 0 !important; right: 0 !important; background: var(--fow-surface) !important; border-radius: 8px; }
[data-testid="stPlotlyChart"] .modebar-group { display: inline-flex !important; padding: 0 !important; background: transparent !important; }
[data-testid="stPlotlyChart"] .modebar-btn { display: inline-flex !important; align-items: center; justify-content: center; width: 44px; height: 44px; padding: 0 !important; }
[data-testid="stPlotlyChart"] .modebar-btn:hover { background: var(--fow-accent-bg); border-radius: 6px; }
@media (hover: none) { [data-testid="stPlotlyChart"] .modebar { opacity: 1 !important; } }
"""
