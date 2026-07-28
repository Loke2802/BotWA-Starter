# ENG-005 — CTO Decisions: Integration Engine

**Date:** 2026-07-22
**Status:** Open Decisions — Awaiting CTO Resolution
**Prerequisite:** ENG005_DOMAIN_ANALYSIS.md (approved)
**Next:** Master Implementation Plan (after all decisions closed)

---

## How to read this document

Each decision is presented as:

> **# — Título**
> **Contexto:** Situación actual y problema.
> **Alternativas:** Opciones (A, B, C) con brief de cada una.
> **Impacto en los 5 Engines:** Cómo afecta a CE, BB, KE, AE y al propio IE.
> **Riesgos:** Por alternativa.
> **Recomendación técnica:** Juicio del ingeniero. No vinculante.

El CTO debe seleccionar una alternativa (o combinación) por cada decisión.

---

## D1 — Modelo Inbound/Outbound

### Contexto

Hoy el flujo de integración está partido en dos:

- **Inbound** (WhatsApp → Core): Webhook en `app/channels/whatsapp/webhook.py` llama directamente a `ConversationService.handle_message()`. No pasa por ningún Engine de integración.
- **Outbound** (Core → WhatsApp): `WhatsAppSender.send()` llama directamente a la Graph API de Meta. No pasa por ningún Engine de integración.

El Integration Engine debe gobernar ambas direcciones, pero no está claro si debe ser un proxy obligatorio (todo el tráfico externo pasa por él) o un servicio invocado bajo demanda.

### Alternativas

| | Opción | Descripción |
|---|---|---|
| **A** | Proxy obligatorio bidireccional | Todo tráfico externo (inbound y outbound) atraviesa el IE. Los webhooks llegan al IE, que normaliza y entrega al Engine correspondiente. Las respuestas outbound salen del IE. |
| **B** | IE outbound-only | El IE solo gestiona comunicación saliente. Los webhooks inbound son recibidos por routers específicos que convierten directamente a `ConversationMessage` y llaman al CE. |
| **C** | IE asíncrono con event bus | El IE publica eventos de integración. Los Engines se suscriben. No hay llamada directa IE → Engine. El webhook inbound genera un `IntegrationEvent` que el CE consume. |

### Impacto

| Engine | A (proxy bidireccional) | B (outbound-only) | C (event bus) |
|---|---|---|---|
| **CE** | Recibe `ConversationMessage` del IE en vez de del webhook. No conoce canales. | Sigue recibiendo mensajes del webhook directamente. Sin cambio. | Recibe eventos del bus. Necesita suscripción. Desacoplamiento máximo. |
| **BB** | Sin impacto. Sigue recibiendo `BusinessRequest` del CE. | Sin impacto. | Sin impacto directo. |
| **KE** | Sin impacto. | Sin impacto. | Sin impacto directo. |
| **AE** | Sin impacto. | Sin impacto. | Podría suscribirse a eventos de integración. |
| **IE** | Punto único de entrada/salida. Máxima gobernanza. | Solo modela outbound. Más simple pero incompleto. | Máxima flexibilidad. Mayor complejidad inicial. |

### Riesgos

- **A:** Mayor latencia en inbound (todo pasa por IE). Punto único de fallo si no se diseña bien.
- **B:** No hay trazabilidad del inbound. Los canales siguen acoplados a routers específicos.
- **C:** Complejidad alta para Starter. Event bus introduce state management, retry de eventos, ordering.

### Recomendación técnica

**B** para Starter (iterativo). El inbound puede migrarse al IE más adelante. El outbound es donde más se necesita gobernanza hoy (reintentos, monitoreo, errores). **A** es el destino arquitectónico correcto según D-012 pero puede abordarse en una segunda iteración.

---

## D2 — ChannelAdapter Ownership

### Contexto

Hoy `ChannelAdapter` (abstracto + `HttpChannelAdapter`) vive en `app/core/conversation/`. Según D-012, la traducción a protocolos externos es responsabilidad del Integration Engine, no del Conversation Engine.

`ChannelAdapter.adapt()` recibe `BusinessResponse` y devuelve `ChannelResponse`. No traduce a protocolos de proveedor — solo adapta el formato interno de respuesta.

### Alternativas

| | Opción | Descripción |
|---|---|---|
| **A** | Mover `ChannelAdapter` al IE | El CE produce `ChannelResponse` canónico. El IE adapta a protocolo específico. El CE no conoce canales. |
| **B** | Mantener en CE | El CE sigue siendo responsable de la adaptación. El IE gestiona otras integraciones (CRM, ERP, etc.). |
| **C** | Dos niveles: CE Adapter + IE Integration Adapter | CE tiene un adaptador mínimo (response → canónico). IE tiene Integration Adapters (canónico → protocolo externo). |

### Impacto

| Engine | A (mover al IE) | B (mantener en CE) | C (dos niveles) |
|---|---|---|---|
| **CE** | Pierde `ChannelAdapter`. Su responsabilidad termina en `ChannelResponse`. | Mantiene ownership. Sin cambio. | Mantiene adaptador mínimo. Cambio menor. |
| **BB** | Sin impacto. | Sin impacto. | Sin impacto. |
| **KE** | Sin impacto. | Sin impacto. | Sin impacto. |
| **AE** | Sin impacto. | Sin impacto. | Sin impacto. |
| **IE** | Gana ownership de adaptación a canales. | Solo gestiona no-channel integrations. | Gestiona todo. Separación clara de concerns. |

### Riesgos

