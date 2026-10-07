# Luri CRM — nombres, duplicados y concurrencia local

06/10/2026, rama `codex/luri-crm-increment-1`. Continúa los índices exactos del
incremento anterior y conserva sus cambios. Implementación y ensayos con datos
ficticios en PostgreSQL 17 local; sin DigitalOcean, despliegue ni llamadas externas.

## Implementación

La migración aditiva `20261006_0032`, después de `0031`, crea `contact_name_state`
y `contact_name_token`. No modifica contactos, oportunidades ni historial.
Guarda HMAC SHA-256 de fragmentos de uno/dos caracteres y del nombre normalizado,
separados por empresa y propósito. El nombre permanece cifrado. Los tokens
permiten observar igualdad y frecuencia dentro de la empresa; no eliminan esa
exposición inherente a un índice protegido. Las claves foráneas compuestas y
claves primarias impiden asociaciones entre empresas y tokens repetidos.

`ContactNameIndex` obtiene candidatos en SQL y verifica la coincidencia parcial
descifrando solamente sus nombres. Conserva acentos, mayúsculas, palabras en
distinto orden y Unicode. Comprueba falsos positivos de fragmentos: `abc` no
coincide con `abbc`. Para palabras de hasta dos caracteres, el fragmento indexado
ya representa la subcadena exacta y permite contar consultas amplias sin
descifrar todos sus resultados. Las consultas largas y poco selectivas todavía
pueden requerir muchos nombres; no se promete coste constante.

`DuplicateIndex` agrupa señales protegidas en SQL y recibe solamente señales
compartidas o necesarias para comparar datos pendientes. Mantiene el orden,
los motivos, los 20 pares por página y los resultados del algoritmo anterior.
Descifra nombres de la página presentada. No fusiona contactos automáticamente:
la revisión, firma de confirmación, permisos y conservación de originales siguen
en `DuplicateService`. No hay corte de 2000 ni caché de resultados.

Ambos índices comprueban la copia del campo cifrado y el identificador de clave
contra el contacto actual. Los registros ausentes u obsoletos se consultan por
respaldo; un cambio SQL o de clave no oculta coincidencias. La comparación incluye
la señal pendiente contra un contacto indexado que antes era único. Los GET no
escriben. La sincronización comparte la transacción existente: rollback revierte
contacto e índices. La actualización sin permiso de identidad sincroniza sólo
nombre; no descifra teléfono/correo. La ficha principal sigue siendo accesible
mediante los nombres de originales unidos.

`CrmService` conserva permisos, filtros, conteo, paginación y resolución de alias.
Nombre sigue disponible al viewer; teléfono/correo exigen
`contacts.read_sensitive`. Calidad de clientes conserva sus permisos sensibles.
Owner y operador mantienen sus permisos comerciales, sin ampliar roles.

Aplicar `0032` antes de arrancar la aplicación. La reconstrucción existente
`CrmService.rebuild_search_index(org, actor)` incluye ambos índices y exige
`contacts.update` y `contacts.read_sensitive`. Procesa 256 contactos por lote y
envía los tokens de nombre en sentencias de hasta 200 filas. Los bloqueos se
mantienen hasta el commit; planificar mantenimiento y espacio adicional para
tokens. Si no se reconstruye, el respaldo conserva resultados con mayor coste.
Rotar la clave principal de identidad sigue requiriendo su procedimiento completo.

## Pruebas y evidencia

Suite general: **1113 aprobadas, 68 omitidas, una advertencia**. Las omisiones no
acreditan esos casos. Además, **7 pruebas PostgreSQL** aprobadas y **12 pruebas
dirigidas** aprobadas para nombres y protecciones del ensayo simultáneo. Las cuatro
pruebas de nombres cubren volumen mayor a 2000, descifrado limitado, falsos
fragmentos, Unicode, cambios SQL/clave, duplicados equivalentes, singleton frente
a datos pendientes, tenant, claves foráneas y rollback. La advertencia existente
es la deprecación Starlette/httpx.

