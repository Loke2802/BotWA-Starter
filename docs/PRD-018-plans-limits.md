# PRD-018 Plans and Limits v1

**Estado:** CLOSED

**Cierre aprobado:** PR #28, merge commit
`63f2fc79444e6b3f85b516b917860fb17fa8f779`, final approved head
`2776a1b2ca6082142f14862c4eac4cf889eea631`.

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

## Decisiones de arquitectura cerradas

- `Organization` es el scope comercial y tenant canónico.
- `plan_definition` es un catálogo interno seed-controlled; `plan_code` es
  estable y está separado de `display_name`.
- `organization_plan_assignment` es el Source of Truth 1:1 del plan vigente.
- El plan `default` habilita todas las features y define todos los límites como
  `unlimited`; Organizations existentes fueron backfilled y nuevas Organizations
  reciben ese assignment dentro de su Unit of Work.
- `configuration` JSONB es estrictamente tipada y allowlisted. Features booleanas
  y resource-count hard limits son mecanismos separados; `unlimited` es
  explícito, sin magic numbers.
- Los counts proceden de Sources of Truth operacionales. No existe
  `usage_counter`; Analytics y Audit no son SoT de enforcement.
- El enforcement es obligatorio y fail-closed. Plan y RBAC son mecanismos
  separados, y solo Platform Admin asigna o cambia plan en v1.
- Organization `FOR UPDATE` protege concurrencia; assignment usa optimistic
  versioning y same-plan PUT es un no-op idempotente.
- Downgrade es no destructivo; over-limit bloquea nuevos consumos sin destruir
  recursos; upgrade toma efecto inmediatamente después del commit.
- Retired plans no aceptan nuevas asignaciones, aunque assignments existentes
  siguen siendo válidos.
- Audit PRD-017 registra `plan.changed` con metadata tipada en la misma
  transacción. Audit WRITE nunca se plan-gatea.
- Aislamiento tenant estricto, PostgreSQL-only, sin cache/Redis y sin frontend.

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

### Contrato fail-closed cerrado

`PlanEnforcementService` es una dependencia obligatoria de todo application
service que expone acciones plan-gated. No existe `Optional`, default `None`,
bypass condicional ni `NullPlanEnforcementService` de producción. Todos los
composition roots de producción construyen el enforcement con el mismo objeto
SQLAlchemy `Session` usado por repository, AuditWriter, lock, count, mutación y
commit owner.

Las consuming actions ejecutan enforcement siempre. Las reducing actions
permanecen permitidas para evitar lock-in. El worker existente de Automation,
WhatsApp inbound/outbound, la resolución runtime de Business Calendar, la
resolución de handoffs abiertos y Audit WRITE no son consuming/read-gated y se
preservan después de un downgrade.

Analytics read requiere `analytics`; export requiere `analytics_export` y también
la lectura canónica de Analytics. Audit read requiere `audit`. Audit WRITE nunca
se plan-gatea.

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

## Gates finales de cierre

- Focused PRD-018 + fail-closed: 36 passed, 2 warnings;
- expanded affected-domain regression: 159 passed, 2 warnings;
- PostgreSQL PRD-018: 3 passed;
- full pytest: 787 passed, 21 skipped, 2 warnings;
- mypy: PASS — 430 source files;
- Ruff: PASS;
- Black: PASS — 430 files;
- `git diff --check`: PASS;
- Alembic head: `20260810_0019`;
- migration cycle `0018 → 0019 → 0018 → 0019`: PASS.

## Exclusiones y limitaciones conocidas

- sin Billing ni scope PRD-019;
- sin subscriptions, checkout, invoices, payments ni provider sync;
- sin billing cycles ni renewals;
- sin cuotas/metering de mensajes;
- sin pricing/currencies/trials/overage;
- sin catálogo mutable por API;
- sin historial de assignments dedicado (Audit conserva cambios exitosos);
- sin frontend;
- sin Redis ni caché;
- sin rate limiting comercial;
- únicamente PostgreSQL para garantías concurrentes.

PRD-019 permanece `NOT STARTED`.