- **A:** Cambio estructural en CE. Dependencies.py se modifica.
- **B:** El CE sigue con una responsabilidad que no le pertenece (D-012). Duplicidad futura.
- **C:** Dos abstracciones similares. Confusión conceptual si no se nombran bien.

### Recomendación técnica

**C.** El `ChannelAdapter` actual no hace verdadera adaptación a protocolos — solo convierte `BusinessResponse` → `ChannelResponse`. Eso es legítimo del CE. El IE necesita `IntegrationAdapter` para la verdadera traducción a protocolos externos (ConversationMessage → payload WhatsApp API). Son dos responsabilidades distintas con dos interfaces distintas.

---

## D3 — IntegrationRequest Model

### Contexto

No existe `IntegrationRequest`. Los Engines que necesiten una integración (hoy solo CE para outbound) no tienen un contrato estándar para solicitarla.

### Alternativas

| | Opción | Descripción |
|---|---|---|
| **A** | Genérico con payload dict | `IntegrationRequest(capability: str, tenant_id: str, payload: dict)` |
| **B** | Tipado por capacidad | Cada capacidad tiene su propio request model (e.g., `MessagingRequest`, `CrmQueryRequest`) que extiende una base. |
| **C** | Híbrido | Envoltorio genérico con payload tipado: `IntegrationRequest[T](capability, tenant_id, payload: T)` |

### Impacto

| Engine | A (dict) | B (tipado) | C (híbrido) |
|---|---|---|---|
| **CE** | Construye dict simple. | Necesita conocer tipo específico (e.g., `MessagingRequest`). | Construye genérico con payload tipado. |
| **BB** | Sin impacto (no llama al IE directamente). | Sin impacto. | Sin impacto. |
| **KE** | Si KE necesita IE, construye dict. | Necesita conocer tipo. | Genérico + payload tipado. |
| **AE** | Si AE necesita IE, construye dict. | Ídem KE. | Ídem KE. |
| **IE** | Gateway valida dict genéricamente. | Gateway puede validar tipos específicos. | Gateway valida envoltorio + tipo interno. |

### Riesgos

- **A:** Pérdida de tipo. Validación débil. Descubrimiento difícil (¿qué campos espera cada capacidad?).
- **B:** Multiplicación de modelos. Cada nueva capacidad requiere nuevo tipo.
- **C:** Requiere Generics/Typing. Python 3.12+ lo soporta bien. Mayor complejidad de tipos.

### Recomendación técnica

**C.** Python 3.12+ soporta `Generic[T]` nativamente. El Integration Gateway puede validar el envoltorio sin conocer el payload interno, y el Adapter conoce el tipo concreto. Balance entre seguridad de tipos y flexibilidad.

---

## D4 — Provider Registry

### Contexto

Hoy los proveedores están hardcodeados. Solo existe WhatsApp, configurado en `Settings`. No hay un registro de proveedores que el Provider Resolver pueda consultar.

### Alternativas

| | Opción | Descripción |
|---|---|---|
| **A** | Registro estático en código | Similar a `create_default_registry()` del Automation Engine. Los `IntegrationAdapter` se registran en un diccionario en memoria al iniciar. |
| **B** | Registro en base de datos | Los proveedores se configuran por tenant en DB. El Provider Resolver consulta la configuración activa. |
| **C** | Híbrido | Catálogo de capacidades y adaptadores en código. Configuración de tenant (qué proveedor usa) en DB. |

### Impacto

| Engine | A (estático) | B (DB) | C (híbrido) |
|---|---|---|---|
| **CE** | Sin impacto. | Sin impacto. | Sin impacto. |
| **BB** | Sin impacto. | Sin impacto. | Sin impacto. |
| **KE** | Sin impacto. | Sin impacto. | Sin impacto. |
| **AE** | Sin impacto. | Sin impacto. | Sin impacto. |
| **IE** | Registro simple. Sin DB dependency para funcionar. Proveedores fijos hasta reinicio. | Full multi-tenant. Configurable sin deploy. Más complejo. | Lo mejor de ambos. Adaptadores en código, configuración en DB. |

### Riesgos

- **A:** No soporta multi-tenant. Cambiar proveedor requiere deploy.
- **B:** Complejidad alta. El IE necesita DB para funcionar incluso en desarrollo.
- **C:** Mayor complejidad que A pero menor que B. Dos fuentes de verdad que deben sincronizarse.

### Recomendación técnica

**A** para Starter (usando el mismo patrón que `TaskRegistry`). **Migrar a C** cuando se necesite multi-tenant real. El registro estático es suficiente para el MVP con 1–2 canales y permite que el IE funcione sin DB.

---

## D5 — Multi-tenant Configuration

### Contexto

Hoy toda la configuración está en `Settings` (variables de entorno). WhatsApp token, phone number ID, API version — todo global. No existe aislamiento por tenant.

### Alternativas

| | Opción | Descripción |
|---|---|---|
| **A** | Config global en Settings (status quo) | Una configuración por deployment. Cada deploy sirve a un tenant. |
| **B** | Config por tenant en DB | Cada empresa tiene su propia configuración de proveedores almacenada en DB. |
| **C** | Config en DB + secret store | Configuración no sensible en DB. Credenciales en secret store (vault, AWS Secrets Manager). |

### Impacto

