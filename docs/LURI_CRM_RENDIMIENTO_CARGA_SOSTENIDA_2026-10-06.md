# Luri CRM — rendimiento y carga sostenida local

06–07/10/2026. Rama `codex/luri-crm-local-performance`, basada en `4b25562`;
conserva los incrementos anteriores. PostgreSQL 17 local y datos ficticios:
10 003 contactos cifrados, 10 002 principales activos y 24 pares de duplicados.
No necesita DigitalOcean. No se ha desplegado ni llamado a IA/WhatsApp externos.

## Implementación

La búsqueda agrupa los fragmentos HMAC antes de unir los candidatos con el
estado y contacto actuales. Evita el plan que consultaba el índice de tokens
una vez por cada contacto en búsquedas amplias. Los candidatos indexados y
pendientes se combinan con `UNION ALL`, manteniendo la comprobación del campo
cifrado y la clave actual. Una consulta larga sigue verificando su coincidencia
descifrando los nombres candidatos; `contacto` requiere 9 975 nombres más los
20 nombres presentados. No se ha sustituido la coincidencia parcial por exacta.

`contact_search_ids.py` concentra el transporte de conjuntos grandes de UUID:
por encima de 200 usa un parámetro JSON ligado, expandido en SQL en PostgreSQL
y SQLite. Mantiene el filtro de empresa, sin tablas temporales ni interpolación
de valores en SQL. Los conjuntos pequeños y otros dialectos conservan `IN`.

Duplicados agrupa primero señales protegidas compartidas de la empresa y después
comprueba estado, clave, contacto activo y ausencia de unión. Los grupos iniciales
son un superconjunto: señales obsoletas/archivadas pueden añadir candidatos,
pero no pares falsos, porque sus miembros se validan antes de comparar.
El respaldo incluye la comparación de un contacto pendiente contra una señal
indexada anteriormente única. No hay límite de 2000 ni fusiones automáticas.

Autenticación y CRM comparten la sesión de base de datos de cada petición mediante
la dependencia existente de FastAPI. Evita reservar dos conexiones simultáneas
para una petición autenticada. Se comprueban de nuevo cuenta, empresa y versión
del token en cada petición; no existe caché de autorización entre peticiones.
El cierre sigue en `get_session`. No se ampliaron pool, timeouts ni permisos.

No requiere una migración adicional: la aplicación necesita `0032` del incremento
anterior. Persistencia, transacciones, snapshots, aliases y cifrado se conservan.

## Mediciones SQL

`profile_crm_queries_local.py` registra planes `EXPLAIN ANALYZE/BUFFERS`, número
de descifrados y tiempo del servicio. Tiene límites de repeticiones y acepta sólo
manifiestos sintéticos locales. No guarda parámetros, claves ni tokens de acceso.
Llama al servicio con el actor recuperado de la base; la autenticación HTTP normal
se comprueba por separado en el ensayo sostenido.

Cada repetición usa una sesión SQLAlchemy nueva, pero **no vacía buffers de
PostgreSQL ni del sistema operativo**. La primera muestra no prueba una caché
física fría. Son tres muestras por caso, con ruido local; no son un SLO ni una
comparación controlada de capacidad. El tiempo de los eventos de cursor excluye
la lectura posterior de un cursor de servidor; no debe restarse del total para
atribuir el resto exclusivamente a CPU o descifrado.

| Consulta / total | Antes: tres muestras (s) | Final: tres muestras (s) |
| --- | --- | --- |
| `perez jose` / 2 | 0.742, 0.106, 0.111 | 0.782, 0.052, 0.044 |
| `grupo marta` / 23 | 3.232, 0.406, 0.379 | 2.675, 0.569, 0.083 |
| `co` / 9 975 | 0.321, 0.401, 0.347 | 0.255, 0.199, 0.344 |
| `contacto` / 9 975 | 2.715, 2.119, 6.154 | 4.163, 3.950, 4.411 |
| Duplicados / 24 pares | 1.283, 0.386, 0.356 | 3.651, 0.350, 0.307 |

El plan de candidatos amplios pasó de 1 916.412 ms a 144.575 ms en las
capturas; desaparecieron las 10 003 consultas individuales al índice de tokens.
Esto **no equivale a mejorar siempre el tiempo completo**: `contacto` sigue
descifrando casi todos los nombres, y la primera consulta de duplicados final
fue más lenta. El JSON conserva las primeras muestras y los planes completos.

- [Perfil previo](validacion-local/performance-baseline-sql.json).
- [Perfil del código final](validacion-local/performance-final-sql.json).

## Carga sostenida

El primer intento falló con un HTTP `500`: `psycopg.errors.ConnectionTimeout`
en la consulta del usuario de la autenticación normal. Coincidió con la suite
completa y un perfil pesado ejecutándose en el mismo equipo. Esa coincidencia
no demuestra la causa. Se conserva el fallo y no se cuenta como ensayo aprobado.
La repetición usa el código final y excluye otros trabajos locales pesados.

[Evidencia del primer intento fallido](validacion-local/performance-first-failed.json).
El log completo queda en la carpeta local fechada
`performance/20261007T042827260740Z/server.log`; no se sustituye por un resultado
aprobado al repetir.

