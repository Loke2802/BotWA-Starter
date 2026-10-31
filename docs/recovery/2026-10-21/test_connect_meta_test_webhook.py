"""Offline connection safety tests; only synthetic credentials and HTTP mocks."""

import importlib.util
import json
import sys
import time
from contextlib import nullcontext
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs

import httpx
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session


@pytest.fixture
def helper(monkeypatch):
    monkeypatch.setenv("LURI_OPS_SCOPED_USER_ID", "100000000000000001")
    monkeypatch.setenv(
        "LURI_OPS_PUBLIC_WEBHOOK_ID", "00000000-0000-4000-8000-000000000001"
    )
    folder = Path(__file__).parent
    monkeypatch.syspath_prepend(str(folder))
    spec = importlib.util.spec_from_file_location(
        "webhook_connector", folder / "connect_meta_test_webhook.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    return module


def metadata(helper):
    return {
        "is_valid": True,
        "app_id": helper.APP_ID,
        "type": "SYSTEM_USER",
        "user_id": helper.SCOPED_USER_ID,
        "expires_at": int(time.time()) + 60 * 86400,
        "scopes": list(helper.SCOPES),
    }


def test_debug_batch_has_only_read_subrequest_and_no_secrets_in_http_url(helper):
    requests = []
    token, secret = "synthetic-access-credential", "a" * 32

    def handler(request):
        requests.append(request)
        return httpx.Response(
            200, json=[{"code": 200, "body": json.dumps({"data": metadata(helper)})}]
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = helper.inspect_token(client, "v22.0", token, secret)
    assert result["passed"] is True
    request = requests[0]
    assert request.method == "POST"
    assert str(request.url) == "https://graph.facebook.com/v22.0/"
    assert token not in str(request.url) and secret not in str(request.url)
    assert request.headers["Authorization"] == f"Bearer {helper.APP_ID}|{secret}"
    batch = json.loads(parse_qs(request.content.decode())["batch"][0])
    assert len(batch) == 1 and batch[0]["method"] == "GET"
    assert batch[0]["relative_url"].startswith("debug_token?input_token=")
    assert token not in json.dumps(result) and secret not in json.dumps(result)


@pytest.mark.parametrize(
    "change",
    [
        {"app_id": "wrong-app"},
        {"is_valid": False},
        {"type": "USER"},
        {"user_id": "wrong-user"},
        {"expires_at": 0},
        {"expires_at": 1},
        {"scopes": ["whatsapp_business_management"]},
    ],
)
def test_incomplete_identity_scope_or_expiry_is_not_ready(helper, change):
    data = metadata(helper)
    data.update(change)
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                200, json=[{"code": 200, "body": json.dumps({"data": data})}]
            )
        )
    ) as client:
        assert (
            helper.inspect_token(client, "v22.0", "synthetic-token", "a" * 32)["passed"]
            is False
        )


@pytest.mark.parametrize(
    "override,expected", [(None, True), ("https://unrelated.invalid/callback", False)]
)
def test_preserves_unknown_existing_override(helper, override, expected):
    row = {
        "whatsapp_business_api_data": {"id": helper.APP_ID},
        "override_callback_uri": override,
    }
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"data": [row]})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = helper.inspect_subscription(client, "v22.0", "synthetic-token")
    assert result["safe_to_set_test_override"] is expected
    assert requests[0].method == "GET"
    assert requests[0].url.path == f"/v22.0/{helper.WABA_ID}/subscribed_apps"
    assert "unrelated.invalid" not in json.dumps(result)


def test_provider_error_redacts_body_and_keeps_numeric_code(helper):
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                400,
                json={
                    "error": {
                        "code": 190,
                        "message": "synthetic-sensitive-provider-data",
                    }
                },
            )
        )
    ) as client:
        payload, result = helper.safe_request(
            client, "GET", "https://graph.facebook.com/v22.0/"
        )
    assert payload is None and result["provider_error_code"] == 190
    assert "synthetic-sensitive-provider-data" not in json.dumps(result)