| Engine | A (global) | B (DB) | C (DB + secrets) |
|---|---|---|---|
| **CE** | Sin impacto. | Sin impacto. | Sin impacto. |
| **BB** | Sin impacto. | Sin impacto. | Sin impacto. |
| **KE** | Sin impacto. | Sin impacto. | Sin impacto. |
| **AE** | Sin impacto. | Sin impacto. | Sin impacto. |
| **IE** | `ProviderResolver` no necesita resolver por tenant. Simple. | `ProviderResolver` consulta configuración del tenant en cada request. | Ídem B + integración con secret store. |

### Riesgos

- **A:** No escala a multi-tenant. Cada tenant requiere un deployment separado.
- **B:** Manejo de secretos en DB (token en texto plano). Riesgo de seguridad.
- **C:** Complejidad operativa. Dependencia externa (vault). Latencia adicional en cada resolución.

### Recomendación técnica

**A** para Starter (un deployment = un tenant). Preparar el modelo de datos en DB para migración futura a **C**, pero no activarlo hasta que haya al menos 2 tenants reales. El `ProviderResolver` debe diseñarse con una interfaz que permita swapping: `ConfigProvider(ABC)` con `EnvConfigProvider` ahora y `DbConfigProvider` después.

---

## D6 — Authentication / Credentials

### Contexto

El token de WhatsApp es una string plana en `.env`. Se inyecta directamente en `WhatsAppClient`. Sin gestión de secretos, sin rotación, sin aislamiento por tenant.

### Alternativas

| | Opción | Descripción |
|---|---|---|
| **A** | Status quo (env vars) | Token en `.env`. Se lee en `Settings`. Se pasa al client. |
| **B** | Env vars + encriptación en DB | Token en env para desarrollo. En producción, encriptado en DB con clave maestra en env. |
| **C** | Secret store externo | Vault, AWS Secrets Manager, o similar. El IE obtiene credenciales bajo demanda. |

### Impacto

| Engine | A (env vars) | B (DB encriptado) | C (secret store) |
|---|---|---|---|
| **CE** | Sin impacto. | Sin impacto. | Sin impacto. |
| **BB** | Sin impacto. | Sin impacto. | Sin impacto. |
| **KE** | Sin impacto. | Sin impacto. | Sin impacto. |
| **AE** | Sin impacto. | Sin impacto. | Sin impacto. |
| **IE** | `ProviderResolver` lee de Settings. Simple. | Necesita desencriptar. Clave maestra en env. | Necesita cliente de secret store. Latencia adicional. |

### Riesgos

- **A:** Token en texto plano. Sin rotación. Exposición en logs.
- **B:** Clave maestra en env (mismo problema). Encriptación/desencriptación añade complejidad.
- **C:** Dependencia externa. Latencia. Costo operativo. Complejidad en desarrollo local.

### Recomendación técnica

**A** para desarrollo local. **Preparar abstracción `CredentialProvider`** desde el inicio para que el IE pueda migrar a **B** o **C** sin cambios estructurales. En producción Starter, **B** es suficiente (clave maestra en env, tokens en DB encriptados).

---

## D7 — Retry Strategy

### Contexto

Hoy no hay reintentos. `WhatsAppSender.send()` captura `HTTPStatusError` y `RequestError`, loggea, y devuelve `SendResult(success=False)`. El webhook responde OK independientemente.

### Alternativas

| | Opción | Descripción |
|---|---|---|
| **A** | Sin reintentos (status quo) | Error se loggea y propaga. El Engine solicitante decide si reintenta. |
| **B** | Retry fijo | N reintentos con delay fijo. Configurable globalmente. |
| **C** | Exponential backoff con jitter | N reintentos con delay exponencial + random jitter. Configurable por integración. |

### Impacto

| Engine | A (sin retry) | B (fijo) | C (exponential backoff) |
|---|---|---|---|
| **CE** | Outbound puede fallar silenciosamente. | El CE espera mientras IE reintenta (si sync). | Ídem B pero más resiliente. |
| **BB** | Sin impacto. | Sin impacto. | Sin impacto. |
| **KE** | Sin impacto. | Sin impacto. | Sin impacto. |
| **AE** | Sin impacto (AE no usa IE hoy). | Sin impacto. | Sin impacto. |
| **IE** | Simple. Sin state management de retry. | State simple (contador). | State management más complejo. Timer/scheduler para retry diferido. |

### Riesgos

- **A:** Pérdida de mensajes. Sin resiliencia.
- **B:** Riesgo de thundering herd si muchos reintentos coinciden.
- **C:** Complejidad. Mensajes en cola de retry. Posible pérdida si la aplicación se reinicia.

### Recomendación técnica

**C.** Es el estándar de la industria para integraciones externas. El patrón es conocido y predecible. Para Starter, implementar con un `RetryPolicy` configurable por adaptador (similar al que ya existe en Automation Engine: `max_attempts`, `delay_seconds`, `backoff_multiplier`). El reintento debe ser responsabilidad del Integration Monitor, no del Adapter.

---

## D8 — Timeout Management

### Contexto

Hoy `WhatsAppClient` tiene timeout hardcodeado de 30 segundos. No hay timeout por tipo de integración ni por proveedor.

### Alternativas

| | Opción | Descripción |
|---|---|---|
| **A** | Timeout global único | Una sola configuración de timeout para todas las integraciones. |
| **B** | Timeout por capacidad | Cada capacidad define su timeout (messaging=10s, CRM=30s, LLM=60s). |
| **C** | Timeout por proveedor + capacidad | Jerarquía: timeout del proveedor como base, sobrescribible por capacidad. |

### Impacto