La repetición **pasó**: 902.823 s desde el comienzo de las oleadas hasta la
verificación final previa al reinicio, 201 oleadas y **1608 solicitudes de carga**,
más comprobaciones auxiliares. No hubo errores inesperados. Hubo 200 conflictos
`409` esperados, una creación idempotente, 201 versiones, 200 acciones completadas,
una pendiente y un vínculo con la conversación. SQL y login normal después del
reinicio confirmaron el registro y las tres páginas de historial. La venta ganada
anterior mantuvo íntegro su historial.

| Solicitud | Muestras | Mediana | p95 | Máximo |
| --- | ---: | ---: | ---: | ---: |
| Nombre owner | 201 | 0.3171 s | 0.5816 s | 9.0120 s |
| Nombre viewer | 201 | 0.2977 s | 0.6322 s | 9.0690 s |
| Teléfono owner | 201 | 0.3076 s | 0.5837 s | 8.9029 s |
| Correo owner | 201 | 0.3133 s | 0.6010 s | 9.1263 s |
| Primera página de duplicados | 201 | 0.5339 s | 0.9746 s | 9.5880 s |

El máximo de nombre/duplicados ocurrió en la tercera oleada. Nombre tuvo mediana
0.3688 s en las primeras 25 y 0.3413 s en las últimas 25; duplicados, 0.6556 s y
0.5478 s. Esas ventanas no mostraron aumento de mediana, pero no prueban ausencia
de fugas ni estabilidad indefinida. Los picos de unos nueve segundos siguen en
el informe y deben medirse antes de establecer un SLO. No se deriva capacidad
máxima de una carga cerrada con esperas.

- [Carga HTTP, tiempos, SQL y reinicio](validacion-local/performance-sustained-authorized-http.json).
- [Manifiesto y huellas de restauración](validacion-local/performance-sustained-recovery.json).

El ejecutor restaura una copia independiente, compara huellas de las 64 tablas
antes de sus escrituras intencionales y verifica que el origen no cambió.
La carga es cerrada y espaciada: ocho clientes HTTP por oleada, cuatro roles,
dos sesiones del mismo owner en la creación y owner/operador compitiendo en
ediciones. No representa ocho usuarios continuamente conectados ni carga abierta.
Los tiempos de solicitud excluyen las esperas intencionales entre oleadas.

El recorrido exige una sola creación idempotente, exactamente un ganador y un
`409` por ronda, acción anterior completada, una acción pendiente y un vínculo
con conversación. Verifica SQL, lecturas HTTP, rechazo a viewer/otra empresa,
historial original de la venta y persistencia tras reiniciar la API. El verificador
lee todas las páginas de historial, hasta 1001 versiones, en vez de asumir que
la primera página contiene el historial completo. Un fallo produce evidencia
fallida y detiene únicamente el servidor temporal propio; no se elimina la base.

## Pruebas ejecutadas

- Suite general: **1121 aprobadas, 68 omitidas, una advertencia**.
- PostgreSQL: **7 aprobadas**, una advertencia.
- Nombres/búsqueda/duplicados: **12 dirigidas aprobadas**.
- Sesión autenticada y protecciones del ensayo: **8 aprobadas**.
- Ruff aprobado; Black: 596 archivos sin cambios. Mypy: 575 archivos de
  `app tests` y 430 de `app scripts`, con bases explícitas de paquetes.

Las pruebas nuevas verifican equivalencia de búsquedas amplias, aislamiento del
parámetro de UUID, una petición autenticada con una sola conexión disponible,
rechazo inmediato a un token revocado, historial de 201 versiones en tres páginas,
rechazo de versiones repetidas y límites del ejecutor. No acreditan los casos
omitidos. La advertencia existente es la deprecación de Starlette/httpx.

## Repetir y comprobar

Desde el checkout y con `luri-crm-local-recovery` activo en localhost:15437:

```powershell
Set-Location 'D:\BotWA Starter\.worktrees\luri-crm-increment-1'
& 'D:\BotWA Starter\.venv\Scripts\python.exe' -m scripts.profile_crm_queries_local --manifest docs/validacion-local/concurrency-recovery.json --source-report docs/validacion-local/name-duplicates-authorized-http.json --output docs/validacion-local/performance-profile-new.json --repeats 3
& 'D:\BotWA Starter\.venv\Scripts\python.exe' -m scripts.rehearse_crm_sustained_local --container luri-crm-local-recovery --source-manifest docs/validacion-local/concurrency-recovery.json --source-report docs/validacion-local/name-duplicates-authorized-http.json --output-dir docs/validacion-local/performance --seconds 900 --rounds 200
```

Ejecutar el perfil y la carga por separado. El ejecutor guarda la evidencia en
una carpeta fechada y usa el puerto 8777. Las bases y backups locales no están
en Git. En otro equipo hay que generar primero el recorrido ficticio documentado
en el incremento anterior; un manifiesto de esta máquina no copia su base.

## Pendientes y límites

Faltan despliegue, reconstrucción de índices en el entorno definitivo, piloto con
usuarios reales y pruebas reales de IA/WhatsApp. Medir consultas amplias y frías,
más usuarios simultáneos y carga abierta antes de fijar capacidad u objetivos de
latencia. Los picos iniciales y el coste de descifrar búsquedas poco selectivas
siguen siendo límites reales. Estas pruebas locales no acreditan disponibilidad
externa ni capacidad de producción.
