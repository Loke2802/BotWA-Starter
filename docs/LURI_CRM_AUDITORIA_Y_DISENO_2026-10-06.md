# Luri: auditoría inicial y primer incremento de CRM

Fecha: 06/10/2026. Requisitos: [LURI-CTX-001](LURI-CTX-001_CONTEXTO_MAESTRO_CRM_2026-10-06.md).
Estado: revisión estática y diseño propuesto; no implementación ni validación del entorno actual.

## Contexto confirmado

Kalivur es la empresa madre; Kalivur Marketing Pro es su unidad de marketing;
Luri es el producto de asistentes IA y la empleada digital de Kalivur.
El objetivo es un CRM comercial multiempresa y multicanal, configurable por negocio.
Kalivur Marketing Pro es el primer piloto comercial propuesto. Los antecedentes
de Kalivur Site y LumiKids se conservan; no acreditan activación de este piloto.

Potencial de compra, etapa de oportunidad y atención son dimensiones independientes.
Una conversación resuelta no es una venta ganada, y una venta no verifica un pago.
La IA propone con evidencia; el humano confirma cambios comerciales en la primera versión.

## Alcance y evidencia

- Checkout principal: `master`, HEAD `f626bf2480749ad4102aeb40d0f726d38f393e97`.
  Tiene cambios previos en código y reorganización de documentos. Se conservaron.
- Referencia disponible en objetos Git y `origin/master` local:
  `026ca10d3276ed06cb8f644549e807a684921f22`, merge PR #45.
  Se inspeccionó con `git show` y `git ls-tree`, sin mover HEAD ni reemplazar archivos.
- `git ls-remote origin refs/heads/master` falló por conectividad. La referencia
  remota guardada no acredita el master remoto actual.
- No se consultó staging, PostgreSQL desplegado ni panel autenticado en esta revisión.
  No se ejecutaron pruebas, migraciones, llamadas IA ni mensajes.
- `D:/Kalivur Web/docs/CRM_INTRANET.md` documenta una comprobación autenticada
  histórica del CRM del 16/09. `LURI_CONTEXTO_PARA_GPT_2026-09-24.md` documenta
  staging PR #45 y actualización Meta del 26/09. Son antecedentes, no estado vivo.
- El paquete de 40 casos sintéticos citado por el usuario no fue ejecutado aquí.

Las rutas de evidencia de la matriz se refieren al árbol de `026ca10`, salvo indicación.
Completo significa recorrido requerido acreditado; parcial, componentes presentes;
ausente, sin implementación encontrada en el árbol revisado; desconocido, sin acceso/evidencia.

## Matriz CRM-01 a CRM-10

| ID | Estado del código revisado | Evidencia | Pendiente para el requisito completo |
|---|---|---|---|
| CRM-01 Bandeja | Parcial | `app/portal/conversations.js`, `app/api/conversation_management_routes.py`, `app/api/human_handoff_routes.py`: historial y respuesta humana | Integrar ficha/oportunidad, filtros comerciales, cuenta visible y recorrido autenticado actual |
| CRM-02 Múltiples WhatsApp | Parcial | `app/infrastructure/models/whatsapp_channel_configuration.py`: empresa, bot, número único; conversación con cuenta de origen | Selector/filtro de cuenta y pruebas con dos números; verificar restricciones del resolver y transporte |
| CRM-03 Multicanal | Parcial | Contratos de canal, adaptador WhatsApp y canal HTTP existentes | Messenger, Instagram, TikTok y chat web completo sin evidencia de integración operativa; permisos/capacidades por proveedor pendientes |
| CRM-04 Avance | Parcial | `app/application/contacts/crm.py`, `app/infrastructure/models/customer_profile.py`: responsable, interés, fecha de seguimiento y versión | Necesidades estructuradas, oportunidad independiente, etapa y acción con descripción |
| CRM-05 Potencial | Parcial | `app/domain/contacts/crm_contracts.py`: `lead/customer/inactive` e interés de servicio | Dimensión independiente de potencial; no convertir clasificación antigua en intención confirmada |
| CRM-06 Ventas | Ausente | Árbol de modelos/migraciones sin entidad oportunidad/pipeline; `customer_profile` es 1:1 con contacto | Varias oportunidades por contacto, etapas configurables, cierre y razones |
| CRM-07 Seguimiento | Parcial | `next_follow_up_at`, filtro `due` y contador en `CrmService`/portal | Actividades con responsable, estado, historial y vencimientos por oportunidad |
| CRM-08 Recompra | Ausente | Sin entidad compra comercial/regla de recompra encontrada | Compra con evidencia, regla configurable, revisión humana y nueva oportunidad; Billing SaaS no sustituye compras de clientes |
| CRM-09 Arquitectura | Parcial | Capas domain/application/infrastructure/API, contactos cifrados, FKs por empresa en perfil, transporte persistido, `app/operations/ai_consumer.py` | Garantías del nuevo CRM, entrega incierta, recuperación/migración y restauración probadas |
| CRM-10 Auditabilidad | Parcial | Pruebas CRM unitarias/PostgreSQL, auditoría transaccional y control de versión del perfil | Pruebas del incremento: aislamiento, idempotencia, carreras, fallos; ejecución actual no realizada |

