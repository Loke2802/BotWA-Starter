# Luri CRM — recorrido integral local reproducible

06/10/2026. Rama `codex/luri-crm-increment-1`, commits previos conservados.
Este incremento añade pruebas ejecutables y evidencia; no modifica la lógica del
CRM, no requiere otra migración y no realiza despliegue.

La [ampliación posterior de búsqueda y duplicados](LURI_CRM_BUSQUEDA_GLOBAL_DUPLICADOS_2026-10-06.md)
extiende el mismo comando: añade 10 000 contactos ficticios cifrados y verifica
búsqueda global, permisos y duplicados completos antes y después del reinicio.
Los resultados originales descritos abajo se conservan como evidencia histórica.

## Ejecutar con un comando

Requisitos: Docker Desktop activo, el contenedor local existente
`luri-crm-local-recovery` con PostgreSQL y su puerto `127.0.0.1:15437`, el entorno
Python del proyecto y el puerto `8770` libre. No instala ni descarga servicios.
Desde el checkout independiente:

```powershell
Set-Location 'D:\BotWA Starter\.worktrees\luri-crm-increment-1'
& 'D:\BotWA Starter\.venv\Scripts\python.exe' -m scripts.rehearse_crm_journey_local --container luri-crm-local-recovery --output-dir docs/validacion-local/journey
```

Puede cambiarse `--server-port` y `--database-port`; la preparación comprueba que
PostgreSQL esté vinculado a localhost en el puerto indicado. Si el puerto del
servidor está ocupado, rechaza la ejecución y no detiene el proceso que lo ocupa.

Cada ejecución crea bases ficticias con nombres únicos y una carpeta de evidencia
con fecha. Conserva tanto los resultados aprobados como los fallidos. No elimina
bases ni modifica la demo anterior de `8766`. El servidor temporal del recorrido
se detiene al terminar, incluso ante un error; solo controla el proceso que creó.

## Recorrido y comprobaciones

1. Reutiliza el ensayo de migración/backup/restauración con datos anteriores al
   CRM y obtiene una base PostgreSQL restaurada en el esquema `0030`.
2. Arranca la aplicación en localhost, con IA apagada, autenticación normal y
   cuatro usuarios ficticios: owner, operador, viewer y otra empresa.
3. Comprueba entrada sin sesión denegada, assets del panel disponibles,
   conversación → contexto comercial → cliente existente → ficha con conversación.
4. Dos solicitudes HTTP simultáneas crean la misma oportunidad con una clave:
   debe haber un solo ID, un vínculo con la conversación y una acción vencida.
   Un cuerpo distinto con esa clave debe producir conflicto.
5. Owner y operador compiten por la misma versión. Una respuesta debe ser `200`
   y la otra `409`; solo queda versión 2, en Oferta, con la primera acción completada
   y la siguiente programada. No cambia importe ni responsable.
6. Registra una llamada vinculada. Repetir el mismo cuerpo/clave conserva su ID;
   cambiar el cuerpo con esa clave devuelve `409`.
7. Cierra la oportunidad como Ganada, completa la segunda acción y comprueba
   las versiones 1/2/3 del historial, la llamada y los dos registros de acción.
8. Consulta métricas desde el inicio del recorrido: exactamente un cierre ganado,
   cero perdidos, 195.75 PEN, conversión 100% y tiempo registrado en Nueva/Oferta.
9. Viewer recibe contenido restringido y no puede crear, editar ni registrar
   actividades. Otra empresa recibe `403` en la ruta ajena y `404` para ese ID en
   su propia ruta; sus métricas permanecen vacías. Las denegaciones no cambian
   la venta ni su historial.
10. Consulta directamente PostgreSQL: versión y etapa final, 3 snapshots, 2
    acciones, 1 actividad y 1 vínculo, todos por empresa y oportunidad; título
    comercial almacenado cifrado.