| Engine | A (global) | B (por capacidad) | C (proveedor + capacidad) |
|---|---|---|---|
| **CE** | Outbound bloqueado máximo N segundos. | Timeout más preciso por tipo de envío. | Máxima precisión. |
| **BB** | Sin impacto. | Sin impacto. | Sin impacto. |
| **KE** | Sin impacto. | Sin impacto. | Sin impacto. |
| **AE** | Sin impacto. | Sin impacto. | Sin impacto. |
| **IE** | Config simple. Una constante. | Requiere mapa capacidad→timeout en Provider Resolver o Adapter. | Requiere configuración por proveedor en Registry. |

### Riesgos

- **A:** Timeout largo bloquea hilos. Timeout corto mata integraciones lentas.
- **B:** Mayor configuración. Olvidar configurar una capacidad usa default.
- **C:** Complejidad de configuración. Jerarquía puede ser confusa.

### Recomendación técnica

**B.** Es el balance óptimo. El Integration Monitor debe detectar timeouts frecuentes y publicar eventos. El timeout debe ser configurable en el `ProviderConfig` con un default sensato por capacidad.

---

## D9 — Circuit Breaker

### Contexto

No existe circuit breaker. Si la API de Meta está caída, cada mensaje intenta enviarse, espera 30s timeout, falla, loggea el error. Sin protección.

### Alternativas

| | Opción | Descripción |
|---|---|---|
| **A** | Sin circuit breaker | Cada request intenta la conexión. El error se maneja individualmente. |
| **B** | Circuit breaker simple | Closed → Open tras N fallos consecutivos. Open → Half-open tras M segundos. Half-open → Closed si el próximo request funciona. |
| **C** | Circuit breaker con métricas | Ídem B pero con ventana deslizante de tiempo y umbral de tasa de error. |

### Impacto

| Engine | A (sin CB) | B (simple) | C (métricas) |
|---|---|---|---|
| **CE** | Riesgo de latencia alta si Meta está caída. | Respuesta rápida de fallo cuando circuit open. | Ídem B. |
| **BB** | Sin impacto. | Sin impacto. | Sin impacto. |
| **KE** | Sin impacto. | Sin impacto. | Sin impacto. |
| **AE** | Sin impacto. | Sin impacto. | Sin impacto. |
| **IE** | Sin state. | State por proveedor (abierto/cerrado/medio-abierto). | State + métricas. Mayor precisión. |

### Riesgos

- **A:** Degradación del sistema cuando un proveedor externo falla (threads bloqueados en timeout).
- **B:** Umbral fijo puede abrir el circuito prematuramente o no abrirlo cuando debería.
- **C:** Complejidad. Configuración de ventana, umbral, muestreo.

### Recomendación técnica

**B** para Starter. Suficiente para proteger contra fallos masivos de proveedor. **Migrar a C** cuando haya suficientes datos de integración para ajustar umbrales. El Circuit Breaker debe vivir en el Integration Monitor o como wrapper del Provider Client.

---

## D10 — Health Checks

### Contexto

Hoy el endpoint `/health` devuelve `{"status":"ok"}` estáticamente. No verifica conectividad con proveedores externos. Si Meta está caído, `/health` responde OK.

### Alternativas

| | Opción | Descripción |
|---|---|---|
| **A** | Sin health checks de proveedores | Status quo. Health check solo verifica que la app responde. |
| **B** | Health check bajo demanda | `/health` intenta verificar cada proveedor (e.g., llama a un endpoint de Meta) y reporta estado. |
| **C** | Health check periódico en background | Un worker revisa periódicamente la conectividad con cada proveedor y actualiza un estado en memoria o DB. |

### Impacto

| Engine | A (sin HC) | B (bajo demanda) | C (periódico) |
|---|---|---|---|
| **CE** | No sabe si el canal está disponible. | Puede saberlo si consulta al IE. | Puede saberlo consultando estado en IE. |
| **BB** | Sin impacto. | Sin impacto. | Sin impacto. |
| **KE** | Sin impacto. | Sin impacto. | Sin impacto. |
| **AE** | Sin impacto. | Sin impacto. | Sin impacto. |
| **IE** | Sin responsabilidad de health. | Health check en cada request. Latencia. | Worker en background. Estado siempre actualizado. |

### Riesgos

- **A:** Ciego ante caídas de proveedor. Mensajes se pierden sin alerta.
- **B:** Health check lento si hay muchos proveedores. Puede rate-limitear al proveedor.
- **C:** Complejidad del worker. Estado eventualmente consistente (ventana entre health check y caída real).

### Recomendación técnica

**B + C.** Health check periódico para monitoreo interno. Health check bajo demanda para decisiones críticas (e.g., antes de enviar un mensaje importante). El Integration Monitor debe exponer el estado de cada proveedor como métrica.

---

## D11 — Rate Limiting

### Contexto

WhatsApp API tiene rate limits (aprox. 80 msg/segundo por número de teléfono). Hoy no hay control. Si BotWA envía rápidamente, Meta responde 429 y el mensaje se pierde.

### Alternativas

| | Opción | Descripción |
|---|---|---|
| **A** | Sin rate limiting | Dejar que Meta rechace con 429. Sin reintento controlado. |
| **B** | Token bucket simple | Un bucket por proveedor. N tokens por segundo. Si no hay tokens, se encola o rechaza. |
| **C** | Rate limiting adaptativo | Ajusta dinámicamente la tasa basado en respuestas 429 y latencia del proveedor. |

### Impacto

