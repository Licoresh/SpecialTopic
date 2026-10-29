import plotly.express as px
import plotly.graph_objects as go
from .analytics import counts
import streamlit as st
from textwrap import wrap
from html import escape
from math import ceil


def style_chart(fig):
    """Apply shared chart presentation without changing traces or calculations."""
    fig.update_layout(font=dict(family="Arial, sans-serif", size=13, color=st.get_option("theme.textColor")),
                      paper_bgcolor=st.get_option("theme.backgroundColor"),
                      plot_bgcolor=st.get_option("theme.backgroundColor"),
                      margin=dict(l=20, r=20, t=65, b=35),
                      title=dict(font=dict(size=17), x=.02, xanchor="left"),
                      legend=dict(orientation="h", y=-.2, x=0),
                      hovermode="closest",
                      hoverlabel=dict(bgcolor="#173B38", bordercolor="#173B38",
                                      font=dict(color="#FFFFFF", size=13), align="left", namelength=-1))
    fig.update_xaxes(automargin=True, title_font_size=12)
    fig.update_yaxes(automargin=True, title_font_size=12)
    return fig

def _hover_text(value):
    return "<br>".join(escape(part) for part in wrap(str(value), 34))


def count_axis(maximum=0):
    """Keep indivisible counts on integer ticks, including after chart zooms."""
    return dict(tickmode="linear", tick0=0, dtick=max(1, ceil(maximum / 8)), tickformat=",d")


def bar(frame, x, y, title, color=None):
    data = frame.assign(_hover_label=frame[x].map(_hover_text))
    custom = ["_hover_label"]
    group = ""
    if color:
        data["_hover_group"] = frame[color].map(_hover_text)
        custom.append("_hover_group")
        group = "%{customdata[1]}<br>"
    fig = px.bar(data, x=x, y=y, color=color, title=title, template="plotly_white", custom_data=custom)
    is_count = y in ("job_ads", "employer_demand_count")
    value = "%{y:,d}" if is_count else "%{y}"
    fig.update_traces(hovertemplate="<b>%{customdata[0]}</b><br>" + group + escape(y.replace("_", " ").capitalize()) + ": " + value + "<extra></extra>")
    fig.update_layout(margin=dict(l=15, r=15, t=55, b=15))
    if y in ("job_ads", "employer_demand_count") and not frame.empty:
        fig.update_yaxes(**count_axis(frame[y].max()), rangemode="tozero")
    return fig

def distribution(frame, field, title, limit=20):
    data = counts(frame, field).head(limit)
    # Horizontal bars keep category and competency names readable on narrow screens.
    data["_hover_label"] = data[field].map(_hover_text)
    fig = px.bar(data, x="count", y=field, orientation="h", title=title, custom_data=["_hover_label"],
                 labels={"count": "Count", field: field.replace("_", " ").capitalize()})
    fig.update_traces(hovertemplate="<b>%{customdata[0]}</b><br>Count: %{x:,d}<extra></extra>")
    fig.update_xaxes(**count_axis(data["count"].max() if not data.empty else 0), rangemode="tozero")
    fig.update_yaxes(autorange="reversed")
    fig.update_yaxes(tickmode="array", tickvals=data[field].tolist(),
                     ticktext=["<br>".join(escape(part) for part in wrap(str(value), 22, max_lines=2, placeholder="…")) for value in data[field]])
    fig.update_layout(height=max(300, 110 + 42 * len(data)))
    return fig

def heatmap(matrix, title):
    palette = st.get_option("theme.chartSequentialColors") or "Blues"
    if matrix.empty:
        return go.Figure().update_layout(title=title)
    fig = px.imshow(matrix, aspect="auto", title=title, color_continuous_scale=palette, labels={"color": "Count"})
    fig.update_coloraxes(colorbar=count_axis(matrix.to_numpy().max()))
    return fig
