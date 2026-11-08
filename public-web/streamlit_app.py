"""Anonymous Streamlit edition of the public job-ad analyzer."""

from __future__ import annotations

import base64
import hashlib
from html import escape as escape_html
import json
from pathlib import Path
import sys
import time

import pandas as pd
import streamlit as st

APP_ICON = Path(__file__).resolve().parent / "site" / "assets" / "job_market_mark.svg"
st.set_page_config(page_title="Future of Work | Public analyzer", page_icon=APP_ICON,
                   layout="wide", initial_sidebar_state="collapsed")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import FIELDS
from src.column_mapping import suggest_column_mapping
from src.design import apply_design
from src.loaders import load_data
from src.public_engine import MAX_HOSTED_UPLOAD_BYTES, RESULT_SCHEMA_VERSION, analyze_upload, health
from src.ui import (analysis_workflow, featured_result_chart, featured_visual_chart, job_market_metrics, result_chart_options,
                    result_count_chart, result_heatmap, result_insight,
                    result_role_distribution)
from src.visualization import education_bar, heatmap, job_title_trend

PUBLIC_VERSION = "3.0.100"


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
REQUIRED_FIELDS = ("job_title", "job_description", "required_skills", "preferred_skills", "qualifications")
OPTIONAL_FIELDS = tuple(field for field in FIELDS["jobs"] if field not in REQUIRED_FIELDS and field != "source_id")
ENGINE = health(hosted=True)