Ruff y Black cubren `app`, `tests`, `scripts` y la migración nueva. Las migraciones
históricas tienen problemas previos de formato fuera del alcance de este cambio.
Mypy aprobado en `app tests` (572 archivos) y, con bases explícitas de paquetes,
en `app scripts` (427 archivos). `git diff --check` aprobado.

El recorrido HTTP previo comprueba 10 003 contactos cifrados, 10 002 principales
activos, 24 pares de duplicados, permisos, venta ganada de 195.75 PEN, acciones,
historial, reinicio y restauración. La primera consulta fría por nombre llegó a
4.324 s, mientras una repetida tras reinicio tardó 1.079 s. Son mediciones locales
individuales, no garantías de producción. El informe conserva las muestras frías.

- [Recorrido autenticado de búsqueda y recuperación](validacion-local/name-duplicates-authorized-http.json).
- [Manifiesto del recorrido restaurado](validacion-local/name-duplicates-recovery.json).
- [Concurrencia HTTP, SQL, tiempos y reinicio](validacion-local/concurrency-authorized-http.json).
- [Manifiesto de la copia usada para concurrencia](validacion-local/concurrency-recovery.json).

La comprobación final autenticada sobre la copia del ensayo encontró los mismos
24 pares en dos páginas, examinando 10 002 principales activos. Las dos páginas
tardaron juntas 2.893 s, frente a 16.992 s del primer recorrido sin índices de
nombre/duplicados. Nombre tardó 1.481 s en la primera búsqueda de esta sesión;
viewer 0.141 s. Son muestras de ejecuciones diferentes en la misma máquina,
no una comparación controlada de rendimiento. Se verificaron 10 003 estados y
320 319 tokens de nombre, y PostgreSQL rechazó dos asociaciones entre empresas.

El ensayo simultáneo final pasó 56 solicitudes en siete oleadas de ocho sesiones:
creación y seis rondas de edición. SQL confirmó una oportunidad para la clave
repetida, siete versiones, seis acciones completadas, una pendiente y un vínculo
con la conversación. Cada edición obtuvo exactamente un `200` y un `409`, sin
sobrescritura silenciosa. Viewer no pudo editar (`403`); la otra empresa no pudo
consultar el registro (`404` en su propio espacio). La venta ganada anterior
conservó íntegro su historial. Login normal tras reinicio confirmó el registro
y sus siete snapshots persistidos. Las 64 huellas coincidieron al restaurar,
antes de las escrituras intencionales, y el origen quedó intacto.

| Solicitud bajo concurrencia | Muestras | Mediana | Máximo |
| --- | ---: | ---: | ---: |
| Nombre owner | 7 | 0.763 s | 5.477 s |
| Nombre viewer | 7 | 0.730 s | 5.435 s |
| Teléfono | 7 | 0.536 s | 5.240 s |
| Correo | 7 | 0.655 s | 5.239 s |
| Primera página de duplicados | 7 | 1.618 s | 11.483 s |

Los tiempos incluyen picos iniciales; el JSON conserva todas las muestras y p95.
Con siete muestras, ese p95 equivale al máximo y no sirve para dimensionar
producción. Hubo actividad local de pruebas/panel; no fue un laboratorio aislado.
La reconstrucción de 10 003 contactos tardó 174.072 s de servicio y 193.733 s
incluyendo estadísticas y comprobaciones posteriores. `EXPLAIN ANALYZE` confirmó
`ix_contact_name_lookup` y `ix_contact_search_exact`. Este coste de mantenimiento
y el espacio de tokens deben medirse antes de desplegar.

## Repetir los ensayos

Desde este checkout, con `luri-crm-local-recovery` activo en localhost:15437:

