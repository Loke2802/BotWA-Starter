# Luri CRM — regresión completa local y preparación de pruebas

07/10/2026. Rama `codex/luri-crm-final-local-regression`, desde `cdeb68b`.
Conserva rendimiento (`9f3c333`), autorización (`08c81c6`), historial paginado
(`07aec7b`), herramienta de validación (`916d236`) y mejora móvil (`cdeb68b`).
`eb38622` añade la preparación del esquema SQLite para las pruebas. El checkout
original conserva sus cambios. No hay despliegue, DigitalOcean ni envíos reales
a IA o WhatsApp.

## Diagnóstico y ejecución parcial conservada

La repetición completa `20261007T131501618707Z`, sobre `cdeb68b`, pasó Ruff,
Black y tipos. Se detuvo su proceso pytest propio después de 829.98 segundos
para resolver la preparación repetida de esquemas; no alcanzó el límite de
3600 segundos ni completó la suite. La herramienta registró `failed` y terminó
con código 1. El código permaneció igual durante sus controles. Después de
detener pytest, aprobaron las siete pruebas PostgreSQL en 15.89 s internos
(23.257 s de fase). Ese resultado parcial no acredita una suite completa.
[Registro de la ejecución parcial](validacion-local/quality-later-partial.json).

En un diagnóstico aparte, dos bases vacías de 63 tablas tardaron 50.02 y
51.39 segundos en ejecutar `Base.metadata.create_all`. Copiar una de esas
bases cerradas tardó 0.204 segundos y la copia conservó las 63 tablas.
El diagnóstico coincidió con la suite; los tiempos incluyen esa circunstancia.
Son medidas de preparación de pruebas en este equipo, no latencia del CRM
ni identificación de una causa del sistema operativo.
[Medidas originales](validacion-local/sqlite-empty-schema-baseline.json).

## Implementación de la preparación

`tests/sqlite_schema_support.py` crea una plantilla vacía por definición SQL
del esquema SQLite. La huella incluye tablas, restricciones e índices. Un
cambio en tablas o índices genera una nueva plantilla, comprobado con una
prueba de evolución del esquema. Se cierra el motor antes de copiar y se
rechaza una plantilla con filas. La copia crea el destino de forma exclusiva:
no sobrescribe una base o evidencia retenida.

La fixture de sesión `sqlite_schema` prepara únicamente las fixtures que la
solicitan: oportunidades, autorización CRM, sesión por petición e IA simulada.
Cada caso conserva su archivo SQLite propio y siembra sus datos después de
copiar. Permanecen las sesiones independientes, reaperturas, claves foráneas,
pool de una conexión y aserciones existentes. Las pruebas de migración siguen
creando y evolucionando sus esquemas originales. Las pruebas PostgreSQL
conservan su implementación. No se cambia la sincronización o durabilidad
SQLite ni el código del producto para acelerar las comprobaciones.

Cuatro pruebas nuevas verifican aislamiento de datos y persistencia tras
reabrir, restricciones únicas y foráneas, evolución de tablas e índices,
prevención de sobrescritura y rechazo de datos sembrados. Aprobaron en 2.35 s.
Otras once comprobaciones con fixtures reales aprobaron en 84.77 s: JWT y
permisos actuales, referencias entre empresas, historial con edición concurrente,
una conexión por petición y recuperación de IA/WhatsApp ficticios. La primera
preparación tomó 37.51 s; las siguientes reutilizaron el esquema vacío. Ese
grupo se ejecutó junto al análisis de tipos y sus tiempos no constituyen un
benchmark aislado del producto.

El análisis de tipos señaló dos comparaciones de filas en las pruebas nuevas;
se ajustaron a resultados escalares y se repitieron los cuatro contratos.

## Validación final

La ejecución final usa el commit fijo `eb38622`, con código sin modificaciones
durante los controles:

```powershell
& 'D:\BotWA Starter\.venv\Scripts\python.exe' scripts/check_crm_local.py --suite all --timeout 3600 --postgres
```

