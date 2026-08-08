# PRD-013 Integration Management

Estado: CLOSED.

PRD-001 a PRD-013 y PRD-015 permanecen CLOSED. PRD-014 Dashboard y PRD-016 a
PRD-023 permanecen NOT STARTED.

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

El lifecycle del refresh token es explicito:

- si Google retorna uno nuevo, se cifra y reemplaza de forma atomica la credential de
  la misma integration y organizacion;
- si Google lo omite y ya existe una credential valida, se conserva sin
  reescribirla ni borrarla;
- si Google lo omite y no existe credential previa, el callback falla con
  `INTEGRATION_AUTH_REQUIRED`, no crea una credential vacia y no deja la
  integration falsamente conectada.

El consumo del nonce se confirma en una transaccion local antes de invocar al
provider. Por ello, un timeout, 5xx o fallo de persistencia posterior no permite
reutilizar el state. Credential, rotacion y health se confirman atomicamente y
cualquier fallo SQL ejecuta rollback y se reduce a un error seguro. El riesgo
residual aceptado es: el token externo puede haber sido emitido aunque falle la
persistencia local; el usuario debe reiniciar OAuth. No se implementa revocacion
compensatoria sin un contrato futuro explicito.

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

- cierre tecnico final: PR #20 merged;
- merge commit: `be52bbc49c6b34fc6b515e915564810068a74da3`;
- final review head: `beb3a6a01c5a983ab5d83a485f268dfc3202fa3b`;
- suite completa: 705 passed, 12 skipped, 2 warnings;
- pruebas focalizadas PRD-013: 39 passed;
- compatibilidad PRD-012/015: 18 passed;
- Google real smoke: SKIPPED sin credenciales explicitas;
- mypy: PASS, 374 source files;
- Ruff: PASS;
- Black: PASS, 374 files;
- `git diff --check`: PASS;
- PostgreSQL PRD-013 smoke: 1 passed; valida persistencia cifrada, nonce single-use,
  rollback real y aislamiento tenant;
- cadena Alembic: `20260807_0014 -> 20260807_0015 -> 20260808_0016`;
- Alembic head unico: `20260808_0016`.

El smoke PostgreSQL valida tablas migradas, conexion/credential/health
persistentes, cifrado real, lifecycle, aislamiento tenant, provider fake a traves
de persistencia real, nueva sesion y ausencia de plaintext.

## Google real smoke manual

El test `tests/integration/test_prd013_google_real_smoke.py` solo corre si existen
las cuatro variables de desarrollo requeridas para client ID, client secret,
redirect URI y refresh token. Deben inyectarse en el entorno seguro del proceso;
no se guardan en archivos, comandos compartidos ni logs. El flujo manual obtiene
el refresh token mediante OAuth start/callback y despues valida health y metadata
read-only. Este smoke es un gate operativo de habilitacion externa y no bloquea
el cierre de PRD-013 cuando no existen credenciales externas aprobadas.

Antes de habilitar Google Calendar en staging o produccion es obligatorio ejecutar
el smoke real con credenciales de desarrollo aprobadas y validar consent,
callback, refresh, Calendar List y FreeBusy. La ausencia actual de credenciales
mantiene ese smoke en `SKIPPED`; no autoriza habilitar la integracion externamente.

## Exclusiones

No se implementan CRM/ERP reales, Outlook, Sheets, Gmail, Zapier, Make, n8n, MCP,
webhooks genericos, arbitrary HTTP/code, event sync, calendar writes, booking,
marketplace, polling, Redis, Celery, circuit breaker ni PRD-014. No se modifica
ninguna responsabilidad del Core Automation Engine.
