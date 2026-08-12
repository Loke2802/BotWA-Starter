# PRD-018 Plans and Limits v1

**Estado:** IMPLEMENTED — PENDING CTO REVIEW

## Objetivo

PRD-018 define qué capacidades y cuántos recursos operativos puede usar actualmente
una `Organization`. La Organization es el scope comercial y tenant canónico. El
sistema es interno, PostgreSQL-only y no introduce Billing.

## Alcance

- catálogo técnico de planes no mutable por API;
- asignación actual 1:1 por Organization;
- entitlements booleanos;
- límites duros calculados desde Sources of Truth operacionales;
- enforcement en application services;
- lectura tenant-scoped del plan efectivo;
- cambio administrativo con optimistic concurrency;
- Audit PRD-017 en la misma Session/transacción;
- locking PostgreSQL por Organization para serializar cambio de plan y consumo.

## PRD-018 vs PRD-019

PRD-018 no contiene subscription, checkout, invoice, renewal, billing cycle,
provider de pago, pricing, currency, trial, overage ni metered usage. Tampoco define
cuotas de mensajes. Todo ese alcance permanece exclusivamente en PRD-019, que
continúa `NOT STARTED`.

RBAC autoriza quién puede ejecutar una operación; Plan determina si la Organization
tiene la capacidad comercial. Analytics, Audit, Rate Limiting y Billing conservan
sus propios Sources of Truth.

## Persistencia y migración

Alembic `20260810_0019`, descendiente único de `20260808_0018`, crea solo:

### `plan_definition`

- `id` UUID PK;
- `plan_code` estable, único y no nulo;
- `display_name` no nulo;
- `status`: `active | retired`;
- `configuration` JSONB no nulo;
- timestamps timezone-aware.

Un plan retirado no acepta nuevas asignaciones, pero conserva el comportamiento de
assignments existentes. No existe delete físico por API ni CRUD público del catálogo.

### `organization_plan_assignment`

- `organization_id` UUID PK/FK;
- `plan_definition_id` UUID FK no nulo;
- `version > 0`;
- `assigned_by_user_id` nullable;
- timestamps timezone-aware.

La FK 1:1 es el único Source of Truth del plan vigente. La ausencia de assignment
es una violación de invariantes y nunca activa fallback silencioso.

## Default bootstrap y backfill

La migración crea de forma determinista el plan técnico `default` con todas las
features habilitadas y todos los límites `unlimited`. Cada Organization existente
recibe exactamente un assignment versión 1 sin fabricar Audit histórico.

`OrganizationService.create` crea Organization + assignment default + Audit
`organization.created` en la misma unidad de trabajo. El bootstrap no añade un
evento `plan.assigned` redundante.

## Configuración cerrada

`PlanConfiguration` usa Pydantic `extra="forbid"` y contiene exclusivamente
`features` y `limits`.

Features v1:

- `analytics`;
- `analytics_export`;
- `audit`;
- `integrations`;
- `automations`;
- `human_handoff`;
- `business_calendar`;
- `knowledge`;
- `whatsapp_configuration`.

Límites v1:

- `max_active_bots`;
- `max_active_users`;
- `max_integrations`;
- `max_automations`;
- `max_business_calendars`;
- `max_whatsapp_configurations`;
- `max_knowledge_entries`.

Cada límite es una unión discriminada:

```json
{"kind": "limited", "value": 3}
```

o:

```json
{"kind": "unlimited"}
```

`limited.value = 0` significa capacidad explícitamente nula. No existen `-1`,
`null`, cero mágico ni contadores derivados.

## Semántica de consumo

- Bots: `status = active`; crear inactive no consume, activar sí.
- Users: `status = active`; create activo consume, inactive libera.
- Integrations: `status != archived`.
- Automations: `status != archived`.
- Business Calendars: `status != archived`.
- WhatsApp configurations: todo registro existente; delete físico libera.
- Knowledge entries: `status != archived`.

Los counts se ejecutan con `COUNT` SQL directo sobre el SoT operacional. No se usa
Analytics, Audit, `usage_counter`, caché global, Redis ni columnas denormalizadas.
Los índices compuestos Organization/status añadidos para Bot y User completan el
shape de sus queries; los demás recursos ya disponían de índices apropiados.

## Enforcement

`PlanEnforcementService` expone contratos tipados equivalentes a
`require_feature`, `require_capacity` y `require_consuming_action`. No abre Session,
no hace commit y no conoce HTTP.

