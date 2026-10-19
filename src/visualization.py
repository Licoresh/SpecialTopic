import plotly.express as px
import plotly.graph_objects as go
from .analytics import counts
import streamlit as st
from textwrap import wrap
from html import escape


def style_chart(fig):
    """Apply shared chart presentation without changing traces or calculations."""
    fig.update_layout(font=dict(family="Arial, sans-serif", size=13, color=st.get_option("theme.textColor")),
                      paper_bgcolor=st.get_option("theme.backgroundColor"),
                      plot_bgcolor=st.get_option("theme.backgroundColor"),
                      margin=dict(l=20, r=20, t=65, b=35),
                      title=dict(font=dict(size=17), x=.02, xanchor="left"),
                      legend=dict(orientation="h", y=-.2, x=0),
                      hoverlabel=dict(font_size=13))
    fig.update_xaxes(automargin=True, title_font_size=12)
    fig.update_yaxes(automargin=True, title_font_size=12)
    return fig

def bar(frame, x, y, title, color=None):
    fig = px.bar(frame, x=x, y=y, color=color, title=title, template="plotly_white")
    fig.update_layout(margin=dict(l=15, r=15, t=55, b=15))
    return fig

def distribution(frame, field, title, limit=20):
    data = counts(frame, field).head(limit)
    # Horizontal bars keep category and competency names readable on narrow screens.
    fig = px.bar(data, x="count", y=field, orientation="h", title=title,
                 labels={"count": "Count", field: field.replace("_", " ").capitalize()})
    fig.update_yaxes(autorange="reversed")
    fig.update_yaxes(tickmode="array", tickvals=data[field].tolist(),
                     ticktext=["<br>".join(escape(part) for part in wrap(str(value), 22, max_lines=2, placeholder="…")) for value in data[field]])
    fig.update_layout(height=max(300, 110 + 42 * len(data)))
    return fig

def heatmap(matrix, title):
    palette = st.get_option("theme.chartSequentialColors") or "Blues"
    return px.imshow(matrix, aspect="auto", title=title, color_continuous_scale=palette, labels={"color": "Count"}) if not matrix.empty else go.Figure().update_layout(title=title)