Para todos los requisitos: despliegue/DB/panel actual y validación externa quedan
**desconocidos** en esta revisión. La presencia de pruebas no equivale a su ejecución.

## Reutilización y límites

- Reutilizar `organization`, usuarios/permisos, `contact`, `customer_profile`,
  conversaciones/mensajes, handoff, Audit y transporte. No crear otro cliente
  comercial paralelo al contacto cifrado existente.
- El perfil ya contiene clasificación, interés, responsable y seguimiento;
  preservarlos y sus contratos. `service_interest` tiene valores exclusivos de
  Kalivur: la ampliación necesita catálogo por empresa, sin invalidar datos antiguos.
- `contact` representa actualmente una identidad por empresa/canal/hash. No
  afirmar que ya permite varias identidades por contacto. Posponer uniones
  multicanal a un diseño con evidencia, procedencia y revisión humana.
- Mantener `classification` como relación comercial histórica; no usarla como
  potencial, etapa ni prueba de compra. Una oportunidad ganada no cambia esa
  clasificación ni genera compra automáticamente.
- El responsable del perfil no sustituye al de cada oportunidad; handoff mantiene
  su asignación de atención. Pueden ser personas diferentes.
- PR #44/#45 contienen IA persistente y respuesta validada. El documento del
  18/09 sobre IA pendiente es un antecedente y no describe esa referencia.

## Incremento 1 propuesto: conversación, ficha, oportunidad y próxima acción

Recorrido: seleccionar empresa y conversación → leer historial → abrir contacto
existente → crear o vincular una oportunidad → guardar responsable y próxima
acción con fecha, o motivo explícito para no programarla → recargar y verificar.
Responder por el handoff/transportes actuales, mostrando la cuenta real.

La primera versión usa confirmación humana. No activa mensajes automáticos,
IA pagada ni nuevos proveedores. No agrega servicios de infraestructura.

### Modelo y migraciones propuestos

PostgreSQL será fuente de verdad del CRM. Propuesta aditiva sobre una base
actualizada y verificada; el número de revisión se decide desde el head real de Alembic.

| Recurso | Propuesta |
|---|---|
| Pipeline/etapa | Configuración por empresa; clave estable, nombre, orden, tipo `open/won/lost`, versión. Seed inicial configurable según LURI-CTX-001 |
| Oportunidad | UUID, empresa, contacto, pipeline/etapa, título/necesidad protegida, responsable, importe decimal opcional, moneda obligatoria si hay importe, versión, creación/actualización/cierre y razón |
| Vínculo conversación-oportunidad | Empresa, conversación, oportunidad; unicidad del vínculo. Una conversación y un contacto admiten varias oportunidades |
| Actividad | UUID, empresa, contacto/oportunidad, responsable, descripción protegida, fecha con zona, estado `pending/completed/cancelled`, versión y marcas de resolución |
| Próxima acción | Referencia a actividad pendiente de la oportunidad o motivo protegido explícito de ausencia; sin duplicar fecha/descripción como segunda fuente de verdad |
| Potencial del contacto | Ampliación del perfil existente, código configurable independiente; valor inicial `unassessed`, origen/actor/fecha/evidencia. Sin backfill inferido desde `lead/customer/inactive` |
| Historial comercial | Transiciones de etapa/acción, actor, fecha y versión; separado del Audit administrativo, sin copiar conversaciones |

FKs compuestas por recurso y empresa deben impedir vínculos cruzados, también
para responsable, etapa, actividad y conversación. Agregar las unicidades
compuestas que falten en padres, comprobando registros legacy antes del upgrade.
Validar pertenencia activa de usuarios en servicio y conservar responsable histórico.
La coherencia de pipeline/etapa y contacto/oportunidad se garantiza con FKs
compuestas o restricciones equivalentes, además de validación de aplicación.
Índices por empresa/contacto, etapa/responsable y estado/vencimiento.

Escritura de oportunidad + vínculo + primera actividad + historial + Audit en
una transacción. Concurrencia optimista por versión y locks acotados donde
corresponda. Idempotencia de creación por empresa/actor/operación/clave y digest
del payload: misma clave/datos devuelve el resultado; datos diferentes, conflicto.

No migrar automáticamente fechas de seguimiento del contacto hacia una
oportunidad: conservarlas y mostrar procedencia hasta una vinculación humana.
Compras, cobros y recompra pertenecen a incrementos posteriores.

### Contratos API propuestos, todavía no implementados

Prefijo `/organizations/{organization_id}`; aplicar autenticación y autorización
scoped en servicio, no confiar en la empresa ni permisos enviados por el navegador.

