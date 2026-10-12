"""Authenticate direct page entries before importing the full workspace UI."""


def render_page(page_title: str) -> None:
    from .auth_ui import require_workspace_access

    require_workspace_access()

    # Delay analytical imports until the page has passed the access check.
    from .ui import render

    render(page_title)
