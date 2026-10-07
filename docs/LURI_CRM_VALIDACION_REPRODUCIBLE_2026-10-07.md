# Luri CRM: validación local reproducible — 07/10/2026

Esta entrega continúa rendimiento, autorización e historial con un comando que
comprueba la calidad del código y conserva evidencia de cada fase. Reutiliza las
pruebas existentes; no cambia el producto, instala dependencias ni despliega.

## Ejecutar

Desde el checkout independiente y con las dependencias de desarrollo instaladas:

```powershell
Set-Location 'D:\BotWA Starter\.worktrees\luri-crm-increment-1'
& 'D:\BotWA Starter\.venv\Scripts\python.exe' -m scripts.check_crm_local
```

Por defecto ejecuta Ruff, Black en comprobación, mypy sobre aplicación/pruebas y
aplicación/scripts, y las pruebas `test_crm*.py`, portal y autenticación. Para la
suite completa, seguida de las siete pruebas PostgreSQL específicas del CRM:

```powershell
& 'D:\BotWA Starter\.venv\Scripts\python.exe' -m scripts.check_crm_local --suite all --postgres
```

Para el conjunto específico del CRM en un equipo con recursos limitados, la
repetición final usa un límite mayor por fase:

```powershell
& 'D:\BotWA Starter\.venv\Scripts\python.exe' -m scripts.check_crm_local --suite crm --timeout 3600 --postgres
```

PostgreSQL es opcional y requiere el contenedor ficticio ya preparado
`luri-crm-local-recovery`, con `crm_local_test`, usuario `botwa` y clave ficticia
`crm_local_test`, puerto **127.0.0.1:15437** y esquema actual. El comando verifica
el contenedor, todas las publicaciones del puerto y la revisión Alembic antes
de probarlo. `--container` y `--database-port` permiten otra instancia local con
nombre `luri-crm-local-*`; la base y credenciales siguen siendo las ficticias.
No ejecuta migraciones, restauraciones, `DROP` ni `TRUNCATE`. Los fixtures del
CRM crean y limpian sus registros sintéticos por empresa.

Las dos URLs de prueba quedan en SQLite en memoria. Se eliminan del entorno
heredado todos los selectores `BOTWA_*_POSTGRES_URL`, incluidos los PRD antiguos
que activarían limpieza global. Sólo la fase PostgreSQL activa
`BOTWA_CRM_POSTGRES_URL`, para esos dos archivos de integración. La IA externa
queda desactivada. El entorno del proceso que invoca el comando no se modifica.

## Evidencia y fallos

Cada ejecución crea una carpeta nueva en `.audit-results/crm-local/<UTC>/`, con
`quality.json` y stdout/stderr por fase. El código de salida es 1 si falla una
comprobación, el entorno PostgreSQL o la integridad del código. La evidencia
incluye revisión inicial de Git, cabecera Alembic y huella SHA-256 de los archivos
de código/configuración comprobados; un cambio durante las pruebas impide dar
el resultado por aprobado. El JSON no incluye variables de entorno ni claves.
Una revisión Git inicial no representa los cambios aún sin commit: la huella
identifica los archivos efectivamente probados.

Cada fase tiene límite de 1200 segundos, configurable con `--timeout` entre 60
y 3600 segundos. Al excederlo, el comando detiene su árbol de procesos para que
el intérprete hijo de un lanzador de Windows tampoco continúe. Necesita permiso
local para detener sus propios procesos. Un fallo de esa limpieza se registra
como fallo global y exige revisar los procesos; nunca se considera aprobado.
Las fases independientes siguen aportando diagnóstico aunque otra falle.

Las once pruebas nuevas verifican selectores y entorno, rechazo de contenedores
y puertos ajenos, publicaciones no locales, directorios de evidencia, códigos
reales de salida, logs, huellas y detención de un hijo antes de una escritura
retardada, y registro del fallo si falta la configuración antes de calcular la
huella. La primera ejecución de las diez pruebas iniciales bajo sandbox pasó
nueve y falló
la detención por restricción del entorno. Se identificó y detuvo exclusivamente
su árbol sintético; esa ejecución no se cuenta como aprobada.

El primer ensayo del comando completo también detectó `WinError 5` al acceder
al temporal compartido `pytest-of-user`. Se finalizó únicamente su pytest
identificado; el comando conservó el fallo aunque las siete pruebas PostgreSQL
pasaron. El cambio de código durante esa corrección también invalidó su huella.
La versión corregida usa `--basetemp` con dos directorios nuevos dentro de la
carpeta única de ejecución: uno para la suite y otro para PostgreSQL. Evita
heredar permisos de temporales compartidos y no reutiliza una carpeta anterior.

