# PRD-017 Audit Log v1

**Estado:** IMPLEMENTED — PENDING CTO REVIEW

**Alembic revision:** `20260808_0018`

## Objetivo y alcance

PRD-017 incorpora un ledger administrativo tenant-scoped y append-only en
PostgreSQL. Responde quién realizó qué acción administrativa exitosa, cuándo y
sobre qué recurso. Cada evento conserva actor, rol efectivo, acción, recurso,
timestamp, correlación UUID opcional y metadata mínima tipada y allowlisted.

El módulo Audit es independiente e incluye contratos, `AuditWriter`, repositorio
SQLAlchemy/PostgreSQL, `AuditQueryService`, API read-only, cursor keyset firmado,
RBAC, observabilidad y pruebas PostgreSQL reales.

## Non-goals y fronteras

Audit no es application/technical logging, Analytics, event sourcing, event bus,
message history, domain history, SIEM ni payload archive. V1 no incluye denials,
failed operations, auth failures, IP/User-Agent, full text, export, frontend,
scheduler, Kafka, Redis, Celery, retention automática, hash chains, backfill ni
PRD-018.

Los historiales `conversation_management_event`, `handoff_event`, `handoff_cycle`,
`business_calendar_audit_event`, Automation receipts/executions e Integration/
Core events conservan su finalidad y no se convierten en Audit genérico.

## Frontera histórica

Audit empieza con PRD-017. No fabrica eventos anteriores desde domain histories,
timestamps, changelogs ni receipts. **Pre-PRD-017 audit history is incomplete by
design and is not fabricated.**

## Esquema `audit_event`

La única tabla nueva contiene `id UUID`, `organization_id` FK, `actor_type`,
`actor_user_id` FK nullable, `actor_role` nullable, `action`, `resource_type`,
`resource_id UUID` nullable sin FK polimórfica, `result`, `metadata JSONB`,
`correlation_id UUID` nullable y `occurred_at`/`created_at` como `TIMESTAMPTZ`.
Las FKs no usan cascade ni `SET NULL`.

Actor types: `user`, `system`, `automation`. Un usuario requiere UUID real y
snapshot del rol canónico (`viewer`, `operator`, `organization_admin`,
`organization_owner`, `platform_admin`); no guarda nombre/email. Platform Admin
sigue siendo `user` y el evento usa la organización objetivo. System/Automation
requieren usuario y rol nulos. `organization.created` usa `system` porque el
bootstrap carece de usuario real.

`result` solo permite `success`. No hay permiso `audit.write`, mutation service ni
API UPDATE/DELETE/PATCH/PUT. Append-only es una garantía de application layer y
del permissions model DB vigente, no contra SQL manual de un DBA.

## Catálogos allowlisted

- Organization: `organization.created`, `organization.updated`,
  `organization.deactivated`.
- User/Access: `user.created`, `user.updated`, `user.deactivated`,
  `user.role_changed`, `user.password_changed`.
- Bot: `bot.created`, `bot.updated`, `bot.activated`, `bot.deactivated`.
- Conversation: `conversation.closed`, `conversation.reopened`,
  `conversation.archived`.
- Handoff: `handoff.requested`, `handoff.claimed`, `handoff.released`,
  `handoff.transferred`, `handoff.resolved`, `handoff.returned_to_bot`.
- Automation: `automation.created`, `automation.updated`,
  `automation.activated`, `automation.deactivated`, `automation.archived`,
  `automation.retry_requested`.
- Integration: `integration.created`, `integration.updated`,
  `integration.activated`, `integration.deactivated`, `integration.archived`,
  `integration.credentials_rotated`.
- Business Calendar: `business_calendar.created`, `business_calendar.updated`,
  `business_calendar.activated`, `business_calendar.deactivated`,
  `business_calendar.archived`.

Resource types: `organization`, `user`, `bot`, `conversation`, `handoff`,
`automation`, `integration`, `business_calendar`. Analytics no forma parte de v1.

## `AuditWriter`, atomicidad e idempotencia

`AuditWriter.append(AuditEventDraft)` usa la `Session` existente, adjunta el
evento y nunca hace commit ni abre otra transacción. El application service es
dueño de commit/rollback. Mutación y audit se confirman juntos; un fallo del
audit revierte la mutación y un rollback funcional no deja evento huérfano. Se
reutiliza el timestamp semántico cuando ya existe.

Audit sigue la idempotencia funcional: si un replay no ejecuta otra vez la acción,
no genera otro evento. No tiene idempotency engine propio.

## Metadata, PII y secretos

