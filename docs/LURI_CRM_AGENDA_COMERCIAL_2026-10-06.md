# Agenda comercial de Luri

Implementación local del 06/10/2026 en `codex/luri-crm-increment-1`.
Conserva los incrementos anteriores y reutiliza el seguimiento, la ficha,
el editor de oportunidades y el historial existentes. Sin despliegue ni DigitalOcean.

La entrada «Agenda comercial» abre en **Hoy**, según la zona de la empresa.
**Vencidas** contiene acciones pendientes anteriores a la hora de referencia;
**Próximas** empieza a medianoche de mañana. Una acción vencida de hoy también
aparece en Hoy: los contadores no deben sumarse como categorías excluyentes.
Se conservan los filtros de etapa y responsable, la paginación, todas las abiertas
y las oportunidades sin acción programada. «Pendientes desde ahora» mantiene la
semántica anterior del filtro `upcoming` de la API.

Solo cuentan acciones pendientes de la versión actual de oportunidades abiertas.
Completar, sustituir o cerrar conserva historial y retira la acción antigua de la agenda.
Los límites del día se calculan en la zona de la empresa y se convierten a UTC por
separado; contemplan días con cambio de horario. Una zona heredada inválida usa UTC
tanto en la clasificación como en la etiqueta. No requiere migración nueva.

Permisos, aislamiento de empresas, cifrado y contenido restringido del viewer siguen
en las rutas existentes. El módulo del panel descarta respuestas de otra empresa.
La versión del recurso JS cambió para que una pestaña con caché cargue la nueva agenda.

## Validación ejecutada

- 15 pruebas focalizadas aprobadas de seguimiento, ficha y rutas del portal; un aviso
  de deprecación de Starlette/httpx. Incluyen medianoche en Lima, día de 23 horas en
  Madrid, extremos inclusivo/exclusivo, paginación, filtro por responsable y exclusión
  de acciones anteriores después de programar la siguiente.
- 10 pruebas de navegador con API simulada aprobadas: Hoy por defecto, Próximas,
  abrir la ficha correcta, filtros, editor/historial reutilizados, conflictos, viewer,
  escape HTML, permisos y respuestas tardías.
- HTTP autenticado con PostgreSQL local aprobado para propietario, operador, viewer
  y otra empresa; límites diarios, fechas retornadas, contadores y acceso restringido.
  Evidencia: [agenda-authorized-http.json](validacion-local/agenda-authorized-http.json).
- Recorrido normal en el panel sintético: reprogramar la propuesta desde Próximas
  a hoy, guardar, consultar Hoy y abrir la ficha. Se conserva la versión sustituida.
  Evidencia visual: [agenda-today.png](validacion-local/agenda-today.png).
- Ruff, Black, mypy, sintaxis JavaScript y `git diff --check` aprobados.

La suite general anterior de 1070 pruebas corresponde a la entrega previa; no se
declara como una nueva ejecución de toda la suite para esta mejora.

## Probar el recorrido

1. Abrir http://127.0.0.1:8766/portal con las cuentas sintéticas de la
   [guía anterior](LURI_CRM_FICHA_ACTIVIDADES_RESUMEN_IA_2026-10-06.md).
2. Agenda comercial → Hoy. La demostración del 06/10 tiene «Enviar propuesta revisada»
   a las 19:00 de Lima. Al cambiar de día aparecerá entre las vencidas.
3. Filtrar por responsable y etapa; comprobar Vencidas, Próximas y Sin acción.
4. Abrir ficha del cliente o editar oportunidad → marcar acción anterior completada
   si se realizó → programar siguiente fecha → guardar → revisar el historial.
5. Actualizar la agenda para recalcular la referencia temporal. Entrar como viewer
   para comprobar la consulta restringida y ausencia de edición.

Pendiente externo: despliegue, configuración y prueba con usuarios/datos reales.
No añade notificaciones, mensajes automáticos ni integra calendarios externos.
