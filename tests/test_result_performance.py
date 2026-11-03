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


def test_psf_picker_reaches_later_occurrences_without_unbounded_options():
    app = AppTest.from_string('''
import pandas as pd
from src.ui import psf_mapping_review
skills = pd.DataFrame({
    "extraction_id": [f"occ-{i}" for i in range(230)],
    "source_id": [f"ad-{i}" for i in range(230)],
    "original_phrase": [f"Synthetic phrase {i}" for i in range(230)],
    "original_text": [f"Synthetic evidence {i}" for i in range(230)],
})
jobs = pd.DataFrame({"source_id": skills.source_id, "job_title": "Synthetic job"})
taxonomy = pd.DataFrame({"competency_id": ["TEST-1"], "competency_name": ["Synthetic skill"]})
empty = pd.DataFrame(columns=["extraction_id"])
psf_mapping_review(skills, jobs, taxonomy, empty, empty)
''').run(timeout=30)
    assert not app.exception and not app.error
    picker = app.selectbox(key="psf_review_occurrence_choice")
    assert len(picker.options) == 100 and picker.value is None
    app.number_input(key="psf_review_page").set_value(3).run(timeout=30)
    picker = app.selectbox(key="psf_review_occurrence_choice")
    assert not app.exception and len(picker.options) == 30
    picker.select_index(29).run(timeout=30)
    assert not app.exception and not app.error
    assert app.selectbox(key="psf_review_occurrence_choice").value == "occ-229"
    assert app.dataframe[0].value["Source ad ID"].tolist() == ["ad-229"]
    assert any("Synthetic evidence 229" in item.value for item in app.get("text"))
    app.text_input(key="psf_review_search").set_value("occ-229").run(timeout=30)
    assert not app.exception and not app.error
    assert len(app.selectbox(key="psf_review_occurrence_choice").options) == 1
    app.text_input(key="psf_review_search").set_value("no such occurrence").run(timeout=30)
    assert not app.exception and not app.error
    assert any("No skill occurrences match" in item.value for item in app.info)


def test_result_counts_reuse_analysis_revision_and_refresh_after_change(monkeypatch):
    tables = result_tables()
    tables["alignment_results"] = pd.DataFrame({"normalized_skill": ["sql"], "status": ["NOT MAPPED"]})
    tables["unmapped_skills"] = pd.DataFrame({"normalized_skill": ["sql"], "employer_skill": ["SQL"],
                                               "employer_demand_count": [2]})
    counted = Mock(wraps=ui.unmapped_chart_counts)
    monkeypatch.setattr(ui, "unmapped_chart_counts", counted)
    monkeypatch.setattr(ui, "current_analysis", lambda: True)
    monkeypatch.setattr(ui, "filtered_bundle", lambda: (tables, {"settings": {"emerging_min_jobs": 2}}))
    app = AppTest.from_string("from src.ui import research_page\nresearch_page('Unmapped / Emerging Skills')")
    app.session_state["_fow_loaded_bundle_revision"] = "synthetic-revision-1"
    app.run(timeout=30)
    assert not app.exception and not app.error
    assert counted.call_count == 1
    assert {item.label: item.value for item in app.metric}["Unmapped skill labels"] == "1"
    app.run(timeout=30)
    assert not app.exception and counted.call_count == 1
    tables["alignment_results"].loc[0, "status"] = "ALIGNED"
    app.session_state["_fow_loaded_bundle_revision"] = "synthetic-revision-2"
    app.run(timeout=30)
    assert not app.exception and not app.error and counted.call_count == 2
    assert {item.label: item.value for item in app.metric}["Unmapped skill labels"] == "0"


def test_psf_mapping_chart_aggregate_reuses_analysis_revision(monkeypatch):
    tables = result_tables()
    tables["psf_competency_demand"] = pd.DataFrame({"psf_competency": ["Programming"], "job_ad_count": [1]})
    tables["psf_mapping_reviews"] = pd.DataFrame(columns=["extraction_id"])
    reference = pd.DataFrame({"competency_id": ["TEST-1"], "competency_name": ["Programming"],
                              "job_role": ["Analyst"]})
    build = Mock(wraps=ui.psf_demand_tables)
    monkeypatch.setattr(ui, "psf_demand_tables", build)
    monkeypatch.setattr(ui.storage, "read_frame", lambda name: reference)
    monkeypatch.setattr(ui, "current_analysis", lambda: True)
    monkeypatch.setattr(ui, "filtered_bundle", lambda: (tables, {}))
    monkeypatch.setattr(ui, "psf_mapping_review", lambda *args: None)
    app = AppTest.from_string("from src.ui import research_page\nresearch_page('PSF Mapping')")
    app.session_state["_fow_loaded_bundle_revision"] = "synthetic-revision-1"
    app.run(timeout=30)
    assert not app.exception and not app.error and build.call_count == 1
    app.run(timeout=30)
    assert not app.exception and not app.error and build.call_count == 1
    app.session_state["_fow_loaded_bundle_revision"] = "synthetic-revision-2"
    app.run(timeout=30)
    assert not app.exception and not app.error and build.call_count == 2


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
    assert app.selectbox(key="result_roles_display").value == "Job titles"
    assert not app.multiselect
    app.selectbox(key="result_roles_display").select("Skills by occupational family").run(timeout=30)
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


