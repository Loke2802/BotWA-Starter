# Historial y atención humana desde el portal

La vista Conversaciones permite abrir el detalle, recorrer las páginas del
historial y consultar el estado de los mensajes. Las acciones de atención
permiten solicitar, tomar, dejar en espera, resolver o devolver la atención a
Luri según los permisos efectivos de `/permissions/me` y la asignación vigente.
El backend sigue siendo la autoridad para permisos, aislamiento y destinatarios.

La respuesta humana está disponible para la atención activa asignada al usuario
o para los roles administrativos autorizados. Cada envío utiliza una clave de
idempotencia. Ante un fallo de conexión, reintentar el mismo texto reutiliza la
clave incluso después de recargar el portal en la misma sesión del navegador.
Solo se guarda un hash y la clave en sessionStorage, no el texto del mensaje.
El estado «Enviado al proveedor» no se presenta como confirmación de entrega.

Los datos de una solicitud tardía se descartan al cambiar de empresa o salir.
Los mensajes se muestran como texto escapado. Inicio distingue entre ausencia
de mensajes y ausencia de vista previa.

Validación local:
- 16 pruebas Python aprobadas: portal, endpoints de atención humana y gestión
  de conversaciones.
- 7 escenarios ejecutados en navegador con datos sintéticos: historial y
  paginación, escape de HTML, permisos, respuesta tardía entre vistas,
  solicitud/toma/respuesta/devolución, reintentos tras recarga y doble envío,
  asignación a otro operador, recuperación de errores y envío confirmado con
  fallo posterior al actualizar el historial.
- Comprobación de sintaxis JavaScript, Ruff, Black y git diff --check.

Para repetir las pruebas de navegador, servir la raíz del repositorio con
`python -m http.server 8765 --bind 127.0.0.1` y abrir
`http://127.0.0.1:8765/tests/portal_conversations.html`.
Las peticiones del módulo se sustituyen por respuestas sintéticas; no se usan
credenciales ni se envían mensajes reales. Las pruebas limpian sessionStorage
de ese origen local dedicado.

No requiere migración ni otro componente de infraestructura. El worker de
recuperación continúa aplazado. La prueba de entrega real de WhatsApp debe
realizarse por separado con un número controlado.
