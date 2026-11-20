# Retención y solicitudes de eliminación de Luri (operación supervisada)

Responsable del piloto: Luis Angelo Echegaray Ayo, administracion@kalivur.com.
Decisión del propietario: conversaciones y contactos, 90 días de inactividad;
memoria IA, 30 días; sin uso para marketing ni entrenamiento. Esta herramienta
implementa una operación local supervisada sobre datos atribuibles en la base de
Luri. No configura proveedores, no activa IA ni ejecuta llamadas externas.

## Alcance implementado

`python -m app.operations.contact_erasure` exige UUID de organización, bot y
contacto. Sin `--apply` produce únicamente fingerprint, recuentos por tabla y
motivos de bloqueo; no imprime nombres, teléfonos, mensajes ni ciphertext.
El modo `retention` requiere al menos 90 días desde la actividad explícita: creación/edición del
contacto, inicio/últimos mensajes de conversación, timestamps de mensajes,
recepción/envío de transporte y última actividad de handoff. El borde de 90 días
exactos es elegible. Los timestamps internos (auditoría, IA, perfil, etc.) no se
llaman interacción: si son recientes producen el bloqueo separado
`recent_related_change`. Esta cautela puede impedir una eliminación aunque se
cumpla la inactividad de 90 días; requiere revisión, no alarga silenciosamente
el reloj ni garantiza cumplimiento automático del plazo.
El modo `request` omite sólo el requisito de edad, después de que el responsable
haya verificado la identidad y alcance de la solicitud fuera de esta CLI.

El grafo comprende contacto/perfil comercial, conversaciones, mensajes, cambios
de estado, eventos de gestión, sesiones/eventos/ciclos de handoff, memoria IA,
trabajos/intentos/checkpoints IA, recibos entrantes, intentos salientes, eventos
de negocio directamente vinculados y auditoría con resource_id directamente
vinculado. Las estadísticas diarias agregadas no se borran ni recalculan.
No se introdujo migración: se utilizan las relaciones existentes hasta 0027.

## Procedimiento (no ejecutado sobre datos reales)

1. Verificar autorización e identidad; identificar los tres UUID en el tenant.
   Contactos sin conversación atribuible no tienen bot demostrable y se bloquean.
2. Reservar una ventana de mantenimiento y detener ingreso/webhooks, consumidores,
   recuperación de transporte, automatizaciones y acciones humanas. Esperar a que
   finalicen operaciones externas; resolver estados inciertos mediante el proceso
   operativo existente. No cambiar estados para forzar una eliminación.
3. Ejecutar preview contra la base correcta:

   ```text
   python -m app.operations.contact_erasure --organization-id ORG_UUID --bot-id BOT_UUID --contact-id CONTACT_UUID --mode retention
   ```

4. Revisar recuentos y bloqueos. Para una solicitud validada utilizar `--mode request`.
   Un bloqueo impide toda eliminación de ese contacto. No hay opción `--force`.
5. Repetir exactamente el alcance y modo añadiendo `--apply --expected-fingerprint HASH`.
   El fingerprint debe proceder de la previsualización revisada. La CLI reevalúa
   elegibilidad y todo el grafo; cualquier cambio invalida el preview. Un resultado
   bloqueado termina con código 2, y una excepción revierte la transacción.
6. Registrar el resultado mínimo en el expediente de la solicitud y reanudar los
   procesos. Una nueva previsualización del contacto eliminado devuelve un grafo
   vacío; reutilizar el fingerprint antiguo se rechaza como `stale_preview`.

Cada ejecución acepta un contacto, con límite total de 10.000 filas por defecto
(`--max-rows`, máximo 100.000). No es un barrido automático ni una tarea programada.
Los operadores deben inventariar candidatos por bot y repetir el procedimiento;
no existe todavía un descubrimiento/paginación automático de contactos vencidos.

## Concurrencia y atomicidad

