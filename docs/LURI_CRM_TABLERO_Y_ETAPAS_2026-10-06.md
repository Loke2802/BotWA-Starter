# Luri CRM: tablero y configuración de etapas — 06/10/2026

Implementación local en `codex/luri-crm-increment-1`, sobre `d1f7564`.
Conserva los incrementos anteriores y el checkout original. No requiere DigitalOcean.
No se ha desplegado, publicado ni enviado mensajes o peticiones a modelos externos.

## Qué cambia

- **Tablero comercial**: una columna por etapa, incluidas ganadas y perdidas;
  totales por columna, filtro por responsable, diez tarjetas por página y
  paginación independiente. Desplazamiento horizontal para ver todas las columnas.
- Cada tarjeta abre la ficha existente, el editor existente y el historial existente.
  Cambiar etapa requiere guardar en el editor; ganar/perder exige motivo de cierre.
  Reabrir exige próxima acción con fecha o motivo sin acción, como el resto del CRM.
- **Etapas comerciales**: propietario/administrador puede renombrar, subir/bajar
  y añadir etapas abiertas, hasta treinta. Los códigos y tipos existentes se conservan.
  Las etapas existentes no se eliminan desde este editor.
- El panel envía `expected_stages` con la configuración leída. Bajo el bloqueo
  de empresa existente, una copia antigua recibe 409 antes de modificar datos/auditar.
  La API anterior sigue aceptando clientes sin esta propiedad por compatibilidad;
  esos clientes conservan la semántica anterior y no tienen protección de copia antigua.
- Códigos y posiciones duplicados se rechazan; el panel conserva un borrador
  corregible ante duplicado/conflicto. Ediciones de oportunidades mantienen su versión.
- Listado de oportunidades y etapas comprueban además que la empresa está activa.
  Viewer recibe contenido restringido; escribir/configurar sigue protegido en servidor.

## Responsabilidades y persistencia

`app/portal/board.js` organiza consultas paginadas y tarjetas. `stages.js` gestiona
el borrador y configuración. `opportunities.js` conserva toda la edición comercial,
validación de acción/cierre, claves de creación y conflictos de versión.
El tablero reutiliza GET oportunidades/etapas/responsables y el reloj/zona de seguimiento.
No crea ventas al moverlas ni duplica CRM, IA, permisos, auditoría o almacenamiento.

`StageConfiguration` valida la configuración; `OpportunityService` compara la copia
bajo bloqueo y realiza el commit con la auditoría existente. No hay migración nueva:
el esquema sigue en `20261006_0028` y usa las tablas existentes.
El historial comercial conserva códigos; muestra los nombres actualmente configurados.
La auditoría de configuración existente registra actor/empresa/acción, sin introducir
un historial completo de nombres de etapa.

La primera suite completa detectó una regresión histórica: `MessageRepository.list`
no fijaba orden y los índices podían invertir mensajes. Se añadió orden explícito
`created_at, id`; la prueba usa fechas distintas e identificadores en orden inverso
para verificar cronología. No se cambia el transporte ni se realizan llamadas de IA.

## Validación ejecutada

- API focalizada: **24 aprobadas**, incluida persistencia de nombres/orden/etapa nueva,
  conflicto de copia antigua, rechazo de posiciones duplicadas, aislamiento de empresa,
  cierre/reapertura y versiones de historial.
- PostgreSQL local real: **4 aprobadas**, con carreras de creación/edición/configuración
  y constraints de empresa. Dos configuraciones simultáneas: una guardada, una 409.
- Interfaz en navegador, API ficticia: **29 aprobadas** (9 tablero/etapas, 8 seguimiento,
  5 oportunidades desde conversación, 7 conversaciones).
- HTTP autenticado con PostgreSQL, sin overrides de autenticación: **aprobado** para
  propietario, operador, viewer y otra empresa; 401 sin sesión, 403 ajeno,
  viewer restringido y PUT de etapas denegado a operador/viewer. La otra empresa
  tiene cero oportunidades; las tres ventas originales se conservan.
- Recorrido de navegador real: propietario movió la propuesta de oferta a decisión,
  confirmación visible y versión **6** persistida con las cinco anteriores; abrió
  la ficha del cliente desde la tarjeta; renombró `new` a «Primer contacto»;
  segunda sesión recibió 409 y conservó borrador; viewer vio contenido restringido
  y acceso denegado al editor de etapas.
- Ruff, Black, mypy y sintaxis Node: **aprobados**. Git diff sin errores de espacios.
- Suite completa final: **1065 aprobadas, 66 omitidas, 1 aviso** en 298,57 s.
  Aviso de deprecación de Starlette/TestClient con httpx.

La primera ejecución completa tuvo **1 fallo, 1064 aprobadas y 65 omitidas**.
El fallo de orden del historial se corrigió antes de repetir la suite; la nueva prueba
PostgreSQL añadida se omite en la ejecución general si no se declara su URL explícita.
Las pruebas omitidas no equivalen a validación externa aprobada.

Evidencia: `docs/validacion-local/board-authorized-http.json`, `board-owner.jpg`,
`board-history.jpg`, `board-viewer.jpg`, `stages-conflict.jpg`.

## Comprobar en el panel local

1. Abrir `http://127.0.0.1:8766/portal`. Entrar con
   `organization_owner@local-crm.example.test`, contraseña sintética `SyntheticCRM2026!`.
2. Ir a **Tablero comercial**. Ver las etapas; deslizar horizontalmente para las últimas.
   Filtrar responsable. Abrir ficha y volver al tablero.
3. **Editar oportunidad** → elegir etapa/responsable/acción y fecha → guardar.
   Comprobar tarjeta en la columna elegida y **Ver historial**. Ganada/perdida pide motivo.
4. **Etapas comerciales** → cambiar nombre/subir/bajar/añadir abierta → guardar.
   Volver al tablero y comprobar los nombres y orden, conservando las oportunidades.
5. Abrir etapas en dos sesiones del propietario. Guardar una y luego la copia antigua:
   debe mostrar conflicto; actualizar y revisar antes de volver a guardar.
6. Con `viewer@local-crm.example.test` (misma contraseña sintética), comprobar tarjetas
   restringidas, ausencia de edición y configuración denegada. Con `operator@local-crm.example.test`
   puede editar oportunidades pero no etapas. Otra empresa: `other-company@local-crm.example.test`.

Si el servidor local se detiene, desde el worktree y con el PostgreSQL sintético activo:

```powershell
& 'D:/BotWA Starter/.venv/Scripts/python.exe' -m scripts.serve_crm_local --manifest docs/validacion-local/recovery.json
```

Los comandos de recuperación/inicio del contenedor figuran en la entrega local anterior.
`scripts.verify_crm_board_local` verifica el estado sintético grabado tras este recorrido
(propuesta en decisión, versión 6), no es un monitor genérico de producción.

## Pendientes y límites

Implementado y validado localmente con datos sintéticos. Pendientes: despliegue,
validación en staging/producción, usuarios reales, WhatsApp/IA reales y carga con volumen
representativo. El tablero usa una consulta paginada por etapa (máximo treinta);
conviene medir esa carga antes de optimizar para empresas grandes.
No incorpora arrastrar tarjetas, ficha comercial ampliada ni métricas por importe/periodo;
esos son incrementos posteriores. El cambio de etapa ya funciona por el editor revisable.
No se ha hecho push, PR, merge ni alterado el checkout principal.