La ejecución `20261007T133801147850Z` terminó con estado `passed` y código 0.
Comenzó a las 08:38:01 y terminó a las 08:47:23 del 07/10/2026, hora de Lima.
La herramienta confirmó que el código permaneció igual antes y después:
`083dfa5315bc1ae84b8613e782e3a071aa2b1268ccfef466088d8c3ceaf9d780`.

| Comprobación | Resultado | Tiempo de fase |
| --- | --- | --- |
| Ruff | aprobado | 1.126 s |
| Black | 602 archivos sin cambios | 3.638 s |
| mypy app/tests | 579 archivos, sin errores | 18.790 s |
| mypy app/scripts | 431 archivos, sin errores | 5.237 s |
| pytest completo | 1143 aprobados, 68 omitidos, 1 aviso | 502.808 s |
| pytest PostgreSQL ficticio | 7 aprobados, 1 aviso | 24.520 s |

Los tiempos internos de pytest fueron 490.86 s para la suite completa y
13.35 s para PostgreSQL. El aviso es la deprecación Starlette/httpx ya presente.
Las 68 omisiones de la suite general incluyen las siete pruebas CRM PostgreSQL
ejecutadas después con su selector específico; las demás requieren otros
entornos opcionales. No se suman las omisiones como éxitos. La herramienta
comprobó el contenedor local y su enlace exclusivo a `127.0.0.1:15437`, con
base ficticia `crm_local_test` y revisión `20261006_0032`.

- [Resultado completo, comandos y huella](validacion-local/quality-full-local.json).
- [Salidas reales de cada comprobación](validacion-local/quality-full-local-summary.txt).

Esta ejecución cierra el pendiente de repetir la validación completa de la
herramienta. La ejecución parcial y el intento anterior con límite de tiempo
permanecen conservados con sus estados originales.

Las páginas del navegador se verifican aparte de esta herramienta. La entrega
móvil aprobó 53 casos de historial, oportunidades, tablero, ficha, agenda y
conversaciones, más cuatro comprobaciones de diseño a cada ancho de 320, 390
y 768 píxeles. El panel autenticado sobre PostgreSQL mostró responsable, etapa,
acción con fecha y foco conservado al cambiar de página en conversación y ficha.
[Evidencia móvil y de teclado](LURI_CRM_ACCESIBILIDAD_HISTORIAL_MOVIL_2026-10-07.md).

## Recorrido y límites

El panel ficticio queda en <http://127.0.0.1:8778/portal>. Ir a Conversaciones,
abrir `***0147` y revisar `Concurrencia local 81f6bb1c`. Desde esa vista se abre
la ficha, el editor de oportunidad y el historial. El editor conserva responsable,
etapa y próxima acción con fecha; cancelar permite revisarlo sin guardar.
En el historial, Tab y Enter permiten navegar y comprobar que el foco permanece
en un control válido. La cuenta local y los pasos de creación/vinculación están
en el [informe del historial](LURI_CRM_HISTORIAL_PAGINADO_2026-10-07.md).

La carga sostenida anterior fue un ensayo local de 902.823 segundos, 201 olas
y 1608 peticiones de esas olas, sobre datos ficticios. Comprobó historial,
idempotencia y recuperación después de reiniciar. Las olas con ocho clientes
estaban espaciadas: no acreditan ocho clientes continuos ni capacidad de
producción. Se conservaron el primer intento fallido y los picos iniciales.
[Informe y evidencia de carga](LURI_CRM_RENDIMIENTO_CARGA_SOSTENIDA_2026-10-06.md).

Quedan dimensionamiento con más carga, búsquedas amplias costosas, lectura
con lectores de pantalla y dispositivos reales, despliegue y migración del
entorno definitivo y un piloto con clientes. La IA y WhatsApp externos siguen
pendientes de validación real. Las pruebas omitidas necesitan sus entornos
específicos; no se presentan como aprobadas.
