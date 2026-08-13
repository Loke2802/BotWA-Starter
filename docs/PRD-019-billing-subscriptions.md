# PRD-019 Billing & Subscriptions v1

**Estado:** CLOSED

**Fecha:** 2026-08-12

## Objetivo

PRD-019 incorpora Billing SaaS tenant-scoped para una `Organization`, con catálogo
interno de precios, suscripción vigente, checkout alojado, sincronización
autoritativa de proveedor y aplicación transaccional del plan de PRD-018. Billing
no reemplaza Plan: `billing_price` referencia un `plan_definition`, mientras
`organization_plan_assignment` continúa siendo la fuente de verdad de entitlements.

El dominio es agnóstico del proveedor. Mercado Pago es el adaptador real v1 y el
adaptador fake determinista permite pruebas sin red. Ningún contrato de dominio o
registro persistido contiene tipos de FastAPI, SDKs de Mercado Pago, PAN, CVV,
métodos de pago ni payloads crudos del proveedor.

La arquitectura cerrada implementa Billing SaaS provider-agnostic y
Organization-scoped mediante BillingAccount, BillingPrice, Subscription y un
ledger técnico de eventos del proveedor. Usa Mercado Pago como adapter real
inicial, hosted checkout, webhook/reconciliation server-side, estado local
last-known-good, transición temporal durable mediante due-transition processor y
una operación interna transaccional de PRD-018 para actualizar el PlanAssignment
efectivo. Plan, BillingPrice, Subscription y PlanAssignment permanecen separados,
sin invoice/payment ledger, metered usage, overage, fiscalidad, frontend ni
PRD-020.

## Límites v1 cerrados

- Billing está deshabilitado por defecto con `BOTWA_BILLING_ENABLED=false`.
- No hay cutover comercial, backfill ni seeds de planes/precios comerciales.
- `Organization` es el único tenant y scope comercial.
- PostgreSQL es obligatorio para locks, índices parciales y consistencia.
- Checkout siempre es hosted; el backend nunca captura credenciales de tarjeta.
- Los redirects de éxito/cancelación no cambian estado local.
- Webhook y reconciliación consultan el estado autoritativo antes de mutar.
- El último estado local válido permanece disponible si el proveedor falla.
- No hay frontend, scheduler, saga, outbox ni transacción distribuida.

## Modelo de persistencia

La revisión `20260812_0020`, descendiente directa de `20260810_0019`, crea
exactamente cuatro tablas y deja un único head:

1. `billing_account`: relación 1:1 por Organization, proveedor, customer externo
   opcional, estado y versión positiva. La identidad externa solo es única cuando
   existe.
2. `billing_price`: referencia al Plan técnico, precio en minor units entero,
   moneda ISO uppercase, intervalo mensual/anual, proveedor e identidad externa.
   No se insertan filas automáticamente.
3. `subscription`: historial durable con una sola fila current por Organization
   para `pending|active|past_due|suspended`, estados terminales preservados,
   períodos, pago, cancelación al cierre, cambio programado, secuencia del
   proveedor, sync y optimistic version.
4. `billing_provider_event`: receipt deduplicado por proveedor/evento con hash
   SHA-256, estado, intentos y error seguro. No guarda el payload crudo.

No existen tablas de invoice, payment, usage ni `billing_operation`; tampoco se
incorporaron outbox o saga.

## Contratos y adaptadores

`BillingProviderPort` define:

- `create_checkout`;
- `request_plan_change`;
- `request_cancellation`;
- `fetch_subscription`;
- `verify_and_normalize_webhook`.

El adaptador Mercado Pago usa `/preapproval` para crear la suscripción y obtener
su `init_point`, y consulta `/preapproval/{id}` antes de aplicar confirmaciones.
Los cambios de importe usan `auto_recurring.transaction_amount` y `currency_id`,
como define la API oficial; no intenta reasignar `preapproval_plan_id`.
Usa timeouts explícitos, token solo desde configuración de entorno, clave secreta
de webhook, HMAC SHA-256, timestamp con tolerancia y comparación constante. Las
fallas de red/5xx se mapean a `PROVIDER_UNAVAILABLE`; rechazos seguros a
`PROVIDER_REJECTED`.

