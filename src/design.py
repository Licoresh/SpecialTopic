"""Shared presentation only; native controls retain their behavior and accessibility."""
import streamlit as st


def apply_design():
    # Configured theme colors stay authoritative in config.toml.
    colors = {key: st.get_option(f"theme.{option}") for key, option in {
        "accent": "primaryColor", "surface": "backgroundColor",
        "soft": "secondaryBackgroundColor", "border": "borderColor"}.items()}
    tokens = ";".join(f"--fow-{key}:{value}" for key, value in colors.items() if value)
    st.html("<style>:root{" + tokens + "}" + CSS + "</style>")


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
.st-key-manual_review_workspace { background: var(--fow-surface); border: 1px solid var(--fow-border); border-radius: 1rem; padding: 1.25rem; }
.st-key-review_controls { gap: .75rem; }
.st-key-review_detail_tools { gap: .5rem; }
.st-key-review_detail_tools button { min-height: 36px; }
"""


CSS = """
:root {
  --fow-radius: .85rem;
  --fow-shadow: 0 4px 18px rgb(20 40 50 / .04);
  --fow-ink: #173B38;
}
[data-testid="stAppViewContainer"] { background: #F5F7F8; }
.stMainBlockContainer {
  /* Preserve Streamlit's native top clearance for its fixed toolbar. */
  max-width: 1480px; padding-inline: clamp(1rem, 3vw, 3rem); padding-bottom: 4rem;
}
h1,h2,h3 { letter-spacing: -.035em; text-wrap: balance; font-weight: 650; }
h1 { max-width: 30ch; }
p,li { line-height: 1.55; }
.st-key-page_heading, .st-key-overview_heading { margin-bottom: 1.25rem; }
.st-key-page_heading p, .st-key-overview_heading p { max-width: 72ch; color: #52666B; }
.st-key-overview_heading h1 { font-size: clamp(2rem, 3.6vw, 3.2rem); line-height: 1.12; max-width: 23ch; }
.st-key-overview_heading [data-testid="stCaptionContainer"] p { color: #11695F; font-size: .75rem; font-weight: 700; letter-spacing: .12em; }
[data-testid="stCaptionContainer"] { opacity: 1; }
[data-testid="stMetric"] {
  border: 1px solid var(--fow-border); border-radius: var(--fow-radius);
  background: var(--fow-surface); padding: 1.15rem 1.25rem; min-height: 120px;
  box-shadow: var(--fow-shadow);
}
[data-testid="stMetricLabel"] { font-weight: 500; }
[data-testid="stMetricValue"] { font-variant-numeric: tabular-nums; letter-spacing: -.04em; font-weight: 650; }
.st-key-overview_metrics { margin-bottom: .5rem; }
.st-key-overview_metrics > [data-testid="stLayoutWrapper"] { flex: 1 1 220px; }
[data-testid="stButton"] button, [data-testid="stDownloadButton"] button,
[data-testid="stFormSubmitButton"] button, [data-testid="stPopover"] button {
  min-height: 44px; font-weight: 600;
}
button:focus-visible, a:focus-visible, input:focus-visible, textarea:focus-visible,
[role="combobox"]:focus-visible {
  outline: 3px solid var(--fow-accent); outline-offset: 3px;
}
[data-testid="stTextInput"] input { min-height: 44px; }
[data-testid="stTextInput"] input, [data-testid="stNumberInput"] input { background: var(--fow-surface); }
[data-testid="stForm"] { padding: 1.5rem; }
[data-testid="stDataFrame"], [data-testid="stPlotlyChart"] {
  border: 1px solid var(--fow-border); border-radius: var(--fow-radius);
}
[data-testid="stPlotlyChart"] { padding: .35rem; background: var(--fow-surface); }
[data-testid="stSidebarNav"] a { min-height: 40px; border-radius: .5rem; }
[data-testid="stSidebarNav"] a[aria-current="page"] { font-weight: 650; background: #E3EFEC; box-shadow: inset 3px 0 #11695F; }
[data-testid="stSidebarNav"] a:hover { background: #EAF0F1; }
[data-testid="stSidebarNav"] span { overflow-wrap: normal; }
.st-key-workspace_toolbar { border-bottom: 1px solid var(--fow-border); padding-bottom: .85rem; margin-bottom: 1.25rem; }
.st-key-workspace_toolbar [data-testid="stCaptionContainer"] p { color: #52666B; font-size: .75rem; font-weight: 650; letter-spacing: .06em; }
/* Own the profile markup; only the popover and sign-out remain native controls. */
[data-testid="stPopoverBody"][aria-label="Account"] {
  width: 288px; min-width: 0; max-width: calc(100vw - 24px);
  padding: 19px; border: 1px solid #EDF1F7; border-radius: 13px;
  background: #fff; box-shadow: 0 14px 35px rgb(44 70 102 / .16);
  overflow: visible;
}
[data-testid="stPopoverBody"][aria-label="Account"]::before {
  content: ""; position: absolute; top: -6px; right: 56px;
  width: 12px; height: 12px; transform: rotate(45deg); background: #fff;
  border-top: 1px solid #EDF1F7; border-left: 1px solid #EDF1F7;
}
.st-key-account_menu { gap: 19px; }
.account-profile { width: 100%; }
.account-profile h3 {
  margin: 0; padding: 3px 5px 19px; color: #142335;
  font: 700 21px/1.2 sans-serif; letter-spacing: -.4px;
}
.account-profile-identity {
  display: flex; align-items: center; gap: 14px;
  padding: 21px 2px; border-block: 1px solid #E7EDF5;
}
.account-profile-avatar {
  display: flex; align-items: center; justify-content: center;
  flex: 0 0 48px; height: 48px; border-radius: 50%;
  background: #E4EFFF; color: #42617E;
}
.account-profile-avatar svg { width: 29px; height: 29px; }
.account-profile-details { min-width: 0; }
.account-profile-email { color: #0873F9; font: 500 14px/1.4 sans-serif; overflow-wrap: anywhere; }
.account-profile-role { margin-top: 5px; color: #61778B; font: 400 14px/1.4 sans-serif; }
.st-key-account_menu [data-testid="stButton"] button {
  min-height: 46px; border: 1px solid #D5E5FC; background: #F0F6FF;
  border-radius: 8px; color: #344F66; gap: 10px; font-weight: 600;
}
.st-key-account_menu [data-testid="stButton"] button p { font-size: 15px; color: #344F66; }
.st-key-account_menu [data-testid="stButton"] button:hover { background: #E4EFFF; border-color: #ADC9EE; }
.st-key-account_trigger [data-testid="stPopoverButton"] { background: #EDF3F9; border: 1px solid #E0E9F2; border-radius: 8px; }
.st-key-home_next { background: var(--fow-ink); color: white; border: 0; padding: clamp(1.25rem, 3vw, 2rem); margin-block: .5rem 1.25rem; }
.st-key-home_next h3, .st-key-home_next p { color: white; }
.st-key-home_next [data-testid="stCaptionContainer"] p { color: #BDE3D8; font-size: .75rem; letter-spacing: .12em; font-weight: 650; }
.st-key-home_next button[kind="primary"] { background: #F1F8F5; border-color: #F1F8F5; color: #173B38; }
.st-key-home_next button[kind="primary"] p { color: #173B38; }
.st-key-home_next button[kind="primary"]:hover { background: #D9EEE6; border-color: #D9EEE6; }
[class*="st-key-workflow_step_"] { background: white; padding: 1.25rem; gap: .5rem; box-shadow: var(--fow-shadow); }
[class*="st-key-workflow_step_"] h4 { font-size: 1.1rem; }
[class*="st-key-workflow_step_"] [data-testid="stCaptionContainer"] p { color: #11695F; font-size: .75rem; font-weight: 650; }
[class*="st-key-workflow_step_"] [data-testid="stButton"] { margin-top: .5rem; }
[class*="st-key-workflow_step_"] > [data-testid="stElementContainer"]:has([data-testid="stMarkdownContainer"]) { min-height: 3rem; }
.st-key-readiness_summary { border-left: 3px solid #A57227; background: #FFFDF7; padding: 1.25rem; margin-top: 1rem; }
.st-key-readiness_summary h3 { font-size: 1.15rem; }
:is(.st-key-login_shell, .st-key-login_shell_busy) { padding-top: clamp(1rem, 5vh, 4rem); }
:is(.st-key-login_panel, .st-key-login_panel_busy) { padding: clamp(1.25rem, 3vw, 2.25rem); box-shadow: var(--fow-shadow); }
:is(.st-key-login_panel, .st-key-login_panel_busy) h1 { font-size: clamp(1.65rem, 4vw, 2.1rem); }
:is(.st-key-login_status, .st-key-login_status_busy) { min-height: 76px; }
:is(.st-key-login_panel, .st-key-login_panel_busy) [data-testid="stForm"] { padding: 0; border: 0; }
.st-key-workflow_0, .st-key-workflow_3 { gap: 1rem; }
.st-key-workflow_0 > [data-testid="stLayoutWrapper"], .st-key-workflow_3 > [data-testid="stLayoutWrapper"] { flex: 1 1 280px; }
.st-key-settings_form { max-width: 880px; }
[data-testid="stAlert"] p { overflow-wrap: anywhere; }
@media (max-width: 900px) {
  [data-testid="stMetric"] { padding: .9rem; }
}
@media (max-width: 640px) {
  .stMainBlockContainer { padding-inline: 1rem; padding-bottom: 3rem; }
  h1 { font-size: 1.8rem; } h2 { font-size: 1.4rem; }
  [data-testid="stForm"] { padding: 1rem; }
  [data-testid="stMetric"] { min-height: 96px; }
  .st-key-manual_review_workspace { padding: .75rem; }
  .st-key-home_next > [data-testid="stLayoutWrapper"] { width: 100%; }
  :is(.st-key-login_shell, .st-key-login_shell_busy) { padding-top: .5rem; }
  :is(.st-key-login_panel, .st-key-login_panel_busy) { padding: 1.15rem; }
  button p { overflow-wrap: anywhere; }
}
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation-duration: .01ms !important; transition-duration: .01ms !important; }
}
"""
