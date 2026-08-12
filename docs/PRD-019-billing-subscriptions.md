# PRD-019 Billing & Subscriptions v1

**Estado:** IMPLEMENTED — PENDING CTO REVIEW

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
Platform Admin y reutiliza el mismo pipeline de transición. Solo audita cambios
materiales. No existe scheduler en PRD-019.

## Transiciones, plan y consistencia

- La activación o upgrade se aplica solo tras confirmación autoritativa.
- Una confirmación actualiza Subscription y el PlanAssignment técnico en la misma
  transacción, mediante `InternalPlanAssignmentService` sin RBAC ni commit propio.
- El endpoint público de PRD-018 conserva su RBAC, versionado y Audit y reutiliza
  esa misma operación interna.
- Un downgrade se programa para `current_period_end`; no elimina recursos.
  `scheduled_change_at` es una guard obligatoria: antes de esa fecha, webhook y
  reconciliación pueden refrescar el estado autoritativo, pero no promueven el
  precio pendiente ni cambian el PlanAssignment.
- Al vencimiento, una reconciliación solicita el cambio y exige confirmación
  autoritativa del precio objetivo antes de promoverlo. Un webhook también puede
  completar la transición si ya observa el monto/moneda o identidad normalizada
  del target. `pending + active` nunca constituye confirmación suficiente.
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
  del proveedor sin revocar acceso ni ejecutar fallback. En
  `scheduled_change_at`, webhook o reconcile completan el estado local y aplican
  únicamente el fallback configurado. `default` nunca es fallback implícito.
- Si Mercado Pago rechaza o no confirma `canceled`, la petición falla, la mutación
  local y `subscription.cancel_requested` se revierten, y no se comunica éxito.
- `past_due` conserva el assignment actual y no suspende por sí solo.
- No se inventa un período de gracia; `grace_until` solo refleja una política
  configurada fuera de este corte.
- Una caída del proveedor no provoca transición destructiva, fallback ni cambio
  de plan.

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

Métricas low-cardinality:

- `billing_checkout_total`;
- `billing_webhook_events_total`;
- `billing_plan_changes_total`;
- `billing_cancellations_total`;
- `billing_reconciliations_total`.

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
- fallback plan code vacío por defecto.

## Pruebas y gates

La suite cubre contratos/modelos, checkout hosted e idempotente, modo disabled,
RBAC y aislamiento tenant, firma/replay/deduplicación, binding interno, estado
autoritativo, orden de eventos, upgrades, guard temporal y confirmación de
downgrades, cancelación inmediata del proveedor con acceso local hasta el cierre,
rechazo e idempotencia de cancelación, ausencia de fallback implícito,
transacción/Audit, API, restricciones PostgreSQL y ciclo
`0019 → 0020 → 0019 → 0020`.

Los resultados finales de gates se registran en los documentos canónicos y en el
Draft PR después de su ejecución completa.

Resultado del hardening final: 25 pruebas PRD-019 y 9 regresiones focalizadas de
scheduling/cancelación pasan; la regresión PRD-017/018/019 cierra en 86 passed;
PostgreSQL PRD-019 en 4 passed; full pytest en 812 passed, 25 skipped y 2 warnings;
mypy, Ruff, Black y `git diff --check` pasan sobre 446 source files, y Alembic
conserva un único head `20260812_0020` con ciclo
`0019 → 0020 → 0019 → 0020` aprobado.

## Exclusiones explícitas

- invoices, invoice PDF/XML, pagos, intentos, refunds y disputes;
- impuestos, SUNAT y facturación electrónica;
- trial, coupons, discounts, credits, prorations y overage;
- message quota/metering y usage aggregation;
- checkout propio, PAN/CVV o almacenamiento de métodos de pago;
- multi-provider activo simultáneo, Stripe y Culqi;
- frontend, scheduler, emails, dunning automático y collections;
- cambios en Analytics, Dashboard o PRD-020;
- saga, outbox y `billing_operation`.

## Gates operativos de go-live

**COMMERCIAL GO-LIVE BLOCKED.** Antes de habilitar Billing en staging o
producción se requieren credenciales productivas aprobadas, al menos un Plan
comercial y un BillingPrice activo verificados, moneda/precio aprobados, plan de
fallback o política restrictiva explícita, política de grace/past_due y smoke
sandbox real.

**Mercado Pago real sandbox smoke: PENDING — EXTERNAL CREDENTIALS REQUIRED.** Debe
validar checkout hosted, firma webhook, activación, cambio, cancelación,
idempotencia y reconcile antes del cutover. Es un gate operativo externo, no se
simula como PASS.

PRD-020 permanece `NOT STARTED`.