| Operación | Contrato |
|---|---|
| Leer contexto comercial | `GET /conversations/{id}/commercial-context`: cuenta/canal, contacto autorizado, oportunidades paginadas, responsables y próximas acciones; PII según permisos |
| Crear oportunidad | `POST /crm/opportunities`: contacto, conversación opcional, pipeline/etapa abierta, responsable, necesidad, importe/moneda opcionales y acción+fecha o motivo de ausencia; `Idempotency-Key`; devuelve 201 y versión |
| Consultar | `GET /crm/opportunities` y `GET /crm/opportunities/{id}`: filtros por contacto, conversación, responsable y etapa; paginación y totales con idéntico scope |
| Vincular conversación | `PUT /crm/opportunities/{id}/conversations/{conversation_id}`: idempotente, misma empresa y contacto; sin vinculación por nombre parecido |
| Modificar | `PATCH /crm/opportunities/{id}`: versión requerida, responsable/importe/necesidad/etapa y razón de cierre; 409 si versión obsoleta |
| Gestionar acción | `POST /crm/opportunities/{id}/activities` y `PATCH /crm/activities/{id}`: creación idempotente, actualización por versión; completar próxima acción exige sustituta o motivo si continúa abierta |
| Confirmar potencial | `PATCH /crm/customers/{contact_id}/potential`: código configurado y versión, actor humano/evidencia; no cambia atención ni oportunidad |

Conservar rutas `/crm/customers`, contratos de conversaciones y handoff.
Añadir permisos explícitos de oportunidades/actividades/potencial al catálogo
RBAC; no otorgar acceso universal a Kalivur. La ficha compuesta requiere los
permisos de cada sección y protege también contadores y búsquedas.
Respuestas: 400/422 para solicitud inválida; 403 sin permiso; 404 para recursos
inexistentes o fuera del ámbito; 409 para conflictos de versión/vínculo/clave.

### Responsabilidades

- `app/domain/crm/`: contratos, estados e invariantes comerciales independientes
  del canal/IA, sin sesiones SQL ni clientes externos.
- `app/application/crm/`: casos de uso, autorización, transacciones, concurrencia,
  idempotencia y auditoría; puertos de repositorios explícitos.
- `app/infrastructure/models/` y `repositories/`: tablas, consultas scoped y locks.
- `app/api/crm_*`: HTTP y errores; no trasladar reglas al portal.
- `app/portal/`: componer bandeja/ficha mediante API; mostrar cuenta, estado de
  guardado y conflicto de edición. El estado de envío procede del transporte.
- IA/worker existentes: conservar; futuras sugerencias comerciales se validan
  por backend y quedan diferenciadas de cambios confirmados.

### Aceptación, fallos y recuperación

1. Crear desde conversación y recuperar tras recarga contacto, oportunidad y acción.
2. Dos oportunidades del mismo contacto mantienen etapas/acciones independientes.
3. Dos empresas no pueden leer, contar, vincular ni asignar recursos entre sí;
   roles sin datos sensibles no reciben PII por el contexto compuesto.
4. Repetición de creación no duplica oportunidad/actividad; edición concurrente
   devuelve conflicto y conserva el primer cambio.
5. Falla de Audit o DB revierte toda la escritura; el panel no anuncia éxito.
6. Cambio de potencial/resolución de conversación no cierra ventas ni confirma pagos.
7. Handoff activo suspende automatización; verificar carrera con envío en vuelo
   en el transporte existente antes de aceptar el recorrido.
8. Timeout del canal no se presenta como entregado ni habilita reenvío ciego.
   El esquema revisado no tiene estado explícito `uncertain`: diseñar un contrato
   compatible de incertidumbre antes de prometer ese estado en el panel.
9. Fechas se persisten con zona y se presentan en zona de empresa; probar vencimientos.
10. Upgrade desde head verificado, unicidades/FKs y rollback compatible se prueban
    con PostgreSQL. Rollback de aplicación preserva tablas/datos; no ejecutar
    downgrade destructivo sobre datos CRM. Restauración requiere prueba separada.

Pruebas necesarias: reglas de dominio, API/RBAC, PostgreSQL para aislamiento,
concurrencia/idempotencia/atomicidad y recorrido del portal. Fakes acreditan
contratos locales; smoke WhatsApp acredita el canal externo por separado.
Diagnóstico: correlación de request/recurso/actor, errores estructurados sin PII;
ante escritura incierta consultar resultado por clave antes de reintentar.

## Continuidad

Siguiente trabajo: revalidar master remoto y desplegado cuando exista acceso,
revisar capacidades del panel y resolver las restricciones de cuenta/transporte;
después convertir este diseño en el PRD/ADR y cambio aislado del incremento 1.
No hay estimación ni porcentaje de avance global. No se decidió conectar CRM/ERP
externo, cambiar hosting ni activar comercialmente el piloto. Si aparecen esas
decisiones, definir autoridad de datos, costo y comportamiento antes de ejecutarlas.
