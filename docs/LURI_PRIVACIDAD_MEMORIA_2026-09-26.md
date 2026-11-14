# Retención de memoria IA: primer incremento técnico

La decisión del propietario para el piloto es limitar conversaciones/contactos a 90 días de inactividad y memoria IA a 30 días. Este incremento implementa exclusivamente la parte de memoria IA. No ejecuta caducidad automática ni eliminación de contactos, conversaciones, mensajes o respaldos. La política pública todavía no debe afirmar que la retención completa está implementada.

## Comportamiento

- `ai_memory.updated_at` registra la última escritura de memoria. La migración `20260926_0027` agrega la columna nullable. Los registros previos quedan con edad desconocida; al leerlos se descarta el contenido y se incrementa la revisión. No se les atribuye una fecha ficticia.
- En la preparación de un trabajo IA, una memoria con más de 30 días se sustituye por `{}` antes de cualquier llamada al proveedor. La lectura de historial para IA se limita a mensajes registrados durante los últimos 30 días. Si hubo una memoria vencida o un trabajo previo de más de 30 días, también excluye eventos antiguos llegados tarde; conserva el mensaje del trabajo actual. Esto impide reconstruir memoria vencida desde historial antiguo.
- Una operación manual y acotada por `organization_id` y `bot_id` presenta candidatos vencidos y, solo con `--apply`, elimina memoria y contenido temporal de trabajos terminales relacionados. Los trabajos activos bloquean la limpieza de su conversación. El comando se ejecuta por lotes de hasta 1000, 100 por defecto.
- Se conserva el historial original y la metadata de intentos necesaria para diagnóstico; el comando no es un procedimiento completo de eliminación por persona. Un trabajo que no termina puede impedir la limpieza hasta su revisión. No se reactivó el worker de recuperación aplazado.

## Uso supervisado en un entorno identificado

Comprobar primero que `BOTWA_DATABASE_URL` apunta inequívocamente a la base prevista. No copiar una URL con contraseña en chats, logs ni scripts. Tras la migración del entorno correspondiente:

```text
python -m app.operations.privacy_retention --organization-id <UUID_ORG> --bot-id <UUID_BOT>
python -m app.operations.privacy_retention --organization-id <UUID_ORG> --bot-id <UUID_BOT> --apply
```

El primer comando solo cuenta. El segundo confirma un lote en la base configurada; no ejecutarlo en staging o producción sin revisar antes el alcance y un respaldo. Las salidas son cantidades, sin nombres, teléfonos o texto de mensajes. Repetir la vista previa tras cada lote. `skipped_active` exige revisar el trabajo antes de cualquier limpieza.

## Migración y reversión

Head esperado: `20260926_0027`, sobre `20260921_0026`. El downgrade adyacente elimina solo `ai_memory.updated_at`. No borra memoria adicional, pero una versión de aplicación anterior podría volver a usar mensajes antiguos como contexto; para revertir de forma segura se debe desactivar el piloto IA y drenar trabajos antes de regresar a ese código. Las tablas y el resto de la infraestructura conservan sus contratos.

## Validación y límites

Las pruebas cubren vista previa, aislamiento de tenant, repetición de limpieza, bloqueo de trabajo activo y ausencia de memoria/historial antiguos en el contexto del siguiente trabajo. La suite PostgreSQL incluye estos dos últimos casos. No se realizaron llamadas a OpenAI ni se ejecutó el comando contra una base remota.

Para cumplir los 90 días de conversaciones/contactos y solicitudes de eliminación se necesita el siguiente incremento: inventario integral de relaciones, bloqueo de ingreso y trabajos, previsualización de borrado, ejecución idempotente, tratamiento de copias/restauraciones y pruebas de aislamiento PostgreSQL. No se debe presentar este PR como cierre de esa obligación.


Incremento posterior en el mismo worktree: `LURI_PRIVACIDAD_ELIMINACION_2026-09-26.md` documenta la operación supervisada por contacto para 90 días y solicitudes verificadas. No constituye retención automática ni cobertura de históricos ambiguos o copias externas.