```powershell
Set-Location 'D:\BotWA Starter\.worktrees\luri-crm-increment-1'
& 'D:\BotWA Starter\.venv\Scripts\python.exe' -m scripts.rehearse_crm_journey_local --container luri-crm-local-recovery --output-dir docs/validacion-local/journey --contact-count 10000
```

El comando crea bases ficticias nuevas y devuelve su carpeta fechada. Para
concurrencia puede usarse la evidencia estable de esta máquina:

```powershell
& 'D:\BotWA Starter\.venv\Scripts\python.exe' -m scripts.rehearse_crm_concurrency_local --container luri-crm-local-recovery --source-manifest docs/validacion-local/name-duplicates-recovery.json --source-report docs/validacion-local/name-duplicates-authorized-http.json --output-dir docs/validacion-local/concurrency --rounds 6
```

En otro equipo, usar el manifiesto restaurado y el `journey.json` generados por
el primer comando. Las bases locales no se incluyen en Git. El ensayo simultáneo
restaura una copia independiente; nunca elimina bases ni usa `--clean`. Compara
las huellas de las 64 tablas antes de las escrituras intencionales, comprueba que
el origen no cambió y refresca estadísticas. Conserva evidencia de fallos y éxitos.
Detiene únicamente su servidor temporal propio en el puerto 8775.

Ocho clientes HTTP independientes sincronizan el comienzo de cada ronda, usando
cuatro roles. Dos sesiones del mismo owner prueban creación idempotente: la clave
existente está delimitada por usuario y empresa. Owner y operador compiten luego
en ediciones que completan la acción anterior. Las otras seis solicitudes buscan
nombre/teléfono/correo/duplicados, consultan nombre como viewer y prueban acceso
desde otra empresa. Operador y viewer reciben `403` al buscar teléfono; no se
modifican permisos para hacer pasar el ensayo. Las métricas no contienen tokens
de autenticación.

## Comprobar el recorrido en el panel

Demo actual: <http://127.0.0.1:8776/portal>. Cuenta ficticia
`organization_owner@local-crm.example.test`, clave `SyntheticCRM2026!`.

1. **Clientes** → **Nombre** → buscar `perez josé` → **Aplicar filtros**: dos
   contactos, con acentos/mayúsculas y palabras en distinto orden.
2. **Calidad de clientes**: 10 002 examinados y 24 coincidencias. **Siguiente**
   muestra cuatro pares en la página 2. La unión sigue siendo una decisión manual.
3. **Conversaciones** → abrir la conversación ficticia → **Abrir ficha del cliente**:
   oportunidad `Concurrencia local 3ca67560`, etapa Oferta presentada y próxima
   acción con fecha. Su importe persistido es 49.50 PEN. Abrir **Ver historial**:
   siete versiones. La venta ganada anterior
   de 195.75 PEN conserva sus tres versiones y acciones completadas.
4. Viewer puede buscar nombre; teléfono/correo y edición permanecen restringidos.

Para volver a levantar la demo si se detiene, con 8776 libre:

```powershell
& 'D:\BotWA Starter\.venv\Scripts\python.exe' -m scripts.serve_crm_local --manifest docs/validacion-local/concurrency-recovery.json --port 8776
```

La automatización validó HTTP y filas PostgreSQL; el panel se comprueba aparte
mediante clicks con login normal. Evidencia: [búsqueda](validacion-local/name-duplicates-search.png),
[segunda página de duplicados](validacion-local/name-duplicates-quality.png).

## Pendientes

Desplegar migración y aplicación, reconstruir índices en el entorno definitivo,
medir almacenamiento y consultas frías/amplias; realizar staging/piloto con
usuarios reales, carga sostenida y más muestras para percentiles confiables;
establecer objetivos de latencia y copias externas con custodia de claves.
El ensayo breve local no acredita capacidad de producción, disponibilidad externa
ni validación real de IA/WhatsApp. No requiere contratar DigitalOcean para repetirlo.
