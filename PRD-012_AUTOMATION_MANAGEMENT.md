# PRD-012 Automation Management

Estado: implemented, pending CTO review.

PRD-012 añade automatizaciones administrativas durables con el único par permitido
`conversation.inbound_received -> request_handoff`. Las definiciones son aisladas
por organización y las ejecuciones conservan snapshots seguros, sin texto de
mensajes, payloads de proveedor, secretos ni PII.

La API vive bajo `/organizations/{organization_id}/automations`. El worker se
ejecuta con `python -m app.operations.automation_worker --once` y reclama trabajo
en PostgreSQL con `FOR UPDATE SKIP LOCKED` y leases. No existe ejecución manual,
DELETE ni un endpoint público para ejecutar reglas.
