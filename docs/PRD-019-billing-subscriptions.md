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
- Un downgrade se programa para `current_period_end`; no elimina recursos. Al
  vencimiento, una reconciliación solicita el cambio y solo entonces lo aplica.
- Cancelación self-service es únicamente `cancel_at_period_end`; no existe
  cancel-now. Al vencimiento, reconcile ejecuta la cancelación remota.
- `past_due` conserva el assignment actual y no suspende por sí solo.
- No se inventa un período de gracia; `grace_until` solo refleja una política
  configurada fuera de este corte.
- Una caída del proveedor no provoca transición destructiva, fallback ni cambio
  de plan.

Para `suspended|canceled|expired`, el fallback solo puede usar
`BOTWA_BILLING_FALLBACK_PLAN_CODE` si está configurado explícitamente. Nunca se
asigna `default` implícitamente. Sin fallback, se conserva el estado comercial,
no se cambia el assignment y se registra `FALLBACK_NOT_CONFIGURED` para
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

Errores públicos cerrados: `BILLING_DISABLED`, `NOT_CONFIGURED`,
`ACCOUNT_NOT_FOUND`, `PRICE_NOT_FOUND`, `PRICE_UNAVAILABLE`,
`SUBSCRIPTION_NOT_FOUND`, `SUBSCRIPTION_CONFLICT`, `INVALID_TRANSITION`,
`VERSION_CONFLICT`, `PROVIDER_UNAVAILABLE`, `PROVIDER_REJECTED`,
`WEBHOOK_INVALID`, `EVENT_DUPLICATE`, `FALLBACK_NOT_CONFIGURED` y `FORBIDDEN`.

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
autoritativo, orden de eventos, upgrades, downgrades programados, cancelación al
período, falta de fallback, transacción/Audit, API, restricciones PostgreSQL y
ciclo `0019 → 0020 → 0019 → 0020`.

Los resultados finales de gates se registran en los documentos canónicos y en el
Draft PR después de su ejecución completa.

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