El orden de las mutaciones consuming es RBAC, tenant/Organization, lifecycle
activo, `SELECT Organization FOR UPDATE`, assignment, feature, count, mutación,
Audit y commit. El lock vive en la misma Session hasta commit/rollback y serializa:

- dos consumos concurrentes del último slot;
- cambio/downgrade de plan contra create/activate concurrente.

No se usan advisory locks, isolation global serializable, slots ni counters.

## Lifecycle

### Upgrade

Entra en vigor después del commit. La siguiente operación observa inmediatamente
los nuevos entitlements y límites.

### Downgrade y over-limit

El downgrade siempre puede completarse y nunca borra, archiva o desactiva recursos.
`current == limit` produce `reached=true, over_limit=false`; `current > limit`
produce ambos en `true`. Nuevas acciones consuming quedan bloqueadas; las acciones
reducing permanecen disponibles.

### Retiro de feature

Bloquea create/activate/publish/request nuevos, pero no rompe workers ni runtime,
no cierra handoffs existentes y permite deactivate/archive/delete para evitar
lock-in. En particular, Automation, Business Calendar, Integration y WhatsApp
existentes continúan operando.

Analytics GET requiere `analytics`; export requiere `analytics_export` y el RBAC
existente. Audit GET requiere `audit`, pero la escritura interna de Audit nunca se
plan-gatea.

## API y RBAC

`GET /organizations/{organization_id}/plan` devuelve identidad estable,
`version`, features y límites con `current/reached/over_limit`. No expone pricing,
currency, provider, subscription ni uso cross-tenant.

`PUT /organizations/{organization_id}/plan` acepta `plan_code` y
`expected_version`. Solo Platform Admin con `plan.assign` puede ejecutarlo.
Owner/Admin tienen `plan.read` en su propia Organization; Operator/Viewer no reciben
permisos nuevos.

La versión se valida antes del no-op. Mismo plan + versión vigente no incrementa
version, no cambia `updated_at` y no genera Audit. Una versión stale devuelve
`PLAN_VERSION_CONFLICT` incluso si el target coincide.

## Audit

El catálogo PRD-017 admite `plan.assigned`, `plan.changed`, resource
`plan_assignment` y `PlanAssignmentMetadata` con únicamente
`from_plan_code | null` y `to_plan_code`. El cambio, metadata y Audit se escriben en
la misma Session/transacción y un fallo del writer revierte el assignment.

No se registra price, currency, billing state, provider payload, invoice, payment,
PII ni secretos.

## Errores seguros

- `PLAN_NOT_FOUND`;
- `PLAN_ASSIGNMENT_NOT_FOUND`;
- `PLAN_FEATURE_NOT_AVAILABLE`;
- `PLAN_LIMIT_REACHED` (puede incluir solo `limit_key`);
- `PLAN_VERSION_CONFLICT`;
- `PLAN_FORBIDDEN`;
- `PLAN_UNAVAILABLE`.

## Observabilidad y seguridad

Métricas low-cardinality: `plan_enforcement_checks_total`,
`plan_enforcement_denials_total`, `plan_assignment_changes_total` y
`plan_query_requests_total`. No etiquetan organization/user/plan/resource. Los logs
no incluyen configuración completa, payload, pricing ni PII.

Toda lectura y count recibe `organization_id` explícita. No existen endpoints
all-tenants ni filtros `all_tenants`.

## Pruebas y aceptación

La cobertura focalizada valida configuración cerrada, unlimited y cero explícito,
bootstrap, counts, feature/limit denial, optimistic concurrency, same-plan no-op,
retired plan, downgrade no destructivo, over-limit, API/RBAC, tenant isolation,
Audit tipado y rollback.

La integración PostgreSQL valida tablas, seed, backfill, JSONB/FKs, row lock,
capacidad concurrente, plan-change-vs-create y el ciclo
`0018 → 0019 → 0018 → 0019`.

## Exclusiones y limitaciones conocidas

- sin Billing ni scope PRD-019;
- sin cuotas/metering de mensajes;
- sin pricing/currencies/trials/overage;
- sin catálogo mutable por API;
- sin historial de assignments dedicado (Audit conserva cambios exitosos);
- sin frontend;
- sin Redis ni caché;
- sin rate limiting comercial;
- únicamente PostgreSQL para garantías concurrentes.

PRD-019 permanece `NOT STARTED`.