| Engine | A (sin RL) | B (token bucket) | C (adaptativo) |
|---|---|---|---|
| **CE** | Mensajes pueden perderse por 429. | Mensajes se encolan o fallan controladamente. | Ídem B, pero más eficiente. |
| **BB** | Sin impacto. | Sin impacto. | Sin impacto. |
| **KE** | Sin impacto. | Sin impacto. | Sin impacto. |
| **AE** | Sin impacto. | Sin impacto. | Sin impacto. |
| **IE** | Sin state. | State por proveedor (tokens disponibles). | State + lógica adaptativa. Mayor complejidad. |

### Riesgos

- **A:** Pérdida de mensajes. Experiencia de cliente inconsistente.
- **B:** Token bucket necesita configuración inicial (tokens/segundo). Difícil de ajustar sin datos.
- **C:** Comportamiento impredecible al inicio (sin datos históricos para ajustar).

### Recomendación técnica

**B** para Starter. Token bucket es simple, eficiente, y conocido. Configurable por proveedor en `ProviderConfig`. El Integration Monitor debe alertar cuando un provider rate-limitea frecuentemente (indica que el bucket necesita ajuste).

---

## D12 — Observabilidad

### Contexto

Hoy la observabilidad de integraciones es mínima: logs estructurados con structlog y eventos de negocio en `BusinessEventModel`. No hay métricas de integración (latencia, tasa de error, throughput).

### Alternativas

| | Opción | Descripción |
|---|---|---|
| **A** | Solo logs | Cada integración loggea inicio, éxito/fallo. Sin métricas ni eventos estructurados. |
| **B** | Logs + IntegrationEvents | Cada integración publica `IntegrationEvent` al modelo de eventos (reutilizando `BusinessEventModel` o creando uno propio). |
| **C** | Logs + IntegrationEvents + métricas | Todo lo anterior + métricas en memoria/DB (latencia p50/p95/p99, tasa de error, throughput, uptime de proveedores). |

### Impacto

| Engine | A (logs) | B (logs + eventos) | C (logs + eventos + métricas) |
|---|---|---|---|
| **CE** | Sin visibilidad de si el mensaje se entregó. | Puede consultar eventos para saber estado de entrega. | Ídem B + métricas históricas. |
| **BB** | Sin impacto. | Sin impacto. | Sin impacto. |
| **KE** | Sin impacto. | Sin impacto. | Sin impacto. |
| **AE** | Sin impacto. | Puede reaccionar a IntegrationEvents. | Ídem B. |
| **IE** | Simple. Sin overhead. | Overhead de escritura de eventos. | Overhead de cálculo de métricas + eventos. |

### Riesgos

- **A:** Imposible diagnosticar problemas de integración sin leer logs manualmente.
- **B:** Volumen de eventos puede ser alto. Sin métricas agregadas.
- **C:** Complejidad. Almacenamiento de métricas. Sin métricas no hay alertas.

### Recomendación técnica

**B** para Starter. Los eventos de integración son el insumo mínimo para trazabilidad. Las métricas agregadas pueden calcularse a partir de los eventos (query sobre la tabla de eventos). Añadir **métricas en memoria** (latencia, tasa de error) como complemento ligero sin persistencia adicional. El Integration Monitor debe ser el componente responsable de toda la observabilidad.

---

## D13 — Sync vs Async IE Calls

### Contexto

Hoy `WhatsAppSender.send()` es async (el webhook la await). Pero el IE podría necesitar ambos modos según la integración: sync para consultas rápidas (CRM lookup), async para procesos largos (email, notificaciones batch).

### Alternativas

| | Opción | Descripción |
|---|---|---|
| **A** | Solo sync | Toda integración es síncrona. El Engine espera la respuesta. |
| **B** | Solo async | Toda integración devuelve un ticket. El Engine consulta después el resultado. |
| **C** | Híbrido configurable | Sync para integraciones rápidas (messaging, CRM query). Async para lentas (email, reportes). Configurable por capacidad. |

### Impacto

| Engine | A (solo sync) | B (solo async) | C (híbrido) |
|---|---|---|---|
| **CE** | Outbound bloquea hasta que IE responde. | Necesita polling o callback. Complejidad. | Sync para messaging (respuesta inmediata). |
| **BB** | Sin impacto (no llama a IE). | Sin impacto. | Sin impacto. |
| **KE** | Si KE consulta CRM externo via IE, espera. | KE necesita manejar callback. | KE usa sync para consultas, async para sincronización. |
| **AE** | AE espera que las tasks terminen. | AE puede disparar y olvidar. | AE elige según tarea. |
| **IE** | Simple. Thread pool. | Cola + worker + callback/pubsub. Complejidad. | Lo mejor de ambos. |

### Riesgos

- **A:** Threads bloqueados en integraciones lentas. Timeouts.
- **B:** Complejidad de estado. Callbacks o polling. Dificultad de depuración.
- **C:** Dos modos = dos caminos de código. Consistencia entre modos.

### Recomendación técnica

**A** para Starter con timeout controlado. **C** cuando haya casos de uso que lo requieran (ej: enviar un reporte por email). El `IntegrationMonitor` debe soportar ambos modos de forma transparente.

---

## D14 — Webhook Ingestion Model

### Contexto

Hoy cada canal registra su propio webhook en FastAPI. WhatsApp tiene `app/channels/whatsapp/webhook.py`. Telegram tendría `app/channels/telegram/webhook.py`. Cada uno monta su ruta en `app/main.py`.

### Alternativas

