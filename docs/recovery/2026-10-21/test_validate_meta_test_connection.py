"""Offline checks with synthetic credentials and a mock HTTP transport only."""

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest


@pytest.fixture
def checker(monkeypatch):
    folder = Path(__file__).parent
    monkeypatch.syspath_prepend(str(folder))
    spec = importlib.util.spec_from_file_location(
        "meta_connection_checker", folder / "validate_meta_test_connection.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # Do not change process-wide logging in the pytest process.
    monkeypatch.setattr(
        module, "logging", SimpleNamespace(CRITICAL=50, disable=lambda _: None)
    )
    return module


@pytest.fixture
def mock_provider(checker, monkeypatch):
    requests = []
    responses = [
        {"id": checker.EXPECTED_USER},
        {
            "data": [
                {"permission": s, "status": "granted"} for s in checker.REQUIRED_SCOPES
            ]
        },
        {
            "data": [
                {
                    "id": checker.EXPECTED_PHONE,
                    "display_phone_number": "+1 555-197-8260",
                }
            ]
        },
    ]
    token = "synthetic-credential-never-print"
    monkeypatch.setattr(checker, "get_settings", lambda: None)
    monkeypatch.setattr(
        checker,
        "EnvironmentSecretCipher",
        SimpleNamespace(
            from_settings=lambda _: SimpleNamespace(decrypt=lambda _: token)
        ),
    )
    real_client = httpx.Client

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=responses[len(requests) - 1])

    def client_factory(**kwargs):
        assert kwargs["follow_redirects"] is False
        assert kwargs["trust_env"] is False
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_client(**kwargs)

    monkeypatch.setattr(checker.httpx, "Client", client_factory)
    return requests, responses, token


def test_only_three_gets_exact_test_target_no_secret_in_url_or_report(
    checker, mock_provider
):
    requests, _, token = mock_provider
    report = checker.validate_with_meta("encrypted-placeholder", "v22.0")
    assert report["status"] == "meta_read_only_checks_passed"
    assert len(requests) == 3
    assert [r.url.path for r in requests] == [
        "/v22.0/me",
        "/v22.0/me/permissions",
        f"/v22.0/{checker.EXPECTED_WABA}/phone_numbers",
    ]
    for request in requests:
        assert request.method == "GET"
        assert request.url.host == "graph.facebook.com"
        assert token not in str(request.url)
        assert request.headers["Authorization"] == f"Bearer {token}"
    assert token not in json.dumps(report)
    assert report["expiration_validation"] == "not_performed"
    assert report["app_id_validation"] == "not_performed"


def test_identity_mismatch_stops_before_other_requests(checker, mock_provider):
    requests, responses, _ = mock_provider
    responses[0] = {"id": "wrong-user", "private_field": "must-not-print"}
    report = checker.validate_with_meta("encrypted-placeholder", "v22.0")
    assert len(requests) == 1
    assert report["expected_system_user_matches"] is False
    assert "must-not-print" not in json.dumps(report)
    assert report["observed_user_id"] is None


def test_identity_diagnostic_outputs_numeric_id_only(checker, mock_provider):
    requests, responses, _ = mock_provider
    responses[0] = {"id": "100000000000000002", "name": "synthetic-private-name"}
    report = checker.validate_with_meta("encrypted-placeholder", "v22.0")
    assert len(requests) == 1
    assert report["observed_user_id"] == "100000000000000002"
    assert report["expected_system_user_name_matches"] is False
    assert "synthetic-private-name" not in json.dumps(report)


def test_scoped_id_difference_requires_pinned_system_id_and_name(
    checker, mock_provider
):
    requests, responses, _ = mock_provider
    responses[0] = {
        "id": "100000000000000001",
        "name": "kalivur_staging_bot",
    }
    responses[1] = {
        "id": checker.EXPECTED_USER,
        "name": "kalivur_staging_bot",
        "system_user_id": 100000000000000001,
    }
    report = checker.validate_with_meta(
        "encrypted-placeholder", "v22.0", identity_only=True
    )
    assert report["status"] == "meta_system_user_identity_confirmed"
    assert len(requests) == 2
    assert requests[1].url.path == f"/v22.0/{checker.EXPECTED_USER}"


