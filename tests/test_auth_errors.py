"""Synthetic authentication failures only; no real accounts or network calls."""
from unittest.mock import Mock

import pytest
import requests
from streamlit.testing.v1 import AppTest

from src import supabase_store as backend


RAW_DETAIL = "SYNTHETIC_PRIVATE_RESPONSE password=secret-test token=private-test"


@pytest.fixture
def auth_post(monkeypatch):
    monkeypatch.setattr(backend, "configuration", lambda: ("https://synthetic-project.example.test", "synthetic-public-key"))
    request = Mock()
    monkeypatch.setattr(backend.requests, "post", request)
    return request


@pytest.mark.parametrize("status,payload,code", [
    (400, {"error_code": "invalid_credentials"}, "invalid_credentials"),
    (400, {"code": "email_not_confirmed"}, "email_not_confirmed"),
    (429, {"error_code": "over_request_rate_limit"}, "auth_rate_limited"),
    (401, {"code": "invalid_api_key"}, "auth_configuration_error"),
    (503, {}, "auth_unavailable"),
    (403, {"code": "unexpected_synthetic_provider_code"}, "auth_rejected"),
])
def test_sign_in_preserves_http_status_and_maps_safe_provider_error(auth_post, status, payload, code):
    response = Mock(status_code=status, ok=False, text=RAW_DETAIL)
    response.json.return_value = {**payload, "msg": RAW_DETAIL, "message": RAW_DETAIL}
    auth_post.return_value = response
    with pytest.raises(backend.SupabaseError) as caught:
        backend.sign_in(" synthetic@example.test ", " pass with spaces ")
    assert caught.value.status_code == status
    assert caught.value.code == code
    assert str(caught.value) == backend.AUTH_ERROR_MESSAGES[code]
    assert "SYNTHETIC_PRIVATE_RESPONSE" not in str(caught.value)
    assert auth_post.call_args.kwargs["json"] == {
        "email": "synthetic@example.test", "password": " pass with spaces "}
    auth_post.assert_called_once()


@pytest.mark.parametrize("exception,code", [
    (requests.exceptions.SSLError(RAW_DETAIL), "auth_certificate_error"),
    (requests.Timeout(RAW_DETAIL), "auth_timeout"),
    (requests.ConnectionError(RAW_DETAIL), "auth_connection_error"),
    (requests.RequestException(RAW_DETAIL), "auth_connection_error"),
])
def test_sign_in_transport_errors_do_not_blame_credentials_or_expose_details(auth_post, exception, code):
    auth_post.side_effect = exception
    with pytest.raises(backend.SupabaseError) as caught:
        backend.sign_in("synthetic@example.test", "synthetic-password")
    assert caught.value.code == code and caught.value.status_code is None
    assert str(caught.value) == backend.AUTH_ERROR_MESSAGES[code]
    assert RAW_DETAIL not in str(caught.value)


@pytest.mark.parametrize("payload", [[], None, {}, {"access_token": "test", "user": None},
                                     {"access_token": "test", "user": {}}])
def test_malformed_success_response_is_a_controlled_safe_error(auth_post, payload):
    auth_post.return_value = Mock(status_code=200, ok=True, json=Mock(return_value=payload))
    with pytest.raises(backend.SupabaseError) as caught:
        backend.sign_in("synthetic@example.test", "synthetic-password")
    assert caught.value.code == "auth_invalid_response"
    assert str(caught.value) == backend.AUTH_ERROR_MESSAGES["auth_invalid_response"]


def test_unreadable_auth_response_is_safe_and_preserves_http_status(auth_post):
    auth_post.return_value = Mock(status_code=502, ok=False, text=RAW_DETAIL,
                                  json=Mock(side_effect=ValueError(RAW_DETAIL)))
    with pytest.raises(backend.SupabaseError) as caught:
        backend.sign_in("synthetic@example.test", "synthetic-password")
    assert caught.value.status_code == 502 and caught.value.code == "auth_unavailable"
    assert RAW_DETAIL not in str(caught.value)
    auth_post.return_value = Mock(status_code=200, ok=True, text=RAW_DETAIL,
                                  json=Mock(side_effect=ValueError(RAW_DETAIL)))
    with pytest.raises(backend.SupabaseError) as caught:
        backend.sign_in("synthetic@example.test", "synthetic-password")
    assert caught.value.code == "auth_invalid_response"


def test_missing_auth_configuration_never_attempts_network(auth_post, monkeypatch):
    monkeypatch.setattr(backend, "configuration", lambda: ("https://synthetic-project.example.test", ""))
    with pytest.raises(backend.SupabaseError) as caught:
        backend.sign_in("synthetic@example.test", "synthetic-password")
    assert caught.value.code == "auth_not_configured"
    assert str(caught.value) == backend.AUTH_ERROR_MESSAGES["auth_not_configured"]
    auth_post.assert_not_called()