def test_remote_checks_stop_after_failed_introspection(helper, monkeypatch):
    monkeypatch.setattr(helper, "graph_version", lambda: "v22.0")
    monkeypatch.setattr(
        helper, "credentials", lambda _: ("synthetic-token", "a" * 32, "v" * 32)
    )
    monkeypatch.setattr(
        helper,
        "new_client",
        lambda: httpx.Client(
            transport=httpx.MockTransport(lambda _: httpx.Response(400))
        ),
    )
    monkeypatch.setattr(
        helper,
        "inspect_subscription",
        lambda *a: pytest.fail("queried after identity failure"),
    )
    assert helper.inspect_remote(None)["ready_to_connect"] is False


def test_default_preflight_does_not_decrypt_or_query_meta(helper, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["helper"])
    monkeypatch.setattr(
        helper,
        "snapshot",
        lambda: SimpleNamespace(status="draft", webhook_enabled=False),
    )
    monkeypatch.setattr(
        helper, "credentials", lambda _: pytest.fail("decrypted in default mode")
    )
    monkeypatch.setattr(
        helper, "inspect_remote", lambda _: pytest.fail("remote default")
    )
    helper.main()
    assert json.loads(capsys.readouterr().out)["ai_enabled"] is False


def test_service_commits_are_not_visible_until_final_commit(helper, tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'atomic.db'}")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE transition_check (id INTEGER)"))
    with helper.AtomicServiceSession(bind=engine) as session:
        session.execute(text("INSERT INTO transition_check VALUES (1)"))
        session.commit()
        with engine.connect() as other:
            assert (
                other.execute(
                    text("SELECT count(*) FROM transition_check")
                ).scalar_one()
                == 0
            )
        Session.commit(session)
    with engine.connect() as connection:
        assert (
            connection.execute(
                text("SELECT count(*) FROM transition_check")
            ).scalar_one()
            == 1
        )
    engine.dispose()


def test_failed_second_service_operation_rolls_back_first(helper, tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'rollback.db'}")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE transition_check (id INTEGER)"))
    with (
        pytest.raises(RuntimeError),
        helper.AtomicServiceSession(bind=engine) as session,
    ):
        session.execute(text("INSERT INTO transition_check VALUES (1)"))
        session.commit()
        raise RuntimeError("synthetic activation failure")
    with engine.connect() as connection:
        assert (
            connection.execute(
                text("SELECT count(*) FROM transition_check")
            ).scalar_one()
            == 0
        )
    engine.dispose()


@pytest.fixture
def connection_flow(helper, monkeypatch):
    changes = []
    writes = []
    monkeypatch.setattr(
        helper,
        "snapshot",
        lambda: SimpleNamespace(status="active", webhook_enabled=True),
    )
    monkeypatch.setattr(
        helper,
        "inspect_remote",
        lambda _: {
            "ready_to_connect": True,
            "subscription": {"override_matches_staging_test": False},
            "token": {"passed": True},
        },
    )
    monkeypatch.setattr(
        helper, "credentials", lambda _: ("synthetic-token", "a" * 32, "v" * 32)
    )
    monkeypatch.setattr(helper, "graph_version", lambda: "v22.0")
    monkeypatch.setattr(helper, "new_client", lambda: nullcontext(None))
    monkeypatch.setattr(
        helper, "set_receiving", lambda _, enabled: changes.append(enabled) or None
    )
    monkeypatch.setattr(
        helper,
        "public_security_checks",
        lambda *a: {"valid_signature": True, "negative_checks": True},
    )
    monkeypatch.setattr(
        helper,
        "subscribe_test_override",
        lambda *a: writes.append(True) or {"acknowledged": True},
    )
    monkeypatch.setattr(
        helper,
        "inspect_subscription",
        lambda *a: {"override_matches_staging_test": True},
    )
    return changes, writes


def test_success_only_enables_receiving_and_keeps_bot_ai_and_transport_off(
    helper, connection_flow
):
    changes, writes = connection_flow
    result = helper.connect()
    assert changes == [True] and writes == [True]
    assert result["status"] == "test_waba_webhook_connected"
    assert result["bot_status"] == "inactive"
    assert result["ai_enabled"] is False and result["transport"] == "disabled"
    assert result["messages_sent"] == 0
    assert result["general_app_callback_changed"] is False


def test_security_failure_disables_local_without_registering_meta(
    helper, connection_flow, monkeypatch
):
    changes, writes = connection_flow
    monkeypatch.setattr(
        helper, "public_security_checks", lambda *a: {"valid_signature": False}
    )
    assert helper.connect()["status"] == "public_security_check_failed_local_disabled"
    assert changes == [True, False] and writes == []


