"""Anonymous Streamlit edition of the public job-ad analyzer."""

from __future__ import annotations

import base64
import hashlib
from html import escape as escape_html
import json
import os
from pathlib import Path
import sys

# Prefer this repository's shared modules even when the host pre-populates
# PYTHONPATH with the project root later in the search order.
ROOT = Path(__file__).resolve().parents[1]
source_root = str(ROOT)
sys.path[:] = [source_root, *(entry for entry in sys.path
                              if os.path.abspath(entry or os.getcwd()) != source_root)]

import pandas as pd
import streamlit as st

APP_ICON = Path(__file__).resolve().parent / "site" / "assets" / "job_market_mark.svg"
st.set_page_config(page_title="Future of Work | Public analyzer", page_icon=APP_ICON,
                   layout="wide", initial_sidebar_state="collapsed")

# The Streamlit watcher uses PYTHONPATH for modules outside the entrypoint folder.
watch_paths = os.environ.get("PYTHONPATH", "").split(os.pathsep)
if source_root not in watch_paths:
    os.environ["PYTHONPATH"] = os.pathsep.join([source_root, *filter(None, watch_paths)])

from src.config import FIELDS, PUBLIC_VERSION, TEXT_FIELDS
from src.column_mapping import suggest_column_mapping
from src.analytics import experience_chart_insight, location_chart_insight
from src.design import apply_design
from src.job_profile import selected_timeline
from src.loaders import load_data
from src.public_engine import MAX_HOSTED_UPLOAD_BYTES, analyze_upload, automatic_analysis_revision, health
from src.ui import (analysis_workflow, chart, collect_result_plots, featured_result_chart, featured_visual_chart, job_market_metrics,
                    alignment_status_insight, chart_download_target, chart_evidence_target, ordered_result_table, result_chart_options, result_count_chart,
                    result_heatmap, result_insight, result_single_metric)
from src.visualization import education_bar, job_title_trend
from src.timeline_table import timeline_table

@st.cache_resource
def _recent_upload_component():
    return st.components.v2.component(
        "fow_public_recent_upload_cache",
        html='<span aria-hidden="true"></span>',
        js=Path(__file__).with_name("recent_upload_storage.js").read_text(encoding="utf-8"),
    )

FIELD_LABELS = {
    "job_title": "Job title", "job_description": "Job description", "required_skills": "Required skills",
    "preferred_skills": "Preferred skills", "qualifications": "Qualifications", "job_id": "Job ID",
    "job_family": "Job family", "company": "Employer", "industry": "Industry", "location": "Location",
    "education_requirement": "Education", "experience_requirement": "Experience", "posting_date": "Posting date",
    "source": "Source", "url": "Source URL", "source_id": "Source record ID",
    "employment_type": "Employment type", "salary": "Salary", "employment_size": "Employer size",
    "search_term": "Search term", "collected_at_utc": "Collection date",
}
PRIMARY_FIELDS = ("job_title", "job_description", "required_skills", "preferred_skills", "qualifications")
OPTIONAL_FIELDS = tuple(field for field in FIELDS["jobs"] if field not in PRIMARY_FIELDS)
ENGINE = health(hosted=True)