@pytest.mark.parametrize("source", ["Environment variable", ".env file", "Streamlit secrets", "Not configured"])
def test_connection_details_reports_origins_without_credentials(tmp_path, monkeypatch, source):
    monkeypatch.setattr(backend, "ROOT", tmp_path)
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_PUBLISHABLE_KEY", raising=False)
    monkeypatch.setattr(backend.st, "secrets", {})
    values = {"SUPABASE_URL": "https://synthetic-project.example.test/", "SUPABASE_PUBLISHABLE_KEY": "synthetic-private-test-key"}
    if source == "Environment variable":
        for name, value in values.items():
            monkeypatch.setenv(name, value)
    elif source == ".env file":
        (tmp_path / ".env").write_text("\n".join(f"{name}={value}" for name, value in values.items()), encoding="utf-8")
    elif source == "Streamlit secrets":
        monkeypatch.setattr(backend.st, "secrets", values)
    details = backend.connection_details()
    assert details == {"host": "Not configured" if source == "Not configured" else "synthetic-project.example.test",
                       "url_source": source, "key_source": source, "key_configured": source != "Not configured"}
    assert "synthetic-private-test-key" not in repr(details)


def test_connection_details_respects_mixed_setting_precedence(tmp_path, monkeypatch):
    monkeypatch.setattr(backend, "ROOT", tmp_path)
    monkeypatch.setenv("SUPABASE_URL", "https://environment.example.test")
    monkeypatch.delenv("SUPABASE_PUBLISHABLE_KEY", raising=False)
    (tmp_path / ".env").write_text("SUPABASE_URL=https://dotenv.example.test\nSUPABASE_PUBLISHABLE_KEY=dotenv-private-test-key", encoding="utf-8")
    monkeypatch.setattr(backend.st, "secrets", {"SUPABASE_URL": "https://secrets.example.test", "SUPABASE_PUBLISHABLE_KEY": "secrets-private-test-key"})
    assert backend.connection_details() == {"host": "environment.example.test", "url_source": "Environment variable",
                                             "key_source": ".env file", "key_configured": True}


def _login_app(monkeypatch):
    monkeypatch.setattr(backend, "configured", lambda: True)
    monkeypatch.setattr(backend, "connection_details", lambda: {
        "host": "synthetic-project.example.test", "url_source": ".env file",
        "key_source": "Environment variable", "key_configured": True})
    return AppTest.from_string("from src.auth_ui import login_page\nlogin_page()").run(timeout=30)


@pytest.mark.parametrize("code", ["invalid_credentials", "email_not_confirmed", "auth_connection_error", "auth_rate_limited"])
def test_login_displays_safe_auth_reason_instead_of_generic_credential_blame(monkeypatch, code):
    signer = Mock(side_effect=backend.SupabaseError(RAW_DETAIL, status_code=400, code=code))
    connection = Mock()
    monkeypatch.setattr(backend, "sign_in", signer)
    monkeypatch.setattr(backend, "check_connection", connection)
    app = _login_app(monkeypatch)
    panel = next(item for item in app.expander if item.label == "Sign-in connection")
    assert not panel.proto.expanded
    app.text_input[0].set_value("synthetic@example.test")
    app.text_input[1].set_value("synthetic-password")
    next(item for item in app.button if item.label == "Sign in").click().run(timeout=30)
    assert not app.exception
    assert [item.value for item in app.error] == [backend.AUTH_ERROR_MESSAGES[code]]
    assert RAW_DETAIL not in " ".join(item.value for item in app.error)
    assert "supabase_access_token" not in app.session_state
    connection.assert_not_called()


def test_team_access_failure_after_auth_does_not_blame_password_or_retain_tokens(monkeypatch):
    monkeypatch.setattr(backend, "sign_in", lambda *args: {
        "access_token": "synthetic-access-token", "refresh_token": "synthetic-refresh-token",
        "user": {"id": "synthetic-user", "email": "synthetic@example.test"}})
    monkeypatch.setattr(backend, "check_connection", Mock(side_effect=backend.SupabaseError(RAW_DETAIL)))
    app = _login_app(monkeypatch)
    app.text_input[0].set_value("synthetic@example.test")
    app.text_input[1].set_value("synthetic-password")
    next(item for item in app.button if item.label == "Sign in").click().run(timeout=30)
    assert not app.exception
    message = " ".join(item.value for item in app.error).casefold()
    assert "accepted" in message and "team" in message
    assert "check your email and password" not in message and "invalid credentials" not in message
    assert "synthetic_private_response" not in message
    assert "supabase_access_token" not in app.session_state
    assert "supabase_refresh_token" not in app.session_state
