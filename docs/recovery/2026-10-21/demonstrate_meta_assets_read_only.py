"""Video B: exact staging assets, read-only Graph calls and safe console output.

No DB writes, sends, callback changes or credential output. The existing token
introspection carries one GET subrequest inside a POST batch body; its actual
HTTP URL contains no credential. --read-meta is explicit; default is local only.
"""

import argparse
import json
import re

from connect_meta_test_webhook import (
    APP_ID,
    CALLBACK,
    PHONE_ID,
    WABA_ID,
    credentials,
    graph_version,
    inspect_remote,
    new_client,
    safe_request,
    snapshot,
)

EXPECTED_DISPLAY = "15551978260"


def exact_test_phone(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        return False
    matches = [
        row
        for row in payload["data"]
        if isinstance(row, dict) and row.get("id") == PHONE_ID
    ]
    return len(matches) == 1 and (
        re.sub(r"\D", "", str(matches[0].get("display_phone_number", "")))
        == EXPECTED_DISPLAY
    )


def inspect_assets(state):
    report = {"status": "video_b_checks_incomplete", "checks": {}}
    if state.status != "active" or not state.webhook_enabled:
        return report
    # snapshot() closed its DB transaction before this function makes any HTTP.
    remote = inspect_remote(state)
    checks = report["checks"]
    checks["app_token_scopes_expiry"] = remote.get("token", {}).get("passed") is True
    subscription = remote.get("subscription", {})
    checks["test_waba_subscription"] = subscription.get("app_subscribed") is True
    checks["exact_staging_callback"] = (
        subscription.get("override_matches_staging_test") is True
    )
    if not all(checks.values()):
        return report
    token, _, _ = credentials(state)
    with new_client() as client:
        payload, query = safe_request(
            client,
            "GET",
            f"https://graph.facebook.com/{graph_version()}/{WABA_ID}/phone_numbers",
            headers={"Authorization": f"Bearer {token}"},
            params={"fields": "id,display_phone_number", "limit": "25"},
        )
    checks["exact_test_phone_in_waba"] = exact_test_phone(payload)
    report["phone_query"] = query
    if all(checks.values()):
        report["status"] = "video_b_read_only_assets_verified"
        # Only fixed identifiers whose correspondence was validated are exposed.
        report["verified_assets"] = {
            "app_id": APP_ID,
            "waba_id": WABA_ID,
            "phone_number_id": PHONE_ID,
            "test_phone": "+1 555-197-8260",
            "callback": CALLBACK,
        }
    return report


def display(report):
    print("LURI — VIDEO B: VALIDACION DE ACTIVOS DE WHATSAPP")
    print("Staging | Empresa: Kalivur | Bot: Kalivur Marketing Pro")
    if report["status"] == "video_b_read_only_assets_verified":
        assets = report["verified_assets"]
        print(f"App Luri: {assets['app_id']} — token, permisos y vigencia VALIDADOS")
        print(f"Cuenta de prueba WABA: {assets['waba_id']} — acceso VALIDADO")
        print(f"Numero de prueba: {assets['test_phone']} — pertenece a ese WABA")
        print(f"Phone Number ID: {assets['phone_number_id']}")
        print("Suscripcion de Luri: VALIDADA")
        print("Callback especifico de staging: VALIDADO")
        print(assets["callback"])
        print("RESULTADO: activos de prueba verificados mediante consultas a Meta.")
    else:
        print("RESULTADO: comprobacion incompleta; no presentar como validada.")
        print(json.dumps(report, ensure_ascii=True))
    print("Solo lectura | Cambios: 0 | Mensajes enviados: 0 | IA: apagada")
    print("Credenciales cifradas; utilizadas en memoria y nunca mostradas.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--read-meta", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    state = snapshot()
    if not args.read_meta:
        print("Preflight local aprobado; no se hicieron consultas a Meta.")
        print("Para la demostracion de solo lectura, ejecutar con --read-meta.")
        return
    report = inspect_assets(state)
    if args.json:
        print(json.dumps(report))
    else:
        display(report)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        raise SystemExit(
            "Comprobacion incompleta; detalles privados omitidos"
        ) from None