| | Opción | Descripción |
|---|---|---|
| **A** | Per-channel routers (status quo) | Cada canal registra su propio endpoint. El webhook llama directamente al CE o al IE. |
| **B** | Single IE webhook receiver | Un único endpoint `/integrations/webhook` que recibe todos los webhooks, detecta el canal por el payload, y delega al IntegrationAdapter correspondiente. |
| **C** | Per-channel routers delegando al IE | Cada canal tiene su router, pero el router delega en el IE para procesar (validar, normalizar) antes de entregar al CE. |

### Impacto

| Engine | A (per-channel) | B (single receiver) | C (routers + IE) |
|---|---|---|---|
| **CE** | Recibe mensaje directamente o vía IE. | Recibe mensaje siempre vía IE. | Recibe mensaje vía IE. Sin cambio vs B. |
| **BB** | Sin impacto. | Sin impacto. | Sin impacto. |
| **KE** | Sin impacto. | Sin impacto. | Sin impacto. |
| **AE** | Sin impacto. | Sin impacto. | Sin impacto. |
| **IE** | No participa en inbound (a menos que B o C). | Punto único de entrada. Conoce todos los canales. | Participa pero los routers existen. |

### Riesgos

- **A:** Sin gobernanza centralizada del inbound. Cada canal es un punto de entrada independiente.
- **B:** Single receiver debe parsear todos los formatos de webhook. Complejidad en el dispatch. Punto único de fallo.
- **C:** Lo peor de ambos: routers existen (complejidad) + IE añade overhead.

### Recomendación técnica

**C** para Starter (migración gradual). Mantener los routers específicos por canal (son simples, frágiles pero conocidos). Que cada router llame al IE para validación y normalización antes de entregar al CE. Eventualmente migrar a **B** cuando todos los canales usen el IE.

---

## D15 — Error Propagation

### Contexto

Hoy `WhatsAppSender` devuelve `SendResult(success, error)`. El webhook loggea el error pero responde HTTP 200 a Meta. El CE nunca sabe si el mensaje se envió o no.

### Alternativas

| | Opción | Descripción |
|---|---|---|
| **A** | Devolver IntegrationResult siempre | Sync: IE devuelve `IntegrationResult` con éxito/fallo + detalles. Async: publica `IntegrationEvent` con el resultado. |
| **B** | Excepciones tipadas | IE lanza excepciones específicas (`ProviderTimeoutError`, `ProviderAuthError`, `ProviderRateLimitedError`). El Engine caller las captura. |
| **C** | Híbrido | Result para sync (predecible, comprobable). Evento para async (desacoplado). Excepción solo para errores de programación (contrato inválido, proveedor no encontrado). |

### Impacto

| Engine | A (IntegrationResult) | B (excepciones) | C (híbrido) |
|---|---|---|---|
| **CE** | Recibe resultado. Decide qué hacer. | Recibe excepción. try/except. | Recibe resultado o excepción según el caso. |
| **BB** | Sin impacto. | Sin impacto. | Sin impacto. |
| **KE** | Si KE usa IE, recibe resultado. | KE necesita try/except. | KE recibe resultado (consultas siempre sync). |
| **AE** | AE recibe resultado en task handler. | AE necesita try/except. | AE usa resultado en handlers sync, evento en async. |
| **IE** | Modelo uniforme de salida. | Excepciones = flujo de control (code smell). | Dos mecanismos. Consistente pero más complejo. |

### Riesgos

- **A:** El caller siempre debe checkear `result.success`. Fácil de olvidar.
- **B:** Excepciones para errores esperados (HTTP 429, timeout) es antipatrón en Python.
- **C:** Dos caminos. El caller necesita saber qué esperar.

### Recomendación técnica

**A.** `IntegrationResult` es el mecanismo correcto para errores esperados de integración. Excepciones para errores inesperados (bug, infraestructura). El caller checkea el resultado y decide respuesta, reintento, o escalación. Patrón usado en Automation Engine (`TaskExecution`).

---

## D16 — Integration Engine Pipeline Architecture

### Contexto

El IE debe ubicarse en la arquitectura. Hoy el `ChannelAdapter` está dentro de `ConversationService`. El IE necesita definir cómo los Engines lo invocan.

### Alternativas

| | Opción | Descripción |
|---|---|---|
| **A** | IE como dependencia directa | Los Engines importan e invocan `IntegrationService` directamente (similar a como CE llama a BB). |
| **B** | IE como middleware | El IE se inserta en el pipeline como middleware. El CE entrega `ChannelResponse` al IE, el IE lo procesa y lo envía. |
| **C** | IE como servicio standalone con API | El IE corre como un proceso/servicio separado con su propia API (interna). Los Engines hacen HTTP/gRPC. |

### Impacto

| Engine | A (dependencia directa) | B (middleware) | C (standalone) |
|---|---|---|---|
| **CE** | Importa `IntegrationService`. Una dependencia más. | No importa nada. El pipeline lo inyecta. | Sin dependencia de código. Llamada HTTP. |
| **BB** | Podría importarlo para CRM queries. | Sin cambios. | Llamada HTTP para CRM queries. |
| **KE** | Podría importarlo para fuentes externas. | Sin cambios. | Llamada HTTP para fuentes externas. |
| **AE** | Podría importarlo para tasks externas. | Sin cambios. | Llamada HTTP para tasks. |
| **IE** | Librería in-process. | Integrado en el pipeline. | Servicio independiente. Escalable por separado. |

### Riesgos

- **A:** Acoplamiento en tiempo de compilación. Cada Engine que necesite IE debe importarlo.
- **B:** El pipeline del CE se vuelve más complejo. Middleware añade latencia a todos los mensajes, incluso los que no necesitan integración externa.
- **C:** Latencia de red. Complejidad operativa (despliegue, monitoreo). Serialización/deserialización.

