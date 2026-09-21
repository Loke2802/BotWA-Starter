# Luri IA: análisis y propuesta para revisión

Fecha: 19 de septiembre de 2026. Estado: **propuesta, sin implementación ni activación**.

Objetivo: un asesor comercial que descubre necesidades, recuerda lo conversado y recomienda soluciones reales del negocio. «Luna conversa y razona. Luri controla los datos y las acciones».

## Decisión necesaria antes de implementar

**Recomiendo GPT-5.6 Luna mediante un adaptador pequeño, memoria explícita y conocimiento publicado del bot. La generación debe ejecutarse fuera del webhook y de sus transacciones.**

Encontré un problema concreto: el webhook espera al procesador; este invoca el motor mientras conserva el bloqueo de una recepción y una transacción abierta. Insertar una llamada remota ahí prolongaría ambos. Además, el endpoint puede devolver OK aunque el procesamiento interno falle: los reintentos de WhatsApp no constituyen una recuperación de generaciones.

Por eso hace falta decidir quién consumirá y recuperará trabajos durables de IA. No he añadido ningún componente ni reactivado el worker de recuperación aplazado.

| Alternativa | Consecuencia | Infraestructura y costo |
|---|---|---|
| **Ampliar el worker de automatizaciones existente** | Consumidor de IA con concurrencia limitada, trabajos persistidos en PostgreSQL y recuperación específica de esos trabajos y su salida. Requiere aislarlo del procesamiento de automatizaciones. | Sin nuevo servicio si la capacidad actual basta; esto debe medirse. Consumo variable de API y almacenamiento. Puede exigir aumentar recursos si afecta al worker. |
| Worker separado | Aislamiento operativo y escalado independiente. | Nuevo componente con su cargo de cómputo, además de API. Cotización pendiente según tamaño; no contratado ni recomendado por defecto para este piloto. |
| Llamada dentro de la petición, cerrando primero la transacción | Evita el bloqueo de base de datos durante inferencia, pero mantiene la espera HTTP. Una caída deja trabajos pendientes hasta recuperación explícita. | Sin nuevo servicio; confiabilidad insuficiente para dar por cumplido el objetivo sin otro mecanismo de recuperación. |

**Mi elección para el piloto es la primera, condicionada a aprobación y medición de capacidad.** Es una ampliación real del worker, no una capacidad que ya exista. Si no se aprueba, debemos resolver esta decisión antes de implementar el recorrido IA. El aplazamiento del worker general de recuperación de WhatsApp permanece vigente.

## A. Estado encontrado

### Base de inspección

Inspeccioné `D:\BotWA Starter\.worktrees\audit-fixes-20260916`. Su árbol Git coincide con el árbol del `master` remoto de `Loke2802/BotWA-Starter`, commit `eda360207f8e8e0e842db784759ad6ba3ed4d899`, consultado durante esta revisión. La coincidencia es de contenido, aunque el commit local sea distinto. No equiparo revisión del repositorio con verificación nueva del despliegue.

Las rutas siguientes son relativas a ese repositorio.

