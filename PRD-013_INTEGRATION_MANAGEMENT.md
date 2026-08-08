# PRD-013 Integration Management

Estado: implemented, pending CTO review.

PRD-001 a PRD-012 permanecen CLOSED. PRD-014 a PRD-022 permanecen NOT
STARTED.

## Alcance

PRD-013 administra conexiones externas tenant-scoped. BotWA/Luri es Source of
Truth de la definicion, configuracion administrativa allowlisted, credenciales
cifradas, lifecycle, health conocido y metadata operativa segura. Google Calendar
continua siendo Source of Truth de calendars, events y disponibilidad; no se
replican events ni payloads del proveedor.

El modelo prepara `integration_type` para `calendar`, `crm`, `erp` y
`custom_api`, pero el unico provider real v1 es `google_calendar`. Las unicas
capabilities son:

- `calendar.metadata.read`;
- `calendar.availability.read`.

No existen operaciones de escritura de events ni un endpoint generico de
ejecucion.

## Persistencia

La migracion `20260807_0015`, con `down_revision=20260807_0014`, crea:

- `integration_connection`: definicion tenant/bot-scoped, lifecycle, version,
  capabilities/configuration allowlisted y health actual;
- `integration_credential`: refresh token dentro de payload cifrado, separado de
  configuration y unico por conexion;
- `integration_health_check`: historial paginado con estado, safe error, tiempo y
  latencia, sin body externo ni secretos;
- `integration_oauth_state`: nonce hasheado, expiracion y consumo single-use para
  replay protection.

Las tablas incluyen FKs, constraints de lifecycle/type/provider/health,
uniqueness tenant-safe e indices para listing, provider/status, credential,
health y OAuth state. Alembic conserva un unico head.

## Lifecycle y health

Lifecycle administrativo:

- `draft`: permite configuracion funcional;
- `active`: permite name/description, pero bloquea cambios funcionales;
- `inactive`: conserva configuracion, credential e historial;
- `archived`: terminal.

Activar requiere provider, configuration y credential validos. La rotacion de
credential es una operacion separada. Los cambios funcionales incrementan
`version`.

Health es independiente del lifecycle:

- `unknown`;
- `healthy`;
- `degraded`;
- `unreachable`;
- `auth_error`.

El health check es on-demand, usa timeout explicito, no descarga events y
persiste solo resultados seguros.

## RBAC y aislamiento

Permisos:

- `integration.read`;
- `integration.create`;
- `integration.update`;
- `integration.activate`;
- `integration.deactivate`;
- `integration.archive`;
- `integration.credentials.update`;
- `integration.health.read`;
- `integration.health.check`.

Owner/admin reciben todos. Operator recibe read y health read/check. Viewer no
recibe permisos de integration por defecto. Platform admin debe usar una ruta
con organization explicita. Lookups normales usan `organization_id +
integration_id`; una referencia cross-tenant retorna 404 seguro. `bot_id` es
opcional y se valida contra la organizacion.

## API administrativa

- `POST /organizations/{organization_id}/integrations`;
- `GET /organizations/{organization_id}/integrations`;
- `GET /organizations/{organization_id}/integrations/{integration_id}`;
- `PATCH /organizations/{organization_id}/integrations/{integration_id}`;
- `POST .../{integration_id}/activate`;
- `POST .../{integration_id}/deactivate`;
- `POST .../{integration_id}/archive`;
- `PUT .../{integration_id}/credentials`;
- `GET .../{integration_id}/health`;
- `POST .../{integration_id}/health-check`;
- `POST .../{integration_id}/oauth/google/start`;
- `GET /integrations/oauth/google/callback`.

No existe DELETE, `/execute`, proxy generico ni endpoint de arbitrary HTTP.

## Credential security

Se reutiliza `SecretCipher`/Fernet. El refresh token se cifra antes de persistir,
puede rotarse y solo se descifra dentro de la frontera tecnica que invoca el
adapter. Configuration no admite tokens ni campos arbitrarios. La API nunca
devuelve credential plaintext.

El access token es efimero y no se persiste. El authorization code se intercambia
una sola vez y tampoco se persiste. Client ID/client secret y redirect URI son
configuracion server-side. No se registran tokens, Authorization headers, raw
Google bodies, stack traces, event content ni PII.

## OAuth Google

OAuth start requiere permiso administrativo y genera una URL con:

- `access_type=offline`;
- state JWT firmado y con expiracion;
- nonce aleatorio persistido solo como SHA-256;
- scopes minimos de Calendar List read-only y event free/busy.

El callback confia unicamente en state. Valida firma, expiracion, nonce,
single-use, tenant, integration y provider; consume el nonce antes del intercambio
para impedir replay aun si falla la red. Luego intercambia el code, cifra el
refresh token si Google lo entrega, valida health con el access token efimero y
retorna solo `{ "status": "connected" }`.

## Provider architecture

`IntegrationProviderRegistry` resuelve adapters. La aplicacion consume el
contrato `CalendarIntegrationAdapter`; no repite branching por provider.
`GoogleCalendarAdapter` implementa:

- authorization URL e intercambio/refresh OAuth;
- health minimo;
- Calendar List y metadata canonica;
- FreeBusy y busy intervals canonicos;
- timeouts y mapeo de 401/403/5xx/malformed/network errors.

Objetos Google crudos no salen del adapter y calendars/availability no se
persisten por defecto.

## Safe errors

Los resultados externos se reducen a codigos allowlisted:

- `INTEGRATION_AUTH_REQUIRED`;
- `INTEGRATION_AUTH_FAILED`;
- `INTEGRATION_UNREACHABLE`;
- `INTEGRATION_PROVIDER_ERROR`;
- `INTEGRATION_CONFIGURATION_INVALID`;
- `INTEGRATION_NOT_ACTIVE`;
- `INTEGRATION_CREDENTIAL_INVALID`;
- `OAUTH_STATE_INVALID`;
- `OAUTH_STATE_EXPIRED`;
- `OAUTH_STATE_REPLAYED`.

## Validacion

- suite completa con PostgreSQL PRD-012/013 habilitado: 678 passed, 1 skipped,
  1 warning;
- Google real smoke: SKIPPED sin credenciales explicitas;
- mypy: PASS, 354 source files;
- Ruff: PASS;
- PostgreSQL PRD-013 smoke: PASS;
- Alembic `0014 -> 0015 -> 0014 -> 0015`: PASS;
- Alembic head: `20260807_0015`.

El smoke PostgreSQL valida tablas migradas, conexion/credential/health
persistentes, cifrado real, lifecycle, aislamiento tenant, provider fake a traves
de persistencia real, nueva sesion y ausencia de plaintext.

## Google real smoke manual

El test `tests/integration/test_prd013_google_real_smoke.py` solo corre si existen
las cuatro variables de desarrollo requeridas para client ID, client secret,
redirect URI y refresh token. Deben inyectarse en el entorno seguro del proceso;
no se guardan en archivos, comandos compartidos ni logs. El flujo manual obtiene
el refresh token mediante OAuth start/callback y despues valida health y metadata
read-only. Este smoke no bloquea PRD-013 cuando no existen credenciales externas.

## Exclusiones

No se implementan CRM/ERP reales, Outlook, Sheets, Gmail, Zapier, Make, n8n, MCP,
webhooks genericos, arbitrary HTTP/code, event sync, calendar writes, booking,
marketplace, polling, Redis, Celery, circuit breaker ni PRD-014. No se modifica
ninguna responsabilidad del Core Automation Engine.