Los adapters implementados son `MercadoPagoBillingProvider` y el adapter fake
determinista `FakeBillingProvider`. Stripe y Culqi quedan fuera de PRD-019.

El email autenticado se transmite únicamente al proveedor durante la creación de
checkout porque Mercado Pago lo exige; no se almacena en las tablas de Billing,
Audit, logs o métricas.

## Checkout e idempotencia

`POST /organizations/{organization_id}/billing/checkout` acepta solo
`billing_price_id` y `Idempotency-Key`. No acepta monto, moneda ni IDs externos.
La identidad interna de la suscripción se deriva de Organization + clave de
idempotencia; un retry con la misma carga reutiliza identidad y request externo,
sin nueva mutación ni Audit. Una clave reutilizada con otra carga falla cerrada.

El Billing Account se crea de forma lazy dentro del lock de Organization. Un
índice parcial impide más de una suscripción current.

## Webhook seguro y reconciliación

Ruta pública: `POST /webhooks/billing/mercado-pago`. No recibe Organization en el
path. El pipeline es:

1. limitar tamaño del body;
2. verificar firma, timestamp, request id y resource id antes de confiar;
3. normalizar el evento y calcular hash sin persistir payload;
4. deduplicar receipt;
5. resolver la suscripción por identidad externa;
6. bloquear Organization y luego Subscription;
7. obtener estado autoritativo del proveedor;
8. validar `external_reference == subscription.id`;
9. descartar secuencias antiguas cuando el proveedor expone versión;
10. actualizar Subscription, PlanAssignment y Audit en la misma Session;
11. marcar receipt y confirmar una sola transacción local.

Eventos repetidos responden éxito sin duplicar mutación ni Audit. Eventos válidos
sin binding conocido se marcan `ignored`. Fallas de procesamiento quedan `failed`
y reintentables, con código seguro. Cuando Billing está deshabilitado el webhook
no procesa transiciones.

`POST /organizations/{organization_id}/billing/reconcile` es exclusivo de
Platform Admin y reutiliza la misma función interna de transición. Es una
herramienta de recovery/administración, no el mecanismo temporal principal.

`BillingDueTransitionProcessor.process_due(now, batch_size)` consulta de forma
acotada y determinista las suscripciones con `scheduled_change_at <= now`, en
orden `scheduled_change_at, id`. Procesa cada Organization en una Unit of Work
independiente con locks `Organization FOR UPDATE → Subscription FOR UPDATE →
PlanAssignment`, por lo que un fallo no detiene el resto del batch.

El repositorio no contiene una primitive genérica de scheduler apropiada fuera del
worker del dominio Automation. PRD-019 no se acopla a ese dominio ni crea un
framework nuevo: `python -m app.operations.billing_due_transitions` es un comando
one-shot e idempotente para un cron/platform job externo. Cadencia recomendada:
cada minuto, con batch configurable y reejecución no solapada.

El scheduler es externo al producto. `POST .../reconcile` permanece como recovery
tool administrativo y nunca como mecanismo temporal principal.

## Transiciones, plan y consistencia

- La activación o upgrade se aplica solo tras confirmación autoritativa.
- Una confirmación actualiza Subscription y el PlanAssignment técnico en la misma
  transacción, mediante `InternalPlanAssignmentService` sin RBAC ni commit propio.
- El endpoint público de PRD-018 conserva su RBAC, versionado y Audit y reutiliza
  esa misma operación interna.
- Un downgrade conserva `current_period_end` como fecha efectiva del entitlement.
  `scheduled_change_at` comienza como due-at operativo anterior al siguiente cobro
  (`current_period_end - BOTWA_BILLING_PROVIDER_CHANGE_LEAD_SECONDS`). El processor
  solicita y confirma anticipadamente el monto objetivo, preserva el PlanAssignment
  actual y reprograma `scheduled_change_at` al boundary efectivo.
