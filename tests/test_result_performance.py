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


def test_cached_analysis_does_not_copy_source_snapshot_and_refreshes_changed_inputs(monkeypatch, tmp_path):
    monkeypatch.setattr(ui.st, "session_state", {"_current_analysis_signature": "synthetic-input-v1"})
    monkeypatch.setattr(ui.storage, "ROOT", tmp_path)
    revision = [1]
    reviews = pd.DataFrame({"extraction_id": ["synthetic"], "rationale": ["first review"]})
    monkeypatch.setattr(ui.storage, "frame_revision", lambda name: revision[0])
    reads = Mock(side_effect=lambda name: reviews.copy() if name == ui.REVIEW_TABLE else pd.DataFrame({"source_id": ["synthetic"]}))
    monkeypatch.setattr(ui.storage, "read_frame", reads)
    extracted = Mock(return_value=pd.DataFrame({"source_id": ["synthetic"], "original_text": ["Source evidence" * 1000]}))
    monkeypatch.setattr(ui, "current_extractions", extracted)
    build = Mock(return_value=({"counts": pd.DataFrame({"job_ads": [1]})}, {"sources": ["synthetic"]}))
    monkeypatch.setattr(ui, "analysis_bundle", build)
    cached = Mock(wraps=ui._session_cached_value)
    monkeypatch.setattr(ui, "_session_cached_value", cached)

    tables, metadata = ui.filtered_bundle()
    tables["counts"].iloc[0, 0] = 999
    metadata["sources"].append("caller mutation")
    tables, metadata = ui.filtered_bundle()
    assert tables["counts"].job_ads.tolist() == [1] and metadata["sources"] == ["synthetic"]
    assert build.call_count == extracted.call_count == 1
    assert sum(call.args[0] == "_fow_source_cache" for call in cached.call_args_list) == 1
    assert sum(call.args[0] == ui.REVIEW_TABLE for call in reads.call_args_list) == 2
    revision[0] = 2
    ui.filtered_bundle()
    reviews.loc[0, "rationale"] = "updated review"
    ui.filtered_bundle()
    assert build.call_count == extracted.call_count == 3


def test_review_queue_preparation_projects_job_metadata_without_losing_evidence(monkeypatch):
    monkeypatch.setattr(ui, "training_candidates", lambda root: pd.DataFrame())
    monkeypatch.setattr(ui, "training_taxonomy", lambda root: pd.DataFrame())
    jobs = pd.DataFrame({"source_id": ["synthetic-ad"], "url": ["https://example.invalid/job"],
                         "job_title": ["Synthetic analyst"], "company": ["Synthetic employer"],
                         "original_text": ["Evidence retained in its source table" * 1000]})
    before = jobs.copy(deep=True)
    def read(name, **kwargs):
        if name == "extractions_original":
            return pd.DataFrame({"original_phrase": ["Python"], "normalized_phrase": ["python"],
                                 "source_type": ["jobs"], "source_id": ["synthetic-ad"]})
        if name == "cleaned_jobs":
            assert kwargs["columns"] == ["source_id", "url", "job_title", "company"]
            return jobs[kwargs["columns"]].copy()
        return pd.DataFrame()
    monkeypatch.setattr(ui.storage, "read_frame", read)
    candidates, _ = ui._build_manual_review_data()
    assert candidates.iloc[0].source_url == jobs.iloc[0].url
    assert candidates.iloc[0].job_title == "Synthetic analyst"
    assert candidates.iloc[0].company == "Synthetic employer"
    assert candidates.iloc[0].original_text == ""  # Resolved for the displayed page, not every queue occurrence.
    pd.testing.assert_frame_equal(jobs, before)


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
