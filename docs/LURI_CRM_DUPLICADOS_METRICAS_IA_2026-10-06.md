# Luri CRM — puntos 3, 4 y 5

Fecha: 06/10/2026. Rama: `codex/luri-crm-increment-1`.
Checkout independiente: `D:\BotWA Starter\.worktrees\luri-crm-increment-1`.
Los commits anteriores se conservan. El checkout principal no fue modificado.

## Cambios entregados

3. **Calidad de clientes** detecta coincidencias de nombre normalizado, teléfono
   y correo, dentro de una empresa. La entrega original examinaba hasta 2000 contactos
   principales activos; [la ampliación de búsqueda y volumen](LURI_CRM_BUSQUEDA_GLOBAL_DUPLICADOS_2026-10-06.md)
   recorre todos los activos, con paginación de resultados. Un nombre coincidente
   es una pista, no una prueba. El usuario elige la ficha principal, revisa ambas
   identidades, notas, perfiles y cantidades de registros, y confirma explícitamente.
   La unión reúne conversaciones, oportunidades y actividades en una transacción.
   Conserva IDs, versiones, vínculos, fechas, autores, notas originales, perfiles,
   mensajes e historial. El origen queda archivado y consultable desde la ficha
   principal; conserva su identidad de canal. Las operaciones CRM posteriores por
   esa identidad resuelven al principal y no duplican la ficha comercial.
   El registro de revisión está cifrado y la acción queda auditada.
4. **Métricas de ventas** muestra cierres ganados/perdidos por fecha de transición,
   responsable e importe históricos, conversión y horas en etapas abiertas.
   Conversión = ganadas / (ganadas + perdidas). Cada nueva transición a cierre
   cuenta como evento; una reapertura seguida de otro cierre puede contar otra vez.
   Editar notas de una venta cerrada no genera un cierre adicional. No son ingresos
   contables ni ventas netas únicas. Los importes se presentan por moneda.
   El tiempo se recorta al periodo y a la hora de referencia, incluyendo etapas
   todavía abiertas; las visitas repetidas a una etapa se acumulan por oportunidad.
   Solo usa el historial registrado, sin reconstruir fechas inexistentes.
   El resumen anterior sigue mostrando oportunidades creadas en el periodo por
   su etapa actual; ambas vistas responden preguntas distintas.
5. **IA sobre oportunidades existentes** permite elegir una venta abierta desde
   la ficha, contrastar necesidad/etapa/acción actuales con la propuesta y revisar
   evidencia de la memoria IA existente. Usar el borrador abre el editor compartido;
   no guarda automáticamente. Conserva importe y responsable, exige revisar fecha
   y usa la versión de la oportunidad para rechazar cambios concurrentes.
   No produce nuevas llamadas al proveedor ni otro motor IA. Sin memoria válida,
   con IA apagada o sin evidencia suficiente, se abstiene. Los cierres se revisan
   manualmente, fuera de esta sugerencia.

## Responsabilidades y acceso

`app/application/crm/duplicates.py` dirige revisión, unión y transacción;
`app/infrastructure/repositories/crm_identity.py` resuelve identidad comercial;
`app/application/crm/sales_metrics.py` calcula métricas de snapshots históricos;
`app/application/crm/suggestions.py` reutiliza las sugerencias existentes.
Contratos tipados en `growth_contracts.py`, rutas en `crm_opportunity_routes.py` y
vistas separadas `customer-quality.js`, `sales-metrics.js`, `customer-workspace.js`.

La unión requiere escritura CRM y permisos de lectura sensible, actualización
y archivo de contactos. Operador y viewer no obtienen vistas privadas de unión.
El viewer puede consultar métricas permitidas sin importes ni moneda. Las rutas,
consultas y claves compuestas mantienen el aislamiento por empresa. Una revisión
obsoleta devuelve conflicto; repetir la misma unión devuelve el resultado guardado.

## Esquema y recuperación

Migración aditiva `20261006_0030`, hija de `0029`: tabla `crm_contact_merge`,
con claves compuestas de origen/principal y empresa. `alembic upgrade head` y
`alembic check` se comprobaron con PostgreSQL local. Si existen uniones, el downgrade
que borraría su evidencia se rechaza; conservar esquema y revertir aplicación.
No se ofrece deshacer una unión desde el panel. Una identificación equivocada
necesita revisión y recuperación controlada; verificar identidades antes de confirmar.

El ensayo corregido siembra datos históricos sin llamar código dependiente del
esquema nuevo. Backup y restauración antes/después verificaron huellas de todas las
tablas, conservación de datos existentes, historial e idempotencia, incluida una
unión restaurada. Evidencia: [growth-recovery.json](validacion-local/growth-recovery.json).
Las bases son ficticias y locales; esto no acredita un backup de producción.