| Área | Evidencia en código | Implicación |
|---|---|---|
| Entrada real | `app/api/whatsapp_live_routes.py`, `app/application/whatsapp_live/processor.py` | Firma, límites, resolución del canal y recepción persistida existen. El endpoint espera al procesador. |
| Atomicidad | `app/infrastructure/repositories/whatsapp_message_transport_repository.py`, `app/infrastructure/unit_of_work.py` | Se adquiere recepción con `FOR UPDATE SKIP LOCKED`; el handler corre bajo savepoint y `atomic_transport`. Los commits internos pasan a flush. El savepoint no libera la transacción exterior. |
| Motor y composición | `app/core/conversation/service.py`, `router.py`, `response_composer.py`; `app/core/business/service.py` | Recorrido síncrono basado en intención, reglas y conocimiento. La respuesta se compone de conocimiento o plantilla. No hay un asesor generativo implementado. |
| Coordinación comercial | `app/application/conversation_management/managed_handler.py` | Registra entrada, automatizaciones y handoff; contiene captura de leads y respuestas que pueden interceptar el motor. Hay que evitar su competencia con el asesor piloto. |
| Historial | `app/application/conversation_management/history.py` | Carga por organización, bot y conversación; excluye mensaje actual. Ventana de 20 mensajes, hasta 4.000 caracteres por mensaje y 16.000 en total. No es memoria semántica durable. |
| Conocimiento autorizado | `app/application/knowledge_management/provider.py`, `retriever.py`; `app/infrastructure/repositories/knowledge_entry_repository.py` | Filtra organización, bot y publicación. El retriever puntúa coincidencias y entrega una sola entrada. No basta para comparar alternativas. |
| Catálogo | `app/domain/knowledge_management/contracts.py`, `app/domain/business_configuration/contracts.py` | Entradas con metadata genérica y configuración de servicios. No encontré un catálogo completo con atributos comerciales tipados y disponibilidad verificable. |
| Catálogo antiguo | `app/infrastructure/models/knowledge_catalog_entry.py`, `app/core/knowledge/db_catalog.py` | Modelo global sin organización/bot. **No debe alimentar al asesor multi-tenant.** |
| Configuración | `app/domain/bot/contracts.py`, `app/application/bots/service.py` | `settings` es JSON genérico; creación y actualización están sujetas a permisos y organización. No hay todavía un contrato específico de activación IA. |
| Atención humana | `app/application/human_handoff/service.py` | Estados de espera/atención bloquean el bot. Existe solicitud por usuario y entrada restringida para automatizaciones; no existe una solicitud tipada del asesor. |
| Procesos | `app/operations/automation_worker.py`, `whatsapp_worker.py` | Hay código de ejecución de automatizaciones y recuperación del transporte. No hay cola/consumidor de generaciones IA. Existencia de código no implica que el componente esté desplegado. |

Revisé también pruebas de idempotencia y reintentos del transporte, bloqueo por handoff, persistencia cifrada, aislamiento y permisos de bots y recuperación de conocimiento publicado. Por ejemplo, el test de fallo del motor demuestra que la recepción queda fallida y que una entrega duplicada no vuelve a ejecutar el handler. **No ejecuté suites en esta etapa documental ni afirmo nuevas pruebas aprobadas.**

### Modelo solicitado