11. Detiene y reinicia el servidor contra la misma base; vuelve a iniciar sesión
    normalmente y repite detalle, historial, actividades, métricas, reintento de
    creación y comprobación de filas. Debe conservar exactamente los resultados.

El historial se comprueba en orden cronológico sin asumir el orden de presentación
de la API, que devuelve primero los cambios recientes.

## Código y evidencia

- `scripts/rehearse_crm_journey_local.py`: prepara la base, controla únicamente
  su servidor, reinicia y guarda el resultado; código de salida distinto de cero
  ante un fallo.
- `scripts/verify_crm_journey_local.py`: recorrido autenticado HTTP, concurrencia,
  permisos, métricas y comprobación SQL. Rechaza destinos remotos, redirecciones,
  credenciales en URL y manifiestos/cuentas fuera del ensayo ficticio.
- `tests/test_crm_journey_runner.py`: 11 casos de destinos/manifiestos rechazados
  y respuesta HTTP inesperada, sin exportar su contenido sensible.
- Evidencia de ejecución aprobada:
  [journey-authorized-http.json](validacion-local/journey-authorized-http.json).
- Manifiesto y huellas de backup/restauración:
  [journey-recovery.json](validacion-local/journey-recovery.json).

La carpeta de cada ejecución contiene `preparation.log`, `server.log`, `recovery.json`
y `journey.json`. Los informes no incluyen contraseñas ni tokens bearer. Contienen
solo datos ficticios del recorrido. La carpeta dinámica está excluida de Git; se
entregan copias estables de la ejecución aprobada. Si falla, el informe identifica
la etapa y conserva los controles alcanzados; consultar el log correspondiente.

Verificación ejecutada: recorrido HTTP/SQL y reinicio aprobados; 11 pruebas del
ejecutor aprobadas; Ruff, Black, mypy y `git diff --check` aprobados. El ensayo de
preparación conserva la advertencia de deprecación Starlette/httpx ya existente.
No se repitió la suite completa anterior: la aplicación no cambió en este incremento.

## Comprobar la ejecución en el panel

Se comprobó la interfaz contra la misma base del recorrido, con autenticación
normal y sin API simulada. La automatización del comando cubre HTTP y PostgreSQL;
los clics del navegador se verificaron aparte. El informe indica explícitamente
`browser_automation: false`.

Panel de esta ejecución: `http://127.0.0.1:8771/portal`.
Owner ficticio: `organization_owner@local-crm.example.test`.
Clave exclusiva de demo: `SyntheticCRM2026!`.

1. **Conversaciones** → `***0147` → **Abrir ficha del cliente**.
2. Buscar **Recorrido integral local 0226a13e**, en Ganada. Consultar su historial
   con Nueva → Oferta → Ganada y las actividades/acciones completadas de la ficha.
3. **Métricas de ventas**: ver un cierre ganado, 195.75 PEN y conversión del 100%.

Evidencia visual: [acciones y llamada](validacion-local/journey-actions.png),
[historial](validacion-local/journey-history.png) y
[métricas](validacion-local/journey-metrics.png).

Para volver a abrir el panel de esa base si el servidor no está activo:

```powershell
& 'D:\BotWA Starter\.venv\Scripts\python.exe' -m scripts.serve_crm_local --manifest docs/validacion-local/journey-recovery.json --port 8771
```

Las bases son locales y se conservan para inspección; un clon del repositorio
necesita ejecutar el ensayo para crear sus propias bases. El comando de ensayo
usa por defecto `8770`, por lo que puede repetirse sin cerrar el panel en `8771`.

## Límites

Esto acredita persistencia y controles de la aplicación con PostgreSQL local y
datos ficticios. No acredita DigitalOcean, staging, carga sostenida, producción,
WhatsApp real, inferencia del proveedor IA ni uso por clientes reales. Tampoco
incluye un ejecutor autónomo de clics del navegador ni una nueva instalación de
Docker/PostgreSQL. Esos pasos siguen separados de este recorrido reproducible.
