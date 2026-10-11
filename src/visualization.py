import plotly.express as px
import plotly.graph_objects as go
from .analytics import counts

def bar(frame, x, y, title, color=None):
    fig = px.bar(frame, x=x, y=y, color=color, title=title, template="plotly_white")
    fig.update_layout(margin=dict(l=15, r=15, t=55, b=15))
    return fig

def distribution(frame, field, title, limit=20):
    data = counts(frame, field).head(limit)
    return bar(data, field, "count", title)

def heatmap(matrix, title):
    return px.imshow(matrix, aspect="auto", title=title, color_continuous_scale="Blues", labels={"color": "Count"}) if not matrix.empty else go.Figure().update_layout(title=title)
