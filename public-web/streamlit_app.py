"""Anonymous Streamlit edition of the public job-ad analyzer."""

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

import pandas as pd
import streamlit as st

st.set_page_config(page_title="Future of Work | Public analyzer", page_icon=":material/work:",
                   layout="wide", initial_sidebar_state="collapsed")

from src.config import FIELDS, VERSION
from src.design import apply_design
from src.loaders import load_data
from src.public_engine import MAX_HOSTED_UPLOAD_BYTES, analyze_upload, health
from src.ui import (featured_result_chart, featured_visual_chart, result_chart_options,
                    result_count_chart, result_heatmap, result_insight,
                    result_role_distribution)
from src.visualization import education_bar, heatmap, job_title_trend


ROOT = Path(__file__).resolve().parents[1]
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
REFERENCE = json.loads((ROOT / "public-web/site/reference.json").read_text(encoding="utf-8"))
ENGINE = health(hosted=True)


def _style():
    apply_design()
    st.html("""<style>
    [data-testid="stSidebar"],[data-testid="stSidebarCollapsedControl"]{display:none!important}
    [data-testid="stHeader"]{background:transparent}
    .stMainBlockContainer{max-width:1440px;padding:1rem clamp(1rem,3vw,2.5rem) 4rem}
    .public-topbar{display:flex;align-items:center;justify-content:space-between;gap:1rem;padding:.25rem 0 1rem;border-bottom:1px solid #e5e3e0}
    .public-topbar img{width:clamp(145px,18vw,205px);height:auto}
    .public-version{color:#647184;font-size:.75rem}
    .public-hero{padding:clamp(1.5rem,4vw,3rem) 0 1.25rem}
    .public-eyebrow{margin:0 0 .35rem;color:#78182b;font-size:.75rem;font-weight:700;letter-spacing:.09em;text-transform:uppercase}
    .public-hero h1{margin:.15rem 0 .55rem;color:#24303d;font-size:clamp(1.8rem,3.2vw,2.6rem);line-height:1.12}
    .public-hero p{max-width:58rem;color:#647184}
    .public-steps{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:1rem;margin:0 0 1.5rem;padding:1rem 1.2rem;border:1px solid #e5e3e0;border-radius:12px;background:#fff}
    .public-step{display:flex;align-items:center;gap:.7rem;color:#24303d;font-size:.85rem;font-weight:650}
    .public-step b{display:grid;place-items:center;flex:0 0 34px;height:34px;border-radius:9px;background:#f7edef;color:#78182b}
    .public-step[data-current="true"] b{background:#78182b;color:#fff}
    .public-step small{display:block;color:#647184;font-size:.72rem;font-weight:400}
    .st-key-public-upload-card,.st-key-public-workflow-card{height:100%;padding:clamp(1rem,2.5vw,1.75rem);border:1px solid #e5e3e0;border-radius:14px;background:#fff}
    .st-key-public-upload-card [data-testid="stFileUploaderDropzone"]{min-height:220px;border:1px dashed #b87885;border-radius:12px;background:#fcf8f8}
    .st-key-public-upload-card [data-testid="stFileUploaderDropzone"] button{background:#78182b;color:white;border:0;border-radius:8px;min-height:44px;font-weight:650}
    .st-key-public-upload-card [data-testid="stFileUploaderDropzone"] button:hover{background:#5e1221;color:white}
    .stFormSubmitButton button,.stButton button[kind="primary"],.stDownloadButton button{min-height:44px;border-radius:8px;font-weight:650}
    .stFormSubmitButton button,.stButton button[kind="primary"]{background:#78182b;border-color:#78182b}
    .stTabs [data-baseweb="tab-list"]{gap:.25rem;flex-wrap:nowrap;overflow-x:auto;border:1px solid #e5d7d5;border-radius:10px;background:#fff;padding:.25rem}
    .stTabs [data-baseweb="tab"]{min-height:38px;padding:.4rem clamp(.45rem,1vw,.9rem);white-space:nowrap;font-size:.78rem}
    .stTabs [aria-selected="true"]{background:#78182b;color:#fff;border-radius:7px}
    .st-key-public-footer{margin-top:3rem;padding-top:1rem;border-top:1px solid #e5e3e0;color:#647184;font-size:.75rem}
    @media(max-width:720px){.public-steps{grid-template-columns:1fr}.public-step small{display:none}.stMainBlockContainer{padding-inline:1rem}}
    </style>""")


