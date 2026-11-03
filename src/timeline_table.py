"""Small browser-only timeline table; playback never reruns the analysis."""
from pathlib import Path

import streamlit as st
from .config import VERSION


@st.cache_resource
def _component(version):
    return st.components.v2.component(
        "job_title_timeline_table",
        html="""
    <section aria-label="Job-title timeline table">
     <div class="toolbar"><div class="playback"><button id="play" type="button">▶ Play</button><button id="pause" type="button">❚❚ Pause</button><output id="month" aria-live="off"></output></div></div>
     <label for="position">Through posting month</label><input id="position" type="range" min="0" step="1">
     <p id="period"></p><div class="table-scroll"><table><thead><tr><th>Job title</th><th>Ads in month</th><th>Dated ads through month</th><th>Monthly counts</th></tr></thead><tbody></tbody></table></div>
    </section>
    """,
        css="""
    :host{font-family:var(--st-font);color:var(--st-text-color)}
    *{box-sizing:border-box}.toolbar,.playback{display:flex;align-items:center;gap:8px;flex-wrap:wrap}.toolbar{justify-content:space-between;margin:4px 0 16px}
    button{min-height:44px;padding:0 16px;border:1px solid var(--st-border-color);border-radius:8px;background:var(--st-background-color);color:var(--st-text-color);font:inherit;cursor:pointer}
    #play{background:var(--st-primary-color);border-color:var(--st-primary-color);color:white}button:disabled{opacity:.5;cursor:default}button:focus-visible,input:focus-visible{outline:2px solid var(--st-primary-color);outline-offset:3px}
    output{font-weight:600;font-variant-numeric:tabular-nums;padding:8px}label,p{font-size:.85rem}input{display:block;width:100%;min-height:36px;accent-color:var(--st-primary-color);margin:4px 0}p{margin:8px 0 16px}
    .table-scroll{overflow-x:auto;border:1px solid var(--st-border-color);border-radius:10px}table{width:100%;border-collapse:collapse;font-size:.875rem}th,td{padding:12px 14px;text-align:left;border-bottom:1px solid var(--st-border-color)}th{background:var(--st-secondary-background-color);font-weight:600}tr:last-child td{border-bottom:0}td:nth-child(2),td:nth-child(3){font-variant-numeric:tabular-nums;text-align:right}svg{display:block;width:100%;min-width:140px;height:38px;overflow:visible;color:var(--st-primary-color)}
    @media(max-width:540px){.toolbar{align-items:stretch}.playback{width:100%}th,td{padding:10px;font-size:.8rem}}
    """,
        js=Path(__file__).with_name("timeline_table.js").read_text(encoding="utf-8"),
    )


def timeline_table_data(monthly, titles):
    matrix = monthly.pivot(index="job_title", columns="month", values="job_ads").sort_index(axis=1)
    months = matrix.columns.tolist()
    series = [{"title": title, "counts": matrix.loc[title].fillna(0).astype(int).tolist() if title in matrix.index else None}
              for title in sorted(titles)]
    return {"months": months, "series": series}


def timeline_table(monthly, titles):
    data = timeline_table_data(monthly, titles)
    _component(VERSION)(data=data, key="job_title_timeline_table", width="stretch", height="content")