def _style():
    apply_design()
    hero_art = base64.b64encode((ROOT / "assets/job_market_hero.svg").read_bytes()).decode("ascii")
    style = """<style>
    [data-testid="stSidebar"],[data-testid="stSidebarCollapsedControl"]{display:none!important}
    [class*="st-key-public_recent_restore"],[class*="st-key-public_recent_save"]{position:fixed!important;left:-10000px!important;top:0!important;width:1px!important;height:1px!important;overflow:hidden!important;opacity:0!important;pointer-events:none!important}
    [data-testid="stHeader"]{background:transparent;height:0}
    .stApp{background:#f8f5f2}
    .stMainBlockContainer{--public-page-pad:clamp(1rem,3vw,2.5rem);max-width:1440px;padding:0 var(--public-page-pad) 4rem;border:1px solid #ebe4e1;border-radius:18px;background:#fff;box-shadow:0 12px 32px #24303d08}
    .public-topbar{position:relative;isolation:isolate;box-sizing:border-box;display:flex;align-items:center;justify-content:space-between;gap:1rem;min-height:104px;width:calc(100% + var(--public-page-pad) + var(--public-page-pad));margin:0 calc(0px - var(--public-page-pad)) 1rem;padding:1rem var(--public-page-pad);overflow:hidden;border:1px solid #e6d9d7;border-radius:12px 12px 0 0;background:#f9efed}
    .public-topbar:after{position:absolute;z-index:-1;inset:12px 0 0 auto;width:min(36%,430px);content:"";background:url("data:image/svg+xml;base64,__HERO_ART__") right bottom/contain no-repeat;opacity:.9;pointer-events:none}
    .public-topbar img{position:relative;z-index:1;display:block;width:clamp(145px,18vw,205px);height:auto}
    .public-version{position:relative;z-index:1;padding:.35rem .7rem;border:1px solid #e6d9d7;border-radius:999px;background:#fffdfbcc;color:#78182b;font-size:.75rem;font-weight:650}
    .public-stage-heading{display:flex;align-items:flex-start;justify-content:space-between;gap:1rem;margin:.1rem 0 1.1rem}
    .st-key-public-stage-actions{gap:.55rem;flex-wrap:wrap!important;margin:.1rem 0 1.1rem}
    .public-stage-heading .public-eyebrow{margin:0 0 .25rem;color:#78182b;font-size:.7rem;font-weight:800;letter-spacing:.085em;text-transform:uppercase}
    .public-stage-heading h1{margin:.1rem 0 .35rem;color:#24303d;font-size:clamp(1.45rem,2.5vw,2rem);line-height:1.15;letter-spacing:-.025em}
    .public-stage-heading p:last-child{max-width:65ch;margin:0;color:#62585d;font-size:.86rem}
    .public-stage-badge{flex:0 0 auto;margin-top:.1rem;padding:.3rem .7rem;border:1px solid #e7e8eb;border-radius:999px;background:#fafafb;color:#647184;font-size:.72rem;font-weight:650;white-space:nowrap}
    .public-steps{display:grid;grid-template-columns:minmax(0,1fr) minmax(2rem,.28fr) minmax(0,1fr) minmax(2rem,.28fr) minmax(0,1fr);align-items:center;gap:.6rem;margin:0 0 1.25rem;padding:.35rem 0 1.15rem;border-bottom:1px solid #e5e3e0}
    .public-step{display:flex;align-items:center;gap:.7rem;color:#24303d;font-size:.85rem;font-weight:650}
    .public-step b{display:grid;place-items:center;flex:0 0 34px;height:34px;border:1px solid #e6d9d7;border-radius:50%;background:#fffcfa;color:#78182b;font-size:.78rem}
    .public-step[data-state="current"] b{border-color:#78182b;background:#78182b;color:#fff;box-shadow:0 2px 8px #78182b26}
    .public-step[data-state="complete"] b{border-color:#cce3d8;background:#edf6f1;color:#16634f}
    .public-step small{display:block;color:#62585d;font-size:.72rem;font-weight:400}
    .public-step-line{height:1px;background:#e5e3e0}
    .st-key-public-upload-card{width:100%;height:100%;min-height:350px;display:flex;flex-direction:column;justify-content:center;gap:.8rem;padding:0;border:0;border-radius:0;background:transparent;box-shadow:none}
    .st-key-public-workflow-card{width:100%;min-width:0;height:100%;padding:clamp(1rem,2.2vw,1.4rem);border:1px solid #e6d9d7;border-radius:12px;background:#fffcfa;box-shadow:0 2px 8px #4d102007}
    .st-key-public-recent-upload{margin-top:.8rem;padding:.8rem 1rem;border:1px solid #e6d9d7;border-radius:10px;background:#fffcfa}
    .public-recent-eyebrow{display:block;color:#78182b;font-size:.68rem;font-weight:800;letter-spacing:.06em;text-transform:uppercase}
    .public-recent-filename{display:block;margin-top:.15rem;color:#24303d;font-size:.88rem;font-weight:700;overflow-wrap:anywhere}
    .st-key-public-upload-card [data-testid="stFileUploaderDropzone"]{position:relative;box-sizing:border-box;min-height:300px;display:flex!important;flex-direction:column!important;align-items:center!important;justify-content:center!important;gap:.75rem;padding:9rem 1rem 1rem!important;border:1px dashed #c9a1a8;border-radius:10px;background:linear-gradient(135deg,#fff 0%,#fcf6f6 100%);text-align:center}
    .st-key-public-upload-card [data-testid="stFileUploaderDropzone"]>div{display:flex;flex-direction:column;align-items:center;gap:.4rem}
    .st-key-public-upload-card [data-testid="stFileUploaderDropzone"]:before{position:absolute;top:2rem;left:50%;display:grid;place-items:center;width:52px;height:52px;transform:translateX(-50%);border-radius:14px;background:#f7edef;color:#78182b;content:"↥";font-size:1.8rem;font-weight:700;pointer-events:none}\n    .st-key-public-upload-card [data-testid="stFileUploaderDropzone"]:after{position:absolute;top:6rem;left:1rem;right:1rem;color:#24303d;content:"Drop your CSV file here\\A or select a file from your device";font-size:.9rem;font-weight:650;line-height:1.5;text-align:center;white-space:pre-line;pointer-events:none}\n    .st-key-public-upload-card [data-testid="stFileUploaderDropzone"]:hover{border-color:#78182b;background:#f7edef}
    .st-key-public-upload-card [data-testid="stFileUploaderDropzone"] [data-testid="stBaseButton-secondary"][aria-label=""]{display:inline-flex!important;align-items:center;justify-content:center;gap:.35rem;min-width:9rem;min-height:44px;padding:.65rem 1rem!important;border:0;border-radius:8px;background:#78182b;color:white;font-size:.86rem!important;font-weight:650;line-height:1.2;text-align:center;white-space:nowrap}
    .st-key-public-upload-card [data-testid="stFileUploaderDropzone"] [data-testid="stBaseButton-secondary"][aria-label=""]:hover{background:#5e1221;color:white}
    .stFormSubmitButton button,.stButton button[kind="primary"],.stDownloadButton button{min-height:44px;border-radius:8px;font-weight:650;transition:background-color .16s ease,transform .16s ease}
    .stFormSubmitButton button,.stButton button[kind="primary"]{background:#78182b;border-color:#78182b;color:#fff}
    .stButton button[kind="primary"]:hover{background:#4d1020;border-color:#4d1020;transform:translateY(-1px)}
    .st-key-public-mapping-card{height:100%;padding:clamp(1rem,2.2vw,1.4rem);border:1px solid #e6d9d7;border-radius:12px;background:#fffcfa;box-shadow:0 2px 8px #4d102007}
    .st-key-public-mapping-card [data-testid="stHorizontalBlock"]{align-items:center}
    .public-workflow-title{margin:0 0 .25rem;color:#24303d;font-size:1.12rem;font-weight:700}
    .public-process-rail{display:grid;gap:.35rem;margin:1rem 0;padding:0;list-style:none}
    .public-process-rail li{display:grid;grid-template-columns:36px minmax(0,1fr);align-items:start;gap:.7rem;padding:.5rem;border-radius:9px}
    .public-step-number{display:grid;place-items:center;width:34px;height:34px;border-radius:50%;background:#f7edef;color:#78182b;font-size:.76rem;font-weight:800}
    .public-process-rail strong,.public-process-rail small{display:block}
    .public-process-rail strong{font-size:.86rem}
    .public-process-rail small{margin-top:.08rem;color:#62585d;font-size:.76rem}
    .public-workflow-note{margin-top:1rem;padding-top:.8rem;border-top:1px solid #e6d9d7;color:#62585d;font-size:.78rem}
    .public-map-head{display:grid;grid-template-columns:1.5fr 1fr .75fr;gap:.8rem;padding:.55rem .7rem;color:#647184;background:#fafafb;font-size:.72rem;font-weight:750;letter-spacing:.04em;text-transform:uppercase}
    [class*="st-key-public-map-row-"]{padding:.12rem .65rem;border-bottom:1px solid #eceef1}
    [class*="st-key-public-map-row-"]:last-child{border-bottom:0}
    [class*="st-key-public-map-row-"] [data-testid="stHorizontalBlock"]{align-items:center}
    .public-file-type{display:grid;place-items:center;width:42px;height:42px;border-radius:10px;background:#f7edef;color:#78182b;font-size:.75rem;font-weight:800}
    .public-filename{color:#24303d;font-size:.88rem;font-weight:700}
    .public-map-status{display:inline-flex;align-items:center;min-height:1.65rem;padding:.2rem .55rem;border-radius:999px;background:#f5f1ef;color:#62585d;font-size:.72rem;font-weight:700;white-space:nowrap}
    .public-map-status[data-state="complete"]{background:#edf6f1;color:#16634f}
    .public-map-status[data-state="required"]{background:#f7edef;color:#78182b}
    .public-map-status[data-state="error"]{background:#fff1f0;color:#a22e3d}
    .public-checklist{display:grid;gap:.75rem;margin:.8rem 0 1rem}
    .public-check{display:flex;align-items:flex-start;gap:.6rem;color:#475569;font-size:.87rem}
    .public-check b{color:#16634f}
    .public-check[data-state="pending"] b{color:#9b8b7e}
    .public-readiness{display:flex;justify-content:space-between;gap:1rem;margin:.9rem 0 .35rem;color:#24303d;font-size:.82rem;font-weight:700}
    .public-actions{display:flex;justify-content:flex-end;gap:.55rem;margin-top:.9rem}
    .public-file-meta{color:#62585d;font-size:.8rem}
    .public-result-meta{display:flex;flex-wrap:wrap;align-items:center;gap:.55rem .8rem;min-width:0}
    .public-result-file{display:flex;flex:1 1 13rem;align-items:center;gap:.55rem;min-width:0}
    .public-result-file-icon{display:grid;flex:0 0 38px;place-items:center;width:38px;height:38px;border-radius:10px;background:#f7edef;color:#78182b;font-size:21px}
    .public-result-file-copy{min-width:0}
    .public-result-file-copy strong,.public-result-file-copy small{display:block}
    .public-result-file-copy strong{color:#24303d;font-size:.84rem;line-height:1.3;overflow-wrap:anywhere}
    .public-result-file-copy small{margin-top:.12rem;color:#62585d;font-size:.71rem}
    .public-linked-chart-indicator{display:flex;align-items:center;justify-content:center;gap:.5rem;margin:.1rem 0;color:#647184;font-size:.73rem;font-weight:650;line-height:1.3;text-align:center}
    .public-linked-chart-indicator:before,.public-linked-chart-indicator:after{content:"";flex:1;max-width:72px;height:1px;background:#e5d7d5}
    .public-linked-chart-indicator .material-symbols-rounded{color:#78182b;font-size:18px}
    .public-result-facts{display:flex;flex:2 1 min(32rem,100%);flex-wrap:nowrap;min-width:0;gap:3px;overflow-x:auto;scrollbar-width:thin;container-type:inline-size}
    .public-result-fact{display:inline-flex;flex:none;align-items:center;gap:.35em;min-height:2.5em;padding:.35em .65em;border:1px solid #e9dfdc;border-radius:999px;background:#fcf9f7;font-size:clamp(.5rem,min(1.6cqi,.44rem + .22vw),.64rem);line-height:1.25;white-space:nowrap}
    .public-result-fact span{color:#647184}
    .public-result-fact strong{color:#24303d;font-weight:700}
    .public-result-fact .public-result-label-compact{display:none}
    @container(max-width:425px){
        .public-result-fact{gap:.25em;padding-inline:.28em}
        .public-result-fact .public-result-label-full{position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%)}
        .public-result-fact .public-result-label-compact:not(:empty){display:inline}
    }
    .public-privacy{margin:.1rem 0 0;color:#62585d;font-size:.78rem}
    .st-key-public-upload-footer{margin-top:1rem;padding-top:.75rem;border-top:1px solid #e6d9d7}
    .st-key-public-upload-footer [data-testid="stHorizontalBlock"]{align-items:center}
    .st-key-public-processing-overlay{position:fixed!important;z-index:100000!important;inset:0!important;width:100vw!important;height:100dvh!important;display:flex!important;align-items:center!important;justify-content:center!important;padding:clamp(1rem,5vw,3rem)!important;overflow:auto!important;background:#19171870!important;backdrop-filter:blur(2px)}
    .st-key-public-processing-overlay[hidden]{display:none!important}
    [data-testid="stElementContainer"]:has(.st-key-public-processing-overlay){display:contents!important;height:0!important;margin:0!important;padding:0!important}
    [data-testid="stLayoutWrapper"]:has(.st-key-public-processing-overlay){display:contents!important}
    .st-key-public-processing-card{position:fixed!important;z-index:100001!important;top:50dvh!important;left:50vw!important;transform:translate(-50%,-50%)!important;width:min(760px,calc(100vw - 2rem))!important;max-height:calc(100dvh - 2rem);margin:0!important;padding:clamp(1.6rem,5vw,3.5rem);overflow:auto;border:1px solid #ffffffb8;border-radius:18px;background:#fff;box-shadow:0 18px 60px #4d10201c;text-align:center}
    .public-processing-brand{display:inline-flex;align-items:center;gap:.7rem;margin-bottom:1.7rem;text-align:left}
    .public-processing-brand img{width:46px;height:48px}
    .public-processing-brand strong,.public-processing-brand small{display:block}
    .public-processing-brand strong{color:#4d1020;font-size:1.05rem}
    .public-processing-brand small{color:#62585d;font-size:.76rem}
    .public-processing-title{margin:.2rem 0 .5rem;color:#24303d;font-size:clamp(1.8rem,4vw,2.5rem);letter-spacing:-.035em}
    .public-processing-copy{color:#62585d}
    .public-processing-status{margin-top:1.4rem;color:#4d1020;font-size:.9rem;font-weight:650}
    .public-processing-meter{display:flex;align-items:center;gap:1rem}
    .public-processing-meter progress{appearance:none;flex:1;min-width:0;height:8px;border:0;border-radius:999px;background:#f2eeec;overflow:hidden}
    .public-processing-meter progress::-webkit-progress-bar{background:#f2eeec}
    .public-processing-meter progress::-webkit-progress-value{background:#78182b}
    .public-processing-meter progress::-moz-progress-bar{background:#78182b}
    .public-processing-percent{color:#4d1020;font-size:.83rem;font-variant-numeric:tabular-nums;font-weight:700;text-align:right}
    .public-processing-continue{min-height:44px;padding:0 .9rem;border:0;border-radius:8px;background:#78182b;color:white}
    .public-processing-privacy{margin:1.3rem 0 0;color:#62585d;font-size:.76rem}
    /* Preload every chart, then skip rendering inactive section contents. */
    .st-key-public-results-tabs [data-testid="stTabs"]{position:relative}
    .st-key-public-results-tabs [data-testid="stTabPanel"][data-inert="true"]{display:block!important;position:absolute;inset:0 0 auto;height:0;overflow:hidden;visibility:hidden}
    .stApp:not(:has(.st-key-public-processing-overlay:not([hidden]))) .st-key-public-results-tabs [data-testid="stTabPanel"][data-inert="true"]{content-visibility:hidden}
    .stApp [data-stale="true"]{opacity:1!important;filter:none!important;transition:none!important}
    .st-key-public-results-tabs [data-testid="stTabs"] [role="tablist"]{display:flex!important;align-items:stretch;width:100%;flex-wrap:nowrap!important;gap:.25rem!important;overflow-x:auto;overflow-y:hidden;border:1px solid #e5d7d5;border-radius:10px;background:#fcf9f7;padding:.25rem;scrollbar-width:thin;scrollbar-color:#d5c4c2 transparent}
    .st-key-public-results-tabs [data-testid="stTabs"] [role="tab"]{box-sizing:border-box;display:flex;flex:1 0 188px;align-items:center;justify-content:center;gap:.45rem;min-width:188px!important;max-width:none;min-height:44px;margin:0;padding:.45rem .55rem;border:0!important;border-radius:7px;background:transparent;color:#24303d;white-space:nowrap;font-size:.78rem;line-height:1.2;text-align:center}
    .st-key-public-results-tabs [data-testid="stTabs"] [role="tab"]>div{display:flex;align-items:center;justify-content:center;white-space:nowrap}
    .st-key-public-results-tabs [data-testid="stTabs"] [role="tab"]::before{display:inline-flex;flex:0 0 21px;align-items:center;justify-content:center;width:21px;height:21px;font:21px/1 "Material Symbols Rounded";font-feature-settings:"liga";font-variation-settings:"FILL" 0,"wght" 500,"GRAD" 0,"opsz" 20}
    .st-key-public-results-tabs [data-testid="stTabs"] [role="tab"]:nth-of-type(1)::before{content:"work"}
    .st-key-public-results-tabs [data-testid="stTabs"] [role="tab"]:nth-of-type(2)::before{content:"location_on"}
    .st-key-public-results-tabs [data-testid="stTabs"] [role="tab"]:nth-of-type(3)::before{content:"school"}
    .st-key-public-results-tabs [data-testid="stTabs"] [role="tab"]:nth-of-type(4)::before{content:"layers"}
    .st-key-public-results-tabs [data-testid="stTabs"] [role="tab"]:nth-of-type(5)::before{content:"fact_check"}
    .st-key-public-results-tabs [data-testid="stTabs"] [role="tab"]:nth-of-type(6)::before{content:"monitoring"}
    .st-key-public-results-tabs [data-testid="stTabs"] [role="tab"]:hover{background:#f4e6e8;color:#641127}
    .st-key-public-results-tabs [data-testid="stTabs"] [role="tab"][aria-selected="true"]{background:#78182b!important;color:#fff!important;border-radius:7px}
    .st-key-public-results-tabs [data-testid="stTabs"] [role="tab"][aria-selected="true"]:hover{background:#641127!important;color:#fff!important}
    .st-key-public-results-tabs [data-testid="stTabs"] [data-baseweb="tab-highlight"]{display:none!important}
    .st-key-public-results-tabs [data-testid="stTabs"] [role="tab"]:focus-visible{outline:2px solid #d6a33d;outline-offset:-2px}
    .st-key-public-results-heading{align-items:center;justify-content:space-between;gap:1rem;margin:.35rem 0 .5rem;padding-top:.6rem;border-top:1px solid #e5e3e0}
    .st-key-public-results-heading [data-testid="stDownloadButton"] button{min-height:44px;white-space:nowrap}
    [class*="st-key-result_chart_controls_public"]{margin:.1rem 0 .9rem;padding:.65rem .75rem;border:1px solid #e5d8d2;border-radius:12px;background:#fbf8f6}
    [class*="st-key-result_chart_selectors_public"] [data-testid="stSelectbox"]{min-width:min(12rem,42vw)}
    [class*="st-key-result_chart_controls_public"] [data-testid="stSelectbox"] label{color:#62585d;font-size:.72rem;font-weight:650}
    [class*="st-key-result_chart_controls_public"] [data-testid="stCaptionContainer"]{padding-top:.2rem;color:#647184;font-size:.7rem}
    [class*="st-key-result_single_"] [data-testid="stMetricValue"],.st-key-public_education_single [data-testid="stMetricValue"]{color:#86142D!important}
    .st-key-public-footer{margin-top:3rem;padding-top:1rem;border-top:1px solid #e5e3e0;color:#647184;font-size:.75rem}
    .stApp:has(.st-key-public-processing-overlay:not([hidden])){overflow:hidden}
    @media(max-width:720px){
        [data-testid="stToolbar"]{display:none!important}
        .stMainBlockContainer{--public-page-pad:.9rem;padding-inline:var(--public-page-pad);border-radius:14px}
        .public-topbar{min-height:82px;padding:.7rem var(--public-page-pad)}
        .public-topbar:after{width:42%;opacity:.32}
        .public-steps{grid-template-columns:repeat(3,minmax(0,1fr));gap:.25rem;margin-bottom:1rem;padding:.25rem 0 .8rem}
        .public-step-line{display:none}
        .public-step{min-width:0;flex-direction:column;justify-content:center;gap:.3rem;text-align:center;font-size:.73rem}
        .public-step b{flex-basis:30px;width:30px;height:30px;font-size:.72rem}
        .public-step span{max-width:100%;font-size:clamp(.62rem,2.4vw,.74rem);line-height:1.15;text-align:center;overflow-wrap:anywhere}
        .public-step small{display:none}
        .st-key-public-upload-card{min-height:0;gap:.55rem}
        .public-map-head{grid-template-columns:repeat(2,minmax(0,1fr));gap:.35rem;font-size:.65rem}
        .public-map-head span:first-child{grid-column:1/-1}
        [class*="st-key-public-map-row-"]{padding:.4rem .25rem}
        [class*="st-key-public-map-row-"] [data-testid="stHorizontalBlock"]{display:grid!important;grid-template-columns:repeat(2,minmax(0,1fr));gap:.25rem .6rem!important}
        [class*="st-key-public-map-row-"] [data-testid="stHorizontalBlock"]>[data-testid="stLayoutWrapper"]:first-child{grid-column:1/-1;width:100%!important}
        [class*="st-key-public-map-row-"] [data-testid="stHorizontalBlock"]>[data-testid="stLayoutWrapper"]:nth-child(2),
        [class*="st-key-public-map-row-"] [data-testid="stHorizontalBlock"]>[data-testid="stLayoutWrapper"]:nth-child(3){width:100%!important;min-width:0}
        .public-result-facts{flex-basis:100%;flex-wrap:wrap;overflow:visible}
        [class*="st-key-result_chart_selectors_public"] [data-testid="stHorizontalBlock"]{flex-wrap:wrap!important}
        [class*="st-key-result_chart_selectors_public"] [data-testid="stSelectbox"]{min-width:100%}
        .st-key-public-results-heading{align-items:stretch;flex-wrap:wrap}
        .st-key-public-results-heading [data-testid="stDownloadButton"],.st-key-public-results-heading [data-testid="stDownloadButton"] button{width:100%}
        .st-key-public-processing-overlay{padding:1rem!important}
        .st-key-public-processing-card{padding:1.5rem 1rem}
        .st-key-public-stage-actions{justify-content:flex-start!important}
        .st-key-public-stage-actions [data-testid="stDownloadButton"],.st-key-public-stage-actions [data-testid="stDownloadButton"] button{width:100%}
        .st-key-public-upload-footer [data-testid="stHorizontalBlock"]{flex-wrap:wrap!important}
    }
    @media(max-width:475px){
        .stMainBlockContainer{--public-page-pad:.75rem;padding-bottom:2rem}
        .public-topbar{min-height:72px;padding-block:.55rem}
        .public-topbar img{width:clamp(128px,38vw,145px)}
        .public-version{padding:.25rem .42rem;font-size:.62rem}
        .public-stage-heading{gap:.5rem;margin-bottom:.75rem}
        .public-stage-heading h1{font-size:clamp(1.25rem,5.4vw,1.5rem);line-height:1.15}
        .public-stage-heading p:last-child{font-size:.8rem;line-height:1.45}
        .public-step{gap:.25rem;font-size:.68rem}
        .public-step b{flex-basis:28px;width:28px;height:28px}
        .st-key-public-upload-card [data-testid="stFileUploaderDropzone"]{min-height:250px;padding:7.25rem 1rem 1rem!important}
        .st-key-public-upload-card [data-testid="stFileUploaderDropzone"]:before{top:1.45rem;width:46px;height:46px;font-size:1.55rem}
        .st-key-public-upload-card [data-testid="stFileUploaderDropzone"]:after{top:5.2rem;font-size:.8rem}
        .st-key-public-upload-card [data-testid="stFileUploaderDropzone"] [data-testid="stBaseButton-secondary"][aria-label=""]{margin-top:.55rem!important}
        .st-key-public-workflow-card,.st-key-public-mapping-card{padding:.9rem}
        .st-key-public-recent-upload{padding:.75rem}
        .st-key-public-recent-upload [data-testid="stHorizontalBlock"]{flex-wrap:wrap!important}
        .st-key-public-recent-upload [data-testid="stButton"],.st-key-public-recent-upload button{width:100%}
        .st-key-result_metrics{display:grid!important;grid-template-columns:repeat(2,minmax(0,1fr));gap:.55rem!important}
        .st-key-result_metrics{grid-auto-rows:6.25rem;align-items:stretch}
        .st-key-result_metrics>[data-testid="stLayoutWrapper"]{width:100%!important;min-width:0!important}
        [class*="st-key-result_metric_"]{height:100%;min-height:0;padding:.55rem!important}
        [class*="st-key-result_metric_"] [data-testid="stMetric"]>div{min-height:48px;padding-left:39px}
        [class*="st-key-result_metric_"] [data-testid="stMetricValue"]{font-size:1.42rem;line-height:1.05}
        [class*="st-key-result_metric_"] [data-testid="stMetricLabel"] p{display:-webkit-box;max-height:2.4em;overflow:hidden;-webkit-box-orient:vertical;-webkit-line-clamp:2;font-size:.62rem;line-height:1.2}
        [class*="st-key-result_metric_"] [data-testid="stMetricIcon"]{left:0;width:30px;height:36px;font-size:23px}
        .st-key-result_metric_1 [data-testid="stMetricIcon"]{left:-.25rem;width:28px;height:32px;font-size:19px}
        .fow-analysis-pipeline ol{grid-template-columns:minmax(0,1fr)!important;gap:1.3rem!important}
        .fow-analysis-pipeline li{min-height:68px;padding:.6rem}
        .fow-analysis-pipeline li+li:before{display:grid;place-items:center;content:"↓";position:absolute;z-index:1;top:-1.18rem;left:50%;width:24px;height:16px;transform:translateX(-50%);border-radius:999px;background:#fff;color:#78182b;font-size:1rem;line-height:1}
        .fow-analysis-pipeline strong{white-space:nowrap;overflow-wrap:normal}
        .fow-analysis-pipeline p{display:-webkit-box;min-height:2.4em;max-height:2.4em;overflow:hidden;-webkit-box-orient:vertical;-webkit-line-clamp:2;font-size:.68rem;line-height:1.2}
        .st-key-public-results-tabs [data-testid="stTabs"] [role="tab"]{flex:0 0 clamp(158px,55vw,188px);min-width:clamp(158px,55vw,188px)!important;font-size:.74rem}
        .st-key-public-results-tabs [data-testid="stTabs"] [role="tablist"]{scroll-snap-type:x proximity;scroll-padding-inline:.25rem}
        .st-key-public-results-tabs [data-testid="stTabs"] [role="tab"]{scroll-snap-align:start}
        .st-key-public-results-heading [data-testid="stDownloadButton"]{width:100%}
        .st-key-public-results-heading [data-testid="stDownloadButton"] button{width:100%}
        [class*="st-key-public_result_chart_header_"] [data-testid="stHorizontalBlock"]{flex-wrap:wrap!important;gap:.35rem!important}
        [class*="st-key-public_result_chart_header_"] [data-testid="stHorizontalBlock"]>[data-testid="stLayoutWrapper"]{width:100%!important;flex:1 1 100%!important;min-width:0!important}
        [class*="st-key-public_result_chart_header_"] [data-testid="stHorizontalBlock"]>[data-testid="stLayoutWrapper"]:last-child [data-testid="stPopover"]{width:max-content!important;margin-left:auto}
        [class*="st-key-public_result_chart_header_"] [data-testid="stHorizontalBlock"]>[data-testid="stLayoutWrapper"]:last-child [data-testid="stPopover"] button{width:auto!important;min-width:0!important;white-space:nowrap}
        [class*="st-key-public_result_chart_header_"] [data-testid="stHorizontalBlock"]>[data-testid="stLayoutWrapper"]:last-child [data-testid="stHorizontalBlock"]{justify-content:flex-end!important}
        .public-processing-title{font-size:1.65rem}
        .public-processing-meter{gap:.6rem}
        .public-processing-privacy{font-size:.7rem}
        .public-process-rail{gap:.25rem}
        .public-process-rail li{gap:.4rem;padding-inline:.25rem}
        .public-step-number{width:28px;height:28px;font-size:.7rem}
        .public-process-rail strong{font-size:.78rem;line-height:1.25}
        .public-process-rail small{font-size:.68rem;line-height:1.3}
        .public-actions{gap:.4rem}
        .public-actions [data-testid="stButton"]{flex:1}
    }
    </style>""".replace("__HERO_ART__", hero_art)
    st.html(style)