def _topbar(step: int, *, results: bool = False):
    logo = (ROOT / "assets/job_market_brand.svg").read_text(encoding="utf-8")
    logo_uri = "data:image/svg+xml;base64," + base64.b64encode(logo.encode("utf-8")).decode("ascii")
    st.html(f'<div class="public-topbar"><img alt="Future of Work" src="{logo_uri}"><span class="public-version">Public analyzer · v{VERSION}</span></div>')
    title = "Analysis results" if results else "Review your dataset" if step == 2 else "Upload your job advertisements"
    intro = ("Explore the shared research charts and evidence for your dataset." if results else
             "Check the detected columns before beginning the analysis." if step == 2 else
             "Start with a CSV dataset. We’ll guide you through the rest.")
    st.html(f'<header class="public-hero"><p class="public-eyebrow">MSU-IIT · Philippine jobs · Skills · PSF-AAI</p><h1>{title}</h1><p>{intro}</p></header>')
    steps = [(1, "Check dataset structure", "Review detected fields and sample rows."),
             (2, "Prepare and analyze", "Use the research classifier and analysis rules."),
             (3, "Explore the findings", "Review trends and PSF-AAI evidence.")]
    st.html('<div class="public-steps" aria-label="Analysis process">' + "".join(
        f'<div class="public-step" data-current="{index == step}"><b>{index:02}</b><span>{name}<small>{detail}</small></span></div>'
        for index, name, detail in steps) + "</div>")


def _suggest_mapping(columns):
    clean = lambda value: "".join(char for char in str(value).casefold() if char.isalnum())
    fields = REFERENCE.get("columns", {})
    mapping, used = {field: "" for field in FIELDS["jobs"]}, set()
    normalized = {column: clean(column.split("__", 1)[0]) for column in columns}
    for exact in (True, False):
        for field in FIELDS["jobs"]:
            if mapping[field]:
                continue
            names = [field] if exact else fields.get(field, [])
            choices = [column for column in columns if column not in used and normalized[column] in {clean(name) for name in names}]
            if len(choices) == 1:
                mapping[field] = choices[0]
                used.add(choices[0])
    return mapping


def _column_label(name):
    if name.startswith("unnamed_column_"):
        return f"Column {name.rsplit('_', 1)[-1]} (blank header)"
    if "__" in name and name.rsplit("__", 1)[-1].isdigit():
        base, suffix = name.rsplit("__", 1)
        return f"{base} [{suffix}]"
    return name


def _read_upload(upload):
    content = upload.getvalue()
    if len(content) > MAX_HOSTED_UPLOAD_BYTES:
        raise ValueError("This public Streamlit app accepts CSV files up to 4 MB.")
    encoding = "utf-16" if content.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig"
    frame = load_data(content, upload.name, encoding=encoding)
    if len(frame) > 100_000:
        raise ValueError("This public analysis is limited to 100,000 rows per upload.")
    return content, frame


def _reset():
    st.session_state["public_upload_key"] = st.session_state.get("public_upload_key", 0) + 1
    for key in ("public_file_hash", "public_filename", "public_content", "public_preview", "public_mapping", "public_result", "public_error"):
        st.session_state.pop(key, None)
    st.rerun()


def _metric_row(summary):
    values = [("Job ads", summary["ads"]), ("Distinct chart skills", summary["chartSkills"]),
              ("Distinct phrases withheld", summary["withheldPhrases"]), ("PSF-AAI reference roles", summary["referenceRoles"])]
    with st.container(horizontal=True, gap="medium", wrap=True):
        for label, value in values:
            with st.container(border=True, width="stretch"):
                st.metric(label, f"{value:,}")


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
    _topbar(3, results=True)
    file_name = result["filename"]
    model = result["model"]
    st.caption(f"{file_name} · {result['summary']['rows']:,} rows · {model['name']} · model {model['version']} · dataset {result['datasetHash'][:16]}")
    st.info("This anonymous run uses the released public classifier and shared analysis functions. It does not apply saved researcher-only labels, mapping reviews, or corrections.", icon=":material/info:")
    _metric_row(result["summary"])
    if st.button("Analyze another file", type="primary", icon=":material/upload_file:", key="public_analyze_another"):
        _reset()
    tabs = st.tabs(["Skills", "Roles and locations", "Qualifications", "PSF-AAI demand", "Alignment evidence", "Unmapped / emerging"])
    with tabs[0]: _skills(result)
    with tabs[1]: _roles(result)
    with tabs[2]: _qualifications(result)
    with tabs[3]: _psf(result)
    with tabs[4]: _alignment(result)
    with tabs[5]: _unmapped(result)
    report_rows = []
    for section, rows in result["charts"].items():
        if isinstance(rows, list):
            for row in rows:
                report_rows.append({"section": section, **row})
    if report_rows:
        st.download_button("Results CSV", pd.DataFrame(report_rows).to_csv(index=False).encode("utf-8-sig"),
                           f"{Path(file_name).stem}-results.csv", "text/csv", key="public_results_csv")