La documentación oficial publica **`gpt-5.6-luna`**, compatible con Responses API y salidas estructuradas. Esto confirma la opción técnica, no el acceso de nuestra cuenta: no realicé llamadas pagadas ni solicité claves. Tarifas base publicadas: USD 0,20 por millón de tokens de entrada y USD 1,20 por millón de salida; existen condiciones adicionales de caché/contexto. [Modelo y tarifas oficiales](https://developers.openai.com/api/docs/models/gpt-5.6-luna).

## B. Diseño propuesto

### Punto de integración

Separar en el procesador la aceptación durable del mensaje de su resolución. Después de resolver contexto, registrar entrada y comprobar handoff, una política del backend elige **recorrido actual** o **trabajo de asesor IA**. La composición se conecta en `app/api/whatsapp_live_dependencies.py`.

No insertar la API dentro de `BusinessBrainService.process` ni sustituir únicamente el clasificador: ambos dejarían sin resolver transacciones, composición de respuesta y memoria.

Para el piloto, conservar los controles compartidos de contacto, transporte, auditoría y handoff, pero evitar que la captura de leads o las plantillas antiguas respondan además del asesor. Registrar cada automatización de entrada una sola vez. Fuera del piloto, mantener el recorrido existente.

### Componentes pequeños

1. **Puerto de generación**: solicitud y resultado internos independientes de OpenAI. El adaptador traduce a Responses API, esquema estricto, timeout, uso y errores. Sin tools, navegación, SQL ni HTTP elegidos por el modelo. Puede reutilizar `httpx`, ya presente.
2. **Servicio asesor**: secuencia acotada de descubrimiento, recuperación y respuesta. No framework de agentes ni routing de modelos.
3. **Recuperador del asesor**: usa repositorio publicado y scoped existente; devuelve varios candidatos limitados y referencias/versiones. Busca con la necesidad acumulada, no solamente el último «sí» del cliente.
4. **Memoria**: necesidades por organización/bot/conversación y asunto comercial. Valor tipado, evidencia del mensaje, estado explícito/inferido/conflictivo/sustituido y revisión. Correcciones sustituyen la necesidad activa conservando trazabilidad; cambio de asunto no mezcla destinatarios ni presupuestos.
5. **Persistencia de ejecución**: trabajo único por recepción, etapas, intentos, vencimiento de reserva, resultado validado y relación con outbox. Memoria y contenido sensible cifrados; no guardarlos como texto libre en `Conversation.extra_data`.
6. **Política y validador**: activación, presupuesto, handoff, fuentes, compatibilidad y contenido comercial. El modelo propone; el backend acepta o rechaza.

### Catálogo mínimo sin infraestructura nueva

Para el piloto propongo una entrada publicada por producto/servicio y metadata `catalog_item` validada al publicar. Su identificador estable será el de la entrada. Nombre, atributos verificables, precio/moneda cuando existan, versión y procedencia. Stock solo si una fuente autorizada lo suministra con vigencia suficiente; en otro caso es desconocido.

Los criterios se configuran por bot mediante `need_definitions`: claves, tipos, unidades, restricciones obligatorias y comparadores permitidos. Edad y dinosaurios pertenecen a la configuración del negocio de juguetes, no al núcleo de Luri. Descripciones libres pueden aportar contexto, pero no demostrar automáticamente compatibilidad crítica: esos atributos requieren normalización y revisión del negocio.

Primero comprobar que el piloto tiene productos y atributos suficientes. Ningún modelo compensa un catálogo que no contiene la información necesaria.

### Activación y límites

Activación efectiva = interruptor global del servidor + organización/bot en piloto autorizado + `settings.generative_ai.enabled` + organización/bot/canal activos. Por defecto, desactivado.

El bloque de settings será tipado y validado en creación y actualización. No permitirá definir claves, URL del proveedor, herramientas, modelos arbitrarios ni presupuestos superiores al límite del servidor. Cambios sujetos a permisos existentes y auditoría. Desactivar cancela trabajos pendientes y suprime resultados en vuelo antes de encolar/enviar; mensajes nuevos vuelven al motor previo. No repetir automáticamente una entrada ya aceptada por ambos motores.

## C. Flujo de ejecución

1. WhatsApp → validar firma, límites e identidad del canal; resolver alcance desde configuración confiable.
2. Transacción corta: deduplicar recepción, registrar mensaje/contacto y efectos de entrada, comprobar handoff y activación, crear trabajo durable si corresponde. Confirmar antes del ACK. Si falla esta persistencia, no confirmar una aceptación inexistente.
3. El consumidor reserva un trabajo con token de propiedad y vencimiento, y confirma/cierra la sesión. Una sola generación activa por conversación; concurrencia global inicial limitada.
4. En otra sesión corta, cargar memoria, historial autorizado y configuración; producir objetos de datos independientes del ORM y cerrar la sesión. Ninguna sesión con transacción abierta durante llamadas remotas, ni siquiera una iniciada por SELECT.
5. Primera llamada Luna: interpretar mensaje, proponer cambios de necesidades, cambio de asunto y términos de búsqueda. Validar claves, tipos y evidencia. Persistir etapa para recuperación.
6. Recuperar varios candidatos publicados exclusivamente del bot, aplicando filtros comerciales con valores conocidos. Cerrar la sesión. Segunda llamada Luna: propuesta de respuesta y selección fundamentada. Si se necesita aclaración y no consultar catálogo, terminar con una sola llamada.
7. Transacción corta final: comprobar propiedad del trabajo, versión de memoria, cambios de entrada, flag, handoff y vigencia de fuentes; validar resultado; guardar memoria, salida, auditoría y outbox de forma atómica. No aceptar resultados obsoletos.
8. Enviar por transporte existente fuera de la transacción. Recuperar también salidas IA pendientes tras una caída entre commit y envío, reutilizando la política de reintentos existente.

El orden lo define una secuencia de aceptación del backend. Nuevos mensajes durante inferencia obligan a comprobar si la respuesta quedó obsoleta: procesarlos en orden o sustituir la generación pendiente por una que incluya las entradas nuevas, con límite de recomputaciones. Nunca enviar dos recomendaciones contradictorias calculadas sobre la misma revisión.

El consumidor de IA no debe bloquear el bucle de automatizaciones: concurrencia separada y acotada, sesiones independientes, apagado supervisado y pruebas de carga. No es suficiente agregar un `await` largo dentro del bucle actual.

## D. Contrato de salida y validaciones

Dos contratos de la misma integración: `DiscoveryResult` y `AdviserResult`. No son agentes autónomos. Este ejemplo conceptual muestra la forma del resultado final; los valores son ficticios y no representan catálogo existente:

```json
{
  "schema_version": "1",
  "reply_text": "Puedo comparar estas opciones contigo.",
  "needs_clarification": false,
  "question": null,
  "handoff_requested": false,
  "handoff_reason": null,
  "discovered_needs": [
    {
      "key": "recipient_age",
      "operation": "set",
      "value": {"kind": "integer", "integer_value": 5},
      "evidence_message_ref": "message_1",
      "evidence_quote": "tiene 5 años",
      "certainty": "explicit"
    }
  ],
  "referenced_knowledge": [
    {"ref": "knowledge_1", "version": "version_1"}
  ],
  "recommended_items": [
    {
      "item_ref": "knowledge_1",
      "matches": [
        {"need_key": "recipient_age", "attribute_ref": "recommended_age_range"}
      ]
    }
  ]
}
```

El esquema real usará alternativas tipadas de valores, campos obligatorios/nullable según variante y `additionalProperties: false`, límites de longitud y cardinalidad. `DiscoveryResult` añade términos de búsqueda y propuesta de continuidad/cambio de asunto; el backend asigna los IDs del asunto. El resultado final no puede cambiar silenciosamente necesidades ya validadas en descubrimiento.

Validaciones de aplicación obligatorias:

- Referencias locales deben pertenecer al conjunto autorizado enviado, con versión vigente. No aceptar IDs inventados, de otro tenant o recuperados de instrucciones del cliente.
- Necesidades deben usar claves configuradas y evidencia real del historial recibido. Las inferencias permanecen hipótesis; no satisfacen una restricción crítica sin aclaración.
- Recomendaciones deben ser productos reales y compatibles con restricciones conocidas. Si falta edad recomendada, no afirmar que es apto para cinco años. Si falta precio, no afirmar que cumple el presupuesto.
- `matches` se evalúa con comparadores autorizados. El backend genera las afirmaciones de precio, stock, características y compatibilidad desde esos datos, no desde números/texto inventados por el modelo.
- `reply_text` es un borrador conversacional, no autoridad comercial ni orden ejecutable. Para el piloto, separar texto social/preguntas de bloques de hechos renderizados por backend; cualquier afirmación comercial no respaldada se rechaza o sustituye por abstención. Para políticas en texto libre, preferir fragmentos autorizados antes que paráfrasis sin comprobación.
- Handoff es una solicitud tipada; jamás se ejecuta leyendo una frase del mensaje al cliente. No hay acciones de reserva, pago o modificación de catálogo.

JSON válido no demuestra verdad semántica. Las salidas estructuradas ayudan al contrato, pero no sustituyen la comprobación de evidencia, pruebas adversariales y revisión de conversaciones. No prometo eliminar toda alucinación con un prompt. [Salidas estructuradas oficiales](https://developers.openai.com/api/docs/guides/structured-outputs).

## E. Manejo de fallos

| Situación | Comportamiento propuesto |
|---|---|
| Timeout, 429, error transitorio | Plazos y reintentos limitados dentro de presupuesto/antigüedad máxima. Persistir intento y siguiente ejecución. Si vence, una respuesta segura y breve; no intentar indefinidamente. |
| Credencial inválida o acceso al modelo denegado | Sin reintentos repetidos; marcar indisponibilidad, aviso operativo sin secretos y fallback seguro. |
| JSON inválido, negativa del proveedor o salida incompleta | No enviar borrador. Como máximo un reintento correctivo presupuestado; después abstención o handoff permitido. |
| Sin resultados | Distinguir «no recuperado» de «no existe». Preguntar un dato útil, informar límite o solicitar humano; nunca inventar catálogo. |
| Falta atributo crítico | Aclarar con el cliente cuando pueda resolverlo; si falta el dato del negocio, no pedir al cliente que lo adivine: reconocerlo o derivar. |
| Caída del proceso | Trabajo en PostgreSQL; reserva vencida recuperable con fencing. Reutilizar etapas/resultados persistidos cuando sigan vigentes. |
| Proveedor respondió pero se cayó antes de guardar | Puede requerirse otra llamada y producir costo duplicado. No prometer inferencia exactamente una vez; registrar intentos y consumo desconocido sin tratarlo como cero. |
| Envío WhatsApp de resultado incierto | Mantener tratamiento de `DELIVERY_UNKNOWN`; no reenviar ciegamente ni afirmar entrega. |
| Handoff iniciado durante inferencia | Descartar/suprimir salida automática al finalizar y antes de envío. Coordinar ambos recorridos con versión/bloqueo corto por conversación. Un envío ya aceptado por el proveedor no puede retirarse. |
| Fuente despublicada, cambio de flag o revisión | Invalidar resultado antes de encolar; revalidar antes del despacho. Cancelar o recalcular con límite, sin usar contexto obsoleto. |

Fallback inicial: mensaje aprobado del tipo «Ahora no puedo comprobar esa información. Puedo continuar cuando esté disponible o solicitar atención del equipo». Ofrecer/solicitar humano solo si está permitido y disponible en el flujo; no afirmar que ya se transfirió antes del commit exitoso. Con handoff activo, silencio automático. No usar una plantilla antigua de ventas como sustituto indiscriminado de una recomendación fallida.

Para handoff, añadir una entrada interna restringida para el asesor, con razones enumeradas, comprobación de plan/configuración, alcance y deduplicación. Reutilizar el ciclo existente; no fingir un usuario ni reutilizar indebidamente `request_automation`.

## F. Seguridad, privacidad y observabilidad

- Organización, bot, conversación, destinatario y permisos proceden del backend. El modelo recibe referencias locales opacas; no selecciona alcance ni destinatarios.
- Toda consulta filtra organización y bot antes de limitar resultados. No usar el catálogo global antiguo. Verificar también escrituras y trabajos recuperados.
- Cliente, documentos y descripciones son datos no confiables, separados de instrucciones del sistema. Una instrucción incrustada no habilita herramientas ni altera filtros, política o handoff.
- Lista de herramientas vacía. URL del proveedor fija y controlada por despliegue. Ningún enlace generado provoca navegación, descarga o llamada HTTP.
- Enviar mensaje actual, historial mínimo, necesidades pertinentes y candidatos limitados. Omitir teléfono, identidad completa y atributos sensibles cuando no sean necesarios; nunca enviar claves, evidencia completa de consentimiento, logs ni fichas completas por defecto.
- Historial IA: mensajes recibidos y respuestas realmente enviadas; no presentar salidas fallidas/pendientes como si el cliente las hubiera leído. Distinguir autor humano/bot y conservar evidencia interna. Respetar las reglas de consentimiento/contacto y supresión existentes; la IA no puede modificarlas ni atribuir consentimiento por inferencia.
- Memoria y snapshots necesarios para recuperación cifrados, acceso scoped y retención limitada al propósito. Eliminar/anonimizar junto con el ciclo de vida correspondiente de la conversación; no transformar memoria de un comprador en perfil transversal de otras empresas.
- Solicitudes sin almacenamiento de respuesta del proveedor (`store: false`), sin conversaciones remotas persistentes ni background del proveedor. Esto **no significa retención cero**: existen políticas separadas de abuso y caché que deben revisarse al activar el piloto. [Controles de datos oficiales](https://developers.openai.com/api/docs/guides/your-data).
- Telemetría por intento: proveedor/modelo reportado, versión de contrato/prompt/configuración, latencia de cola e inferencia, tokens disponibles, costo estimado, resultado, IDs/versiones de fuentes y errores normalizados. Sin conversación completa, prompts, números de teléfono ni cuerpos de excepción con contenido privado en logs.
- No almacenar razonamiento interno del modelo. Registrar decisiones estructuradas y evidencia verificable. Presupuesto por tenant y límite global, incluyendo etapas y reintentos; consumo desconocido requiere reserva conservadora.

El costo de API se estimará con tokens reales de todas las llamadas y las tarifas vigentes, separado del costo de WhatsApp y cómputo. No deducir un costo fijo por conversación antes de medir duración, contexto y reintentos.

## G. Archivos que modificaría o crearía

Rutas relativas al repositorio inspeccionado. Es un plan concreto, no archivos ya implementados.

### Modificar existentes

| Archivo | Cambio propuesto |
|---|---|
| `app/api/whatsapp_live_routes.py` | ACK ligado a aceptación durable del recorrido IA y tratamiento de errores de persistencia. |
| `app/api/whatsapp_live_dependencies.py` | Composición de política, coordinador y dependencias del asesor. |
| `app/application/whatsapp_live/processor.py` | Separar aceptación del piloto de inferencia; enlace con outbox y recuperación. |
| `app/application/conversation_management/managed_handler.py` | Separar controles compartidos de respuestas/captura legacy. |
| `app/application/conversation_management/history.py` | Snapshot con referencias, autor y estado de entrega para IA, sin romper contrato legacy. |
| `app/application/human_handoff/service.py` | Entrada restringida del asesor y coordinación de cancelación/versión. |
| `app/domain/bot/contracts.py` | Contrato validado de configuración IA. |
| `app/application/bots/service.py` | Aplicar validación y límites en creación/actualización; apagado seguro. |
| `app/domain/knowledge_management/contracts.py` | Metadata tipada de catálogo mínimo. |
| `app/application/knowledge_management/service.py` | Validación de atributos comerciales al publicar/actualizar. |
| `app/infrastructure/repositories/knowledge_entry_repository.py` | Recuperación múltiple y comprobación scoped de versiones. |
| `app/infrastructure/repositories/whatsapp_message_transport_repository.py` | Vincular salida IA y deduplicación, conservar políticas de entrega. |
| `app/domain/audit/contracts.py` | Eventos IA con metadata permitida, sin contenido sensible. |
| `app/operations/automation_worker.py` | Solo si se aprueba: consumidor supervisado y acotado que no bloquee automatizaciones. |

### Crear

| Archivo propuesto | Responsabilidad |
|---|---|
| `app/domain/generative_ai/contracts.py` | DiscoveryResult, AdviserResult, necesidades y referencias. |
| `app/domain/generative_ai/ports.py` | Puerto de proveedor/modelo independiente. |
| `app/application/generative_ai/service.py` | Secuencia del asesor y coordinación de etapas. |
| `app/application/generative_ai/policy.py` | Flags, límites, fallback y restricciones. |
| `app/application/generative_ai/context.py` | Snapshot mínimo y memoria por asunto. |
| `app/application/generative_ai/retrieval.py` | Recuperación de candidatos usando infraestructura existente. |
| `app/application/generative_ai/validation.py` | Evidencia, compatibilidad y renderizado comercial seguro. |
| `app/application/generative_ai/prompts.py` | Prompts versionados separados del contenido no confiable. |
| `app/infrastructure/generative_ai/openai_provider.py` | Adaptador Responses de Luna. |
| `app/infrastructure/models/ai_generation.py` | Trabajo e intentos persistidos. |
| `app/infrastructure/models/ai_conversation_memory.py` | Memoria cifrada y versionada. |
| `app/infrastructure/repositories/ai_generation_repository.py` | Reserva, fencing, estados e idempotencia. |
| `app/infrastructure/repositories/ai_memory_repository.py` | Lectura/escritura scoped y control de revisión. |
| `app/operations/ai_consumer.py` | Consumidor invocado por el worker existente; no servicio independiente por defecto. |
| `alembic/versions/<revision_siguiente>_generative_ai.py` | Tablas, índices, restricciones y evolución necesaria de recepción/outbox. |
| `tests/test_generative_ai_*.py` | Contratos, políticas, proveedor falso, integración y recuperación. |
| `tests/fixtures/generative_ai/` | Catálogos y conversaciones sintéticas reproducibles. |

También habrá que conectar modelos/configuración con los registros existentes que correspondan y documentar variables sin secretos. No fijar la revisión de migración hasta implementar, para evitar colisión con trabajo concurrente. La última migración observada es `20260916_0024_transport_and_registration.py`.

## H. Plan de pruebas y aceptación

### Unitarias sin proveedor real

Contratos estrictos; claves desconocidas; tipos y límites; cambios/correcciones de necesidades; versiones; referencias inventadas; compatibilidad con atributos ausentes; precios y stock no respaldados; selección de flag; presupuesto; timeout/429/credencial inválida; salida incompleta; negativa del proveedor; handoff no permitido. Adaptador con transporte HTTP simulado.

### Integración con PostgreSQL

- Dos tenants y dos bots de un tenant: lectura, memoria, referencias, escrituras, configuración y recuperación aisladas.
- Webhook duplicado: una entrada efectiva, un trabajo y una salida. Automatizaciones de entrada sin duplicación.
- Proveedor deliberadamente lento: comprobar ACK anterior a inferencia y ausencia de transacción/conexión retenida durante la espera. Objetivo provisional ACK p95 inferior a un segundo bajo carga del piloto; medir, no asumir.
- Caídas tras aceptación, reserva, primera etapa, resultado final y commit de outbox antes de envío. Reiniciar consumidor y comprobar recuperación y fencing.
- Dos consumidores o reserva vencida: un propietario efectivo finaliza; uno antiguo no escribe ni envía.
- Mensajes consecutivos/correcciones durante inferencia; orden, memoria coherente y supresión de respuesta obsoleta.
- Handoff y apagado del flag en cada frontera; fuente despublicada; error de envío y entrega incierta sin reenvío ciego.
- Automatizaciones continúan durante inferencias lentas. Medir RAM/CPU, cola y retrasos antes de aceptar compartir worker.
- Migración y despliegue con IA desactivada; regresión completa del recorrido anterior, transportes, permisos y handoff.

Extender las suites existentes `test_whatsapp_live_processor_repository.py`, `test_whatsapp_live_endpoint_security.py`, `test_conversation_management.py`, `test_human_handoff.py`, `test_published_bot_knowledge_retriever.py`, `test_bot_management_endpoints.py` y las de conocimiento. Los tests actuales son base, no prueba de estos comportamientos nuevos.

### 40 conversaciones reproducibles propuestas

| Grupo | Cantidad | Ejemplos |
|---|---:|---|
| Descubrimiento y continuidad | 10 | Edad/intereses repartidos en turnos; «sí» contextual; no repetir presupuesto conocido. |
| Correcciones y cambios de asunto | 6 | «No tiene cinco, tiene ocho»; otro destinatario; cambio de producto a servicio. |
| Recomendación fundamentada | 8 | Alternativas reales, presupuesto, restricciones incompatibles, explicación por atributos. |
| Información insuficiente | 6 | Sin edad recomendada, sin precio/stock, búsqueda sin resultados. |
| Seguridad y aislamiento | 6 | Inyección en cliente/documento, producto de otro bot, instrucciones de ampliar permisos. |
| Handoff y fallos | 4 | Solicitud humana, humano activo, timeout, flag apagado. |

Fixtures sintéticas con catálogo, mensajes, estado inicial, necesidades esperadas, referencias permitidas y afirmaciones prohibidas. No exigir texto idéntico: evaluar hechos, continuidad y acciones. Registrar configuración exacta para comparar ejecuciones. Revisión humana de naturalidad y utilidad comercial, además de validaciones automáticas. [Guía oficial de evaluación](https://developers.openai.com/api/docs/guides/evaluation-best-practices).

Para habilitar el piloto: cero filtraciones entre tenants, cero recomendaciones de IDs inexistentes y cero acciones prohibidas en la batería; todos los casos críticos de apagado/handoff/recuperación aprobados. Cualquier afirmación comercial no sustentada bloquea la habilitación hasta corregirse. Estos resultados no constituyen garantía universal fuera del conjunto evaluado.

Las llamadas reales a Luna y la prueba de WhatsApp vienen después de aprobar arquitectura, preparar configuración y acordar el piloto. Esta revisión no requiere acceso al número ni repite la prueba manual previamente aplazada.

## Recomendación y siguiente decisión

Aprobar conceptualmente el asesor con Luna, catálogo publicado por bot, memoria cifrada y contrato validado. Antes de programar el recorrido, resolver expresamente **si ampliamos el worker existente para consumir y recuperar trabajos IA**. Si se acepta, implementar primero persistencia y pruebas con proveedor falso; después conectar Luna y habilitar un único bot con presupuesto limitado.

No se han modificado código, configuración de bots, infraestructura ni despliegues. Este documento no autoriza ni da por realizada la implementación.
