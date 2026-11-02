"""Synthetic interaction checks; never load or alter research records."""
from dataclasses import replace
from unittest.mock import Mock

import pandas as pd
from streamlit.testing.v1 import AppTest
from streamlit.testing.v1.local_script_runner import LocalScriptRunner
from streamlit.runtime.scriptrunner_utils.script_requests import ScriptRequests

from src import ui
from test_result_views import result_tables


def _run_fragment(app, monkeypatch, widget_key):
    # AppTest defaults to full reruns; reproduce the browser's fragment request.
    state = app._session_state._state
    widget_id = state._key_id_mapper.get_id_from_key(widget_key, None)
    fragment_id = state._new_widget_state.widget_metadata[widget_id].fragment_id
    assert fragment_id
    original = LocalScriptRunner.request_rerun

    def request(runner, data):
        # LocalScriptRunner seeds a full rerun on construction; replace that
        # startup request so it cannot override the simulated browser event.
        if not runner._script_thread:
            runner._requests = ScriptRequests()
        return original(runner, replace(data, fragment_id_queue=[fragment_id], is_fragment_scoped_rerun=True))

    with monkeypatch.context() as patch:
        patch.setattr(LocalScriptRunner, "request_rerun", request)
        app.run(timeout=30)
    assert not app.exception and not app.error


def test_evidence_open_and_pagination_skip_sources_and_charts(monkeypatch):
    current = Mock(return_value=True)
    bundle = Mock(return_value=({}, {}))
    plotted = Mock()
    monkeypatch.setattr(ui, "current_analysis", current)
    monkeypatch.setattr(ui, "filtered_bundle", bundle)
    monkeypatch.setattr(ui, "chart", plotted)
    app = AppTest.from_string('''
import pandas as pd
import plotly.graph_objects as go
from src import ui
ui.current_analysis()
ui.filtered_bundle()
ui.chart(go.Figure())
ui.evidence_tables("Synthetic evidence", {"": pd.DataFrame({"skill": [f"skill {i}" for i in range(230)]})},
                   key="synthetic_evidence", note="Synthetic source note")
''').run(timeout=30)
    assert not app.exception and not app.dataframe
    app.session_state["synthetic_evidence"] = True
    _run_fragment(app, monkeypatch, "synthetic_evidence")
    assert current.call_count == bundle.call_count == plotted.call_count == 1
    panel = next(item for item in app.expander if item.label == "Synthetic evidence")
    assert any(item.value == "Synthetic source note" for item in panel.caption)
    assert panel.dataframe[0].value.skill.tolist() == [f"skill {i}" for i in range(100)]
    app.number_input(key="synthetic_evidence_page_0").set_value(3)
    app.session_state["synthetic_evidence"] = True
    _run_fragment(app, monkeypatch, "synthetic_evidence_page_0")
    assert current.call_count == bundle.call_count == plotted.call_count == 1
    assert app.number_input(key="synthetic_evidence_page_0").value == 3
    assert app.dataframe[0].value.skill.tolist() == [f"skill {i}" for i in range(200, 230)]
    app.session_state["synthetic_evidence"] = False
    _run_fragment(app, monkeypatch, "synthetic_evidence")
    assert not app.dataframe
    assert current.call_count == bundle.call_count == plotted.call_count == 1


def test_evidence_pagination_clamps_when_parent_supplies_smaller_snapshot():
    app = AppTest.from_string('''
import pandas as pd
import streamlit as st
from src.ui import evidence_tables
size = st.session_state.get("synthetic_size", 230)
evidence_tables("Synthetic evidence", {"": pd.DataFrame({"row": range(size)})}, key="synthetic_evidence")
''').run(timeout=30)
    app.session_state["synthetic_evidence"] = True
    app.run(timeout=30)
    app.number_input(key="synthetic_evidence_page_0").set_value(3)
    app.session_state["synthetic_evidence"] = True
    app.run(timeout=30)
    assert not app.exception and app.number_input(key="synthetic_evidence_page_0").value == 3
    app.session_state["synthetic_size"] = 115
    app.session_state["synthetic_evidence"] = True
    app.run(timeout=30)
    assert not app.exception and not app.error
    assert app.number_input(key="synthetic_evidence_page_0").value == 2
    assert app.dataframe[0].value.row.tolist() == list(range(100, 115))


def test_chart_cache_reuses_previous_order_and_invalidates_changed_counts(monkeypatch):
    builder = Mock(wraps=ui.ranked_bar)
    monkeypatch.setattr(ui, "ranked_bar", builder)
    monkeypatch.setattr(ui, "chart", Mock())
    app = AppTest.from_string('''
import pandas as pd
import streamlit as st
from src.ui import result_count_chart
frame = pd.DataFrame({"skill": ["alpha", "beta", "gamma"],
                      "job_ads": [st.session_state.get("synthetic_count", 5), 3, 1],
                      "job_ads_pct": [50., 30., 10.]})
before = frame.copy(deep=True)
result_count_chart(frame, "skill", "job_ads", "Synthetic demand", order=st.session_state.get("synthetic_order", "Highest demand"))
pd.testing.assert_frame_equal(frame, before)
''').run(timeout=30)
    assert not app.exception and builder.call_count == 1
    app.session_state["synthetic_order"] = "Lowest demand"
    app.run(timeout=30)
    assert not app.exception and builder.call_count == 2
    app.session_state["synthetic_order"] = "Highest demand"
    app.run(timeout=30)
    assert not app.exception and builder.call_count == 2
    app.session_state["synthetic_count"] = 6
    app.run(timeout=30)
    assert not app.exception and builder.call_count == 3


def test_family_heatmap_filter_redraws_only_its_fragment(monkeypatch):
    tables = result_tables()
    current = Mock(return_value=True)
    bundle = Mock(return_value=(tables, {"settings": {"emerging_min_jobs": 2}}))
    plotted = Mock()
    builder = Mock(wraps=ui.ranked_bar)
    monkeypatch.setattr(ui, "current_analysis", current)
    monkeypatch.setattr(ui, "filtered_bundle", bundle)
    monkeypatch.setattr(ui, "chart", plotted)
    monkeypatch.setattr(ui, "ranked_bar", builder)
    app = AppTest.from_string("from src.ui import research_page\nresearch_page('Job Market Analysis')").run(timeout=30)
    app.button_group(key="result_section").select("Roles and locations").run(timeout=30)
    assert not app.exception and not app.error
    reads, bundles, builds = current.call_count, bundle.call_count, builder.call_count
    plotted.reset_mock()
    app.multiselect(key="result_skill_family_heatmap_families").set_value(["analytics"])
    _run_fragment(app, monkeypatch, "result_skill_family_heatmap_families")
    assert (current.call_count, bundle.call_count, builder.call_count) == (reads, bundles, builds)
    plotted.assert_called_once()
    heatmap = plotted.call_args.args[0]
    assert heatmap.data[0].type == "heatmap"
    assert list(heatmap.data[0].x) == ["analytics"]
    assert set(heatmap.data[0].y) == {"sql", "collaboration", "c++"}