def main():
    _style()
    result = st.session_state.get("public_result")
    if result:
        _results(result)
        st.html('<footer class="st-key-public-footer">Future of Work · Philippine job advertisement analysis · MSU-IIT</footer>')
        return

    _topbar(1)
    left, right = st.columns([1.65, 1], gap="large", vertical_alignment="top")
    with left, st.container(key="public-upload-card"):
        st.subheader("Upload your job advertisements")
        st.caption("Drop a CSV dataset here or select a file from your device.")
        st.caption("Up to 4 MB · 100,000 records · CSV only")
        uploaded = st.file_uploader("Select a CSV file", type=["csv"], key=f"public_upload_{st.session_state.get('public_upload_key', 0)}",
                                    help="Your file is analyzed in this app session and is not added to the research workspace.")
        if uploaded:
            try:
                content, preview = _read_upload(uploaded)
                file_hash = hashlib.sha256(content).hexdigest()
                if st.session_state.get("public_file_hash") != file_hash:
                    st.session_state["public_file_hash"] = file_hash
                    st.session_state["public_filename"] = Path(uploaded.name).name
                    st.session_state["public_content"] = content
                    st.session_state["public_preview"] = preview
                    st.session_state["public_mapping"] = _suggest_mapping(list(preview.columns))
                st.success(f"{uploaded.name} · {len(preview):,} records detected")
                if not ENGINE.get("classifierAvailable"):
                    st.warning("The approved research classifier has not been released to this public app yet. You can inspect and map the file; analysis unlocks after the classifier is released.")
                with st.form("public-column-mapping"):
                    st.subheader("Review your dataset")
                    st.caption("Choose which CSV column matches each field. Every selection stays editable.")
                    mapping = dict(st.session_state["public_mapping"])
                    for field in REQUIRED_FIELDS:
                        mapping[field] = st.selectbox(FIELD_LABELS[field], ["", *preview.columns],
                            index=(["", *preview.columns].index(mapping.get(field, "")) if mapping.get(field, "") in ["", *preview.columns] else 0),
                            format_func=lambda value: "Choose a column" if not value else _column_label(value),
                            key=f"public-map-{file_hash[:10]}-{field}")
                    with st.expander("Optional fields"):
                        for field in OPTIONAL_FIELDS:
                            mapping[field] = st.selectbox(FIELD_LABELS.get(field, field.replace("_", " ").title()), ["", *preview.columns],
                                index=(["", *preview.columns].index(mapping.get(field, "")) if mapping.get(field, "") in ["", *preview.columns] else 0),
                                format_func=lambda value: "Not mapped" if not value else _column_label(value),
                                key=f"public-map-{file_hash[:10]}-{field}")
                    st.session_state["public_mapping"] = mapping
                    ready = bool(mapping.get("job_title") and any(mapping.get(field) for field in REQUIRED_FIELDS[1:]))
                    analyze = st.form_submit_button("Analyze dataset", type="primary", disabled=not (ready and ENGINE.get("classifierAvailable")))
                if analyze:
                    st.session_state["public_mapping"] = mapping
                    try:
                        with st.status("Analyzing job advertisements", expanded=True) as status:
                            progress = st.progress(0, text="Preparing the research analysis…")
                            def update(value, message):
                                progress.progress(min(100, max(0, int(value * 100))), text=message)
                                status.write(message)
                            result = analyze_upload(content, uploaded.name, mapping, hosted=True, progress=update)
                            st.session_state["public_result"] = result
                            status.update(label="Analysis complete", state="complete", expanded=False)
                        st.rerun()
                    except Exception as exc:
                        st.error(str(exc))
                with st.expander("Preview source rows"):
                    st.dataframe(preview.head(8), width="stretch", hide_index=True)
            except (ValueError, OSError) as exc:
                st.error(str(exc))
    with right, st.container(key="public-workflow-card"):
        st.subheader("What happens after uploading?")
        for number, title, detail in (("01", "Check dataset structure", "Review detected fields and sample rows."),
                                      ("02", "Prepare and analyze", "Apply the released research classifier and shared analysis rules."),
                                      ("03", "Explore the findings", "Review trends and PSF-AAI evidence.")):
            st.markdown(f"**{number} · {title}**  \n{detail}")
        st.divider()
        st.caption("Uploads are held in the Streamlit session. This app does not write them or their results to researcher tables or project files.")
    with st.container(key="public-footer"):
        st.caption(f"Future of Work · Philippine job advertisement analysis · v{VERSION}")


main()