### Recomendación técnica

**A** para Starter. Es el mismo patrón que usan todos los Engines (dependencia directa via constructor). **C** es el destino correcto para escalabilidad pero es premature optimization para Starter. El IE debe diseñarse con una interfaz limpia que permita migrar a servicio standalone sin modificar los callers.

---

## D17 — Capability Modeling

### Contexto

El Provider Resolver necesita entender "qué quiere hacer" el Engine solicitante para seleccionar el proveedor adecuado. Hoy no existe este concepto.

### Alternativas

| | Opción | Descripción |
|---|---|---|
| **A** | String-based capabilities | `"send_message"`, `"query_crm"`, `"email_send"`. Flexibles pero frágiles. |
| **B** | Enum-based capabilities | `Capability.SEND_MESSAGE`, `Capability.QUERY_CRM`. Tipado seguro. |
| **C** | Interface-based capabilities | Cada capacidad es una clase/Protocol: `MessagingCapability`, `CrmQueryCapability`. Máxima expresividad. |

### Impacto

| Engine | A (string) | B (enum) | C (interface) |
|---|---|---|---|
| **CE** | Pasa `"send_message"` al IE. | Pasa `Capability.SEND_MESSAGE`. | Necesita conocer la clase. Mayor acoplamiento. |
| **BB** | Pasa `"query_crm"`. | Pasa `Capability.QUERY_CRM`. | Necesita conocer la clase. |
| **KE** | Pasa `"query_external_source"`. | Pasa `Capability.QUERY_EXTERNAL`. | Necesita conocer la clase. |
| **AE** | Pasa `"email_send"`. | Pasa `Capability.EMAIL_SEND`. | Necesita conocer la clase. |
| **IE** | Gateway valida string contra whitelist. | Gateway valida enum. Provider Resolver matchea enum → proveedor. | Resolución más compleja pero más flexible. |

### Riesgos

- **A:** Typos. Descubrimiento difícil. Sin IDE support.
- **B:** Cada nuevo canal requiere nuevo enum value. Compilación. Pero seguro.
- **C:** Over-engineering para Starter. Multiplicación de clases.

### Recomendación técnica

**B.** Enum es el balance óptimo entre seguridad de tipos y simplicidad. El patrón ya se usa en Automation Engine (`TaskExecutionStatus`, `ExecutionStatusType`). Consistente con el código existente.

---

## D18 — Integration Monitor Storage

### Contexto

El Integration Monitor necesita persistir eventos de integración. Hoy existe `BusinessEventModel` en `app/infrastructure/models/business_event.py`.

### Alternativas

| | Opción | Descripción |
|---|---|---|
| **A** | Reutilizar `BusinessEventModel` | Todos los eventos de integración se persisten en la misma tabla que los eventos de negocio. Diferenciados por `source="integration_engine"` y `event_type`. |
| **B** | Nuevo `IntegrationEventModel` | Tabla separada para eventos de integración. Modelo específico con campos de integración (provider, capability, latency_ms, attempt). |
| **C** | Sin persistencia | Eventos solo en memoria (logs, métricas efímeras). Sin consulta histórica. |

### Impacto

| Engine | A (BusinessEventModel) | B (IntegrationEventModel) | C (sin persistencia) |
|---|---|---|---|
| **CE** | Puede consultar eventos de integración en la misma tabla. | Necesita consultar otra tabla para eventos de integración. | No puede consultar históricos. |
| **BB** | Sin impacto. | Sin impacto. | Sin impacto. |
| **KE** | Sin impacto. | Sin impacto. | Sin impacto. |
| **AE** | Puede reaccionar a eventos en la misma tabla. | Necesita observar otra tabla. | Sin eventos históricos. |
| **IE** | Un modelo menos. Tabla única de eventos. | Modelo específico. Consultas más rápidas. Esquema optimizado. | Sin overhead de DB. Sin trazabilidad. |

### Riesgos

- **A:** La tabla de eventos de negocio se mezcla con eventos técnicos de integración. Volumen puede crecer rápido.
- **B:** Duplicidad con `BusinessEventModel`. Dos tablas de eventos con propósitos similares.
- **C:** Imposible auditar integraciones fallidas retrospectivamente.

### Recomendación técnica

**B.** Los eventos de integración tienen un esquema diferente (provider, capability, latency, attempt, provider_status_code) que no justifica forzarlos en `BusinessEventModel`. Una tabla separada permite consultas específicas y evita contaminar el modelo de eventos de negocio.

---

## D19 — Provider Client Abstraction

### Contexto

`WhatsAppClient` usa `httpx.AsyncClient` directamente. Cada nuevo proveedor escribirá su propio cliente HTTP. Sin abstracción compartida para auth, retry, métricas, logging.

### Alternativas

| | Opción | Descripción |
|---|---|---|
| **A** | Sin abstracción | Cada adapter implementa su propio cliente HTTP. Código duplicado. |
| **B** | Cliente HTTP base | Clase base abstracta que provee: auth injection, retry wrapper, timeout, logging, metrics collection. Los adapters extienden y solo implementan `do_call()`. |
| **C** | Integration framework | Usar una librería existente (e.g., `httpx` con middleware propio, o un integration framework). |

### Impacto