def test_chart_presentation_cache_preserves_source_and_refreshes_changed_data(monkeypatch):
    import plotly.graph_objects as go
    monkeypatch.setattr(ui.st, "session_state", {"_fow_current_page": "Job Market Analysis"})
    drawn = Mock()
    heading = Mock()
    monkeypatch.setattr(ui.st, "plotly_chart", drawn)
    monkeypatch.setattr(ui.st, "subheader", heading)
    prepare = Mock(wraps=ui._prepare_chart)
    monkeypatch.setattr(ui, "_prepare_chart", prepare)
    source = go.Figure(go.Bar(x=[3, 1], y=["sql", "python"], orientation="h",
                             customdata=[[75], [25]], hovertemplate="%{customdata[0]}%"),
                       layout=dict(title="Synthetic demand"))
    before = source.to_json()
    ui.chart(source)
    initial = drawn.call_args.args[0].to_json()
    ui.chart(source)
    assert prepare.call_count == 1 and drawn.call_count == heading.call_count == 2
    assert drawn.call_args.args[0].to_json() == initial
    assert source.to_json() == before  # Headings and hover data must survive revisits.
    source.data[0].x = [4, 1]
    ui.chart(source)
    assert prepare.call_count == 2
    assert list(drawn.call_args.args[0].data[0].x) == [4, 1]
    assert drawn.call_args.args[0].data[0].hovertemplate == "%{customdata[0]}%"
    option = ui.st.get_option
    monkeypatch.setattr(ui.st, "get_option", lambda key: "#ffffff" if key == "theme.backgroundColor" else option(key))
    ui.chart(source)
    assert prepare.call_count == 3


def test_heatmap_cache_reuses_filters_and_invalidates_counts_and_denominators(monkeypatch):
    monkeypatch.setattr(ui.st, "session_state", {})
    builder = Mock(wraps=ui.heatmap)
    drawn = Mock()
    monkeypatch.setattr(ui, "heatmap", builder)
    monkeypatch.setattr(ui, "chart", drawn)
    matrix = pd.DataFrame([[2, 1], [1, 0]], index=["analyst", "engineer"], columns=["sql", "python"])
    totals = pd.Series([4, 2], index=matrix.index)
    def render():
        ui.result_heatmap(matrix, "Synthetic heatmap", share_matrix=matrix.div(totals, axis=0).mul(100),
                          row_denominators=totals)
    render()
    original = drawn.call_args.args[0].to_json()
    drawn.call_args.args[0].update_layout(title="Caller edit")
    render()
    assert builder.call_count == 1
    assert drawn.call_args.args[0].to_json() == original
    totals.iloc[0] = 5
    render()
    assert builder.call_count == 2
    matrix.iloc[0, 0] = 3
    render()
    assert builder.call_count == 3

def test_shared_payload_revision_avoids_redownload_and_detects_changes(monkeypatch):
    from src import supabase_store as backend
    state = {}
    revision = ['one']
    monkeypatch.setattr(backend, 'session_state', lambda: state)
    monkeypatch.setattr(backend, 'configuration', lambda: ('https://example.invalid', ''))
    monkeypatch.setattr(backend, 'state_version', lambda name, token: revision[0])
    request = Mock(side_effect=lambda *args, **kwargs: [{'payload': {'value': revision[0]}, 'updated_at': revision[0]}])
    monkeypatch.setattr(backend, '_request', request)
    clock = Mock(side_effect=[0, 16, 32, 48, 64])
    monkeypatch.setattr(backend, 'time', Mock(monotonic=clock))
    read = backend.read_state
    assert read('frame:test', 'test-token') == {'value': 'one'}
    assert read('frame:test', 'test-token') == {'value': 'one'}
    assert request.call_count == 1
    revision[0] = 'two'
    assert read('frame:test', 'test-token') == {'value': 'two'}
    assert request.call_count == 2
    backend.clear_read_cache()
    read('frame:test', 'test-token')
    assert request.call_count == 3
    read('frame:test', 'another-token')
    assert request.call_count == 4

def test_reports_expander_does_not_reload_shared_tables(monkeypatch):
    current = Mock(return_value=True)
    bundle = Mock(return_value=(result_tables(), {'settings': {}}))
    reads = Mock(return_value=pd.DataFrame())
    monkeypatch.setattr(ui, 'current_analysis', current)
    monkeypatch.setattr(ui, 'filtered_bundle', bundle)
    monkeypatch.setattr(ui.storage, 'read_frame', reads)
    monkeypatch.setattr(ui, 'corrections', lambda: pd.DataFrame())
    monkeypatch.setattr(ui, 'report_deliverables', lambda tables, meta, *, prepared: None)
    app = AppTest.from_string("from src.ui import research_page\nresearch_page('Reports')").run(timeout=30)
    assert not app.exception and not app.error
    initial_reads = reads.call_count
    assert initial_reads == 0
    app.session_state['individual_exports'] = True
    _run_fragment(app, monkeypatch, 'individual_exports')
    assert reads.call_count == len(ui.REPORT_AUXILIARY_TABLES)
    assert len(app.get('download_button')) > 0
    _run_fragment(app, monkeypatch, 'individual_exports')
    assert reads.call_count == len(ui.REPORT_AUXILIARY_TABLES)
    assert current.call_count == bundle.call_count == 1