SQLite usa `BEGIN IMMEDIATE`; PostgreSQL adquiere locks `SHARE ROW EXCLUSIVE NOWAIT`
en todas las tablas conocidas, en orden estable. Tanto preview como apply usan una
sesión nueva. Esto impide que escritores cambien o creen relaciones durante la
inspección/eliminación, también si no participan en un protocolo de locks por fila.
Es deliberadamente una operación de mantenimiento: puede bloquear temporalmente
escrituras de otros tenants, pero nunca elimina sus registros. PostgreSQL rechaza
una operación cuando no puede tomar el lock; no espera indefinidamente.

Se valida el ámbito de cada fila con tenant/bot cuando existen esas columnas, así
como enlaces inversos de transporte y claves foráneas entrantes. Relaciones nuevas
no soportadas bloquean antes de depender de CASCADE. La eliminación sigue orden
inverso de claves foráneas y se confirma en una sola transacción. Los trabajos IA
activos o inciertos, tokens persistentes, recibos no procesados, envíos pendientes/
fallidos o con token y handoffs humanos activos impiden el borrado. Los locks de
base no cancelan llamadas que ya estén fuera de la base: de ahí la ventana de
mantenimiento y el rechazo conservador de esos estados.

## Casos que quedan bloqueados y límites de la promesa

- Contacto compartido con otro bot, relaciones cruzadas de tenant/bot o transporte
  utilizado desde otra conversación. No se borra parcialmente el contacto.
- Conversaciones sin tenant o sin contacto, incluso si una cadena histórica parece
  coincidir; no se infiere identidad desde `customer_id`, texto o ciphertext.
- Recibos del bot sin enlace demostrable a mensaje/trabajo/transportes seleccionados.
- Registros Core sin sujeto atribuible: knowledge_query_log, automation_execution,
  automation_task_execution e integration_event; su presencia puede bloquear otros
  contactos conservadoramente. No se borran registros ajenos para desbloquearlos.
- Eventos de negocio sin conversación, business_case_id presente y snapshots de
  automatización del tenant sin relación normalizada de contacto.
- Grafos mayores que el límite. Requieren revisión/migración específica; no se
  fragmenta un contacto dejando copias silenciosamente.

Los bloqueos requieren saneamiento/migración de atribución y revisión humana, no
un bypass. La operación no certifica eliminación de logs operativos, archivos,
respaldos, exportaciones, copias de terceros ni metadatos genéricos de auditoría.
La auditoría con resource_id relacionado sí se elimina; otros productores deben
seguir minimizando sus metadatos. Una nueva comunicación tras la eliminación puede
crear otro contacto: no se implementa una lista de supresión de identidad.

Por ello, no afirmar aún que toda retención a 90 días está automatizada, que todos
los históricos son borrables o que una solicitud cubre copias externas. La memoria
IA de 30 días mantiene su mecanismo separado descrito en
`LURI_PRIVACIDAD_MEMORIA_2026-09-26.md`. Los flags IA permanecen sin cambios/off.

## Verificación local

`tests/test_privacy_erasure.py` ejecuta el contrato en SQLite con FK activas;
`tests/integration/test_privacy_erasure_postgresql.py` ejecuta el mismo contrato
sobre PostgreSQL explícitamente aislado y migrado. Incluye aislamiento de tenant,
contactos compartidos, preview obsoleto, límite de filas, borde de 90 días, solicitud
reciente, rollback, referencias inversas, estados IA activos, ambigüedad histórica,
exclusión de escritores/otras eliminaciones y eliminación del grafo de handoff/IA/
transporte. El gate `scripts/run_postgresql_tests.py` incluye esta suite y rechaza
pruebas saltadas. No se requiere OpenAI ni Meta para estas pruebas.

Resultados de esta entrega local (2026-09-26): 94 pruebas SQLite de privacidad,
memoria y regresión IA/conversacional; 22 pruebas PostgreSQL 17 de privacidad y
memoria, sobre base nueva migrada hasta 0027. Ruff, Black, mypy (542 archivos),
contrato CI, revisión de whitespace y actualización de locks pasan. El contenedor
y su volumen sintético se retiraron al finalizar. No hubo ejecución sobre datos
reales, cambios de flags, despliegue ni comunicación con OpenAI/Meta.