La metadata se crea server-side con Pydantic `extra="forbid"` usando únicamente
`EmptyMetadata`, `ChangedFieldsMetadata`, `StatusTransitionMetadata`,
`RoleAssignmentMetadata` o `CredentialRotationMetadata`. Solo admite nombres de
campo, estados y roles allowlisted o `credential_changed=true`.

No acepta dict arbitrario, request crudo ni snapshots. Prohíbe nombre, email,
teléfono, texto, descripción/reason libre, customer/provider IDs o payloads,
password/hash, tokens, OAuth code/state, API/client/webhook/HMAC secrets, claves,
ciphertext, credenciales e `Idempotency-Key` cruda.

`correlation_id` es UUID nullable. Reutiliza IDs internos seguros como inbound
receipt o correlación de Business Calendar; no copia headers ni IDs externos y
no introduce middleware global.

## Integraciones de dominio

- Organization, User/RBAC y Bot escriben Audit antes de su mismo commit.
- Conversation conserva su history y agrega Audit para transiciones manuales y
  auto-reopen. Auto-reopen usa `system` y el receipt UUID.
- Handoff conserva events/cycles y audita request/claim/release/transfer/resolve/
  return; request de Automation usa `automation`. No guarda reply ni reason libre.
- Automation audita definición y retry manual, no workers, claims, attempts,
  receipts, leasing, heartbeat ni automatic retry.
- Integration audita administración y credential rotation con boolean seguro.
  Health checks y OAuth callback quedan excluidos.
- Business Calendar conserva `business_calendar_audit_event` y hace dual-write
  genérico en la misma transacción, sin duplicado en replay idempotente.
- PRD-016 GET/CSV conserva su contrato read-only: Analytics export queda excluido.
- Denials, failed operations y safe cross-tenant 404 no se auditan.

## Query API, RBAC y tenant isolation

`GET /organizations/{organization_id}/audit-events` acepta filtros opcionales
`actor_user_id`, `action`, `resource_type`, `resource_id`, `from`, `to`, `cursor`
y `limit`.

- UTC timezone-aware; `to` exclusivo.
- Default últimos 30 días; máximo 366; `from < to`.
- Orden `occurred_at DESC, id DESC`.
- Cursor opaco firmado HMAC con timestamp e id; no offset.
- Página default 50, máximo 200.
- Un único SELECT scoped, sin JOIN/N+1 ni lookup de email/nombre.
- Respuesta sin `created_at` ni PII.

`audit.read` corresponde a Organization Admin, Organization Owner y Platform
Admin; Viewer/Operator no. Platform Admin requiere organización explícita. No hay
endpoint global y toda query conserva `organization_id`, incluso con filtros de
actor/recurso. Leer Audit no produce otro audit event.

## PostgreSQL, observabilidad y errores

Índices: `(organization_id, occurred_at DESC, id DESC)`, organization/action,
organization/actor y organization/resource/UUID, todos con timestamp. No hay GIN,
full text ni correlation index sin query real. El fixture de 10.000 eventos
confirma un SELECT O(1) para first page, action, resource y next cursor.

Métricas: `audit_events_written_total`, `audit_write_failures_total`,
`audit_query_requests_total`, `audit_query_duration_seconds`, solo con labels
`operation`/`result` de baja cardinalidad.

Códigos seguros: `AUDIT_INVALID_RANGE`, `AUDIT_RANGE_TOO_LARGE`,
`AUDIT_INVALID_CURSOR`, `AUDIT_INVALID_FILTER`, `AUDIT_FORBIDDEN` y
`AUDIT_UNAVAILABLE`; nunca exponen SQL, tablas, stack, IDs cross-tenant ni
metadata/excepciones internas.

## Retención

PRD-017 v1 defines no automatic retention policy. No hay TTL/worker ni promesa
de conservación indefinida.

## Validación

- focused PRD-017: 12 passed;
- PostgreSQL PRD-017: 3 passed;
- full pytest: 738 passed, 18 skipped, 2 warnings;
- fixture PostgreSQL 10.000 events: PASS, cuatro queries O(1);
- mypy: PASS — 415 source files;
- Ruff: PASS;
- Black: PASS — 415 files;
- `git diff --check`: PASS;
- Alembic: `20260808_0018 (head)`, single head;
- migration cycle `0017 → 0018 → 0017 → 0018`: PASS.

## PRD-018 boundary

PRD-018 Plans and Limits permanece NOT STARTED. PRD-017 no implementa planes,
límites, billing ni ningún alcance de PRD-018.