def test_matching_name_alone_does_not_bypass_pinned_identity(checker, mock_provider):
    requests, responses, _ = mock_provider
    responses[0] = {"id": "100000000000000001", "name": "kalivur_staging_bot"}
    responses[1] = {"id": checker.EXPECTED_USER, "name": "kalivur_staging_bot"}
    report = checker.validate_with_meta(
        "encrypted-placeholder", "v22.0", identity_only=True
    )
    assert report["status"] == "identity_not_confirmed_no_further_requests"
    assert len(requests) == 2


def test_missing_permission_does_not_claim_success(checker, mock_provider):
    _, responses, _ = mock_provider
    responses[1] = {
        "data": [{"permission": "whatsapp_business_management", "status": "declined"}]
    }
    report = checker.validate_with_meta("encrypted-placeholder", "v22.0")
    assert report["status"] == "meta_read_only_checks_incomplete"


def test_access_audit_never_claims_identity_confirmed(checker, mock_provider):
    requests, responses, _ = mock_provider
    responses.pop(0)
    report = checker.validate_with_meta(
        "encrypted-placeholder", "v22.0", access_only=True
    )
    assert len(requests) == 2
    assert [r.url.path for r in requests] == [
        "/v22.0/me/permissions",
        f"/v22.0/{checker.EXPECTED_WABA}/phone_numbers",
    ]
    assert report["expected_system_user_matches"] is None
    assert report["status"] == "meta_read_access_passed_identity_mapping_pending"
    assert report["app_id_validation"] == "not_performed"
    assert report["expiration_validation"] == "not_performed"
    assert report["messages_sent"] == report["mutations"] == 0


def test_wrong_phone_or_display_does_not_claim_success(checker, mock_provider):
    _, responses, _ = mock_provider
    responses[2]["data"][0]["display_phone_number"] = "+1 555-000-0000"
    report = checker.validate_with_meta("encrypted-placeholder", "v22.0")
    assert report["expected_phone_in_test_waba"] is True
    assert report["test_display_phone_matches"] is False
    assert report["status"] == "meta_read_only_checks_incomplete"


@pytest.mark.parametrize(
    "kind", ["exception", "redirect", "body_error", "invalid_json"]
)
def test_errors_and_redirects_do_not_disclose_provider_content(checker, kind):
    secret = "synthetic-sensitive-response"

    def handler(request):
        if kind == "exception":
            raise RuntimeError(secret)
        if kind == "redirect":
            return httpx.Response(
                302, headers={"Location": f"https://example.invalid/{secret}"}
            )
        if kind == "body_error":
            return httpx.Response(200, json={"error": {"message": secret}})
        return httpx.Response(200, text=secret)

    with httpx.Client(
        transport=httpx.MockTransport(handler), base_url="https://graph.facebook.com/"
    ) as client:
        payload, result = checker.safe_get(client, "me", {})
    assert payload is None
    assert secret not in json.dumps(result)


def test_transaction_closed_before_secret_read_or_remote_call(checker, monkeypatch):
    open_sessions = 0

    class FakeSession:
        def __enter__(self):
            nonlocal open_sessions
            open_sessions += 1
            return self

        def __exit__(self, *_):
            nonlocal open_sessions
            open_sessions -= 1

    monkeypatch.setattr(checker, "SessionLocal", FakeSession)
    monkeypatch.setattr(checker, "validate_target", lambda _: (None, None, True))
    monkeypatch.setattr(
        checker,
        "SqlAlchemyWhatsAppConfigurationRepository",
        lambda _: SimpleNamespace(
            get_scoped=lambda *args: SimpleNamespace(
                access_token_ciphertext="ciphertext", public_webhook_id="public-id"
            )
        ),
    )
    monkeypatch.setattr(
        checker, "get_settings", lambda: SimpleNamespace(whatsapp_api_version="v22.0")
    )
    assert checker.read_target() == ("ciphertext", "public-id", "v22.0")
    assert open_sessions == 0


def test_default_mode_makes_no_provider_call(checker, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["checker"])
    monkeypatch.setattr(
        checker, "read_target", lambda: ("ciphertext", "public-id", "v22.0")
    )
    monkeypatch.setattr(
        checker, "validate_with_meta", lambda *_: pytest.fail("unexpected remote call")
    )
    checker.main()
    assert json.loads(capsys.readouterr().out)["transport"] == "disabled"