| Engine | A (sin abstracción) | B (cliente base) | C (framework) |
|---|---|---|---|
| **Todos** | Sin impacto (cada adapter es autónomo). | Sin impacto. | Sin impacto. |
| **IE** | Código duplicado. Inconsistencias entre adapters. | Consistencia. Un solo lugar para retry, timeout, metrics. | Dependencia externa. Menos control. |

### Riesgos

- **A:** Cada adapter reinventa la rueda. Inconsistencia en manejo de errores, timeouts, logging.
- **B:** Puede volverse un god class si no se mantiene enfocado.
- **C:** Dependencia externa. Si el framework no cubre un caso, toca workaround.

### Recomendación técnica

**B.** Un `BaseProviderClient` con hooks para `before_request` (auth, metrics start) y `after_response` (metrics end, retry decision). Los adapters implementan `build_request()` y `parse_response()`. Sin dependencias externas más allá de `httpx`.

---

## D20 — Integration Engine Package Structure

### Contexto

El IE necesita un lugar en la jerarquía del proyecto. Hoy no existe `app/core/integration/`.

### Alternativas

| | Opción | Descripción |
|---|---|---|
| **A** | `app/core/integration/` | Hermano de `business/`, `conversation/`, `knowledge/`, `automation/`. |
| **B** | `app/integration/` | Top-level, separado de `app/core/`. El IE es un Engine transversal. |
| **C** | `app/infrastructure/integration/` | La integración es infraestructura, no lógica de negocio. |

### Impacto

| Engine | A (core/integration) | B (app/integration) | C (infrastructure/integration) |
|---|---|---|---|
| **CE** | Importa de `app.core.integration`. | Importa de `app.integration`. | Importa de `app.infrastructure.integration`. |
| **BB** | Importa de `app.core.integration`. | Importa de `app.integration`. | Importa de `app.infrastructure.integration`. |
| **KE** | Ídem. | Ídem. | Ídem. |
| **AE** | Ídem. | Ídem. | Ídem. |
| **IE** | Un Engine más en el Core. Consistente con ADR-003. | Separado del Core. Menos acoplado visualmente. | Trata IE como plumbing. Contradice ADR-003 (IE es un Engine, no infraestructura). |

### Riesgos

- **A:** El Core se vuelve grande (5 engines). Consistente con la arquitectura actual.
- **B:** Rompe la convención de `app/core/` para Engines. Puede confundir.
- **C:** Contradice ADR-003. El IE es un Engine oficial, no infraestructura.

### Recomendación técnica

**A.** `app/core/integration/`. Es consistente con ADR-003 (Engines en Core), ADR-004 (cada Engine tiene su pipeline), y la estructura existente. Mantiene la simetría: los 5 Engines viven en `app/core/`.

---

## Summary Table

| # | Decisión | Alternativas | Recomendación |
|---|---|---|---|
| D1 | Modelo Inbound/Outbound | A: proxy bidireccional, B: outbound-only, C: event bus | **B** (migrar a A después) |
| D2 | ChannelAdapter Ownership | A: mover al IE, B: mantener en CE, C: dos niveles | **C** (CE Adapter + IE Integration Adapter) |
| D3 | IntegrationRequest Model | A: genérico dict, B: tipado, C: híbrido Generic[T] | **C** |
| D4 | Provider Registry | A: estático, B: DB, C: híbrido | **A** (migrar a C después) |
| D5 | Multi-tenant Configuration | A: global env, B: DB por tenant, C: DB + secrets | **A** (preparar interfaz para migrar a C) |
| D6 | Authentication/Credentials | A: env vars, B: DB encriptado, C: secret store | **A** dev, **B** prod (con CredentialProvider abstraction) |
| D7 | Retry Strategy | A: sin retry, B: fijo, C: exponential backoff + jitter | **C** |
| D8 | Timeout Management | A: global, B: por capacidad, C: proveedor + capacidad | **B** |
| D9 | Circuit Breaker | A: sin CB, B: simple, C: con métricas | **B** (migrar a C después) |
| D10 | Health Checks | A: sin HC, B: bajo demanda, C: periódico | **B + C** |
| D11 | Rate Limiting | A: sin RL, B: token bucket, C: adaptativo | **B** |
| D12 | Observabilidad | A: solo logs, B: logs + eventos, C: + métricas | **B** (métricas en memoria) |
| D13 | Sync vs Async | A: solo sync, B: solo async, C: híbrido | **A** (C después) |
| D14 | Webhook Ingestion | A: per-channel, B: single receiver, C: routers + IE | **C** (migrar a B después) |
| D15 | Error Propagation | A: IntegrationResult, B: excepciones, C: híbrido | **A** |
| D16 | IE Pipeline Architecture | A: dependencia directa, B: middleware, C: standalone service | **A** (migrar a C después) |
| D17 | Capability Modeling | A: string, B: enum, C: interface | **B** |
| D18 | Integration Monitor Storage | A: BusinessEventModel, B: IntegrationEventModel, C: sin persistencia | **B** |
| D19 | Provider Client Abstraction | A: sin abstracción, B: BaseProviderClient, C: framework | **B** |
| D20 | IE Package Structure | A: core/integration, B: app/integration, C: infra/integration | **A** |

---

## Decisiones que requieren atención prioritaria

El CTO debe resolver **D1, D2, D3, D4** primero — son las que definen la estructura fundamental del Engine. Las demás pueden resolverse en paralelo o durante la implementación.

**D1** (inbound/outbound) es la más crítica porque define el alcance del Engine y su relación con el CE.

**D16** (pipeline architecture) es la segunda más crítica porque determina cómo los Engines invocan al IE.
