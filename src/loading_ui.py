"""Skeletons scoped to data fetches that may delay an otherwise visible page."""

from collections.abc import Callable
from typing import TypeVar

import streamlit as st

T = TypeVar("T")


def load_data_with_skeleton(loader: Callable[[], T], *, height: int = 160) -> T:
    """Show a compact placeholder only while the enclosed data load is running.

    Keep page layout and controls outside this context so revisiting a page or
    rerunning a widget never replaces its already-rendered UI with a wireframe.
    Streamlit delays the skeleton briefly, so cached/fast reads do not flash.
    """
    with st.skeleton(height=height):
        return loader()
