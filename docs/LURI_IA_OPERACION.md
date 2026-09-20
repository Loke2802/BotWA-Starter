# Luri IA: implementación y operación del piloto

Fecha: 2026-09-20. Rama: `codex/luri-generative-ai`.

## Decisión aprobada y alcance

El análisis original se conserva sin modificaciones en [la propuesta del 19 de septiembre](LURI_IA_ARQUITECTURA_PROPUESTA_2026-09-19.md). El 20 de septiembre el propietario autorizó ampliar el worker de automatizaciones existente, con cola IA durable y lógicamente separada, sin un servicio nuevo. Esta implementación aplica esa decisión. No reactiva `app.operations.whatsapp_worker`, su bucle de recuperación general ni ningún servicio externo adicional.

No se han realizado llamadas reales a OpenAI ni despliegues como parte de la implementación. Las pruebas sustituyen OpenAI y WhatsApp por proveedores simulados. La habilitación descrita aquí es un procedimiento posterior, no una acción ya ejecutada.

## Recorrido implementado

1. La composición real de WhatsApp conserva firma, identidad del canal, contacto, historial, automatizaciones y bloqueo por handoff.
2. Para el bot piloto, el handler crea `ai_job` dentro de la transacción del mensaje, en lugar de ejecutar el motor antiguo. La recepción queda procesada cuando su responsabilidad de aceptación se completa: historial y trabajo confirmado. La generación tiene su propio estado. No se llama a OpenAI desde el webhook.
3. El proceso `python -m app.operations.automation_worker` mantiene su bucle normal y ejecuta una única vía IA en otro hilo, con su propio event loop y sesiones independientes. No utiliza la cola de automatizaciones para almacenar IA.
4. El consumidor reserva un trabajo con token y vencimiento en PostgreSQL. Cierra su sesión antes de cada llamada al proveedor. Descubrimiento y propuesta de respuesta son hasta dos llamadas a Luna, sin herramientas; se registra cada intento antes de llamar.
5. El backend valida necesidades, evidencia, fuentes y compatibilidad; guarda memoria cifrada y resultado. Recomprueba configuración, handoff, conversación y versiones de conocimiento.
6. El consumidor genera una única entrada de outbox vinculada al trabajo y reutiliza el transporte existente. Recupera exclusivamente la salida de sus propios trabajos IA. La clave `ai:<job UUID>` es única por organización.

Estados de `ai_job`: `pending`, `running`, `retry`, `ready`, `sent`, `failed`, `cancelled`, `delivery_unknown`, `handoff`. La reserva expira tras dos timeouts de proveedor más 60 segundos. Los trabajos tienen dos intentos por defecto; el plazo normal para iniciar generación es cinco minutos. El agotamiento genera un fallback seguro, sujeto a los mismos controles antes de enviar.

Un reinicio entre inferencia y persistencia puede repetir una llamada al modelo y su costo. No se promete facturación exactamente una vez. Una entrega incierta de WhatsApp queda marcada y no se reenvía a ciegas. La idempotencia de base de datos impide duplicar trabajos y outbox; no elimina la incertidumbre de una red externa.

Los mensajes nuevos invalidan respuestas pendientes basadas en una entrada anterior. El siguiente trabajo lee el historial reciente, incluyendo esas entradas, y reconstruye el contexto. El historial original no se sustituye por memoria.

## Contrato y límites funcionales deliberados

La memoria guarda valores con cita y referencia a mensaje, marcados `evidence_backed`, no `confirmed`. No modifica CRM ni consentimiento. Rechaza valores sin evidencia literal, tipos incompatibles y retrocesos a evidencia anterior. El reconocimiento semántico —por ejemplo, a qué destinatario corresponde una cifra— sigue requiriendo evaluación conversacional.

El asesor elige preguntas configuradas, citas autorizadas y productos con pares necesidad/atributo comprobables. **La primera versión no envía prosa comercial libre generada por el modelo.** El backend redacta los bloques comerciales y las preguntas. Esta restricción reduce superficie de alucinación, pero la naturalidad de redacción es más limitada que la visión completa del producto; no debe presentarse como asesor comercial plenamente validado.