def _style():
    apply_design()
    hero_art = base64.b64encode((ROOT / "assets/job_market_hero.svg").read_bytes()).decode("ascii")
    style = """<style>
    [data-testid="stSidebar"],[data-testid="stSidebarCollapsedControl"]{display:none!important}
    [class*="st-key-public_recent_restore"],[class*="st-key-public_recent_save"]{position:fixed!important;left:-10000px!important;top:0!important;width:1px!important;height:1px!important;overflow:hidden!important;opacity:0!important;pointer-events:none!important}
    [data-testid="stHeader"]{background:transparent;height:0}
    .stApp{background:#f8f5f2}
    .stMainBlockContainer{--public-page-pad:clamp(1rem,3vw,2.5rem);max-width:1440px;padding:1rem var(--public-page-pad) 4rem;border:1px solid #ebe4e1;border-radius:18px;background:#fff;box-shadow:0 12px 32px #24303d08}
    .public-topbar{position:relative;isolation:isolate;box-sizing:border-box;display:flex;align-items:center;justify-content:space-between;gap:1rem;min-height:104px;width:calc(100% + var(--public-page-pad) + var(--public-page-pad));margin:-1rem calc(0px - var(--public-page-pad)) 1rem;padding:1rem var(--public-page-pad);overflow:hidden;border:1px solid #e6d9d7;border-radius:12px 12px 0 0;background:#f9efed}
    .public-topbar:after{position:absolute;z-index:-1;inset:12px 0 0 auto;width:min(36%,430px);content:"";background:url("data:image/svg+xml;base64,__HERO_ART__") right bottom/contain no-repeat;opacity:.9;pointer-events:none}
    .public-topbar img{position:relative;z-index:1;display:block;width:clamp(145px,18vw,205px);height:auto}
    .public-version{position:relative;z-index:1;padding:.35rem .7rem;border:1px solid #e6d9d7;border-radius:999px;background:#fffdfbcc;color:#78182b;font-size:.75rem;font-weight:650}
    .public-stage-heading{display:flex;align-items:flex-start;justify-content:space-between;gap:1rem;margin:.1rem 0 1.1rem}
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
    .public-result-file{display:flex;flex:1 1 270px;align-items:center;gap:.55rem;min-width:0}
    .public-result-file-icon{display:grid;flex:0 0 38px;place-items:center;width:38px;height:38px;border-radius:10px;background:#f7edef;color:#78182b;font-size:21px}
    .public-result-file-copy{min-width:0}
    .public-result-file-copy strong,.public-result-file-copy small{display:block}
    .public-result-file-copy strong{color:#24303d;font-size:.84rem;line-height:1.3;overflow-wrap:anywhere}
    .public-result-file-copy small{margin-top:.12rem;color:#62585d;font-size:.71rem}
    .public-result-facts{display:flex;flex:1 1 390px;flex-wrap:wrap;gap:.35rem}
    .public-result-fact{display:inline-flex;align-items:baseline;gap:.3rem;min-height:28px;padding:.3rem .55rem;border:1px solid #e9dfdc;border-radius:999px;background:#fcf9f7;font-size:.69rem;line-height:1.25}
    .public-result-fact span{color:#647184}
    .public-result-fact strong{color:#24303d;font-weight:700;overflow-wrap:anywhere}
    .public-privacy{margin:.1rem 0 0;color:#62585d;font-size:.78rem}
    .st-key-public-upload-footer{margin-top:1rem;padding-top:.75rem;border-top:1px solid #e6d9d7}
    .st-key-public-upload-footer [data-testid="stHorizontalBlock"]{align-items:center}
    .st-key-public-processing-overlay{position:fixed!important;z-index:100000!important;inset:0!important;width:100vw!important;height:100dvh!important;display:flex!important;align-items:center!important;justify-content:center!important;padding:clamp(1rem,5vw,3rem)!important;overflow:auto!important;background:#19171870!important;backdrop-filter:blur(2px)}
    [data-testid="stElementContainer"]:has(.st-key-public-processing-overlay){height:0!important;margin:0!important;padding:0!important}
    .st-key-public-processing-card{position:fixed!important;z-index:100001!important;top:50dvh!important;left:50vw!important;transform:translate(-50%,-50%)!important;width:min(760px,calc(100vw - 2rem))!important;max-height:calc(100dvh - 2rem);margin:0!important;padding:clamp(1.6rem,5vw,3.5rem);overflow:auto;border:1px solid #ffffffb8;border-radius:18px;background:#fff;box-shadow:0 18px 60px #4d10201c;text-align:center}
    .public-processing-brand{display:inline-flex;align-items:center;gap:.7rem;margin-bottom:1.7rem;text-align:left}
    .public-processing-brand img{width:46px;height:48px}
    .public-processing-brand strong,.public-processing-brand small{display:block}
    .public-processing-brand strong{color:#4d1020;font-size:1.05rem}
    .public-processing-brand small{color:#62585d;font-size:.76rem}
    .public-processing-title{margin:.2rem 0 .5rem;color:#24303d;font-size:clamp(1.8rem,4vw,2.5rem);letter-spacing:-.035em}
    .public-processing-copy{color:#62585d}
    .public-processing-status{margin-top:1.4rem;color:#4d1020;font-size:.9rem;font-weight:650}
    .public-processing-percent{color:#4d1020;font-size:.83rem;font-variant-numeric:tabular-nums;font-weight:700;text-align:right}
    .public-processing-privacy{margin:1.3rem 0 0;color:#62585d;font-size:.76rem}
    .st-key-public-processing-overlay .stProgress>div>div{background:#78182b}
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
    .st-key-public-footer{margin-top:3rem;padding-top:1rem;border-top:1px solid #e5e3e0;color:#647184;font-size:.75rem}
    .stApp:has(.st-key-public-processing-overlay){overflow:hidden}
    @media(max-width:720px){.public-steps{grid-template-columns:1fr;gap:.45rem}.public-step-line{display:none}.public-step small{display:none}.stMainBlockContainer{--public-page-pad:1rem;padding-inline:var(--public-page-pad);border-radius:14px}.public-map-head{grid-template-columns:1.2fr 1fr .8fr;gap:.35rem;font-size:.65rem}[class*="st-key-public-map-row-"]{padding-inline:.25rem}.public-topbar{min-height:90px;padding-inline:var(--public-page-pad)}.public-topbar:after{width:48%;opacity:.4}.public-result-facts{flex-basis:100%}.st-key-public-processing-overlay{padding:1rem!important}.st-key-public-processing-card{padding:1.5rem 1rem}}
    @media(max-width:475px){.st-key-public-results-heading{align-items:stretch;flex-wrap:wrap}.st-key-public-results-heading [data-testid="stDownloadButton"]{width:100%}.st-key-public-results-heading [data-testid="stDownloadButton"] button{width:100%}.st-key-public-upload-card [data-testid="stFileUploaderDropzone"]{min-height:280px;padding-top:8.5rem!important}.st-key-public-upload-card [data-testid="stFileUploaderDropzone"]:after{top:5.7rem;font-size:.82rem}.public-topbar{min-height:82px;padding-block:.75rem}.public-topbar img{width:145px}.public-version{padding:.28rem .48rem;font-size:.67rem}.public-stage-heading{gap:.5rem}.public-stage-heading h1{font-size:1.35rem}.public-stage-badge{padding:.25rem .45rem;font-size:.64rem}.public-process-rail{gap:.25rem}.public-process-rail li{gap:.4rem;padding-inline:.25rem}.public-step-number{width:28px;height:28px;font-size:.7rem}.public-process-rail strong{font-size:.78rem;line-height:1.25}.public-process-rail small{font-size:.68rem;line-height:1.3}.public-actions{gap:.4rem}.public-actions [data-testid="stButton"]{flex:1}}
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


def _stage_heading(step, title, intro, badge):
    st.html(f'<header class="public-stage-heading"><div><p class="public-eyebrow">STEP {step:02} / 03</p><h1>{escape_html(title)}</h1><p>{escape_html(intro)}</p></div><span class="public-stage-badge">{escape_html(badge)}</span></header>')


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
        state = "error" if duplicate else "complete" if value else "required" if field == "job_title" else "pending"
        text = "Duplicate" if duplicate else "Matched" if value else "Required" if field == "job_title" else "Choose a column"
        st.html(f'<span class="public-map-status" data-state="{state}">{text}</span>')
    return value


def _read_upload(upload):
    return _read_content(upload.getvalue(), upload.name)


def _read_content(content, filename):
    if len(content) > MAX_HOSTED_UPLOAD_BYTES:
        raise ValueError("This public Streamlit app accepts CSV files up to 4 MB.")
    encoding = "utf-16" if content.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig"
    frame = load_data(content, Path(filename).name, encoding=encoding)
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


def _bar(rows, label, value, title, heading, total, key, order, limit, list_title="Top Displayed Skills"):
    frame = rows if isinstance(rows, pd.DataFrame) else _frame(rows, label, value, total=total)
    if frame.empty:
        st.info("No chartable evidence is available for this selection.")
        return
    featured_result_chart(label, value, heading, total,
        lambda: result_count_chart(frame, label, value, title, order=order, limit=limit, show_heading=False), key=key)


def _controls(prefix):
    return result_chart_options(key_prefix=prefix)


def _chart_settings(page):
    st.session_state["_fow_current_page"] = page
    st.session_state["_table_number"] = 0


def _skills(result):
    _chart_settings("Job Market Analysis")
    charts, ads = result["charts"], result["summary"]["ads"]
    order, limit = _controls("public_skills")
    items = [("skills", "employer_skill", "employer_demand_count", "Employer-requested skills", "Top requested skills", "skills", "Each ad counts once per grouped skill; skill categories overlap."),
             ("technicalSkills", "skill_label", "job_ads", "Technical skills", "Top technical skills", "technical_skills", "Distinct ads per technical skill."),
             ("enablingSkills", "skill_label", "job_ads", "Enabling and interpersonal skills", "Top enabling skills", "enabling_skills", "Distinct ads per enabling skill."),
             ("broadAreas", "category_group", "job_ads", "Broad competency areas", "Most common broad area", "broad_areas", "An ad may contribute to several overlapping areas.")]
    for source, label, value, title, heading, key, note in items:
        st.subheader(title)
        _bar(charts.get(source), label, value, title, heading, ads, key, order, limit)
        st.caption(note)


def _heatmap(matrix, title, summary, rows, key, *, count_label="Job advertisements", shares=None, denominators=None,
             share_label="Share within group", denominator_label="Advertisements in group", group_label="group", transpose=False):
    if matrix.empty:
        st.info("No chartable evidence is available for this comparison.")
        return
    if matrix.size == 1:
        result_heatmap(matrix, title, count_label=count_label, share_matrix=shares, row_denominators=denominators,
                       share_label=share_label, denominator_label=denominator_label, row_group_label=group_label,
                       transpose=transpose)
        return
    featured_visual_chart(lambda: heatmap(matrix, title, count_label=count_label, share_matrix=shares,
                                         row_denominators=denominators, share_label=share_label,
                                         denominator_label=denominator_label, transpose=transpose),
                          summary, rows, key=key, insight_title="Heatmap Insight", list_title="Top Skill × Group")


def _roles(result):
    _chart_settings("Job Market Analysis")
    charts, summary = result["charts"], result["summary"]
    ads = summary["ads"]
    order, limit = _controls("public_roles")
    title_mode = st.selectbox("Job-title overview", ["Most common job titles", "Related role groups", "Specific titles (alphabetical)"], key="public_title_mode")
    title_source, title_label, title = {
        "Most common job titles": ("titles", "common_job_title", "Most common job titles"),
        "Related role groups": ("roleGroups", "job_role_group", "Related role groups"),
        "Specific titles (alphabetical)": ("sourceTitles", "job_title", "Specific job titles"),
    }[title_mode]
    title_order = "Alphabetical" if title_mode.startswith("Specific") else order
    _bar(charts.get(title_source), title_label, "job_ads", title, "Top occupational titles", ads, "titles", title_order, limit)

    family_sizes = {row["job_family"]: int(row["family_ads"]) for row in charts.get("familyAdCounts", [])}
    skill_rows = _frame(charts.get("skills"), "skill_label", "job_ads", total=ads)
    skills = skill_rows.sort_values(["job_ads", "skill_label"], ascending=[False, True], kind="stable").head(min(limit, 15)).skill_label.tolist() if not skill_rows.empty else []
    families = [name for name, _ in sorted(family_sizes.items(), key=lambda row: (-row[1], row[0])) if name != "not stated"]
    if families and skills:
        defaults = families[:8]
        chosen = st.multiselect("Occupational families in the heatmap", families, default=defaults, key="public_family_selection")
        if chosen:
            matrix = pd.DataFrame(0, index=chosen, columns=skills, dtype=int)
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
            _heatmap(matrix, "Top requested skills by occupational family", text,
                     [(f"{skill} · {family}", count) for skill, family, count, _, _ in cells[:3]],
                     "public_family_heatmap", shares=shares, denominators=denominators,
                     share_label="Share of family ads", denominator_label="Advertisements in family",
                     group_label="occupational family", transpose=True)

    title_families = charts.get("titleFamilies", [])
    families_for_titles = sorted({row["job_family"] for row in title_families if row.get("job_family")})
    selected_family = st.selectbox("Occupational family", ["All", *families_for_titles], key="public_explore_family")
    scoped = [row for row in title_families if selected_family == "All" or row["job_family"] == selected_family]
    titles = sorted({row["job_title"] for row in scoped if row.get("job_title")})
    selected_title = st.selectbox("Specific job title", ["All", *titles], key="public_explore_title")
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
         "selected_title", order, min(limit, 10), "Top Displayed Skills")

    region_rows = charts.get("locations", [])
    regions = sorted(row["label"] for row in region_rows)
    selected_region = st.selectbox("Region", ["All", *regions], key="public_region")
    city_rows = [row for row in charts.get("cities", []) if selected_region == "All" or row["region"] == selected_region]
    cities = sorted({row["label"] for row in city_rows})
    selected_city = st.selectbox("City or municipality", ["All", *cities], key="public_city") if selected_region != "All" else "All"
    if selected_region == "All":
        location_data, denominator = region_rows, ads
        location_title, location_label = "Advertisements by Philippine region", "region"
    else:
        location_data = [{"label": row["label"], "count": row["count"]} for row in city_rows if selected_city == "All" or row["label"] == selected_city]
        denominator = int(next((row["count"] for row in region_rows if row["label"] == selected_region), 0)) if selected_city == "All" else int(next((row["count"] for row in city_rows if row["label"] == selected_city), 0))
        location_title, location_label = (f"Cities and municipalities in {selected_region}", "location") if selected_city == "All" else (f"Advertisements in {selected_city}", "location")
    _bar(location_data, "location", "job_ads", location_title, "Top occupational titles", denominator, "locations", order, limit)
    if selected_region == "All":
        skill_data = [row for row in charts.get("regionSkillDemand", []) if row["region"]]
        area = "All regions"
        denominator = summary["withLocation"]
    else:
        skill_data = [row for row in charts.get("citySkillDemand", []) if row["region"] == selected_region and (selected_city == "All" or row["locality"] == selected_city)]
        area = selected_city if selected_city != "All" else selected_region
        denominator = int(next((row["count"] for row in (city_rows if selected_city != "All" else region_rows)
                               if row["label"] == (selected_city if selected_city != "All" else selected_region)), 0))
    skill_counts = {}
    for row in skill_data:
        skill_counts[row["skill_label"]] = skill_counts.get(row["skill_label"], 0) + int(row["job_ads"])
    _bar([{"label": label, "count": count} for label, count in skill_counts.items()], "employer_skill", "employer_demand_count",
         f"Skills in {area}", "Top requested skills", denominator, "location_skills", order, min(limit, 10))

    monthly = charts.get("timelineByTitle", [])
    title_totals = {}
    for row in monthly:
        title_totals[row["label"]] = title_totals.get(row["label"], 0) + int(row["count"])
    title_options = sorted(title_totals, key=lambda name: (-title_totals[name], name))
    timeline_titles = st.multiselect("Job titles to compare", title_options, default=title_options[:5], key="public_timeline_titles")
    if timeline_titles:
        selected = [row for row in monthly if row["label"] in timeline_titles]
        monthly_frame = pd.DataFrame([{"month": row["month"], "job_title": row["label"], "job_ads": row["count"]} for row in selected])
        totals = pd.DataFrame(charts.get("timelineCoverage", []))
        dated = int(totals.loc[totals.label.isin(timeline_titles), "dated"].sum()) if not totals.empty else sum(title_totals.get(title, 0) for title in timeline_titles)
        undated = int(totals.loc[totals.label.isin(timeline_titles), "undated"].sum()) if not totals.empty else 0
        by_month = monthly_frame.groupby("month", as_index=False).job_ads.sum() if not monthly_frame.empty else pd.DataFrame()
        peak = int(by_month.job_ads.max()) if not by_month.empty else 0
        peak_months = by_month.loc[by_month.job_ads.eq(peak), "month"].astype(str).tolist()[:3] if peak else []
        summary_text = f"The chosen titles appear in {dated:,} dated ads. The highest recorded monthly count is {peak:,}, in {', '.join(peak_months)}."
        top = [(title, title_totals.get(title, 0)) for title in timeline_titles]
        featured_visual_chart(lambda: job_title_trend(monthly_frame, "Job-title posting timeline"), summary_text, top,
                              key="title_timeline", insight_title="Timeline Insight", list_title="Dated ads by selected title")
        st.caption(f"{dated:,} dated ads; {undated:,} ads with missing or invalid dates are excluded.")


def _qualifications(result):
    _chart_settings("Job Market Analysis")
    charts, summary = result["charts"], result["summary"]
    order, limit = _controls("public_qualifications")
    education = pd.DataFrame(charts.get("education", []))
    if not education.empty:
        max_value = int(education.job_ads.max())
        leaders = education.loc[education.job_ads.eq(max_value), "education_level"].tolist()
        classified = int(education.job_ads.sum())
        text = (f"Only one classifiable stated level appears in this selection: {education.iloc[0].education_level} ({int(education.iloc[0].job_ads):,} ads)."
                if len(education) == 1 else
                f"{len(leaders):,} displayed levels share the highest count ({max_value:,} ads each): {', '.join(leaders)}. There are {classified:,} ads with one recognized level."
                if len(leaders) > 1 else
                f"{leaders[0]} has the highest classified count ({max_value:,} of {classified:,} ads with one recognized level).")
        top = list(education.sort_values(["job_ads", "level_order"], ascending=[False, True]).head(3)[["education_level", "job_ads"]].itertuples(index=False, name=None))
        featured_visual_chart(lambda: education_bar(education), text, top, key="education", insight_title="Education Insight", list_title="Classified levels", heading="Stated education requirements by level")
    else:
        st.info("No single education level could be classified from the stated requirements.")
    st.caption(f"Education is stated in {summary['withEducation']:,} of {summary['ads']:,} ads. Not stated does not mean education was not required; {summary['educationNeedsReview']:,} stated ads need review.")
    experience = _frame(charts.get("experience"), "requirement", "job_ads", total=summary["ads"])
    shown = experience.sort_values(["job_ads", "requirement"], ascending=[order != "Lowest demand", True]).head(limit) if not experience.empty else experience
    if shown.empty:
        st.info("No experience durations could be compared in this selection.")
    else:
        count = int(shown.job_ads.max())
        leaders = shown.loc[shown.job_ads.eq(count), "requirement"].tolist()
        text = f"{len(leaders):,} displayed durations share the highest count ({count:,} ads each)." if len(leaders) > 1 else f"{str(leaders[0]).capitalize()} is the most frequent duration shown ({count:,} of {summary['ads']:,} selected ads)."
        top = list(shown.sort_values(["job_ads", "requirement"], ascending=[False, True]).head(3)[["requirement", "job_ads"]].itertuples(index=False, name=None))
        st.subheader("Experience requirements")
        with st.container(border=True):
            result_count_chart(shown, "requirement", "job_ads", "Experience duration distribution", order=order, limit=limit, downloads=True, show_heading=False)
            result_insight("Experience Insight", text, top, "Displayed durations")
    st.caption(f"Experience was identified in {summary['withExperience']:,} ads. Exact-year median: {summary['experienceExactMedian']} from {summary['experienceExactCount']:,} ads; ranges and open-ended wording remain separate.")


def _psf(result):
    _chart_settings("Job Market Analysis")
    charts, summary = result["charts"], result["summary"]
    order, limit = _controls("public_psf")
    roles = charts.get("psfRoles", [])
    role_names = [row["label"] for row in roles]
    selected_role = st.selectbox("PSF-AAI reference role", ["All", *role_names], key="public_psf_role")
    if selected_role == "All":
        competencies = charts.get("psf", [])
        denominator = summary["ads"]
    else:
        role_cells = [row for row in charts.get("psfHeatmap", []) if row["role"] == selected_role]
        competencies = [{"label": row["competency"], "count": row["count"]} for row in role_cells]
        denominator = next((int(row["count"]) for row in roles if row["label"] == selected_role), 0)
    _bar(competencies, "psf_competency", "job_ads", "PSF-AAI competencies linked to employer demand", "Most linked competency", denominator,
         "psf_competencies", order, limit, "Top Displayed Competencies")
    _bar(roles, "psf_job_role", "job_ads", "Related PSF-AAI reference roles", "Most represented reference roles", None,
         "psf_roles", order, limit, "Top Displayed Roles")
    if roles:
        role_frame = pd.DataFrame([{"psf_job_role": row["label"], "job_ads": row["count"]} for row in roles])
        result_role_distribution(role_frame)
    cells = charts.get("psfHeatmap", [])
    role_sizes = {row["label"]: int(row["count"]) for row in roles}
    role_options = sorted({row["role"] for row in cells}, key=lambda name: (-role_sizes.get(name, 0), name))
    competencies_options = sorted({row["competency"] for row in cells}, key=lambda name: (-int(next((row["count"] for row in charts.get("psf", []) if row["label"] == name), 0)), name))
    chosen_roles = st.multiselect("Reference roles in the heatmap", role_options, default=role_options[:8], key="public_psf_heatmap_roles")
    chosen_competencies = st.multiselect("PSF-AAI competencies in the heatmap", competencies_options, default=competencies_options[:min(limit, 15)], key="public_psf_heatmap_competencies")
    if chosen_roles and chosen_competencies:
        matrix = pd.DataFrame(0, index=chosen_roles, columns=chosen_competencies, dtype=int)
        for row in cells:
            if row["role"] in chosen_roles and row["competency"] in chosen_competencies:
                matrix.at[row["role"], row["competency"]] = int(row["count"])
        denominators = pd.Series(role_sizes).reindex(matrix.index).fillna(0).astype(int)
        shares = matrix.div(denominators.where(denominators.gt(0), 1), axis=0).mul(100)
        _heatmap(matrix, "PSF-AAI competencies across reference roles", "Counts show ads with automated candidate links.",
                 [], "psf_role_competency_heatmap", shares=shares, denominators=denominators,
                 share_label="Share of role ads", denominator_label="Advertisements linked to role",
                 group_label="reference role", transpose=True)
    if charts.get("psfEvidence"):
        with st.expander("PSF-AAI reference evidence"):
            st.dataframe(pd.DataFrame(charts["psfEvidence"]), width="stretch", hide_index=True)


def _alignment(result):
    _chart_settings("Employer–PSF Alignment")
    rates, summary = result["alignmentRates"], result["summary"]
    metrics = [("Alignment rate", rates.get("alignment_rate")), ("Partially aligned rate", rates.get("partially_aligned_rate")), ("Unmapped rate", rates.get("unmapped_rate"))]
    with st.container(horizontal=True, gap="medium", wrap=True):
        for label, value in metrics:
            with st.container(border=True, width="stretch"):
                st.metric(label, "—" if value is None else f"{value:.1f}%")
    rows = _frame(result["charts"].get("alignment"), "status", "evidence_groups")
    if not rows.empty:
        order, limit = _controls("public_alignment")
        _bar(result["charts"].get("alignment"), "status", "evidence_groups", "Status of Phrase–Competency Evidence Groups",
             "Top requested skills", None, "alignment_status", order, limit, "Status breakdown")
        st.caption(f"{summary['alignmentGroups']:,} phrase–competency evidence groups; statuses are automated candidates, not researcher review decisions.")


def _unmapped(result):
    _chart_settings("Unmapped / Emerging Skills")
    charts, summary = result["charts"], result["summary"]
    order, limit = _controls("public_unmapped")
    for source, title, heading, key in (("unmapped", "Unmapped skill evidence", "Most frequent unmapped skill", "unmapped_evidence"),
                                       ("recurring", "Recurring unmapped phrases for review", "Recurring unmapped skill", "unmapped_recurring")):
        _bar(charts.get(source), "skill_label", "job_ads", title, heading, summary["ads"], key, order, limit,
             "Top Displayed Candidates" if source == "recurring" else "Top Displayed Skills")
    st.caption("A missing PSF-AAI match does not establish a framework gap. Recurrence alone does not establish emergence.")


def _results(result):
    _topbar(3)
    file_name = escape_html(str(result["filename"]))
    model = result["model"]
    details, actions = st.columns([3, 1], vertical_alignment="center")
    with details:
        facts = (("Classifier", str(model["name"])),
                 ("Model ID", str(model["version"])),
                 ("Dataset ID", str(result["datasetHash"][:16])),
                 ("Analysis input ID", str(result["analysisInputHash"][:16])))
        fact_markup = "".join(
            f'<span class="public-result-fact"><span>{escape_html(label)}</span><strong>{escape_html(value)}</strong></span>'
            for label, value in facts
        )
        st.html(f'<div class="public-result-meta" aria-label="Analysis details"><div class="public-result-file"><span class="material-symbols-rounded public-result-file-icon" aria-hidden="true">description</span><div class="public-result-file-copy"><strong>{file_name}</strong><small>{result["summary"]["rows"]:,} CSV rows</small></div></div><div class="public-result-facts">{fact_markup}</div></div>')
    with actions:
        if st.button("Analyze another dataset", type="primary", icon=":material/upload_file:",
                     key="public_analyze_another", width="stretch"):
            _reset()
    analysis_workflow()
    job_market_metrics(result["summary"], result["summary"])

    report_rows = []
    for section, rows in result["charts"].items():
        if isinstance(rows, list):
            report_rows.extend({"section": section, **row} for row in rows)
    with st.container(horizontal=True, vertical_alignment="center", horizontal_alignment="distribute",
                      key="public-results-heading"):
        st.subheader("Results Section", icon=":material/bar_chart:")
        if report_rows:
            st.download_button("Export results", pd.DataFrame(report_rows).to_csv(index=False).encode("utf-8-sig"),
                               f"{Path(file_name).stem}-results.csv", "text/csv", key="public_results_csv",
                               type="primary", icon=":material/download:")
    with st.container(key="public-results-tabs"):
        tabs = st.tabs(["Skills", "Roles and locations", "Qualifications", "PSF-AAI demand", "Alignment evidence", "Unmapped / emerging"])
        with tabs[0]: _skills(result)
        with tabs[1]: _roles(result)
        with tabs[2]: _qualifications(result)
        with tabs[3]: _psf(result)
        with tabs[4]: _alignment(result)
        with tabs[5]: _unmapped(result)


def _process_pending_upload():
    content = st.session_state.get("public_content")
    file_name = st.session_state.get("public_filename")
    mapping = dict(st.session_state.get("public_mapping", {}))
    if content is None or not file_name:
        st.session_state["public_stage"] = "upload"
        st.rerun()

    mark_uri = "data:image/svg+xml;base64," + base64.b64encode(APP_ICON.read_bytes()).decode("ascii")
    with st.container(key="public-processing-overlay"):
        with st.container(key="public-processing-card"):
            st.html(f'<div class="public-processing-brand"><img alt="" src="{mark_uri}"><span><strong>Future of Work</strong><small>MSU-IIT · Job Market Analytics</small></span></div><h1 class="public-processing-title">Analyzing your dataset</h1><p class="public-processing-copy">Applying the public classifier and shared analysis pipeline.</p>')
            message = st.empty()
            message.html('<p class="public-processing-status">Preparing your dataset analysis…</p>')
            bar, value = st.columns([1, .07], vertical_alignment="center", gap="small")
            with bar:
                progress = st.progress(0)
            with value:
                percent = st.empty()
                percent.html('<span class="public-processing-percent">0%</span>')
            st.html('<p class="public-processing-privacy">Your recent upload stays available in this browser session.</p>')

    def update(value, text):
        percentage = min(100, max(0, int(round(float(value) * 100))))
        progress.progress(percentage)
        message.html(f'<p class="public-processing-status">{escape_html(str(text))}</p>')
        percent.html(f'<span class="public-processing-percent">{percentage}%</span>')

    try:
        result = analyze_upload(content, file_name, mapping, hosted=True, progress=update)
    except Exception as exc:
        st.session_state["public_error"] = str(exc)
        st.session_state["public_stage"] = "review"
        st.rerun()
    update(1.0, "Analysis complete. Preparing your results.")
    time.sleep(.45)
    st.session_state["public_result"] = result
    st.session_state["public_stage"] = "results"
    st.session_state.pop("public_error", None)
    st.rerun()


def main():
    _style()
    _restore_recent_upload()
    result = st.session_state.get("public_result")
    if result and result.get("schemaVersion") != RESULT_SCHEMA_VERSION:
        st.session_state.pop("public_result")
        st.session_state["public_stage"] = "review"
        st.info("The counting rules have changed. Start analysis to update your results.")
        result = None
    if result:
        _results(result)
        st.html('<footer class="st-key-public-footer">Future of Work · Philippine job advertisement analysis · MSU-IIT</footer>')
        _persist_recent_upload()
        return

    stage = st.session_state.get("public_stage", "upload")
    processing = stage == "processing"
    if stage not in {"upload", "review", "processing"}:
        st.session_state["public_stage"] = stage = "upload"
        processing = False
    if stage in {"review", "processing"} and st.session_state.get("public_preview") is None:
        st.session_state["public_stage"] = stage = "upload"
        processing = False
    content = st.session_state.get("public_content")
    preview = st.session_state.get("public_preview")
    mapping = dict(st.session_state.get("public_mapping", {}))
    _topbar(1 if stage == "upload" else 2)
    if stage == "upload":
        _stage_heading(1, "Upload your job advertisements", "Start by selecting a CSV dataset. We’ll guide you through the rest.", "CSV format · Up to 4 MB")
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
                            prior = st.session_state.get("public_recent_upload") or {}
                            prior_mapping = prior.get("mapping", {}) if prior.get("file_hash") == file_hash else {}
                            st.session_state["public_mapping"] = dict(prior_mapping) or suggest_column_mapping(preview.columns, "jobs")[0]
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
        file_hash = st.session_state["public_file_hash"]
        file_name = st.session_state["public_filename"]
        columns = list(preview.columns)
        mapping = dict(st.session_state.get("public_mapping", {}))
        fields = (*REQUIRED_FIELDS, *OPTIONAL_FIELDS)
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
                st.html('<div class="public-map-head"><span>CSV column</span><span>Used as</span><span>Status</span></div>')
                for field in REQUIRED_FIELDS:
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

            title_ready = bool(mapping.get("job_title"))
            detail_ready = any(mapping.get(field) for field in REQUIRED_FIELDS[1:])
            unique = not duplicate_columns
            classifier_ready = bool(ENGINE.get("classifierAvailable"))
            ready = title_ready and detail_ready and unique and classifier_ready
            checks = (("CSV structure validated", True),
                      ("Job title and detail columns identified", title_ready and detail_ready),
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
                          disabled=not ready or processing, key="public_start_analysis", width="stretch"):
                st.session_state["public_stage"] = "processing"
                st.session_state.pop("public_error", None)
                st.rerun()

    with st.container(key="public-footer"):
        st.caption(f"Future of Work · Philippine job advertisement analysis · v{PUBLIC_VERSION}")
    _persist_recent_upload()
    if processing:
        _process_pending_upload()


main()
