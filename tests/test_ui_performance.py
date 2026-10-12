"""Session-local performance cache tests; synthetic values only."""
from streamlit.testing.v1 import AppTest


def test_session_cache_reuses_derived_values_without_leaking_mutations():
    app = AppTest.from_string(
        """
import streamlit as st
from src.ui import _session_cached_value
st.session_state.setdefault('synthetic_loads', 0)
def loader():
    st.session_state.synthetic_loads += 1
    return {'rows': []}
value = _session_cached_value('synthetic_cache', 'same-inputs', loader)
value['rows'].append('per-render mutation')
st.session_state.synthetic_rows = len(value['rows'])
"""
    ).run()
    assert not app.exception
    assert app.session_state["synthetic_loads"] == 1
    app.run()
    assert not app.exception
    assert app.session_state["synthetic_loads"] == 1
    assert app.session_state["synthetic_rows"] == 1
