"""Data loads display skeletons only in an explicit output region."""

from collections.abc import Callable
from contextlib import contextmanager
from typing import TypeVar
import streamlit as st

T = TypeVar("T")


def _wireframe(kind, *, cards=None, columns=None, rows=None, controls=None, field_columns=1, view=None):
    """Build only the requested component, without values or extra data work."""
    line = '<span class="fow-skeleton-line"></span>'
    icon = '<span class="fow-skeleton-icon"></span>'
    card = '<div class="fow-skeleton-card" aria-hidden="true">' + icon + '<div class="fow-skeleton-metric-text">' + line * 2 + '</div></div>'
    toolbar = '<div class="fow-skeleton-toolbar" aria-hidden="true">' + line * 3 + '</div>'
    field = '<div class="fow-skeleton-field" aria-hidden="true">' + line + '<span class="fow-skeleton-control"></span></div>'
    heading = '<div class="fow-skeleton-heading" aria-hidden="true">' + icon + line + '</div>'
    disclosure = '<div class="fow-skeleton-disclosure" aria-hidden="true">' + line + '</div>'
    notice = '<div class="fow-skeleton-notice" aria-hidden="true">' + icon + '<div>' + line * 2 + '</div></div>'
    chart_rows = min(15, max(2, rows if rows is not None else 8))
    chart = '<div class="fow-skeleton-chart" aria-hidden="true">' + ''.join('<div class="fow-skeleton-bar">' + line * 2 + '</div>' for _ in range(chart_rows)) + '</div>'
    insight = '<div class="fow-skeleton-insight" aria-hidden="true">' + heading + line * 3 + '<div class="fow-skeleton-insight-list">' + line * 3 + '</div></div>'
    chart_panel = '<div class="fow-skeleton-panel">' + heading + '<div class="fow-skeleton-grid">' + chart + insight + '</div></div>'
    if kind == "table" and columns is None:
        kind = "pending"  # No schema is available until the source has been read.
    if rows is None:
        rows = 10 if kind == "review" else 5
    rows = min(12 if kind == "heatmap" else 10, max(0, int(rows)))
    if kind in {"table", "review", "results", "heatmap", "quality", "evaluation", "file_preview", "psf_charts"}:
        column_count = 4 if kind == "evaluation" else min(12, len(columns)) if columns is not None else (7 if kind == "review" else 1)
        if kind == "evaluation":
            rows = 2
        cell = '<span class="fow-skeleton-cell"></span>' if kind in {"heatmap", "psf_charts"} else line
        table_rows = ''.join('<div class="fow-skeleton-row">' + cell * max(1, column_count) + '</div>'
                             for _ in range(max(1, rows) if kind == "heatmap" else rows + 1))
        table_class = "fow-skeleton-matrix" if kind in {"heatmap", "psf_charts"} else "fow-skeleton-table"
        table = f'<div class="{table_class}" aria-hidden="true">{table_rows}</div>'
    if kind in {"metrics", "job_metrics"}:
        markup = card * min(8, max(1, cards if cards is not None else 4))
    elif kind == "reports":
        report_card = '<div class="fow-skeleton-card" aria-hidden="true">' + icon + line * 3 + '<span class="fow-skeleton-control"></span></div>'
        markup = '<div class="fow-skeleton-toolbar">' + disclosure + '</div>' + heading + report_card * min(8, max(1, cards if cards is not None else 5))
    elif kind == "notice":
        markup = notice
    elif kind == "overview":
        callout = '<div class="fow-skeleton-callout" aria-hidden="true">' + icon + '<div>' + line * 3 + '</div><span class="fow-skeleton-control"></span></div>'
        workflow_card = '<div class="fow-skeleton-workflow-card" aria-hidden="true">' + icon + '<div>' + line * 3 + '</div><span class="fow-skeleton-control"></span></div>'
        markup = '<div class="fow-skeleton-summary">' + card * 4 + '</div>' + callout + heading + '<div class="fow-skeleton-workflow">' + workflow_card * 6 + '</div>'
    elif kind == "readiness":
        markup = notice + line + '<div class="fow-skeleton-summary">' + card * 4 + '</div>'
    elif kind == "study_metrics":
        markup = '<div class="fow-skeleton-study-strip">' + heading + '<div class="fow-skeleton-summary">' + card * 4 + '</div></div>'
    elif kind == "workspace_status":
        markup = notice if view == "local" else notice + '<div class="fow-skeleton-summary">' + ('<div class="fow-skeleton-panel">' + heading + line * 2 + field + '</div>') * 2 + '</div>'
    elif kind == "unmapped":
        markup = toolbar + '<div class="fow-skeleton-summary" aria-hidden="true">' + card * 3 + '</div>' + (chart_panel + disclosure) * 2
    elif kind == "psf_charts":
        markup = chart_panel * 2 + '<div class="fow-skeleton-panel">' + heading + table + disclosure * 2 + '</div>'
    elif kind == "market_section":
        if view == "Qualifications":
            markup = notice + chart_panel * 2 + disclosure * 2
        elif view == "Roles and locations":
            markup = '<div class="fow-skeleton-panel">' + heading + field + '<div class="fow-skeleton-grid">' + chart + insight + '</div></div>' + chart_panel + disclosure
        elif view == "PSF-AAI demand":
            markup = toolbar + chart_panel * 2 + disclosure * 2
        elif view == "Skills":
            markup = chart_panel * 3 + disclosure * 3
        else:
            markup = notice
    elif kind in {"market", "alignment", "mapping", "evaluation"}:
        metrics = '<div class="fow-skeleton-summary" aria-hidden="true">' + card * (4 if kind == "market" else 3) + '</div>'
        if kind == "market":
            tabs = '<div class="fow-skeleton-tabs" aria-hidden="true">' + line * 4 + '</div>'
            markup = metrics + toolbar + heading + tabs
            if view in {"Skills", "Roles and locations", "Qualifications", "PSF-AAI demand"}:
                markup += (notice if view == "Qualifications" else "") + chart_panel
        elif kind == "alignment":
            markup = '<div class="fow-skeleton-document">' + line * 2 + '</div>' + metrics + toolbar + chart_panel + disclosure + notice
        elif kind == "mapping":
            markup = '<div class="fow-skeleton-panel">' + heading + line + field
            if view == "selected":
                markup += disclosure + notice + field + field
            markup += '</div><div class="fow-skeleton-panel">' + heading + toolbar + field + '<div class="fow-skeleton-grid">' + chart + insight + '</div></div>' + disclosure
        else:
            markup = metrics + notice + '<div class="fow-skeleton-panel">' + heading + table + '</div>'
    elif kind == "review":
        markup = toolbar + table
    elif kind == "selector":
        markup = field
    elif kind == "quality":
        markup = '<div class="fow-skeleton-insight">' + heading + line * 4 + '</div>' + disclosure * 2 + heading + table
    elif kind == "settings":
        sections = []
        for control in controls or []:
            if control == "heading":
                sections.append([])
            elif control != "button" and sections:
                sections[-1].append(control)
        markup = ""
        note = '<div class="fow-skeleton-settings-note">' + line * 4 + '</div>'
        for index, fields in enumerate(sections):
            markup += '<div class="fow-skeleton-settings-section"><div class="fow-skeleton-heading">' + line + '</div>'
            markup += f'<div class="fow-skeleton-settings-fields fow-skeleton-settings-fields--{index}">'
            if index == 2:
                markup += note
            for control in fields:
                markup += f'<div class="fow-skeleton-field fow-skeleton-field--{control}">'
                markup += (note if control == "text" and index == 0 else "") + line + '<span class="fow-skeleton-control"></span></div>'
            markup += '</div></div>'
        markup += '<div class="fow-skeleton-field fow-skeleton-field--button">' + line + '<span class="fow-skeleton-control"></span></div>'
    elif kind in {"table", "heatmap", "file_preview"}:
        markup = table
    elif kind == "form":
        fields = controls if controls is not None else ["select"] * (len(columns) if columns is not None else 1)
        markup = '<div class="fow-skeleton-form" style="--fow-field-columns:' + str(field_columns) + '" aria-hidden="true">'
        for control in fields:
            if control == "heading":
                markup += '<div class="fow-skeleton-form-heading">' + line + '</div>'
            else:
                markup += '<div class="fow-skeleton-field fow-skeleton-field--' + control + '">' + line + '<span class="fow-skeleton-control"></span>'
                if view == "usability" and control == "select":
                    markup += '<div class="fow-skeleton-settings-note">' + line * 3 + '</div>'
                markup += '</div>'
        markup += '</div>'
    elif kind == "document":
        markup = '<div class="fow-skeleton-document" aria-hidden="true">' + line * rows + '</div>'
    elif kind in {"comparison", "pending"}:
        markup = '<div class="fow-skeleton-pending" aria-hidden="true">' + icon + '<div>' + line * 2 + '</div></div>'
    elif kind == "results":
        markup = (toolbar + '<div class="fow-skeleton-grid" aria-hidden="true"><div class="fow-skeleton-chart">'
                  + line * 7 + '</div><div class="fow-skeleton-insight">' + line * 5 + '</div></div>' + table)
    else:
        raise ValueError("Unknown loading layout.")
    sizing = f' style="--fow-skeleton-cards:{min(8, max(1, cards))}"' if cards is not None else ""
    variant = ' data-view="usability"' if view == "usability" else ''
    return f'<section class="fow-loading fow-loading--{kind}"{sizing}{variant} role="status" aria-busy="true" aria-label="Loading {kind} content">{markup}</section>'