def _topbar(step: int):
    logo = (ROOT / "assets/job_market_brand.svg").read_text(encoding="utf-8")
    logo_uri = "data:image/svg+xml;base64," + base64.b64encode(logo.encode("utf-8")).decode("ascii")
    st.html(f'<header class="public-topbar"><img alt="Future of Work · Job Market Analytics" src="{logo_uri}"><span class="public-version">Public analyzer · v{PUBLIC_VERSION}</span></header>')
    steps = [(1, "Upload job data", "Choose your CSV file."),
             (2, "Review & analyze", "Validate and process data."),
             (3, "View results", "Explore and export insights.")]
    step_markup = []
    for index, name, detail in steps:
        state = "complete" if index < step else "current" if index == step else "upcoming"
        number = "✓" if state == "complete" else f"{index:02}"
        step_markup.append(f'<div class="public-step" data-state="{state}"><b>{number}</b><span>{name}<small>{detail}</small></span></div>')
    connectors = '<span class="public-step-line" aria-hidden="true"></span>'
    st.html('<div class="public-steps" aria-label="Analysis process">' + connectors.join(step_markup) + "</div>")


def _stage_heading(step, title, intro, badge=None, *, download_template=False):
    heading, actions = st.columns([2.8, 1.4] if download_template else [3, 1],
                                  vertical_alignment="center")
    with heading:
        st.html(f'<header class="public-stage-heading"><div><p class="public-eyebrow">STEP {step:02} / 03</p><h1>{escape_html(title)}</h1><p>{escape_html(intro)}</p></div></header>')
    with actions:
        with st.container(horizontal=True, vertical_alignment="center",
                          horizontal_alignment="right", key="public-stage-actions"):
            if badge:
                st.html(f'<span class="public-stage-badge">{escape_html(badge)}</span>')
            if download_template:
                columns = ("job_title", "job_description", "required_skills", "preferred_skills",
                           "qualifications", "education_requirement", "experience_requirement",
                           "location", "company", "posting_date")
                template = (",".join(columns) + "\r\n").encode("utf-8-sig")
                st.download_button("Download CSV template", template, "job_ads_template.csv",
                                   "text/csv", icon=":material/download:", key="public_csv_template")


