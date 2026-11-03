"""Downloads contain the selected graph values; file generation waits for a click."""
from html import unescape, escape
import re

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from .reporting import export_csv


def _plain(value):
    return unescape(re.sub(r"<[^>]*>", " ", value)).strip() if isinstance(value, str) else value


def _axis_title(fig, axis, default):
    return _plain(getattr(fig.layout, axis).title.text or default)


def _custom_columns(trace):
    return [(int(index), _plain(label)) for label, index in re.findall(
        r"(?:^|<br>)([^<>:]+):\s*%\{customdata\[(\d+)\]", trace.hovertemplate or ""
    )]


def chart_table(fig):
    """Export the coordinates, counts and labelled hover values actually plotted."""
    rows = []
    for trace in fig.data:
        name = _plain(trace.name or "")
        custom = trace.customdata
        columns = _custom_columns(trace)
        if trace.type == "heatmap":
            x_label = _axis_title(fig, "xaxis", "Column")
            y_label = _axis_title(fig, "yaxis", "Row")
            if y_label == x_label:
                y_label += " (row)"
            color_label = _plain(fig.layout.coloraxis.colorbar.title.text or "Value")
            x_values = list(trace.x) if trace.x is not None else list(range(len(trace.z[0])))
            y_values = list(trace.y) if trace.y is not None else list(range(len(trace.z)))
            for y, values in enumerate(trace.z):
                for x, value in enumerate(values):
                    row = {y_label: _plain(y_values[y]), x_label: _plain(x_values[x]), color_label: value}
                    if custom is not None:
                        for index, label in columns:
                            row.setdefault(label, _plain(custom[y][x][index]))
                    rows.append(row)
        elif trace.type == "pie":
            rows.extend({"Series": name, "Category": _plain(label), "Value": value}
                        for label, value in zip(trace.labels, trace.values))
        else:
            x_values, y_values = getattr(trace, "x", None), getattr(trace, "y", None)
            if x_values is None or y_values is None:
                continue
            x_label = _axis_title(fig, "xaxis", "Value" if getattr(trace, "orientation", None) == "h" else "X")
            y_label = _axis_title(fig, "yaxis", "Category" if getattr(trace, "orientation", None) == "h" else "Value")
            if y_label == x_label:
                y_label += " (y)"
            for position, (x, y) in enumerate(zip(x_values, y_values)):
                row = {"Series": name, x_label: _plain(x), y_label: _plain(y)}
                if custom is not None:
                    for index, label in columns:
                        row.setdefault(label, _plain(custom[position][index]))
                rows.append(row)
    frame = pd.DataFrame(rows)
    if "Series" in frame and frame.Series.eq("").all():
        frame = frame.drop(columns="Series")
    return frame


def chart_html(fig, title, *, full_html=True, include_plotlyjs=True):
    """Preserve the complete figure and playback frames in a standalone HTML file."""
    exported = go.Figure(fig)
    exported.update_layout(title_text=title, title_x=.02, margin_t=max(65, fig.layout.margin.t or 0))
    return exported.to_html(include_plotlyjs=include_plotlyjs, full_html=full_html, auto_play=False,
                            config={"displaylogo": False, "responsive": True,
                                    "toImageButtonOptions": {"format": "png", "filename": chart_filename(title)}})


def chart_filename(title):
    return re.sub(r"[^a-z0-9]+", "-", title.casefold()).strip("-")[:100] or "research-chart"


def chart_downloads(fig, title, *, key):
    with st.container(horizontal=True, horizontal_alignment="right"):
        _chart_download_menu(fig, title, key=key)


def _chart_download_menu(fig, title, *, key):
    filename = chart_filename(title)
    with st.popover("Download graph", icon=":material/download:", key=f"{key}_downloads"):
        st.download_button("Graph data (CSV)", data=lambda: export_csv(chart_table(fig)),
                           file_name=f"{filename}.csv", mime="text/csv", key=f"{key}_csv",
                           icon=":material/table:", on_click="ignore", width="stretch")
        st.download_button("Interactive graph (HTML)", data=lambda: chart_html(fig, title),
                           file_name=f"{filename}.html", mime="text/html", key=f"{key}_html",
                           icon=":material/code:", on_click="ignore", width="stretch")
        st.caption("For a PNG image, use the camera button on the graph or in its downloaded HTML file.")


def chart_group_html(figures, title):
    parts = [chart_html(fig, name, full_html=False, include_plotlyjs=index == 0)
             for index, (name, fig) in enumerate(figures.items())]
    return f'<!doctype html><html><head><meta charset="utf-8"><title>{escape(title)}</title></head><body style="margin:24px">' + "".join(parts) + "</body></html>"


def chart_group_data(figures):
    return pd.concat([chart_table(fig).assign(Graph=name) for name, fig in figures.items()], ignore_index=True) if figures else pd.DataFrame()


def chart_group_downloads(figures, title, *, key):
    figures = {name: fig for name, fig in figures.items() if fig is not None}
    filename = chart_filename(title)
    with st.popover("Download section", icon=":material/download:", key=f"{key}_downloads", disabled=not figures):
        st.download_button("Section graphs (HTML)", data=lambda: chart_group_html(figures, title),
                           file_name=f"{filename}.html", mime="text/html", key=f"{key}_html",
                           icon=":material/code:", on_click="ignore", width="stretch")
        st.download_button("Section data (CSV)", data=lambda: export_csv(chart_group_data(figures)),
                           file_name=f"{filename}.csv", mime="text/csv", key=f"{key}_csv",
                           icon=":material/table:", on_click="ignore", width="stretch")
        st.caption("Includes the location and skill charts for the current region and city selection. Use each chart’s camera for PNG.")
