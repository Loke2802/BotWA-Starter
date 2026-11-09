# PRD-024 — Bandeja Unificada Multi-WhatsApp

## Objetivo

Convertir la vista de conversaciones de Luri en una bandeja operativa capaz de reunir
las conversaciones de múltiples números de WhatsApp de una misma empresa y permitir
que el equipo encuentre rápidamente lo que necesita sin cambiar de teléfono, sesión
ni aplicación.

Kalivur debe usar esta capacidad internamente y ofrecerla a sus clientes como parte
de Luri.

## Principios

1. Una sola bandeja por empresa.
2. Cada conversación conserva la identidad de la línea de WhatsApp que la recibió.
3. El aislamiento multi-tenant existente no se debilita: una empresa cliente nunca
   puede ver conversaciones de otra.
4. Los permisos del backend siguen siendo la autoridad para lectura, contenido,
   handoff y respuesta.
5. La bandeja debe seguir siendo útil cuando una empresa pase de 1 a decenas de
   números.

## Alcance de esta primera entrega

- Listar juntas las conversaciones de todas las configuraciones de WhatsApp del
  tenant activo.
- Mostrar en cada fila la línea/configuración de WhatsApp correspondiente.
- Filtrar por:
  - línea de WhatsApp;
  - estado de conversación: abierta, cerrada o archivada;
  - teléfono/identificador exacto del cliente.
- Mantener los filtros durante la paginación.
- Mostrar la línea también en el detalle de la conversación.
- Mantener historial, handoff humano, respuesta manual, idempotencia y RBAC actuales.
- No requiere migración: Conversation ya conserva channel_configuration_id.

## API

GET /organizations/{organization_id}/conversations

Nuevo parámetro opcional:

- channel_configuration_id: UUID

El filtro es adicional a los ya existentes: bot_id, channel_type, status,
external_customer_id, has_inbound y has_outbound.

ConversationSummary expone channel_configuration_id para que el portal pueda
identificar la línea sin consultar el detalle individual de cada conversación.

## UX

La vista principal se denomina “Bandeja de conversaciones”.

Filtros visibles al inicio:

- Todos los números / línea específica.
- Todos / Abiertas / Cerradas / Archivadas.
- Cliente / teléfono.
- Aplicar filtros.
- Limpiar.

Cada conversación muestra:

- cliente enmascarado;
- estado;
- cantidad de mensajes;
- línea de WhatsApp;
- última actividad;
- acceso al detalle.

## Seguridad

- El listado continúa scoped por organization_id.
- El selector de líneas solo consulta bots y configuraciones accesibles por el
  usuario autenticado.
- El contenido de mensajes continúa protegido por conversation.read_content.
- No se exponen access tokens, verify tokens ni app secrets.
- La respuesta humana sigue requiriendo handoff y los permisos existentes.

## Evolución prevista

Siguientes incrementos, sin bloquear esta entrega:

- filtros por asignado, estado de handoff y “requiere humano”;
- no leídos y menciones;
- búsqueda por nombre/contacto;
- etiquetas y vistas guardadas;
- prioridades y SLA;
- bandejas personales “Mías”, “Sin asignar” y “Luri”;
- selección masiva y acciones por lote;
- métricas por número;
- modo plataforma para administración Kalivur entre tenants sin romper el
  aislamiento de los clientes;
- incorporación de Instagram, Messenger, webchat y correo bajo el mismo patrón de
  canal, cuando se priorice omnicanalidad.

## Criterios de aceptación

1. Dos números de WhatsApp activos en la misma empresa aparecen en una sola bandeja.
2. Se puede elegir “Todos los números” o una línea concreta.
3. El filtro de línea se aplica en servidor, no solo visualmente.
4. La línea correcta aparece en listado y detalle.
5. Los filtros sobreviven a Anterior/Siguiente.
6. Un usuario sin permiso de contenido no obtiene el texto de mensajes.
7. Las acciones de handoff y envío conservan el comportamiento e idempotencia actual.
8. No hay cambios de esquema de base de datos en esta entrega.
