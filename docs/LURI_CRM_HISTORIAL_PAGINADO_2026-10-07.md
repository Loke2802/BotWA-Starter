# Luri CRM — historial completo y paginación estable

07/10/2026. Rama `codex/luri-crm-history-pagination`, basada en `08c81c6`.
Incluye los cambios anteriores de rendimiento y autorización. Implementación
local; no despliegue ni DigitalOcean.

## Problema y resultado

El panel sólo mostraba las últimas 20 versiones de una oportunidad. El ensayo
sostenido produjo 201 versiones persistidas, pero la original no era accesible
desde ese control. Ahora **Ver historial** permite recorrer todas las páginas,
volver hacia versiones recientes y **Actualizar historial** para incluir cambios
nuevos. Conversación, ficha, tablero y agenda reutilizan el mismo módulo.

`app/portal/opportunity-history.js` se ocupa de cargar y presentar snapshots.
`opportunities.js` conserva creación, edición, vinculación y sus claves
idempotentes. El historial no tiene comandos de escritura ni genera otro estado
comercial. Escapa los datos mostrados, mantiene controles y mensaje de carga,
conserva la página anterior ante fallos y permite reintentar. Descarta respuestas
antiguas al cambiar de empresa/cerrar la ficha o abrir un editor. Cada contexto
conserva su propia página; ficha y conversación pueden estar abiertas sin mezclarse.

## API y estabilidad de las páginas

El endpoint existente `/crm/opportunities/{id}/history` sigue devolviendo la
misma lista y conserva `page`/`page_size`. Añade `through_version` opcional,
entero positivo acotado, aplicado por el repositorio junto al filtro de empresa
y oportunidad. El servicio comprueba permiso, pertenencia y existencia antes
de leer el historial; la redacción de viewer sigue vigente. Sin el parámetro,
la conducta anterior se mantiene.

El panel toma como referencia la mayor versión de su primera página y conserva
ese límite al navegar. Una edición posterior no desplaza los resultados ni hace
repetir/saltar snapshots. **Actualizar historial** vuelve a la página 1 y toma
una referencia nueva. Esto depende del historial inmutable y de versiones
crecientes existentes, no de una copia en memoria del historial completo.

Cada página muestra 20 versiones. Si está completa, una consulta adicional de
una fila comprueba si queda alguna anterior; evita ofrecer una página vacía cuando
el total es múltiplo de 20. No añade un conteo total supuesto a la API. No requiere
una nueva migración: debe existir `0032` del incremento anterior.

## Pruebas y evidencia

- Suite final: **1128 aprobadas, 68 omitidas, una advertencia**, 421.36 s.
- PostgreSQL: **7 aprobadas** (6 de oportunidades y una de clientes).
- Dirigidas de API, autorización y assets: **8 aprobadas**.
- Navegador con API simulada: **50 aprobadas**, incluidas las ocho nuevas de
  historial y 42 de conversación, creación, tablero/etapas, ficha y agenda.
- Ruff aprobado; Black: 597 archivos sin cambios. Mypy: 576 archivos en
  `app tests` y 430 en `app scripts`. `git diff --check` aprobado.

Las omisiones no acreditan validación. La advertencia existente es la deprecación
Starlette/httpx. Un primer intento de la suite se interrumpió: una prueba histórica
intentaba PostgreSQL:5432 por falta de `BOTWA_TEST_DATABASE_URL`. La ejecución
final fijó ambos selectores SQLite; PostgreSQL se comprobó por separado con
`BOTWA_CRM_POSTGRES_URL` explícito en la base ficticia. No se cuenta la ejecución
interrumpida ni una selección PostgreSQL omitida como prueba aprobada.

La prueba de API introduce una nueva edición después de leer la primera página;
con la referencia anterior recupera las versiones 7..1 sin repeticiones y, al
actualizar, obtiene la 8. Comprueba límite mínimo, viewer redactado y UUID ajeno.
Las ocho de navegador cubren 41 versiones, edición entre páginas, total exacto
de 40, historial vacío, fallo recuperable, cambio de empresa, editor que invalida
una respuesta pendiente y lecturas acotadas sin escritura.

Además se comprobó el panel **con login normal y PostgreSQL**, sobre la copia
del ensayo sostenido: oportunidad `Concurrencia local 81f6bb1c`, etapa Oferta
presentada, próxima acción con fecha y 49.50 PEN persistidos. Se recorrieron las
once páginas, desde versión 201 hasta la original 1: **201 versiones distintas,
en orden, sin faltantes**. La página 11 deshabilitó versiones anteriores.
Desde la ficha se comprobaron página 1 (201..182) y página 2 (181..162), mientras
la conversación mantuvo su página 11 y versión original. No aparecieron errores
de consola en esa demo. Después del login, el recorrido comercial fue de lectura:
no añadió oportunidades, acciones ni snapshots. Los archivos de evidencia del
ensayo permanecen intactos; el login conserva su registro normal de acceso.

- [Versiones visibles y contextos independientes](validacion-local/history-browser.json).
- [Resultados de las 50 pruebas del panel](validacion-local/history-portal-regressions.json).
- [Captura de la versión original](validacion-local/history-original-browser.png).
- [Carga sostenida y comprobación SQL/reinicio](validacion-local/performance-sustained-authorized-http.json).

## Comprobar el recorrido en el panel

Demo actual: <http://127.0.0.1:8778/portal>. Cuenta ficticia
`organization_owner@local-crm.example.test`, clave `SyntheticCRM2026!`.

1. **Conversaciones** → abrir `***0147`.
2. En `Concurrencia local 81f6bb1c`, **Ver historial**: versión 201 y página 1.
3. **Versiones anteriores** recorre hasta la página 11, versión 1 y acción
   inicial. **Versiones más recientes** permite volver.
4. **Actualizar historial** regresa al comienzo e incluye ediciones nuevas.
5. **Abrir ficha del cliente** → la misma oportunidad → **Ver historial**.
   Sus controles son independientes de la conversación.
6. Para editar o crear una oportunidad, usar los controles existentes y elegir
   responsable, etapa y próxima acción con fecha. Las modificaciones se guardan
   sólo al enviar el formulario; el historial se mantiene en la API.

Si el servidor se detiene, con 8778 libre y el contenedor local activo:

```powershell
Set-Location 'D:\BotWA Starter\.worktrees\luri-crm-increment-1'
& 'D:\BotWA Starter\.venv\Scripts\python.exe' -m scripts.serve_crm_local --manifest docs/validacion-local/performance-sustained-recovery.json --port 8778
```

Las bases ficticias de esta máquina no están en Git. Para generar nuevas, repetir
el recorrido y ensayo sostenido de los informes anteriores. El servidor temporal
de fixtures se detiene al terminar; la demo de 8778 queda disponible.

## Entrega y pendientes

Commits previos: `9f3c333` (rendimiento) y `08c81c6` (autorización). La rama
actual añade historial y contiene ambos; el checkout original conserva sus
cambios. No se ha enviado a un remoto ni desplegado.

La carga local pasó 902.823 s y 1608 solicitudes, con 200 conflictos esperados,
201 snapshots y persistencia tras reinicio. Quedan picos iniciales de unos nueve
segundos, coste de búsquedas amplias y dimensionamiento con más usuarios/carga
abierta. Faltan entorno definitivo, migración/reconstrucción, piloto real, custodia
de claves y validación externa de IA/WhatsApp. Las pruebas locales y el navegador
con datos ficticios no sustituyen ese despliegue ni una validación con clientes reales.
