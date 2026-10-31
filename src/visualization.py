import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from .analytics import counts
import streamlit as st
from textwrap import wrap
from html import escape
from math import ceil


def style_chart(fig):
    """Apply shared chart presentation without changing traces or calculations."""
    is_heatmap = any(trace.type == "heatmap" for trace in fig.data)
    margin = dict(l=20, r=20, t=65, b=35)
    if is_heatmap:
        ticktext = fig.layout.xaxis.ticktext or ()
        longest_tick = max((len(line) for label in ticktext for line in str(label).split("<br>")), default=12)
        margin = dict(l=70, r=110, t=75, b=min(225, max(135, 90 + 4 * longest_tick)))
    fig.update_layout(font=dict(family="Arial, sans-serif", size=13, color=st.get_option("theme.textColor")),
                      paper_bgcolor=st.get_option("theme.backgroundColor"),
                      plot_bgcolor=st.get_option("theme.backgroundColor"),
                      margin=margin,
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

def distribution(frame, field, title, limit=20, *, order="Highest demand"):
    if order not in ("Highest demand", "Alphabetical"):
        raise ValueError("Choose Highest demand or Alphabetical chart order.")
    data = counts(frame, field)
    data["_sort_label"] = data[field].astype(str).str.casefold()
    by, ascending = (["count", "_sort_label"], [False, True]) if order == "Highest demand" else (["_sort_label"], [True])
    data = data.sort_values(by, ascending=ascending, kind="stable").head(limit)
    # Horizontal bars keep category and competency names readable on narrow screens.
    data["_hover_label"] = data[field].map(_hover_text)
    fig = px.bar(data, x="count", y=field, orientation="h", title=title, custom_data=["_hover_label"],
                 labels={"count": "Count", field: field.replace("_", " ").capitalize()})
    fig.update_traces(hovertemplate="<b>%{customdata[0]}</b><br>Count: %{x:,d}<extra></extra>")
    if field == "status":
        colors = {"aligned": st.get_option("theme.primaryColor"), "partially aligned": st.get_option("theme.orangeColor"),
                  "not mapped": st.get_option("theme.redColor"), "unclassified": "#77838D"}
        fig.update_traces(marker_color=[colors.get(str(value).casefold(), "#77838D") for value in data[field]])
    fig.update_xaxes(**count_axis(data["count"].max() if not data.empty else 0), rangemode="tozero")
    fig.update_yaxes(autorange="reversed")
    fig.update_yaxes(tickmode="array", tickvals=data[field].tolist(),
                     ticktext=["<br>".join(escape(part) for part in wrap(str(value), 22, max_lines=2, placeholder="…")) for value in data[field]])
    fig.update_layout(height=max(300, 110 + 42 * len(data)))
    return fig


def ranked_bar(frame, label, value, title, *, order="Highest demand", limit=20):
    """Display already-aggregated advertisement counts without changing their units."""
    if order not in ("Highest demand", "Alphabetical", "Framework order"):
        raise ValueError("Choose Highest demand or Alphabetical chart order.")
    if not isinstance(limit, int) or limit < 1:
        raise ValueError("Chart limit must be a positive whole number.")
    data = frame.copy()
    numbers = pd.to_numeric(data[value], errors="coerce")
    if numbers.isna().any() or numbers.lt(0).any() or numbers.mod(1).ne(0).any():
        raise ValueError("Advertisement counts must be nonnegative whole numbers.")
    data[value] = numbers.astype(int)
    data["_sort_label"] = data[label].astype(str).str.casefold()
    by, ascending = ([value, "_sort_label"], [False, True]) if order == "Highest demand" else (["_sort_label"], [True])
    if order == "Framework order":
        by, ascending = ["framework_order", "_sort_label"], [True, True]
    data = data.sort_values(by, ascending=ascending, kind="stable").head(limit)
    data["_hover_label"] = data[label].map(_hover_text)
    custom = ["_hover_label"]
    hover = "<b>%{customdata[0]}</b><br>Job advertisements: %{x:,d}"
    percentage = next((field for field in ("job_ads_pct", "employer_demand_pct") if field in data), None)
    if percentage:
        custom.append(percentage)
        hover += "<br>Share of selected ads: %{customdata[1]:.1f}%"
    fig = px.bar(data, x=value, y=label, orientation="h", custom_data=custom,
                 title=title, labels={value: "Job advertisements", label: label.replace("_", " ").capitalize()})
    colors = [st.get_option("theme.primaryColor") if order == "Highest demand" and count == data[value].max() else "#71A89E" for count in data[value]]
    fig.update_traces(marker_color=colors, texttemplate="%{x:,d}", textposition="outside",
                      textfont=dict(color="#173B38"), cliponaxis=False,
                      hovertemplate=hover + "<extra></extra>")
    maximum = data[value].max() if not data.empty else 0
    fig.update_xaxes(**count_axis(maximum), range=[0, max(1, maximum * 1.18)], title="Job advertisements",
                     showgrid=False, zeroline=False)
    fig.update_yaxes(autorange="reversed", tickmode="array", tickvals=data[label].tolist(),
                     ticktext=data["_hover_label"].tolist(), title=None, showgrid=False)
    max_lines = max((value.count("<br>") + 1 for value in data["_hover_label"]), default=1)
    row_height = max(42, 18 * max_lines + 16)
    fig.update_layout(height=max(300, 115 + row_height * len(data)), showlegend=False,
                      margin=dict(l=20, r=45, t=65, b=35))
    return fig


def education_bar(frame):
    """Educational progression, rather than demand rank, determines the x axis."""
    data = frame.sort_values("level_order", kind="stable")
    fig = px.bar(data, x="job_ads", y="education_level", orientation="h", custom_data=["job_ads_pct"],
                 title="Education levels stated in advertisements",
                 labels={"education_level": "Education level", "job_ads": "Job advertisements"})
    fig.update_traces(marker_color="#71A89E", texttemplate="%{x:,d}", textposition="outside", cliponaxis=False,
                      hovertemplate="<b>%{y}</b><br>Job advertisements: %{x:,d}<br>Share of selected ads: %{customdata[0]:.1f}%<extra></extra>")
    maximum = data.job_ads.max() if not data.empty else 0
    fig.update_xaxes(**count_axis(maximum), range=[0, max(1, maximum * 1.18)], title="Job advertisements",
                     showgrid=False, zeroline=False)
    fig.update_yaxes(categoryorder="array", categoryarray=data.education_level.tolist(), autorange="reversed",
                     title=None, showgrid=False)
    fig.update_layout(height=max(300, 145 + 42 * len(data)), showlegend=False,
                      margin=dict(l=20, r=45, t=65, b=35))
    return fig


def heatmap(matrix, title, *, count_label="Count", share_matrix=None, row_denominators=None,
            share_label="Share within row group", denominator_label="Row-group advertisements"):
    if matrix.empty:
        return go.Figure().update_layout(title=title)
    display_matrix = matrix
    shares = None
    denominators = None
    if share_matrix is not None:
        shares = pd.DataFrame(share_matrix).reindex(index=matrix.index, columns=matrix.columns).fillna(0).astype(float)
        if shares.lt(0).any().any() or shares.gt(100).any().any():
            raise ValueError("Heatmap shares must be between 0 and 100 percent.")
        display_matrix = shares
        if row_denominators is not None:
            denominators = pd.to_numeric(pd.Series(row_denominators), errors="coerce").reindex(matrix.index).fillna(0)
    x_label = str(matrix.columns.name or "Category").replace("_", " ").capitalize()
    y_label = str(matrix.index.name or "Category").replace("_", " ").capitalize()
    color_label = share_label if shares is not None else count_label
    fig = px.imshow(display_matrix, aspect="auto", title=title, color_continuous_scale=st.get_option("theme.chartSequentialColors"),
                    labels={"x": x_label, "y": y_label, "color": color_label})
    if shares is not None:
        fig.update_coloraxes(cmin=0, cmax=100,
                            colorbar=dict(title=color_label, tickmode="linear", tick0=0, dtick=20,
                                          tickformat=".0f", ticksuffix="%"))
    else:
        fig.update_coloraxes(colorbar=count_axis(matrix.to_numpy().max()))
    fig.update_xaxes(type="category", tickmode="array", tickvals=matrix.columns.tolist(),
                     ticktext=[_hover_text(value) for value in matrix.columns], side="bottom",
                     tickangle=-45, automargin=True)
    fig.update_yaxes(type="category", tickmode="array", tickvals=matrix.index.tolist(),
                     ticktext=[_hover_text(value) for value in matrix.index])
    custom = []
    for row_index, row in enumerate(matrix.index):
        row_data = []
        for column_index, column in enumerate(matrix.columns):
            cell = [_hover_text(row), _hover_text(column)]
            if shares is not None:
                cell.extend([int(matrix.iat[row_index, column_index]), shares.iat[row_index, column_index]])
                if denominators is not None:
                    cell.append(int(denominators.iloc[row_index]))
            row_data.append(cell)
        custom.append(row_data)
    hover = escape(y_label) + ": %{customdata[0]}<br>" + escape(x_label) + ": %{customdata[1]}<br>"
    if shares is not None:
        hover += escape(count_label) + ": %{customdata[2]:,d}<br>" + escape(share_label) + ": %{customdata[3]:.1f}%"
        if denominators is not None:
            hover += "<br>" + escape(denominator_label) + ": %{customdata[4]:,d}"
    else:
        hover += escape(count_label) + ": %{z:,d}"
    fig.update_traces(customdata=custom, hovertemplate=hover + "<extra></extra>")
    label_space = 100 if len(matrix.columns) > 8 else 0
    fig.update_layout(height=min(1000, max(340, 170 + 32 * len(matrix)) + label_space))
    return fig