- En `current_period_end`, el processor verifica nuevamente el snapshot
  autoritativo, promueve el BillingPrice, cambia PlanAssignment, limpia pending y
  scheduling, y emite exactamente un `subscription.plan_changed` system Audit.
  Webhook y reconcile reutilizan las mismas guards; `pending + active` nunca basta.
- Mercado Pago v1 permite cambios de precio dentro del mismo intervalo. Un cambio
  mensual↔anual se rechaza fail-closed porque la API de suscripción no documenta
  cambio de frecuencia; requiere una estrategia comercial posterior.
- Mercado Pago no documenta `cancel_at_period_end` ni una desactivación futura.
  Su primitive oficial es el `PUT /preapproval/{id}` inmediato con
  `status=canceled`; la cancelación no puede reactivarse. Por ello, una solicitud
  self-service primero exige que el proveedor acepte esa cancelación. Solo después
  persiste y audita `cancel_at_period_end` localmente.
  Contrato verificado en la documentación oficial de
  [gestión de suscripciones](https://www.mercadopago.com.pe/developers/en/docs/subscriptions/subscription-management)
  y [gestión de suscriptores](https://www.mercadopago.com.pe/developers/en/docs/subscription-plans/manage-subscription-plan).
- La cancelación confirmada en Mercado Pago es la garantía durable de no-renovación
  y no depende de ejecutar reconcile exactamente al cierre. Luri conserva el
  PlanAssignment durante el período ya pagado; un webhook previo actualiza estado
  del proveedor sin revocar acceso ni ejecutar fallback. En `scheduled_change_at`,
  el due processor cierra el estado local incluso sin webhook ni actividad, y
  aplica únicamente el fallback configurado. `default` nunca es fallback implícito.
- Si Mercado Pago rechaza o no confirma `canceled`, la petición falla, la mutación
  local y `subscription.cancel_requested` se revierten, y no se comunica éxito.
- `past_due` conserva el assignment actual y no suspende por sí solo.
- No se inventa un período de gracia; `grace_until` solo refleja una política
  configurada fuera de este corte.
- Una caída del proveedor no provoca transición destructiva, fallback ni cambio
  de plan.

`PlanEnforcementService` sigue leyendo únicamente
`organization_plan_assignment`; Billing no participa en cada request de
enforcement. Plan representa capabilities, BillingPrice la oferta comercial,
Subscription la relación comercial y PlanAssignment el entitlement efectivo.

Para `suspended|canceled|expired`, el fallback solo puede usar
`BOTWA_BILLING_FALLBACK_PLAN_CODE` si está configurado explícitamente. Nunca se
asigna `default` implícitamente. Sin fallback, se conserva el estado comercial,
no se cambia el assignment y se registra `BILLING_FALLBACK_NOT_CONFIGURED` para
reconciliación operativa.

## API y RBAC

- `GET /organizations/{id}/billing`: Owner, Organization Admin y Platform Admin.
- `POST .../checkout`: Owner y Platform Admin.
- `POST .../change-plan`: Owner y Platform Admin.
- `POST .../cancel`: Owner y Platform Admin.
- `POST .../reconcile`: solo Platform Admin mediante `billing.manage`.

Operator y Viewer no reciben permisos Billing. Billing no concede `plan.assign`.
La respuesta GET no expone customer/subscription/price IDs externos, monto, email
ni secretos; contiene enabled, status, plan, intervalo, período, cancelación,
pago, cambio pendiente, sync, freshness y versión.

## Auditoría, observabilidad y errores

Acciones allowlisted:

- `billing.checkout_created`;
- `subscription.created`;
- `subscription.activated`;
- `subscription.plan_change_requested`;
- `subscription.plan_changed`;
- `subscription.cancel_requested`;
- `subscription.canceled`;
- `subscription.reconciled`.

Metadata limitada a códigos de plan, intervalo y flag de cancelación. No contiene
montos, IDs externos, PII ni secretos. Requests Owner/Admin usan actor user;
confirmaciones del proveedor usan actor system. Audit es obligatorio/fail-closed
y participa en la misma transacción que la mutación local.

Las acciones comerciales/administrativas exitosas se registran en Audit; el
procesamiento técnico del proveedor/webhook se registra en
`billing_provider_event`. Las transiciones automáticas confirmadas usan
`actor_type=system`, sin usuario o Platform Admin ficticio. Subscription,
PlanAssignment, Audit y procesamiento del evento comparten la misma transacción
local; la llamada al proveedor externo nunca forma parte de la transacción
PostgreSQL.

Métricas low-cardinality:

- `billing_checkout_total`;
- `billing_webhook_events_total`;
- `billing_plan_changes_total`;
- `billing_cancellations_total`;
- `billing_reconciliations_total`.
- `billing_due_transitions_total{operation=cancellation|downgrade,
  result=success|retryable_failure|skipped}`.

Los logs del job contienen solo operación, conteos y safe error code; nunca tenant,
subscription ID, identidad externa, monto, PII ni secretos.

El checkout es hosted: Luri no recibe PAN, CVV ni métodos de pago y no almacena
payloads crudos del proveedor. No hay secretos en DB, Audit o logs. Los webhooks
son firmados, timestamp-bounded, deduplicados, provider-bound, resueltos al tenant
interno, confirmados mediante fetch autoritativo y protegidos contra eventos fuera
de orden.

Errores públicos cerrados: `BILLING_DISABLED`, `BILLING_NOT_CONFIGURED`,
`BILLING_ACCOUNT_NOT_FOUND`, `BILLING_PRICE_NOT_FOUND`, `BILLING_PRICE_UNAVAILABLE`,
`SUBSCRIPTION_NOT_FOUND`, `SUBSCRIPTION_CONFLICT`,
`SUBSCRIPTION_INVALID_TRANSITION`,
`SUBSCRIPTION_VERSION_CONFLICT`, `BILLING_PROVIDER_UNAVAILABLE`,
`BILLING_PROVIDER_REJECTED`, `BILLING_WEBHOOK_INVALID`,
`BILLING_EVENT_DUPLICATE`, `BILLING_FALLBACK_NOT_CONFIGURED` y
`BILLING_FORBIDDEN`.

## Configuración

- `BOTWA_BILLING_ENABLED=false`;
- `BOTWA_BILLING_PROVIDER=mercado_pago`;
- `BOTWA_BILLING_MERCADO_PAGO_ACCESS_TOKEN`;
- `BOTWA_BILLING_MERCADO_PAGO_WEBHOOK_SECRET`;
- timeouts connect/read explícitos;
- URLs HTTPS de success/cancel;
- máximo de body y tolerancia de firma;
- freshness local;
- fallback plan code vacío por defecto;
- `BOTWA_BILLING_DUE_BATCH_SIZE=100`;
- `BOTWA_BILLING_PROVIDER_CHANGE_LEAD_SECONDS=3600`.

La documentación oficial de Mercado Pago confirma que el PUT cambia
`auto_recurring.transaction_amount` y expone `next_payment_date`, pero no promete
qué ocurre con un cobro ya generado ni garantiza una llamada posterior al boundary.
Por ello el cambio se prepara antes del próximo cobro. El lead de una hora y la
cadencia de un minuto son defaults operativos conservadores, no una garantía del
proveedor; deben verificarse con el sandbox real antes del go-live comercial.

## Pruebas y gates

La suite cubre contratos/modelos, checkout hosted e idempotente, modo disabled,
RBAC y aislamiento tenant, firma/replay/deduplicación, binding interno, estado
autoritativo, orden de eventos, upgrades, guard temporal y confirmación de
downgrades, cancelación inmediata del proveedor con acceso local hasta el cierre,
rechazo e idempotencia de cancelación, processor sin webhook, batch/retry,
aislamiento de fallo por tenant, lock order, carrera webhook/processor,
ausencia de fallback implícito, transacción/Audit, API, restricciones PostgreSQL y ciclo
`0019 → 0020 → 0019 → 0020`.

Los resultados finales de gates se registran en los documentos canónicos y en el
Draft PR después de su ejecución completa.

Resultado del hardening final:

- focused PRD-019: 34 passed, 2 warnings;
- due-transition processor: 10 passed, 24 deselected, 2 warnings;
- scheduling/cancellation regression: 17 passed, 17 deselected, 2 warnings;
- PRD-017/018/019 regression: 95 passed, 2 warnings;
- PostgreSQL PRD-019: 5 passed;
- migration cycle `0019 → 0020 → 0019 → 0020`: PASS;
- full pytest: 821 passed, 26 skipped, 2 warnings;
- mypy: PASS — 449 source files;
- Ruff: PASS;
- Black: PASS — 449 files;
- `git diff --check`: PASS;
- Alembic: `20260812_0020`, one head.

## Exclusiones explícitas

- invoices, invoice PDF/XML, pagos, intentos, refunds y disputes;
- impuestos, SUNAT y facturación electrónica;
- trial, coupons, discounts, credits, prorations y overage;
- message quota/metering y usage aggregation;
- checkout propio, PAN/CVV o almacenamiento de métodos de pago;
- multi-provider activo simultáneo, Stripe y Culqi;
- frontend, scheduler interno, emails, dunning automático y collections;
- cambios en Analytics, Dashboard o PRD-020;
- saga, outbox y `billing_operation`.

## Gates operativos de go-live

**COMMERCIAL GO-LIVE BLOCKED.** Antes de habilitar Billing en staging o
producción se requieren credenciales Mercado Pago aprobadas, al menos un Plan
comercial y un BillingPrice activo verificados, moneda/precio aprobados, plan de
fallback o política restrictiva explícita, política de grace/past_due, scheduler
externo configurado para due-transitions y smoke sandbox real. El código permanece
deshabilitado por defecto con `BOTWA_BILLING_ENABLED=false`; el cierre técnico del
PRD no equivale a commercial go-live.

**Mercado Pago real sandbox smoke: PENDING — EXTERNAL CREDENTIALS REQUIRED.** Debe
validar checkout hosted, signed webhook, activación, timing real del cambio de
monto, cancelación inmediata del proveedor, acceso local durante el período
pagado, due-transition processor, fallback, idempotencia y reconcile antes del
cutover. Es un gate operativo externo, no se simula como PASS y no bloquea el
estado técnico CLOSED.

PRD-020 permanece `NOT STARTED`.

## Implementation Closure

PRD-019 quedó cerrado documentalmente después de que la implementación aprobada
se integró mediante el PR #30 con merge commit normal
`5a87ffc32be4315ebb6f9e64826bdb96f36ada58`. El head final aprobado e integrado
fue `2a15b7f022c2989d73bb97d9b964495dba961778`; no se usó squash ni rebase.

La revisión final conserva Alembic `20260812_0020` como único head y las cuatro
tablas `billing_account`, `billing_price`, `subscription` y
`billing_provider_event`. Mercado Pago queda como proveedor real inicial detrás
de la frontera provider-agnostic. El comando operacional de transición temporal
es `python -m app.operations.billing_due_transitions`, recomendado cada minuto
mediante scheduler externo.

La cancelación se confirma inmediatamente provider-side para garantizar
no-renewal, mantiene el PlanAssignment durante el período pagado y finaliza el
entitlement mediante `scheduled_change_at`/`current_period_end`; solo un fallback
comercial explícito puede reemplazarlo. `default` es el bootstrap técnico unlimited
de PRD-018 y nunca un fallback comercial. Sin fallback se conserva un estado
seguro que requiere intervención del operador y jamás se concede unlimited.

El downgrade se programa localmente, prepara anticipadamente el cambio de monto
con `BOTWA_BILLING_PROVIDER_CHANGE_LEAD_SECONDS=3600`, preserva PlanAssignment
hasta el boundary y promueve BillingPrice/PlanAssignment en
`current_period_end`. Los retries son idempotentes y el timing real de Mercado
Pago debe aprobarse en sandbox antes de habilitar Billing comercialmente.

Los gates finales aprobados son los registrados en la sección anterior. Billing
comercial continúa BLOCKED y el smoke real de Mercado Pago continúa
`PENDING — EXTERNAL CREDENTIALS REQUIRED`; ambos son gates operativos posteriores,
no blockers del cierre técnico. PRD-020 permanece `NOT STARTED` y no se inició
discovery ni implementación.