Una segunda ejecución completa alcanzó el límite de 1200 s en pytest: el comando
detuvo su árbol, continuó el diagnóstico PostgreSQL y guardó resultado global
fallido. No es una suite completa aprobada ni una medida de capacidad del CRM.
Mientras terminaba PostgreSQL se mejoró el registro del fallo inicial, lo que
también invalidó la huella de esa ejecución. Un intento específico posterior fue
interrumpido expresamente para corregir el control de constantes Windows
detectado por mypy para Linux. Se conserva como interrumpido, sin sumar sus
pruebas parciales. La versión corregida pasó esa comprobación de tipos para
Linux; la ejecución y detención de procesos se han probado en Windows.

- [Primer ensayo fallido](validacion-local/quality-first-failed.json).
- [Suite completa con límite excedido](validacion-local/quality-full-timed-out.json).
- [Ensayo interrumpido durante la corrección de portabilidad](validacion-local/quality-interrupted-portability.json).

El comando no ejecuta pruebas de navegador ni despliega. Las 50 comprobaciones
del panel y las 201 versiones recorridas con login normal son evidencia separada
de [historial y recorrido](LURI_CRM_HISTORIAL_PAGINADO_2026-10-07.md).

Antes de incorporar esta herramienta, la aplicación de `07aec7b` pasó la suite
completa: **1128 aprobadas, 68 omitidas y una advertencia**, en 421.36 s, además
de siete pruebas PostgreSQL. Esta entrega sólo cambia scripts, pruebas y
documentación; no modifica la aplicación. Aquella suite completa y la repetición
del nuevo comando son comprobaciones distintas. Los resultados parciales de
una repetición interrumpida o con tiempo excedido no se suman como aprobados.

## Resultado definitivo del comando

Ejecución del 07/10/2026, 06:15:20–06:39:44 UTC, con `--suite crm --timeout
3600 --postgres`: **aprobada**, código de salida 0 y código intacto durante las
comprobaciones. Las once pruebas nuevas están incluidas en las 117, no se suman
otra vez.

| Comprobación | Resultado |
| --- | --- |
| Ruff | Aprobado |
| Black | 600 archivos sin cambios |
| mypy aplicación/pruebas | 577 archivos aprobados |
| mypy aplicación/scripts | 431 archivos aprobados |
| pytest CRM, portal y autenticación | 117 aprobadas, una advertencia, 1390.38 s internos |
| pytest PostgreSQL ficticio | 7 aprobadas, una advertencia, 14.17 s internos |
| SHA-256 antes/después | Igual; integridad aprobada |

La advertencia existente es la deprecación de Starlette/FastAPI para su cliente
de pruebas `httpx`. Los tiempos de fase del JSON incluyen el arranque del
intérprete y pueden ser mayores que los tiempos internos de pytest. La huella
del código es `d68c16d12d866e685d954f2091e60f8a3c86d02e1941089a1fceb13a420bd05f`;
el commit inicial del informe es `07aec7b`, con la herramienta aún sin commit.

- [Resultado completo y comandos](validacion-local/quality-local.json).
- [Salida real de cada comprobación](validacion-local/quality-local-summary.txt).

La nueva ejecución completa con `--suite all` queda pendiente en condiciones
con recursos suficientes o con un límite mayor. La ejecución específica del
CRM aprobada y la suite completa anterior no sustituyen ese pendiente.

## Entrega y límites

La rama `codex/luri-crm-local-quality-gate` conserva `9f3c333` (rendimiento),
`08c81c6` (autorización) y `07aec7b` (historial), y añade el comando y sus pruebas.
El checkout original conserva los cambios previos; no se envió a un remoto.

La demo ficticia queda en <http://127.0.0.1:8778/portal>. Para repetir conversación
→ ficha → oportunidad → responsable, etapa y próxima acción, usar los pasos y
cuenta local del informe de historial. Las bases locales no forman parte de Git.

Después del ensayo se renovó el login normal de la cuenta ficticia y se abrió
`***0147` → `Concurrencia local 81f6bb1c`. Conservaba responsable, Oferta
presentada y acción ronda 200 con fecha. La primera página seguía hasta la
versión 201 y la última mostraba la original 1, con versiones anteriores
deshabilitadas. Se dejó esa pestaña abierta. Fue una consulta comercial: el
login conserva su registro normal de acceso y no se enviaron ediciones.
[Captura final del panel](validacion-local/quality-panel-final.png).

Durante la repetición se observaron unos 520 MB de memoria física libre en un
equipo de unos 8 GB. Una prueba aislada con temporales nuevos de Windows pasó
en 37.61 s con acceso ampliado y 39.21 s bajo sandbox; cambiar sólo el directorio
no explicó la demora. Son observaciones del entorno de pruebas, no medidas de
latencia del CRM ni prueba de una fuga. Se cerraron seis servidores de demos
anteriores creados por esta tarea y cinco de sus pestañas, conservando bases,
evidencia y el servidor/pestaña de 8778. No se detuvieron servicios ajenos.

Faltan despliegue, migración/reconstrucción del entorno definitivo, piloto con
clientes y validación externa de IA/WhatsApp. Quedan búsquedas amplias costosas,
picos iniciales del ensayo y dimensionamiento con más usuarios. Las pruebas
omitidas requieren sus entornos específicos y no acreditan validación real.
