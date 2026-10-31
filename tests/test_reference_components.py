"""Reference-style controls retain real metrics and route exports to Reports."""
from unittest.mock import Mock

from src import ui
from test_result_views import result_app, result_tables


def test_export_action_opens_reports_without_changing_research_counts(monkeypatch):
    route = Mock()
    monkeypatch.setattr(ui.st, 'switch_page', route)
    app, _ = result_app(monkeypatch, result_tables())
    before = {metric.label: metric.value for metric in app.metric}
    app.button(key='results_export').click().run(timeout=30)
    assert not app.exception and not app.error
    route.assert_called_once_with('pages/14_Reports.py')
    assert {metric.label: metric.value for metric in app.metric} == before
    assert before['Selected job advertisements'] == '4'
    assert before['Distinct skills in charts'] == '3'
    assert before['Distinct phrases withheld'] == '1'