## Verificación ejecutada

- Suite Python completa: 1077 aprobadas, 68 omitidas y 1 advertencia.
- 28 pruebas focalizadas de regresión: aprobadas, incluido
  fallo posterior a todas las escrituras y rollback de vínculos/actividades.
- Tras conservar explícitamente los metadatos de transporte de las conversaciones,
  se repitieron las 4 pruebas de crecimiento y las 6 de PostgreSQL. La atribución
  comercial cambia; identificadores, destinatario y fechas de transporte permanecen.
- 6 pruebas PostgreSQL: aprobadas, incluida unión simultánea desde dos sesiones.
- 48 pruebas de interfaz en navegador: 6 calidad/métricas, 11 ficha/IA/resumen,
  9 tablero, 10 agenda, 5 oportunidades, 7 conversaciones. Usan API simulada.
- HTTP con autenticación normal y PostgreSQL: owner, operador, viewer y otra
  empresa; unión/reintento, historial/notas, métricas, contenido restringido,
  aislamiento y sugerencia contra otro cliente. También se repitió el recorrido
  HTTP previo de ficha, actividades, resumen y abstención IA.
- Panel local con API real: creación ficticia, revisión y unión manual guardada,
  ficha original consultable y métricas del cierre de 80 PEN.
- Ruff, Black, mypy, sintaxis JS y `git diff --check`: aprobados.

La suite presenta una advertencia de deprecación de Starlette/httpx. Las pruebas
omitidas necesitan integraciones explícitas; no equivalen a validación externa.
La propuesta positiva IA se comprobó con memoria y proveedor simulados. En el
panel autenticado la IA está apagada y se verificó abstención, no inferencia real.

Evidencias: [HTTP](validacion-local/growth-authorized-http.json),
[revisión manual](validacion-local/growth-merge-review.png),
[unión guardada](validacion-local/growth-merge-saved.png),
[métricas](validacion-local/growth-sales-metrics.png).

## Comprobar en el panel

1. Abrir `http://127.0.0.1:8766/portal`. Cuenta ficticia owner:
   `organization_owner@local-crm.example.test`, clave de demo `SyntheticCRM2026!`.
2. En **Clientes**, abrir **Cliente duplicado de prueba HTTP**. Ver la oportunidad
   ganada y **Fichas originales conservadas**; abrir un original para consultar sus
   notas y volver mediante **Abrir ficha principal**. Las uniones de demo ya están
   realizadas. Para repetir la revisión, crear otro contacto ficticio de igual nombre
   con teléfono distinto; revisar identidades en **Calidad de clientes**.
3. En **Métricas de ventas**, seleccionar periodo y responsable. El cierre ficticio
   muestra 80 PEN y conversión del 100%; comparar con el historial de esa venta.
4. En **Conversaciones**, abrir la conversación de **Synthetic client** y su ficha.
   Elegir la conversación y una oportunidad abierta en **Aplicar sugerencia a**.
   Consultar IA: en esta demo aparece abstención por IA apagada. El flujo positivo
   de revisión, versión y conservación de campos se puede comprobar en
   `http://127.0.0.1:8765/tests/portal_crm_customer_workspace.html` (API simulada).
5. Repetir con viewer y operador, usando sus cuentas del manifiesto de recuperación,
   y comprobar restricciones; otra empresa no accede a estos clientes.

Reiniciar servidor de la demo existente desde el checkout independiente:

```powershell
& 'D:\BotWA Starter\.venv\Scripts\python.exe' -m scripts.serve_crm_local --manifest docs/validacion-local/customer-recovery.json
```

Repetir comprobación HTTP del incremento:

```powershell
& 'D:\BotWA Starter\.venv\Scripts\python.exe' -m scripts.verify_crm_growth_local --base-url http://127.0.0.1:8766 --manifest docs/validacion-local/customer-recovery.json --state docs/validacion-local/growth-http-state.json --output docs/validacion-local/growth-authorized-http.json
```

## Pendientes de despliegue y validación real

No se desplegó ni se contrató DigitalOcean. Quedan infraestructura y staging,
backup/migración con datos reales, prueba de carga concurrente e índices cifrados
para volúmenes mayores. El corte de 2000 ya fue eliminado en la ampliación. También falta
validar la IA habilitada con su proveedor y memoria reales, WhatsApp real y un
piloto con usuarios. El trabajo local no acredita esos pasos ni autoriza publicar.