Cada negocio define sus criterios; no hay reglas de juguetes hardcodeadas. Se preserva memoria de necesidades entre turnos y se puede reemplazar al cambiar de asunto; el historial permite conservar la conversación anterior. No hay búsqueda vectorial ni memoria transversal entre empresas.

El catálogo utiliza entradas publicadas de conocimiento con `metadata.catalog_item`. Las fuentes no publicadas, de otro bot o con metadata inválida no son candidatos. La búsqueda es lexical, con un máximo de 12 entradas; puede no encontrar un producto existente. «No recuperado» no significa «no existe». Las políticas en texto se responden con citas literales, no con afirmaciones comerciales inventadas.

La interfaz del proveedor es independiente; el único adaptador/modelo habilitado es OpenAI `gpt-5.6-luna`. No hay routing ni fallback a otro modelo. [Documentación del modelo](https://developers.openai.com/api/docs/models/gpt-5.6-luna).

## Migración y archivos

Nueva migración: `alembic/versions/20260920_0025_generative_ai.py`, sobre `20260916_0024`.

- `ai_job`: alcance, recepción única, secuencia, reserva, estado, resultado cifrado temporal, versiones de fuentes y salida única.
- `ai_memory`: memoria cifrada y revisión por conversación, con organización y bot.
- `ai_attempt`: proveedor, modelo, etapa, versión del prompt, parámetros no secretos, duración, consumo conocido y resultado normalizado. Un consumo desconocido permanece NULL.

Paquetes nuevos: `app/domain/generative_ai/`, `app/application/generative_ai/`, `app/infrastructure/generative_ai/`; modelo `app/infrastructure/models/ai_generation.py`; operaciones `app/operations/ai_consumer.py` y `ai_metrics.py`.

Se modifican composición y procesador de WhatsApp, handler gestionado, servicio de bots, contratos de bots/conocimiento/auditoría, handoff, settings, registro de modelos, worker existente, gates de migración CI y ejecutor de pruebas PostgreSQL. El PR contiene el inventario exacto y las pruebas añadidas.

Preparación de despliegue posterior, con todos los flags apagados:

```text
alembic heads
alembic upgrade head
alembic current
```

El head esperado es `20260920_0025`. No ejecutar estas órdenes contra una base ajena ni producción durante revisión. CI valida una base PostgreSQL aislada y el ciclo adyacente de migración.

## Variables nuevas

Todas usan prefijo `BOTWA_`. Ninguna requiere cambiar el comando del worker.

| Variable | Valor inicial/default | Dónde |
|---|---|---|
| `BOTWA_AI_ENABLED` | `false` | API y worker; poner `true` solo al preparar el piloto. |
| `BOTWA_AI_PILOT_SCOPES` | `[]` | API y worker; JSON de cadenas `organization UUID:bot UUID`. |
| `BOTWA_AI_OPENAI_API_KEY` | sin valor | Solo worker; secreto cifrado del entorno. |
| `BOTWA_AI_TIMEOUT_SECONDS` | `20` | Worker; entre 1 y 60. |
| `BOTWA_AI_MAX_OUTPUT_TOKENS` | `1600` | Worker; entre 256 y 4000, por llamada. |
| `BOTWA_AI_MAX_ATTEMPTS` | `2` | Worker; entre 1 y 3, por trabajo. |
| `BOTWA_AI_JOB_MAX_AGE_SECONDS` | `300` | Worker; entre 60 y 1800. |
| `BOTWA_AI_DAILY_CALL_LIMIT` | `500` | Worker; límite global de intentos diarios, incluyendo resultados desconocidos. |

Ejemplo de allowlist, reemplazando ambos UUID por los del piloto:

```json
["00000000-0000-4000-8000-000000000001:00000000-0000-4000-8000-000000000002"]
```

Se reutilizan `BOTWA_DATABASE_URL`, las claves de cifrado de WhatsApp, la configuración del cliente Meta y la allowlist de destinatarios existentes. No regenerar la clave de cifrado durante esta configuración: protege también datos anteriores.

## Configurar OpenAI sin exponer secretos

1. En la plataforma OpenAI, preparar un proyecto dedicado al piloto, con facturación y límites adecuados. Comprobar acceso a `gpt-5.6-luna` antes de habilitar el bot. Esta comprobación operativa sigue pendiente; publicar el modelo no garantiza acceso de la cuenta.
2. Crear una clave de proyecto/cuenta de servicio con el mínimo acceso necesario para Responses. No usar una clave personal compartida con otros entornos.
3. Guardarla directamente en el campo secreto/cifrado de variables del componente worker como `BOTWA_AI_OPENAI_API_KEY`. No pegarla en chats, Git, un JSON de bot, comandos con el valor literal ni logs. No hace falta enviarla al componente API.
4. Mantener desactivado el bot mientras se preparan variables y migración. Cambiar variables de proceso requiere reiniciar/desplegar el componente; este documento no ejecuta ese paso.
5. Tras autorización explícita de llamadas pagadas, realizar un smoke pequeño y revisar `ai_attempt` y métricas; nunca imprimir la clave ni el contexto del proveedor.

Se usa Responses con `store: false`, lista de herramientas vacía, sin conversaciones remotas persistentes y sin modo background del proveedor. No confundir esto con retención cero: las políticas de abuso/caché son distintas. [Controles de datos](https://developers.openai.com/api/docs/guides/your-data).

## Preparar catálogo y activar únicamente el piloto

Necesitas un usuario con `bots.update` de la organización objetivo y permisos de conocimiento para preparar fuentes. Los endpoints conservan sus controles de alcance.

Primero preparar y publicar fuentes revisadas. Ejemplo ilustrativo de metadata de una entrada existente —no es un producto real ni debe publicarse sin verificarlo—:

```json
{
  "catalog_item": {
    "name": "Producto verificado del negocio",
    "attributes": [
      {"key": "recommended_age", "label": "Edad recomendada", "value": "4 a 7 años", "minimum": 4, "maximum": 7},
      {"key": "interest", "label": "Temática", "value": "dinosaurios"}
    ]
  }
}
```

No añadir precio, stock, compatibilidad o edades que no provengan del negocio. Los comparadores `range` y `at_most` usan los límites numéricos autorizados; `equals` y `contains` comparan texto. Un criterio `required` impide recomendar hasta que exista necesidad y compatibilidad verificable.

Después:

1. Configurar la allowlist con **un solo** par organización/bot en API y worker. Mantener los demás bots sin IA.
2. Verificar migración, worker activo, claves de cifrado y allowlist de salida WhatsApp. No es suficiente encender el flag de API si el worker no puede consumir.
3. Obtener `GET /bots/{bot_id}` mediante una sesión administrativa autorizada. Conservar todos los valores existentes de `bot.settings`.
4. Fusionar el siguiente bloque dentro de esos settings y enviar `PATCH /bots/{bot_id}` con `{"settings": <settings completos fusionados>}`. El PATCH reemplaza el objeto settings: no enviar únicamente IA si existen otras claves que deban conservarse.

```json
{
  "generative_ai": {
    "enabled": true,
    "daily_jobs": 25,
    "needs": [
      {"key": "recipient_age", "question": "¿Qué edad tiene la persona que lo usará?", "kind": "number", "required": true, "attribute": "recommended_age", "comparison": "range"},
      {"key": "interest", "question": "¿Qué temas le gustan?", "kind": "text", "required": false, "attribute": "interest", "comparison": "contains"}
    ]
  }
}
```

`daily_jobs` limita el presupuesto a dos llamadas por ese número de trabajos diarios; los reintentos también consumen ese cupo. No garantiza exactamente 25 conversaciones completas. El límite global puede ser más restrictivo. El modelo y URL no son configurables por el tenant.

La activación efectiva exige allowlist + flag global + flag de bot + organización/bot/canal activos. Sin eso continúa el motor previo. No existe todavía un formulario específico de IA en el portal: se usa la API administrativa existente.

## Métricas y capacidad

En el entorno del worker, ejecutar la consulta de solo lectura:

```text
python -m app.operations.ai_metrics
```

El consumidor registra también `ai_worker_metrics` aproximadamente cada 30 segundos entre iteraciones. Las métricas persistidas sobreviven a reinicios:

- trabajos por estado y antigüedad del más antiguo;
- espera hasta inicio, media/p95/máximo;
- duración de cada llamada al modelo;
- tiempo desde aceptación del mensaje hasta envío confirmado por el transporte;
- errores, resultados desconocidos y reintentos;
- tokens conocidos de entrada/salida y número de consumos desconocidos;
- trabajos IA en ejecución frente a capacidad inicial 1;
- antigüedad de la automatización pendiente más atrasada.

La muestra de latencias/consumo usa las últimas 24 horas, limitada a 10.000 trabajos/20.000 llamadas, e informa cuando alcanza ese límite. El tiempo hasta `sent` no equivale a lectura del cliente. CPU/RAM se observan en las métricas existentes del componente de DigitalOcean; no se ha creado otro exportador o endpoint público.

Registrar una línea base del worker sin IA y comparar durante el piloto. Propuesta de revisión: cola creciente en varios intervalos, retrasos de automatización frente a su línea base, CPU/RAM sostenidamente altas o timeouts frecuentes. Antes de aumentar recursos o separar workers, presentar esos datos y discutir el costo. No afirmar capacidad suficiente basándose únicamente en tests con proveedor falso.

## Apagado y rollback

1. **Primero desactivar el bot**: GET de settings, conservar sus otras claves, poner `generative_ai.enabled=false`, PATCH con settings completos. Esto cancela sus trabajos activos y salidas pendientes que aún no están en entrega. Cambiar otro valor del bloque IA también invalida los trabajos anteriores.
2. Verificar mediante métricas/consulta que no queden trabajos activos de ese piloto. Una petición ya aceptada por OpenAI o WhatsApp no puede retirarse retroactivamente.
3. Los mensajes nuevos vuelven al comportamiento previo. No reprocesar automáticamente entradas anteriores por ambos motores.
4. Si se quiere apagar toda la función, retirar scopes y poner `BOTWA_AI_ENABLED=false` en API y worker, reiniciando los procesos cuando esté autorizado. Hacerlo después de desactivar bots evita que trabajos previos reaparezcan al reactivar la configuración global.
5. Para rollback del código, usar la imagen anterior autorizada con IA apagada y **conservar inicialmente las tablas nuevas**. No necesitan eliminarse para desactivar la función.
6. `alembic downgrade 20260916_0024` elimina tablas y datos IA; reservarlo para una base de pruebas o una operación de eliminación expresamente aprobada, con respaldo y sin procesos de la versión nueva.

No reintentar manualmente una salida `delivery_unknown` sin comprobar qué ocurrió en el proveedor. Un resultado desconocido exige revisión, no un bucle automático.

## Pruebas y límites pendientes

Se añaden pruebas unitarias/de composición con proveedor simulado y una suite PostgreSQL para reservas concurrentes, reinicios, conexiones cerradas e idempotencia de punta a punta. Los controles son pytest, ruff, black, mypy, contratos CI, locks, auditoría de dependencias, migraciones PostgreSQL, secretos y seguridad del contenedor. Los resultados finales se consignan en la entrega/PR, distinguiendo checks ejecutados y pendientes.

No considerar implementados o validados todavía:

- acceso real de la cuenta a Luna, latencia/costo/calidad real y envío comercial por WhatsApp con esta integración;
- capacidad suficiente del worker bajo tráfico real;
- la evaluación comercial completa de 30–50 conversaciones y su aprobación humana;
- redacción comercial libre del modelo, búsqueda semántica/vectorial o catálogo/inventario transaccional;
- UI específica para configurar IA, alertas externas o política automática de retención/eliminación de memoria;
- reservas, pagos, herramientas externas, otros modelos o multiagente;
- recuperación general de entradas/salidas WhatsApp ajenas a IA;
- despliegue a staging/producción, merge o activación del piloto.

La memoria y los mensajes siguen siendo datos privados, cifrados y de acceso scoped. Antes de un uso ampliado habrá que acordar su retención y eliminación; no se registran conversaciones completas en logs de aplicación.