def _column_label(name):
    if name.startswith("unnamed_column_"):
        return f"Column {name.rsplit('_', 1)[-1]} (blank header)"
    if "__" in name and name.rsplit("__", 1)[-1].isdigit():
        base, suffix = name.rsplit("__", 1)
        return f"{base} [{suffix}]"
    return name


def _mapping_row(field, columns, mapping, file_hash, duplicate_columns=()):
    label = FIELD_LABELS.get(field, field.replace("_", " ").title())
    key = f"public-map-{file_hash[:10]}-{field}"
    if key not in st.session_state:
        st.session_state[key] = mapping.get(field, "")
    source, target, status = st.columns([1.5, 1, .75], vertical_alignment="center")
    with source:
        value = st.selectbox(f"CSV column for {label}", ["", *columns],
            format_func=lambda item: "Choose a column" if not item else _column_label(item),
            key=key, label_visibility="collapsed", help=f"Choose which CSV column contains {label.lower()}.")
    with target:
        st.markdown(f"**{label}**")
    with status:
        duplicate = value in duplicate_columns
        state = "error" if duplicate else "complete" if value else "pending"
        text = "Duplicate" if duplicate else "Matched" if value else "Choose a column"
        st.html(f'<span class="public-map-status" data-state="{state}">{text}</span>')
    return value


def _read_upload(upload):
    return _read_content(upload.getvalue(), upload.name)


def _read_content(content, filename):
    if len(content) > MAX_HOSTED_UPLOAD_BYTES:
        raise ValueError("This public Streamlit app accepts CSV files up to 4 MB.")
    frame = load_data(content, Path(filename).name, encoding="auto")
    if len(frame) > 100_000:
        raise ValueError("This public analysis is limited to 100,000 rows per upload.")
    return content, frame


def _component_value(state, name):
    return state.get(name) if isinstance(state, dict) else getattr(state, name, None)


