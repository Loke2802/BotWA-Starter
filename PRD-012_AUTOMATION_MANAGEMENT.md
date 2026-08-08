# PRD-012 Automation Management

## Objetivo, problema, alcance y exclusiones

Automatiza un Human Handoff auditable para inbound que cumpla reglas aprobadas. El
alcance se limita a `conversation.inbound_received -> request_handoff`; no altera
Core Automation, no permite reglas libres, contenido, PII, Redis/Celery ni acciones
adicionales.

## Trigger, condiciones, acción, definitions y lifecycle

El trigger público único es `conversation.inbound_received`. Las condiciones AND
allowlisted son `channel_type`, `bot_id`, `business_hours_state`,
`conversation_status` y `handoff_active`; la acción es `request_handoff` con reason
code limitado. Definitions tenant-scoped pasan draft→active→inactive/archived;
archived es terminal. Cambios funcionales aumentan versión; nombre/descripción no.

## Receipts, executions, snapshots e idempotencia

Receipts contienen solo IDs, canal, tiempo y business-hours seguros. Su unique key
absorbe duplicados. Executions son únicas por definition/version/receipt y mantienen
snapshots inmutables, intentos, disponibilidad, leases y códigos seguros; nunca
texto, payloads de proveedor, secretos ni PII.

## Worker, leases, retries, concurrencia y loops

El worker PostgreSQL reclama con `FOR UPDATE SKIP LOCKED`, recupera leases vencidos
y usa batches. Hay máximo tres intentos con backoff inmediato/+5s/+30s; retry manual
reutiliza la execution. Deactivate/archive cancela pending. `source_automation_id`
no tiene FK deliberadamente para no acoplar productores/ciclos y se descarta para
prevenir loops de profundidad mayor de uno.

## RBAC, tenant isolation, API e integraciones

Los permisos cubren CRUD de definitions y lectura/retry de executions. Todas las
rutas y repositorios están filtrados por organization_id. Inbound persiste tras
resolver organización, bot, Contact y Conversation y reutiliza PRD-005 para estado
de horario; nunca ejecuta en webhook. Human Handoff se solicita mediante una
operación interna limitada, idempotente y sin impersonar usuarios.

## Migración, Docker, pruebas, riesgos y cierre

La migración `20260807_0014` contiene FKs, constraints e índices para listing,
receipts y claims. Docker Compose incluye `automation-worker`. Las pruebas cubren
contratos, lifecycle, RBAC, isolation, worker y regresiones. El cierre exige gates
y smoke PostgreSQL; el riesgo residual es operativo y se mitiga con leases/retries.
PRD-013 permanece NOT STARTED.

Estado: CLOSED.

PRD-012 fue aprobado por CTO y fusionado en `master` mediante el PR #14. La
validacion post-merge cerro con 652 pruebas, mypy/Ruff/Black PASS y Alembic head
`20260807_0014`.

PRD-012 añade automatizaciones administrativas durables con el único par permitido
`conversation.inbound_received -> request_handoff`. Las definiciones son aisladas
por organización y las ejecuciones conservan snapshots seguros, sin texto de
mensajes, payloads de proveedor, secretos ni PII.

La API vive bajo `/organizations/{organization_id}/automations`. El worker se
ejecuta con `python -m app.operations.automation_worker --once` y reclama trabajo
en PostgreSQL con `FOR UPDATE SKIP LOCKED` y leases. No existe ejecución manual,
DELETE ni un endpoint público para ejecutar reglas.