@contextmanager
def loading_content(key, kind, *, cards=None, columns=None, rows=None, controls=None, field_columns=1, view=None, defer=False):
    """Replace a first-load wireframe with content at the same stable slot.

    Load data before calling the yielded function; render inside its returned
    container. Reruns retain the existing container and its widget state.
    With defer=True, keep the pending slot until rendering finishes; the page
    styles its new body as hidden while that pending slot is present.
    """
    host = st.container(key=key)
    ready = st.session_state.setdefault("_fow_loading_ready", {})
    pending = None if ready.get(key) else host.empty()
    if pending is not None:
        options = {"cards": cards, "columns": columns, "rows": rows}
        if controls is not None:
            options.update(controls=controls, field_columns=field_columns)
        if view is not None:
            options["view"] = view
        pending.html(_wireframe(kind, **options))
    rendered = False

    def content():
        nonlocal rendered
        rendered = True
        return (pending if pending is not None and not defer else host).container(key=f"{key}_body")

    try:
        yield content
    except Exception:
        ready.pop(key, None)
        if pending is not None and rendered and not defer:
            pending.empty()
        raise
    else:
        if rendered:
            ready[key] = True
        else:
            ready.pop(key, None)
    finally:
        if pending is not None and (not rendered or defer):
            pending.empty()


def load_data_with_skeleton(loader: Callable[[], T], *, height: int = 160, region=None) -> T:
    """Load data, optionally showing a skeleton in its reserved result container.

    Render the result into ``region``. Data-only calls stay invisible rather
    than inserting a temporary box between unrelated controls and content.
    """
    if region is None:
        return loader()
    with region.skeleton(height=height):
        return loader()