def _upload_revision(recent):
    identity = json.dumps([recent["file_hash"], recent["filename"], recent.get("mapping", {})],
                          sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def _mount_upload_cache(action, *, key, record=None, revision=None):
    return _recent_upload_component()(
        data={"action": action, "record": record, "revision": revision}, key=key,
        on_recent_change=lambda: None, on_saved_change=lambda: None, on_error_change=lambda: None,
        width="content", height=1,
    )


def _restore_recent_upload():
    state = _mount_upload_cache("restore", key="public_recent_restore")
    record = _component_value(state, "recent")
    if not record or st.session_state.get("public_recent_upload"):
        return
    try:
        content = base64.b64decode(record["content"], validate=True)
        file_hash = hashlib.sha256(content).hexdigest()
        filename = Path(record["filename"]).name
        if file_hash != record["fileHash"]:
            return
        content, preview = _read_content(content, filename)
        mapping = record.get("mapping") if isinstance(record.get("mapping"), dict) else {}
        recent = {"file_hash": file_hash, "filename": filename, "content": content,
                  "preview": preview, "mapping": mapping}
    except (KeyError, TypeError, ValueError, OSError):
        return
    st.session_state["public_recent_upload"] = recent
    st.session_state["_public_recent_saved_revision"] = _upload_revision(recent)
    st.session_state["_public_recent_saved_file_hash"] = file_hash


@st.fragment
def _persist_recent_upload():
    recent = st.session_state.get("public_recent_upload")
    if not recent:
        _mount_upload_cache("idle", key="public_recent_save")
        return
    revision = _upload_revision(recent)
    if st.session_state.get("_public_recent_saved_revision") == revision:
        _mount_upload_cache("idle", key="public_recent_save")
        return
    same_file = st.session_state.get("_public_recent_saved_file_hash") == recent["file_hash"]
    record = {"fileHash": recent["file_hash"], "filename": recent["filename"],
              "mapping": recent.get("mapping", {})}
    action = "update" if same_file else "save"
    if not same_file:
        record["content"] = base64.b64encode(recent["content"]).decode("ascii")
    state = _mount_upload_cache(action, key="public_recent_save", record=record, revision=revision)
    if _component_value(state, "saved") == revision:
        st.session_state["_public_recent_saved_revision"] = revision
        st.session_state["_public_recent_saved_file_hash"] = recent["file_hash"]


def _reset():
    st.session_state["public_upload_key"] = st.session_state.get("public_upload_key", 0) + 1
    # Keep public_recent_upload so it can be reused until this browser session ends.
    for key in ("public_file_hash", "public_filename", "public_content", "public_preview", "public_mapping", "public_result", "public_error", "public_stage", "public_using_recent_upload"):
        st.session_state.pop(key, None)
    st.rerun()


def _frame(rows, label, value, *, total=None):
    frame = pd.DataFrame(rows or []).rename(columns={"label": label, "count": value})
    if total and not frame.empty:
        frame["job_ads_pct"] = frame[value].astype(float).div(total).mul(100)
    return frame


def _bar(rows, label, value, title, heading, total, key, order, limit, list_title="Top Displayed Skills",
         *, extra_controls=None, note=None):
    frame = rows if isinstance(rows, pd.DataFrame) else _frame(rows, label, value, total=total)
    if frame.empty:
        if extra_controls:
            with st.container(border=True, key=f"job_market_featured_{key}"):
                st.subheader(title, icon=":material/bar_chart:")
                extra_controls()
                st.info("No chartable evidence is available for this selection.")
        else:
            st.info("No chartable evidence is available for this selection.")
        return
    featured_result_chart(
        label, value, heading, total,
        lambda: result_count_chart(frame, label, value, title, order=order,
                                   limit=limit, show_heading=False),
        key=key, render_controls=extra_controls,
        card_heading=title, embedded=False, note=note,
    )


def _controls(prefix):
    return result_chart_options(key_prefix=prefix, public=True)


def _chart_settings(page):
    st.session_state["_fow_current_page"] = page
    st.session_state["_table_number"] = 0


@st.fragment
def _skills(result):
    _chart_settings("Job Market Analysis")
    charts, ads = result["charts"], result["summary"]["ads"]
    order, limit = _controls("public_skills")
    items = [("skills", "employer_skill", "employer_demand_count", "Employer-requested skills", "Top requested skills", "skills", "Each ad counts once per grouped skill; skill categories overlap."),
             ("technicalSkills", "skill_label", "job_ads", "Technical skills", "Top technical skills", "technical_skills", "Distinct ads per technical skill."),
             ("enablingSkills", "skill_label", "job_ads", "Enabling and interpersonal skills", "Top enabling skills", "soft_/_enabling_skills", "Distinct ads per enabling skill."),
             ("broadAreas", "category_group", "job_ads", "Broad competency areas", "Most common broad area", "broad_competency_areas", "An ad may contribute to several overlapping areas.")]
    for source, label, value, title, heading, key, note in items:
        _bar(charts.get(source), label, value, title, heading, ads, key, order, limit,
             note=note)


def _heatmap(matrix, title, summary, rows, key, *, count_label="Job advertisements", shares=None, denominators=None,
             share_label="Share within group", denominator_label="Advertisements in group", group_label="group",
             transpose=False, render_controls=None):
    if matrix.empty or not matrix.to_numpy().any():
        if render_controls:
            render_controls()
        st.info("No chartable evidence is available for this comparison.")
        return
    def render():
        result_heatmap(matrix, title, count_label=count_label, share_matrix=shares, row_denominators=denominators,
                       share_label=share_label, denominator_label=denominator_label, row_group_label=group_label,
                       transpose=transpose)

    if matrix.size == 1:
        if render_controls:
            with st.container(border=True, key=f"public-single-heatmap-{key}"):
                render_controls()
                render()
        else:
            render()
    else:
        featured_visual_chart(render, summary, rows, key=key, insight_title="Heatmap Insight",
                              list_title="Top Skill × Group", render_controls=render_controls, embedded=False)


@st.fragment
def _roles(result):
    _chart_settings("Job Market Analysis")
    charts, summary = result["charts"], result["summary"]
    ads = summary["ads"]
    order, limit = _controls("public_roles")
    _role_titles(charts, ads, order, limit)
    _role_family_heatmap(charts, ads, order, limit)
    _role_skills(charts, ads, order, limit)
    _role_locations(charts, summary, ads, order, limit)
    _role_timeline(charts)


@st.fragment
def _role_titles(charts, ads, order, limit):
    title_mode = st.session_state.get("public_title_mode", "Most common job titles")
    if title_mode == "Specific titles (alphabetical)":
        title_mode = "Specific job titles"
        st.session_state["public_title_mode"] = title_mode
    title_mode_options = ["Most common job titles", "Related role groups", "Specific job titles"]
    def title_controls():
        st.selectbox("Explore job titles", title_mode_options, key="public_title_mode")
    title_source, title_label, title = {
        "Most common job titles": ("titles", "common_job_title", "Most common job titles"),
        "Related role groups": ("roleGroups", "job_role_group", "Related role groups"),
        "Specific job titles": ("sourceTitles", "job_title", "Specific job titles"),
    }[title_mode]
    title_order = order
    _bar(charts.get(title_source), title_label, "job_ads", title, "Top occupational titles", ads, "titles", title_order, limit,
         extra_controls=title_controls)


@st.fragment
def _role_family_heatmap(charts, ads, order, limit):
    family_sizes = {row["job_family"]: int(row["family_ads"]) for row in charts.get("familyAdCounts", [])}
    skill_rows = _frame(charts.get("skills"), "skill_label", "job_ads", total=ads)
    skills = ordered_result_table(skill_rows, "skill_label", order, "job_ads").head(min(limit, 15)).skill_label.tolist() if not skill_rows.empty else []
    families = [name for name, _ in sorted(family_sizes.items(), key=lambda row: (-row[1], row[0])) if name != "not stated"]
    if families and skills:
        defaults = families[:8]
        saved_families = st.session_state.get("public_family_selection")
        chosen = defaults if saved_families is None else [name for name in saved_families if name in families]
        if saved_families is not None and chosen != saved_families:
            st.session_state["public_family_selection"] = chosen
        def family_controls():
            options = {"default": defaults} if "public_family_selection" not in st.session_state else {}
            st.multiselect("Compare job families", families, key="public_family_selection", **options)
        if chosen:
            matrix = pd.DataFrame(0, index=chosen, columns=skills, dtype=int).rename_axis(
                index="occupational family", columns="skill")
            for row in charts.get("familySkillDemand", []):
                if row["job_family"] in chosen and row["skill_label"] in skills:
                    matrix.at[row["job_family"], row["skill_label"]] = int(row["job_ads"])
            denominators = pd.Series(family_sizes).reindex(matrix.index).fillna(0).astype(int)
            shares = matrix.div(denominators.where(denominators.gt(0), 1), axis=0).mul(100)
            cells = [(skill, family, int(matrix.at[family, skill]), int(denominators[family]), float(shares.at[family, skill]))
                     for family in chosen for skill in skills if matrix.at[family, skill] > 0]
            cells.sort(key=lambda row: (-row[4], -row[2], row[0], row[1]))
            best = cells[0] if cells else None
            text = "No chartable evidence is available for this comparison." if best is None else (
                f"{best[0]} has the highest displayed within-family share in {best[1]}: {best[2]:,} of {best[3]:,} ads ({best[4]:.1f}%).")
            if len(cells) > 1 and best and sum(cell[4] == best[4] for cell in cells) > 1:
                ties = sum(cell[4] == best[4] for cell in cells)
                text = f"{ties:,} displayed skill–family pairs tie for the highest within-family share ({best[4]:.1f}%)."
            title = "Least frequent requested skills by occupational family" if order == "Lowest demand" else "Top requested skills by occupational family"
            _heatmap(matrix, title, text,
                     [(f"{skill} · {family}", count) for skill, family, count, _, _ in cells[:3]],
                     "public_family_heatmap", shares=shares, denominators=denominators,
                     share_label="Share of family ads", denominator_label="Advertisements in family",
                     group_label="occupational family", transpose=True, render_controls=family_controls)
        else:
            with st.container(border=True, key="public-family-heatmap-empty-card"):
                family_controls()
                st.info("Choose at least one job family to compare skill demand.")
    else:
        st.caption("The occupational family heatmap needs job family data and chartable skills.")


@st.fragment
def _role_skills(charts, ads, order, limit):
    title_families = charts.get("titleFamilies", [])
    families_for_titles = sorted({row["job_family"] for row in title_families if row.get("job_family")})
    selected_family = st.session_state.get("public_explore_family", "All")
    if selected_family not in ["All", *families_for_titles]:
        selected_family = "All"
        st.session_state["public_explore_family"] = selected_family
    scoped = [row for row in title_families if selected_family == "All" or row["job_family"] == selected_family]
    titles = sorted({row["job_title"] for row in scoped if row.get("job_title")})
    selected_title = st.session_state.get("public_explore_title", "All")
    if selected_title not in ["All", *titles]:
        selected_title = "All"
        st.session_state["public_explore_title"] = selected_title
    def selected_title_controls():
        st.selectbox("Job family", ["All", *families_for_titles], key="public_explore_family")
        scoped_family = st.session_state.get("public_explore_family", "All")
        scoped_titles = sorted({row["job_title"] for row in title_families
                                if row.get("job_title") and
                                (scoped_family == "All" or row["job_family"] == scoped_family)})
        if st.session_state.get("public_explore_title", "All") not in ["All", *scoped_titles]:
            st.session_state["public_explore_title"] = "All"
        st.selectbox("Specific job title", ["All", *scoped_titles], key="public_explore_title")
    family_sizes = {row["job_family"]: int(row["family_ads"]) for row in charts.get("familyAdCounts", [])}
    title_groups = [row for row in scoped if selected_title == "All" or row["job_title"] == selected_title]
    if selected_family == "All" and selected_title == "All":
        selected_skills, selected_ads = charts.get("skills", []), ads
    else:
        selected_ads = (int(family_sizes.get(selected_family, 0)) if selected_title == "All" else
                        sum(int(row["job_ads"]) for row in title_groups))
        families_set, titles_set = {row["job_family"] for row in title_groups}, {row["job_title"] for row in title_groups}
        counts = {}
        for row in charts.get("titleSkillDemand", []):
            if row["job_family"] in families_set and row["job_title"] in titles_set:
                counts[row["skill_label"]] = counts.get(row["skill_label"], 0) + int(row["job_ads"])
        selected_skills = [{"label": label, "count": count} for label, count in counts.items()]
    label = selected_title if selected_title != "All" else selected_family if selected_family != "All" else "all selected advertisements"
    _bar(selected_skills, "employer_skill", "employer_demand_count", f"Top skills for {label}", "Top requested skills", selected_ads,
         "selected_title", order, min(limit, 10), "Top Displayed Skills", extra_controls=selected_title_controls)


@st.fragment
def _role_locations(charts, summary, ads, order, limit):
    region_rows = charts.get("locations", [])
    regions = sorted(row["label"] for row in region_rows)
    selected_region = st.session_state.get("public_region", "All")
    if selected_region not in ["All", *regions]:
        selected_region = "All"
        st.session_state["public_region"] = selected_region
    city_rows = [row for row in charts.get("cities", []) if selected_region == "All" or row["region"] == selected_region]
    cities = sorted({row["label"] for row in city_rows})
    selected_city = st.session_state.get("public_city", "All") if selected_region != "All" else "All"
    if selected_city not in ["All", *cities]:
        selected_city = "All"
        st.session_state["public_city"] = selected_city
    def location_controls():
        st.selectbox("Region", ["All", *regions], key="public_region")
        region = st.session_state.get("public_region", "All")
        if region != "All":
            available_cities = sorted({row["label"] for row in charts.get("cities", []) if row["region"] == region})
            if st.session_state.get("public_city", "All") not in ["All", *available_cities]:
                st.session_state["public_city"] = "All"
            st.selectbox("City or municipality", ["All", *available_cities], key="public_city")
    if selected_region == "All":
        location_data, denominator = region_rows, ads
        location_title, location_label = "Advertisements by Philippine region", "region"
    else:
        location_data = [{"label": row["label"], "count": row["count"]} for row in city_rows if selected_city == "All" or row["label"] == selected_city]
        denominator = int(next((row["count"] for row in region_rows if row["label"] == selected_region), 0))
        location_title, location_label = f"Cities and municipalities in {selected_region}", "locality"
    location_frame = _frame(location_data, location_label, "job_ads", total=denominator)
    location_denominator = denominator
    if selected_region == "All":
        skill_data = [row for row in charts.get("regionSkillDemand", []) if row["region"]]
        area = "All regions"
        denominator = summary["withLocation"]
    elif selected_city == "All":
        skill_data = [row for row in charts.get("regionSkillDemand", []) if row["region"] == selected_region]
        area = selected_region
    else:
        skill_data = [row for row in charts.get("citySkillDemand", []) if row["region"] == selected_region and row["locality"] == selected_city]
        area = selected_city
        denominator = int(next((row["count"] for row in city_rows if row["label"] == selected_city), 0))
    skill_counts = {}
    for row in skill_data:
        skill_counts[row["skill_label"]] = skill_counts.get(row["skill_label"], 0) + int(row["job_ads"])
    skill_data = [{"label": label, "count": count} for label, count in skill_counts.items()]
    skill_frame = _frame(skill_data, "skill_label", "job_ads", total=denominator)
    if location_frame.empty:
        st.info("No classifiable location is available in this selection.")
    else:
        location_summary, top_skills = location_chart_insight(
            ordered_result_table(location_frame, location_label, order, "job_ads").head(limit),
            ordered_result_table(skill_frame, "skill_label", order, "job_ads").head(min(limit, 10)),
            location_label, location_denominator)
        featured_visual_chart(
            lambda: result_count_chart(location_frame, location_label, "job_ads", location_title, order=order, limit=limit),
            location_summary, top_skills, key="public_locations", insight_title="Location Insight",
            list_title="Top Displayed Skills", render_controls=location_controls)
        if not skill_frame.empty:
            st.html('<div class="public-linked-chart-indicator" role="note"><span class="material-symbols-rounded" aria-hidden="true">link</span><span>Both charts follow your selected region and city</span></div>')
    _bar(skill_data, "employer_skill", "employer_demand_count",
         f"Skills in {area}", "Top requested skills", denominator, "location_skills", order, min(limit, 10))


@st.fragment
def _role_timeline(charts):
    monthly = charts.get("timelineByTitle", [])
    title_totals = {}
    for row in monthly:
        title_totals[row["label"]] = title_totals.get(row["label"], 0) + int(row["count"])
    coverage = pd.DataFrame(charts.get("timelineCoverage", []), columns=["label", "dated", "undated"])
    title_options = sorted(name for name in coverage.label if name)
    defaults = sorted(title_totals, key=lambda name: (-title_totals[name], name))[:5] or title_options[:5]
    def timeline_controls():
        options = {"default": defaults} if "public_timeline_titles" not in st.session_state else {}
        st.multiselect("Job titles to compare", title_options, max_selections=8,
                       key="public_timeline_titles", **options)
    saved_titles = st.session_state.get("public_timeline_titles")
    timeline_titles = defaults if saved_titles is None else [name for name in saved_titles if name in title_options]
    if saved_titles is not None and timeline_titles != saved_titles:
        st.session_state["public_timeline_titles"] = timeline_titles
    if timeline_titles:
        all_months = pd.DataFrame(monthly, columns=["month", "label", "count"]).rename(columns={"label": "job_title", "count": "job_ads"})
        monthly_frame = selected_timeline(all_months, timeline_titles)
        totals = coverage.loc[coverage.label.isin(timeline_titles)]
        dated, undated = int(totals.dated.sum()), int(totals.undated.sum())
        by_month = monthly_frame.groupby("month", as_index=False).job_ads.sum() if not monthly_frame.empty else pd.DataFrame()
        peak = int(by_month.job_ads.max()) if not by_month.empty else 0
        peak_months = by_month.loc[by_month.job_ads.eq(peak), "month"].astype(str).tolist()[:3] if peak else []
        summary_text = f"The chosen titles appear in {dated:,} dated ads. The highest recorded monthly count is {peak:,}, in {', '.join(peak_months)}."
        top = sorted(((title, title_totals.get(title, 0)) for title in timeline_titles), key=lambda row: (-row[1], row[0]))
        if monthly_frame.empty:
            with st.container(border=True, key="public-timeline-empty-card"):
                st.subheader("Job posting trends", icon=":material/timeline:")
                timeline_controls()
                st.info("No usable posting dates are available for these job titles.")
        elif monthly_frame.month.nunique() > 1:
            featured_visual_chart(lambda: chart(job_title_trend(monthly_frame), show_heading=False),
                                  summary_text, top, key="title_timeline",
                                  insight_title="Timeline Insight", list_title="Dated ads by selected title",
                                  render_controls=timeline_controls, embedded=False,
                                  heading="Job posting trends",
                                  note=f"{dated:,} dated ads; {undated:,} ads with missing or invalid dates are excluded.")
        else:
            with st.container(border=True, key="public-posting-timeline"):
                st.subheader("Job posting activity", icon=":material/timeline:")
                timeline_controls()
                st.info("Only one posting month is available; the table shows counts without implying a time trend.")
                timeline_table(monthly_frame, timeline_titles)
    else:
        with st.container(border=True, key="public-timeline-unselected-card"):
            st.subheader("Job posting trends", icon=":material/timeline:")
            timeline_controls()
            st.info("Choose at least one job title to view posting activity.")


@st.fragment
def _qualifications(result):
    _chart_settings("Job Market Analysis")
    charts, summary = result["charts"], result["summary"]
    order, limit = _controls("public_qualifications")
    education_note = (f"Education or entry-eligibility evidence was found in {summary['withEducation']:,} of {summary['ads']:,} ads. "
                      "Fresh-graduate eligibility and unspecified degree levels are grouped under College / Undergraduate. "
                      "General education-requirement-unspecified evidence is kept in the table and omitted from the chart; categories can overlap.")
    education = pd.DataFrame(charts.get("education", []))
    education_table = pd.DataFrame(charts.get("educationTable", []))
    education_evidence = (education_table[["education_level", "job_ads", "job_ads_pct"]].rename(columns={
        "education_level": "Education category", "job_ads": "Job advertisements", "job_ads_pct": "Share",
    }) if not education_table.empty else pd.DataFrame(columns=["Education category", "Job advertisements", "Share"]))
    if not education.empty:
        max_value = int(education.job_ads.max())
        leaders = education.loc[education.job_ads.eq(max_value), "education_level"].tolist()
        text = (f"{education.iloc[0].education_level} appears in {int(education.iloc[0].job_ads):,} distinct ads in this selection."
                if len(education) == 1 else
                f"{len(leaders):,} displayed categories share the highest count ({max_value:,} ads each): {', '.join(leaders)}. Categories may overlap within an ad."
                if len(leaders) > 1 else
                f"{leaders[0]} appears in the most ads ({max_value:,}). Categories may overlap within an ad.")
        top = list(education.sort_values(["job_ads", "level_order"], ascending=[False, True]).head(3)[["education_level", "job_ads"]].itertuples(index=False, name=None))
        heading = "Education and entry requirements"
        figure = education_bar(education)
        if len(education) == 1:
            def render_education_metric():
                result_single_metric(heading, leaders[0], max_value, "Job advertisements", text,
                                     key="public_education_single", figure=figure)
                return figure
            featured_visual_chart(render_education_metric, text, top, key="education",
                                  insight_title="Education Insight", list_title="Most mentioned categories",
                                  heading=heading, note=education_note, evidence_frame=education_evidence,
                                  evidence_note="All education categories, including Unspecified. Unspecified is included in this table but excluded from the chart; categories count distinct ads and may overlap.")
        else:
            featured_visual_chart(lambda: chart(figure, title=heading, show_heading=False),
                                  text, top, key="education", insight_title="Education Insight",
                                  list_title="Most mentioned categories", heading=heading, note=education_note,
                                  evidence_frame=education_evidence,
                                  evidence_note="All education categories, including Unspecified. Unspecified is included in this table but excluded from the chart; categories count distinct ads and may overlap.")
    else:
        with st.container(border=True, key="public-education-unspecified-card"):
            st.subheader("Education and entry requirements", icon=":material/bar_chart:")
            if summary["withEducation"]:
                st.info("Education evidence is present, but only at the general Unspecified level. It appears in the evidence table and is intentionally omitted from the chart.")
                with st.expander("View education evidence table"):
                    st.caption("Distinct advertisements by grouped education category. General Unspecified evidence is table-only.")
                    if education_evidence.empty:
                        st.info("No grouped education evidence rows are available.")
                    else:
                        display(education_evidence, key="public_education_unspecified_evidence")
            else:
                st.info("No education or entry-eligibility evidence was detected in the selected ads.")
    experience = _frame(charts.get("experience"), "requirement", "job_ads", total=summary["ads"])
    if experience.empty:
        st.info("No experience durations could be compared in this selection.")
    else:
        def experience_insight(figure):
            shown = pd.DataFrame([(str(name), int(count)) for trace in figure.data
                                  for name, count in zip(trace.y, trace.x)], columns=["requirement", "job_ads"])
            text, top = experience_chart_insight(shown, summary["ads"])
            result_insight("Experience Insight", text, top, "Displayed durations")
        featured_visual_chart(
            lambda: result_count_chart(experience, "requirement", "job_ads", "Experience duration distribution",
                                       order=order, limit=limit,
                                       show_heading=False),
            "", [], key="public_experience", insight_title="Experience Insight",
            list_title="Displayed durations", heading="Experience requirements",
            render_insight=experience_insight, embedded=False,
            note=(f"Experience evidence was found in {summary['withExperience']:,} ads. Exact-year median: "
                  f"{summary['experienceExactMedian']} from {summary['experienceExactCount']:,} ads; ranges and open-ended wording remain separate."),
        )


@st.fragment
def _psf(result):
    _chart_settings("Job Market Analysis")
    charts, summary = result["charts"], result["summary"]
    order, limit = _controls("public_psf")
    _psf_competencies(result, charts, summary, order, limit)
    _bar(charts.get("psfRoles", []), "psf_job_role", "job_ads", "Related PSF-AAI reference roles",
         "Most represented reference roles", summary["ads"], "psf_roles", order, limit, "Top Displayed Roles")
    _psf_heatmap(charts, limit)
    _psf_reference_evidence(charts)


@st.fragment
def _psf_competencies(result, charts, summary, order, limit):
    roles = charts.get("psfRoles", [])
    role_labels = result.get("reference", {}).get("roles", {})
    role_names = sorted(set(role_labels) | {row["label"] for row in roles})
    selected_role = st.session_state.get("public_psf_role", "All")
    if selected_role not in ["All", *role_names]:
        selected_role = "All"
        st.session_state["public_psf_role"] = selected_role
    def psf_role_control():
        st.selectbox("Filter by reference role", ["All", *role_names], key="public_psf_role",
                     format_func=lambda role: role_labels.get(role, role))
    if selected_role == "All":
        competencies = charts.get("psf", [])
        denominator = summary["ads"]
    else:
        role_cells = [row for row in charts.get("psfHeatmap", []) if row["role"] == selected_role]
        competencies = [{"label": row["competency"], "count": row["count"]} for row in role_cells]
        denominator = next((int(row["count"]) for row in roles if row["label"] == selected_role), 0)
    _bar(competencies, "psf_competency", "job_ads", "PSF-AAI competencies linked to employer demand", "Most linked competency", denominator,
         "psf_competencies", order, limit, "Top Displayed Competencies",
         extra_controls=psf_role_control)


@st.fragment
def _psf_heatmap(charts, limit):
    cells = charts.get("psfHeatmap", [])
    role_sizes = {row["label"]: int(row["count"]) for row in charts.get("psfRoles", [])}
    role_options = sorted({row["role"] for row in cells}, key=lambda name: (-role_sizes.get(name, 0), name))
    competency_sizes = {row["label"]: int(row["count"]) for row in charts.get("psf", [])}
    competencies_options = sorted({row["competency"] for row in cells},
                                  key=lambda name: (-competency_sizes.get(name, 0), name))
    role_defaults, competency_defaults = role_options[:8], competencies_options[:min(limit, 15)]
    saved_roles = st.session_state.get("public_psf_heatmap_roles")
    saved_competencies = st.session_state.get("public_psf_heatmap_competencies")
    chosen_roles = role_defaults if saved_roles is None else [name for name in saved_roles if name in role_options]
    chosen_competencies = (competency_defaults if saved_competencies is None else
                           [name for name in saved_competencies if name in competencies_options])
    if saved_roles is not None and chosen_roles != saved_roles:
        st.session_state["public_psf_heatmap_roles"] = chosen_roles
    if saved_competencies is not None and chosen_competencies != saved_competencies:
        st.session_state["public_psf_heatmap_competencies"] = chosen_competencies
    def psf_heatmap_controls():
        role_args = {"default": role_defaults} if "public_psf_heatmap_roles" not in st.session_state else {}
        competency_args = ({"default": competency_defaults}
                           if "public_psf_heatmap_competencies" not in st.session_state else {})
        st.multiselect("Compare reference roles", role_options, key="public_psf_heatmap_roles", **role_args)
        st.multiselect("Choose competencies", competencies_options,
                       key="public_psf_heatmap_competencies", **competency_args)
    if chosen_roles and chosen_competencies:
        matrix = pd.DataFrame(0, index=chosen_roles, columns=chosen_competencies, dtype=int).rename_axis(
            index="reference role", columns="competency")
        for row in cells:
            if row["role"] in chosen_roles and row["competency"] in chosen_competencies:
                matrix.at[row["role"], row["competency"]] = int(row["count"])
        denominators = pd.Series(role_sizes).reindex(matrix.index).fillna(0).astype(int)
        shares = matrix.div(denominators.where(denominators.gt(0), 1), axis=0).mul(100)
        _heatmap(matrix, "PSF-AAI competencies across reference roles", "Counts show ads with automated candidate links.",
                 [], "psf_role_competency_heatmap", shares=shares, denominators=denominators,
                 share_label="Share of role ads", denominator_label="Advertisements linked to role",
                  group_label="reference role", transpose=True, render_controls=psf_heatmap_controls)
    elif cells:
        with st.container(border=True, key="public-psf-heatmap-empty-card"):
            psf_heatmap_controls()
            st.info("Choose at least one reference role and one competency to display the heatmap.")
    else:
        st.caption("The PSF-AAI heatmap needs advertisements with role and competency links.")


def _psf_reference_evidence(charts):
    if charts.get("psfEvidence"):
        with st.expander("PSF-AAI reference evidence"):
            st.caption("Includes official competencies with zero matching advertisements in this dataset.")
            st.dataframe(pd.DataFrame(charts["psfEvidence"]).rename(columns={
                "label": "Competency", "count": "Matching ads", "roles": "Framework roles", "families": "Occupational families", "sourcePage": "PDF page",
            }), width="stretch", hide_index=True)
            if profiles := charts.get("psfRoleProfiles"):
                st.markdown("**Official role descriptions**")
                st.caption("Role descriptions provide context and are not additional competency labels.")
                st.dataframe(pd.DataFrame(profiles).reindex(columns=["job_role", "occupational_family", "role_description", "role_source_page", "source_page"]).rename(columns={
                    "job_role": "Reference role", "occupational_family": "Occupational family", "role_description": "Role description",
                    "role_source_page": "Description PDF page", "source_page": "Skills PDF page",
                }), hide_index=True, width="stretch")


@st.fragment
def _alignment(result):
    _chart_settings("Employer–PSF Alignment")
    order, limit = _controls("public_alignment")
    summary = result["summary"]
    rows = _frame(result["charts"].get("alignment"), "status", "evidence_groups")
    if not rows.empty:
        with st.container(border=True, key="public-alignment-evidence-card"):
            with st.container(key="public_result_chart_header_alignment"):
                heading_column, download_slot = st.columns([3.2, 1], vertical_alignment="center")
                with heading_column:
                    st.subheader("Phrase–competency evidence by status", icon=":material/fact_check:")
            bar_column, insight_column = st.columns([3.2, 1], vertical_alignment="center")
            evidence_slot = st.container()
            with bar_column, chart_download_target(download_slot), chart_evidence_target(evidence_slot):
                status_chart = result_count_chart(
                    rows, "status", "evidence_groups", "Status of Phrase–Competency Evidence Groups",
                    order=order, limit=limit, show_heading=False, value_label="Evidence groups",
                )
            with insight_column:
                if status_chart is not None:
                    alignment_status_insight(status_chart)
            st.caption(f"{summary['alignmentGroups']:,} phrase–competency evidence groups. Status labels summarize automatically grouped evidence and may include candidates for manual review.")


@st.fragment
def _unmapped(result):
    _chart_settings("Unmapped / Emerging Skills")
    charts, summary = result["charts"], result["summary"]
    order, limit = _controls("public_unmapped")
    for source, title, heading, key in (
        ("unmapped", "Unmapped skill evidence", "Most frequent unmapped skill", "unmapped_evidence"),
        ("recurring", "Recurring unmapped phrases for review", "Recurring unmapped skill", "unmapped_recurring"),
    ):
        _bar(charts.get(source), "skill_label", "job_ads", title, heading, summary["ads"], key, order, limit,
             "Top Displayed Candidates" if source == "recurring" else "Top Displayed Skills")
    st.caption("A missing PSF-AAI match does not establish a framework gap. Recurrence alone does not establish emergence.")


def _results(result):
    _topbar(3)
    file_name = escape_html(str(result["filename"]))
    model = result["model"]
    details, actions = st.columns([3, 1], vertical_alignment="center")
    with details:
        facts = (("Classifier", "", str(model["name"])),
                 ("Model ID", "Model", str(model["version"])),
                 ("Dataset ID", "CSV", str(result["datasetHash"][:16])),
                 ("Analysis input ID", "Input", str(result["analysisInputHash"][:16])))
        fact_markup = "".join(
            f'<span class="public-result-fact"><span class="public-result-label-full">{label}</span>'
            f'<span class="public-result-label-compact" aria-hidden="true">{short_label}</span>'
            f'<strong>{escape_html(value)}</strong></span>'
            for label, short_label, value in facts
        )
        st.html(f'<div class="public-result-meta"><div class="public-result-file"><span class="material-symbols-rounded public-result-file-icon" aria-hidden="true">description</span><div class="public-result-file-copy"><strong>{file_name}</strong><small>{result["summary"]["rows"]:,} CSV rows</small></div></div><div class="public-result-facts" role="group" aria-label="Analysis details" tabindex="0">{fact_markup}</div></div>')
    with actions:
        if st.button("Analyze another dataset", type="primary", icon=":material/upload_file:",
                     key="public_analyze_another", width="stretch"):
            _reset()
    analysis_workflow()
    job_market_metrics(result["summary"], result["summary"])

    with st.container(horizontal=True, vertical_alignment="center", horizontal_alignment="distribute",
                      key="public-results-heading"):
        st.subheader("Results Section", icon=":material/bar_chart:")
        if any(isinstance(rows, list) and rows for rows in result["charts"].values()):
            def report_csv():
                rows = [{"section": section, **row}
                        for section, items in result["charts"].items() if isinstance(items, list)
                        for row in items]
                return pd.DataFrame(rows).to_csv(index=False).encode("utf-8-sig")

            st.download_button("Export results", report_csv,
                               f"{Path(file_name).stem}-results.csv", "text/csv", key="public_results_csv",
                               type="primary", icon=":material/download:", on_click="ignore")
    with st.container(key="public-results-tabs"):
        tabs = st.tabs(["Skills", "Roles and locations", "Qualifications", "PSF-AAI demand", "Alignment evidence", "Unmapped / emerging"])
        with tabs[0]: _skills(result)
        with tabs[1]: _roles(result)
        with tabs[2]: _qualifications(result)
        with tabs[3]: _psf(result)
        with tabs[4]: _alignment(result)
        with tabs[5]: _unmapped(result)


def _results_screen(result, *, preload=False):
    if preload:
        with collect_result_plots() as plots:
            _results(result)
        script = Path(__file__).with_name("result_chart_readiness.js").read_text(encoding="utf-8")
        st.html(f"<script>({script})({len(plots)});</script>", unsafe_allow_javascript=True)
    else:
        _results(result)
    st.html('<footer class="st-key-public-footer">Future of Work · Philippine job advertisement analysis</footer>')
    _persist_recent_upload()


def _process_pending_upload(loading_slot):
    content = st.session_state.get("public_content")
    file_name = st.session_state.get("public_filename")
    mapping = dict(st.session_state.get("public_mapping", {}))
    if content is None or not file_name:
        st.session_state["public_stage"] = "upload"
        st.rerun()

    mark_uri = "data:image/svg+xml;base64," + base64.b64encode(APP_ICON.read_bytes()).decode("ascii")
    with loading_slot.container(key="public-processing-overlay"):
        with st.container(key="public-processing-card"):
            st.html(f'<div class="public-processing-brand"><img alt="" src="{mark_uri}"><span><strong>Future of Work</strong><small>Job Market Analytics</small></span></div><h1 class="public-processing-title">Analyzing your dataset</h1><p class="public-processing-copy">Applying the public classifier and shared analysis pipeline.</p>')
            meter = st.empty()
            st.html('<button type="button" class="public-processing-continue" hidden>View available results</button>')
            st.html('<p class="public-processing-privacy">Your recent upload stays available in this browser session.</p>')

    def update(value, text):
        percentage = min(95, max(0, round(float(value) * 100)))
        meter.html(f'<p class="public-processing-status" role="status">{escape_html(str(text))}</p>'
                   '<div class="public-processing-meter">'
                   f'<progress aria-label="Analysis progress" max="100" value="{percentage}"></progress>'
                   f'<span class="public-processing-percent" aria-hidden="true">{percentage}%</span></div>')

    update(0, "Preparing your dataset analysis…")
    try:
        result = analyze_upload(content, file_name, mapping, hosted=True, progress=update)
        update(.95, "Drawing the charts in all six sections…")
        _results_screen(result, preload=True)
    except Exception as exc:
        st.session_state["public_error"] = str(exc)
        st.session_state["public_stage"] = "review"
        st.rerun()
    st.session_state["public_result"] = result
    st.session_state["public_stage"] = "results"
    st.session_state.pop("public_error", None)


@st.fragment
def _review_mapping(preview):
    file_hash = st.session_state["public_file_hash"]
    file_name = st.session_state["public_filename"]
    columns = list(preview.columns)
    mapping = dict(st.session_state.get("public_mapping", {}))
    fields = (*PRIMARY_FIELDS, *OPTIONAL_FIELDS)
    selected = [st.session_state.get(f"public-map-{file_hash[:10]}-{field}", mapping.get(field, "")) for field in fields]
    counts = {column: selected.count(column) for column in set(selected) if column}
    duplicate_columns = {column for column, count in counts.items() if count > 1}
    with st.container(key="public-review-layout"):
        left, right = st.columns([1.65, .95], gap="medium", vertical_alignment="top")
        with left, st.container(key="public-mapping-card"):
            file_icon, file_details, file_status = st.columns([.16, 1.6, .7], vertical_alignment="center")
            with file_icon:
                st.html('<span class="public-file-type">CSV</span>')
            with file_details:
                st.html(f'<span class="public-filename">{escape_html(file_name)}</span>')
                st.caption(f"Dataset · {len(preview):,} records detected")
            with file_status:
                st.html('<span class="public-map-status" data-state="complete">✓ File ready</span>')
            st.divider()
            st.subheader("Detected column mapping")
            st.caption("Review the suggested matches. Choose a CSV column for each field; you can edit any match before analysis.")
            def reset_suggestions():
                fresh, _ = suggest_column_mapping(columns, "jobs")
                for field, column in fresh.items():
                    st.session_state[f"public-map-{file_hash[:10]}-{field}"] = column
            st.button("Re-detect columns", on_click=reset_suggestions)
            st.html('<div class="public-map-head"><span>CSV column</span><span>Used as</span><span>Status</span></div>')
            for field in PRIMARY_FIELDS:
                with st.container(key=f"public-map-row-{field}"):
                    mapping[field] = _mapping_row(field, columns, mapping, file_hash, duplicate_columns)
            with st.expander("Optional fields"):
                st.html('<div class="public-map-head"><span>CSV column</span><span>Used as</span><span>Status</span></div>')
                for field in OPTIONAL_FIELDS:
                    with st.container(key=f"public-map-row-{field}"):
                        mapping[field] = _mapping_row(field, columns, mapping, file_hash, duplicate_columns)
            st.session_state["public_mapping"] = mapping
            recent = st.session_state.get("public_recent_upload")
            if recent and recent.get("file_hash") == file_hash:
                recent["mapping"] = dict(mapping)
            if duplicate_columns:
                st.warning("A CSV column is mapped more than once. Choose each source column once to keep its evidence traceable.")
            with st.expander("Preview sample rows"):
                st.dataframe(preview.head(8), width="stretch", hide_index=True)

        text_ready = any(mapping.get(field) for field in TEXT_FIELDS["jobs"])
        unique = not duplicate_columns
        classifier_ready = bool(ENGINE.get("classifierAvailable"))
        ready = text_ready and unique and classifier_ready
        checks = (("CSV structure validated", True),
                  ("At least one job text column identified", text_ready),
                  ("Each source column is used once", unique),
                  ("Public classifier available", classifier_ready))
        completed = sum(done for _, done in checks)
        with right, st.container(key="public-workflow-card"):
            st.html('<h2 class="public-workflow-title">Analysis checklist</h2><p class="public-file-meta">A transparent review before results are generated.</p>')
            st.html('<div class="public-checklist">' + "".join(
                f'<div class="public-check" data-state="{"complete" if done else "pending"}"><b aria-hidden="true">{"✓" if done else "○"}</b><span>{label}</span></div>'
                for label, done in checks) + "</div>")
            st.html(f'<div class="public-readiness"><span>{"Ready to analyze" if ready else "Complete the review"}</span><span>{completed * 25}%</span></div>')
            st.progress(completed * 25)
            st.html('<p class="public-workflow-note">Results depend on the structure, quality, and coverage of the uploaded dataset.</p>')
            if not classifier_ready:
                st.warning("The public classifier is unavailable. You can review the columns, but analysis cannot start until it is available.")
    st.markdown('<p class="public-privacy">Your latest CSV stays available until this browser session ends.</p>', unsafe_allow_html=True)
    _, back, analyze = st.columns([5, 1, 1.45], gap="small")
    with back:
        if st.button("Back", icon=":material/arrow_back:", key="public_back_to_upload", width="stretch"):
            st.session_state["public_stage"] = "upload"
            st.rerun()
    with analyze:
        if st.button("Start analysis", type="primary", icon=":material/arrow_forward:",
                      disabled=not ready, key="public_start_analysis", width="stretch"):
            st.session_state["public_stage"] = "processing"
            st.session_state.pop("public_error", None)
            st.rerun()

    _persist_recent_upload()


def main():
    _style()
    _restore_recent_upload()
    result = st.session_state.get("public_result")
    if result and result.get("analysisRevision") != automatic_analysis_revision():
        st.session_state.pop("public_result")
        can_refresh = st.session_state.get("public_content") is not None and st.session_state.get("public_filename")
        st.session_state["public_stage"] = "processing" if can_refresh else "review"
        if not can_refresh:
            st.info("The analysis reference has been updated. Use your recent upload to refresh the results.")
        result = None
    if result:
        _results_screen(result)
        return

    loading_slot = st.empty()
    stage = st.session_state.get("public_stage", "upload")
    processing = stage == "processing"
    if stage not in {"upload", "review", "processing"}:
        st.session_state["public_stage"] = stage = "upload"
        processing = False
    if stage == "review" and st.session_state.get("public_preview") is None:
        st.session_state["public_stage"] = stage = "upload"
        processing = False
    if processing:
        _process_pending_upload(loading_slot)
        return
    content = st.session_state.get("public_content")
    preview = st.session_state.get("public_preview")
    mapping = dict(st.session_state.get("public_mapping", {}))
    _topbar(1 if stage == "upload" else 2)
    if stage == "upload":
        _stage_heading(1, "Upload your job advertisements", "Start by selecting a CSV dataset. We’ll guide you through the rest.", download_template=True)
    else:
        _stage_heading(2, "Review your dataset", "Check the detected columns before beginning the analysis.", "Dataset structure")
    if st.session_state.get("public_error"):
        st.error(st.session_state["public_error"])
    if stage == "upload":
        with st.container(key="public-upload-layout"):
            left, right = st.columns([1.65, .95], gap="medium", vertical_alignment="top")
            with left, st.container(key="public-upload-card"):
                uploaded = st.file_uploader("Select a CSV file", type=["csv"], key=f"public_upload_{st.session_state.get('public_upload_key', 0)}",
                                            help="Your file is processed for this session and is not added to the research workspace.",
                                            label_visibility="collapsed")
                if uploaded is None and st.session_state.get("public_file_hash") and not st.session_state.get("public_using_recent_upload"):
                    for key in ("public_file_hash", "public_filename", "public_content", "public_preview", "public_mapping"):
                        st.session_state.pop(key, None)
                    content = preview = None
                    mapping = {}
                if uploaded is not None:
                    st.session_state["public_using_recent_upload"] = False
                    try:
                        raw_content = uploaded.getvalue()
                        file_hash = hashlib.sha256(raw_content).hexdigest()
                        if st.session_state.get("public_file_hash") != file_hash:
                            content, preview = _read_upload(uploaded)
                            st.session_state["public_file_hash"] = file_hash
                            st.session_state["public_filename"] = Path(uploaded.name).name
                            st.session_state["public_content"] = content
                            st.session_state["public_preview"] = preview
                            st.session_state["public_mapping"] = suggest_column_mapping(preview.columns, "jobs")[0]
                            st.session_state.pop("public_error", None)
                        else:
                            content = st.session_state["public_content"]
                            preview = st.session_state["public_preview"]
                        st.session_state["public_recent_upload"] = {
                            "file_hash": file_hash,
                            "filename": Path(uploaded.name).name,
                            "content": content,
                            "preview": preview,
                            "mapping": dict(st.session_state.get("public_mapping", {})),
                        }
                        st.success(f"{Path(uploaded.name).name} · {len(preview):,} records detected")
                        with st.expander("Preview sample rows"):
                            st.dataframe(preview.head(8), width="stretch", hide_index=True)
                    except (ValueError, OSError) as exc:
                        st.error(str(exc))
                        for key in ("public_file_hash", "public_filename", "public_content", "public_preview", "public_mapping"):
                            st.session_state.pop(key, None)
                recent = st.session_state.get("public_recent_upload")
                if recent and (uploaded is None or recent.get("file_hash") != st.session_state.get("public_file_hash")):
                    with st.container(key="public-recent-upload"):
                        info, action = st.columns([2.2, 1], vertical_alignment="center")
                        with info:
                            st.html(f'<span class="public-recent-eyebrow">Recent upload</span><strong class="public-recent-filename">{escape_html(recent["filename"])}</strong>')
                            size_mb = len(recent["content"]) / (1024 * 1024)
                            st.caption(f'{len(recent["preview"]):,} rows · {size_mb:.1f} MB · Available while this browser session is open.')
                        with action:
                            action_label = "Review recent upload" if recent.get("file_hash") == st.session_state.get("public_file_hash") else "Use recent upload"
                            if st.button(action_label, icon=":material/replay:", key="public_use_recent_upload", width="stretch"):
                                st.session_state["public_upload_key"] = st.session_state.get("public_upload_key", 0) + 1
                                st.session_state["public_file_hash"] = recent["file_hash"]
                                st.session_state["public_filename"] = recent["filename"]
                                st.session_state["public_content"] = recent["content"]
                                st.session_state["public_preview"] = recent["preview"]
                                st.session_state["public_mapping"] = dict(recent.get("mapping", {}))
                                st.session_state["public_using_recent_upload"] = True
                                st.session_state["public_stage"] = "review"
                                st.rerun()
            with right, st.container(key="public-workflow-card"):
                st.html('<h2 class="public-workflow-title">What happens after uploading?</h2><ol class="public-process-rail" aria-label="Analysis process"><li><span class="public-step-number">01</span><span><strong>Check dataset structure</strong><small>Review detected fields and sample rows.</small></span></li><li><span class="public-step-number">02</span><span><strong>Prepare and analyze</strong><small>Clean records and apply the public classifier.</small></span></li><li><span class="public-step-number">03</span><span><strong>Explore the findings</strong><small>Review trends and PSF-AAI evidence.</small></span></li></ol><p class="public-workflow-note">Your latest CSV stays available in this browser session.</p>')
        with st.container(key="public-upload-footer"):
            privacy, action = st.columns([3, 1], vertical_alignment="center")
            with privacy:
                st.caption("Your latest CSV stays available until this browser session ends.")
            with action:
                can_continue = bool(st.session_state.get("public_file_hash")) and content is not None and preview is not None
                if st.button("Preview next step", type="primary", icon=":material/arrow_forward:",
                             disabled=not can_continue, key="public_preview_next", width="stretch"):
                    st.session_state["public_stage"] = "review"
                    st.rerun()
    else:
        if content is None or preview is None:
            st.session_state["public_stage"] = "upload"
            st.rerun()
        _review_mapping(preview)

    with st.container(key="public-footer"):
        st.caption(f"Future of Work · Philippine job advertisement analysis · v{PUBLIC_VERSION}")
    if stage == "upload":
        _persist_recent_upload()


main()