def test_unconfirmed_registration_disables_local_and_does_not_retry_post(
    helper, connection_flow, monkeypatch
):
    changes, writes = connection_flow
    monkeypatch.setattr(
        helper,
        "inspect_subscription",
        lambda *a: {"override_matches_staging_test": False},
    )
    assert helper.connect()["status"] == "subscription_not_confirmed_local_disabled"
    assert changes == [True, False] and writes == [True]


def test_existing_override_is_not_written_again(helper, connection_flow, monkeypatch):
    changes, writes = connection_flow
    monkeypatch.setattr(
        helper,
        "inspect_remote",
        lambda _: {
            "ready_to_connect": True,
            "subscription": {"override_matches_staging_test": True},
            "token": {"passed": True},
        },
    )
    assert helper.connect()["status"] == "test_waba_webhook_connected"
    assert changes == [True] and writes == []


def test_failed_remote_preflight_never_changes_local_or_remote(
    helper, connection_flow, monkeypatch
):
    changes, writes = connection_flow
    monkeypatch.setattr(helper, "inspect_remote", lambda _: {"ready_to_connect": False})
    assert helper.connect()["status"] == "connection_preflight_failed_no_changes"
    assert changes == [] and writes == []


def test_unexpected_failure_redacts_exception_and_disables_local(
    helper, connection_flow, monkeypatch
):
    changes, _ = connection_flow

    def failure(*_):
        raise SystemExit("synthetic-sensitive-exception")

    monkeypatch.setattr(helper, "public_security_checks", failure)
    result = helper.connect()
    assert changes == [True, False]
    assert result["rollback"] == "local_channel_disabled"
    assert "synthetic-sensitive-exception" not in json.dumps(result)


def test_register_uses_only_exact_waba_and_body_for_verify_token(helper):
    calls = []
    token, verify = "synthetic-token", "synthetic-verify-value"

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={"success": True})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        assert helper.subscribe_test_override(client, "v22.0", token, verify)[
            "acknowledged"
        ]
    request = calls[0]
    assert len(calls) == 1 and request.method == "POST"
    assert request.url.path == f"/v22.0/{helper.WABA_ID}/subscribed_apps"
    assert token not in str(request.url) and verify not in str(request.url)
    assert json.loads(request.content) == {
        "override_callback_uri": helper.CALLBACK,
        "verify_token": verify,
    }


def test_signed_checks_never_call_messages_endpoint(helper):
    calls = []

    def handler(request):
        calls.append(request)
        if request.method == "GET":
            return httpx.Response(403)
        if request.headers.get("X-Hub-Signature-256") not in (
            None,
            "sha256=" + "0" * 64,
        ):
            return httpx.Response(200, text="Signature valid")
        return httpx.Response(403)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        assert all(helper.public_security_checks(client, "a" * 32).values())
    assert len(calls) == 4
    assert all(request.url.host == "staging-api.kalivur.com" for request in calls)
    assert all("/messages" not in request.url.path for request in calls)


def test_transition_aborts_if_target_changed_before_lock(helper, monkeypatch):
    stamp = datetime.now(UTC)
    state = helper.Snapshot(
        stamp, "draft", False, "access-cipher", "app-cipher", "verify-cipher"
    )
    monkeypatch.setattr(helper, "AtomicServiceSession", lambda **kw: nullcontext(None))
    monkeypatch.setattr(helper, "correlation_context", nullcontext)
    monkeypatch.setattr(
        helper,
        "validate_target",
        lambda *a, **kw: (None, stamp + timedelta(seconds=1), True),
    )
    monkeypatch.setattr(
        helper,
        "SqlAlchemyWhatsAppConfigurationRepository",
        lambda _: SimpleNamespace(
            get_scoped=lambda *a, **kw: SimpleNamespace(
                public_webhook_id=helper.PUBLIC_ID
            )
        ),
    )
    monkeypatch.setattr(
        helper,
        "WhatsAppConfigurationService",
        lambda *a: pytest.fail("changed channel written"),
    )
    with pytest.raises(SystemExit, match="Channel changed"):
        helper.set_receiving(state, True)
