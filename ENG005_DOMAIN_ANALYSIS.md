# ENG-005 — Integration Engine Domain Analysis

**Date:** 2026-07-22
**Status:** Domain Analysis — Ready for CTO Review
**References:** D-012 (all chapters), ADR-003, ADR-005, ADR-006, ADR-007, ADR-009, CONTEXT_FOR_AI.md, BOTWA_ARCHITECTURE_MILESTONE_REVIEW.md, SPEC_Fase_4_v1.0, código actual

---

## 1. Responsabilidad

### 1.1 ¿Qué hace exactamente el Integration Engine?

El Integration Engine es la **frontera tecnológica** de BotWA. Su responsabilidad fundamental es gestionar toda comunicación entre el Core de BotWA (Engines 1–4) y sistemas externos.

**Responsabilidades (según D-012-01):**
- Conectarse con APIs externas
- Consumir servicios externos
- Publicar información hacia el exterior
- Adaptar protocolos (traducir contratos canónicos a protocolos de proveedor)
- Gestionar autenticación contra sistemas externos
- Administrar adaptadores (un adaptador por proveedor)
- Manejar errores de integración (timeouts, fallos, reintentos)
- Normalizar respuestas externas a modelos canónicos
- Monitorear el ciclo de vida de cada integración

**Pipeline oficial (D-012-03):**

```
Integration Request
  → Integration Gateway (validar, normalizar, registrar)
  → Provider Resolver (seleccionar proveedor según tenant)
  → Integration Adapter (traducir a protocolo externo)
  → External System
  → Response Normalizer (traducir respuesta a modelo canónico)
  → Integration Response
```

### 1.2 ¿Qué NO debe hacer?

| No debe | Porque pertenece a |
|---|---|
| Tomar decisiones de negocio | Business Brain (ENG-001) |
| Ejecutar workflows internos | Automation Engine (ENG-004) |
| Mantener conversaciones | Conversation Engine (ENG-002) |
| Administrar conocimiento | Knowledge Engine (ENG-003) |
| Aplicar reglas de negocio | Business Brain (ENG-001) |
| Interpretar intenciones | Business Brain (via IntentClassifier) |
| Seleccionar estrategias | Business Brain (via DecisionMaker) |
| Detectar topics | Conversation Engine (via TopicDetector) |
| Componer respuestas | Conversation Engine (via ResponseComposer) |

### 1.3 Frontera respecto a cada Engine

**Respecto a Conversation Engine:**
- **CE** recibe mensajes, construye contexto, detecta topics, compone respuestas, gestiona estado.
- **IE** traduce respuestas de canal canónico (ChannelResponse) al protocolo específico del proveedor (e.g., payload JSON de WhatsApp API).
- **Frontera:** CE produce `ChannelResponse` (canónico). IE consume `ChannelResponse` y produce `ProviderRequest` (específico).
- **Estado actual:** CE tiene `HttpChannelAdapter` dentro de su paquete que devuelve directamente un `ChannelResponse` con status+message. Para WhatsApp, la adaptación ocurre en `mapper.py` y `sender.py` fuera de cualquier Engine — **no hay frontera**.

**Respecto a Business Brain:**
- **BB** decide qué debe ocurrir (status, intent, confidence, needs_knowledge).
- **IE** nunca recibe ni procesa decisiones de negocio. No es consumidor de `BusinessDecision`.
- **Frontera:** BB → Conversation (BusinessDecision) → Response Composer → ChannelResponse → IE → Provider Request.
- **Estado actual:** No existe relación directa BB→IE. Correcto.

**Respecto a Knowledge Engine:**
- **KE** consulta fuentes de conocimiento internas (catálogo, providers).
- **IE** podría gestionar fuentes externas de conocimiento (APIs de documentos, ERPs, CRMs) cuando KE lo requiera.
- **Frontera:** KE nunca accede directamente a APIs externas. Si necesita información externa, lo solicita al IE mediante `IntegrationRequest`.
- **Estado actual:** KE usa repositorio DB local y provider in-memory. No hay solicitudes externas. La frontera no está implementada.

**Respecto a Automation Engine:**
- **AE** orquesta workflows internos (tasks, task handlers).
- **IE** gestiona comunicación externa. Si una task necesita enviar un email, llamar a una API externa, o sincronizar con CRM, AE delega en IE.
- **Frontera:** AE → IntegrationRequest → IE → External System → IntegrationResponse → AE.
- **Estado actual:** AE ejecuta task handlers que operan sobre datos internos. Ningún handler actual requiere integración externa. La frontera no está implementada.

---

## 2. Objetos de Dominio

Según D-012, BP-012, SPEC_Fase_4 y ADR-007. Se listan solo los contratos definidos en los Blueprints. No se asumen nombres no documentados.

### 2.1 Contratos Identificados (desde los Blueprints)

| Objeto | Fuente | Descripción |
|---|---|---|
| `IntegrationRequest` | D-012-04, BP-012 | Solicitud de integración. Entrada al Integration Gateway. Contiene la capacidad solicitada, payload canónico y metadatos del tenant. |
| `ValidatedIntegrationRequest` | D-012-04 | Salida del Gateway. IntegrationRequest validado y enriquecido, listo para resolución de proveedor. |
| `ProviderContext` | D-012-05 | Salida del Provider Resolver. Contiene el proveedor seleccionado, configuración del tenant, credenciales, y metadata de conexión. |
| `ProviderRequest` | D-012-06, D-012-07 | Traducción específica al protocolo del proveedor. Entrada al Integration Monitor y al sistema externo. |
| `Canonical Integration Response` | D-012-06 | Respuesta normalizada del adaptador. También referida como `IntegrationResponse`. Modelo canónico desacoplado del proveedor. |
| `IntegrationResult` | D-012-07 | Resultado completo de la integración. Incluye éxito/fallo, datos, errores, tiempos, reintentos. |
| `IntegrationEvent` | D-012-07, BP-012 | Evento publicable con metadata de la integración (inicio, fin, error, timeout). |
| `IntegrationResponse` | D-012-03, BP-012 | Respuesta final del pipeline. Equivalente a `Canonical Integration Response`. |

### 2.2 Contratos No Definidos (a confirmar por CTO)

Los siguientes contratos *no aparecen* en los Blueprints D-012 ni en la SPEC. Son candidatos naturales que surgen del análisis de fronteras:

| Contrato Candidato | Justificación |
|---|---|
| `IntegrationCapability` | Tipo de capacidad solicitada (e.g., "messaging", "crm_query", "email_send", "storage_get"). El Provider Resolver necesita esto para seleccionar proveedor. |
| `ProviderConfig` | Configuración específica del proveedor por tenant. Endpoints, credenciales, rate limits, timeouts. |
| `AuthCredential` | Credenciales (API key, OAuth token, basic auth). Debe gestionarse de forma segura, no en código. |
| `IntegrationStatus` | Estado de la integración (pending, in_progress, completed, failed, timeout). |
| `HealthCheckResult` | Resultado de health check de un proveedor. Para Integration Monitor. |

### 2.3 Ownership por ADR-005

Siguiendo ADR-005, todos los objetos de dominio del Integration Engine serán propiedad exclusiva del Integration Engine. Ningún otro Engine los crea, modifica o elimina.

---

## 3. Pipeline Conceptual

### 3.1 Flujo completo (Engine solicitante → IE → Sistema externo → IE → Engine solicitante)

```
┌─────────────────────────────────────────────────────────────────────┐
│                    ENGINE SOLICITANTE                                │
│  (Conversation, Business Brain, Knowledge, Automation)               │
│                                                                      │
│  1. Construye IntegrationRequest                                     │
│     - Capability: "send_message" | "query_crm" | etc.               │
│     - Payload canónico                                               │
│     - Tenant ID                                                      │
│  2. Llama a IntegrationEngine.execute(request)                       │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│  INTEGRATION ENGINE                                                  │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │ INTEGRATION GATEWAY                                             │ │
│  │  - Recibe IntegrationRequest                                    │ │
│  │  - Valida contrato (campos requeridos, tipos, formato)          │ │
│  │  - Verifica integridad (payload completo)                       │ │
│  │  - Rechaza si inválido → IntegrationResult con error            │ │
│  │  - Registra inicio de integración (IntegrationMonitor)          │ │
│  │  - Prepara ValidatedIntegrationRequest                          │ │
│  │  - Delega al Provider Resolver                                  │ │
│  └──────────────────────────┬──────────────────────────────────────┘ │
│                             │                                        │
│                             ▼                                        │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │ PROVIDER RESOLVER                                               │ │
│  │  - Recibe ValidatedIntegrationRequest                           │ │
│  │  - Identifica capacidad solicitada                              │ │
│  │  - Consulta configuración del tenant                            │ │
│  │  - Selecciona proveedor según tenant config + fallback policy    │ │
│  │  - Genera ProviderContext (proveedor, credenciales, endpoint)   │ │
│  │  - Delega al Integration Adapter                                │ │
│  └──────────────────────────┬──────────────────────────────────────┘ │
│                             │                                        │
│                             ▼                                        │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │ INTEGRATION ADAPTER                                             │ │
│  │  - Recibe ProviderContext + ValidatedIntegrationRequest         │ │
│  │  - Traduce payload canónico → ProviderRequest (específico)     │ │
│  │  - Ejecuta llamada externa (HTTP, SDK, etc.)                    │ │
│  │  - Captura respuesta del sistema externo                        │ │
│  │  - Normaliza respuesta → Canonical Integration Response         │ │
│  │  - Delega al Response Normalizer (o IntegrationMonitor)         │ │
│  └──────────────────────────┬──────────────────────────────────────┘ │
│                             │                                        │
│                             ▼                                        │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │ RESPONSE NORMALIZER (parte del Adapter, separado conceptualmente)│ │
│  │  - Transforma respuesta externa a modelo canónico               │ │
│  │  - Preserva datos relevantes, descarta ruido de proveedor       │ │
│  │  - Genera Canonical Integration Response                        │ │
│  └──────────────────────────┬──────────────────────────────────────┘ │
│                             │                                        │
│                             ▼                                        │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │ INTEGRATION MONITOR                                             │ │
│  │  - Registra fin de integración (start → end timestamps)         │ │
│  │  - Publica IntegrationEvent (éxito/fallo/timeout)               │ │
│  │  - Actualiza métricas (latencia, tasa de error, reintentos)     │ │
│  │  - Genera IntegrationResult completo                            │ │
│  └──────────────────────────┬──────────────────────────────────────┘ │
│                             │                                        │
│                             ▼                                        │
│  ── IntegrationResponse → IntegrationResult → al Engine solicitante │
└─────────────────────────────────────────────────────────────────────┘
```

### 3.2 Direccionalidad

El pipeline es **bidireccional** en concepto pero **síncrono por solicitud**:

- **Outbound (Core → Externo):** Engine solicita una integración → IE traduce y envía → respuesta normalizada vuelve.
- **Inbound (Externo → Core):** Webhook externo → IE recibe → normaliza → entrega al Engine correspondiente. Este flujo *inverso* no está detallado en D-012. El webhook de WhatsApp actualmente bypasea completamente el IE.

### 3.3 Modos de integración

| Modo | Descripción | Uso típico |
|---|---|---|
| **Sync** | Engine espera respuesta | Consulta a CRM, envío de mensaje |
| **Async (fire-and-forget)** | Engine no espera respuesta | Publicación de evento, log externo |
| **Webhook/Inbound** | Sistema externo inicia | Recepción de mensaje WhatsApp, callback de pago |
| **Polling** | IE consulta periódicamente | Estado de entrega, actualización de lead |
| **Stream** | Conexión persistente | Tiempo real, websocket |

---

## 4. Integraciones — Clasificación por Tipo

### 4.1 Mensajería (Channels)

Canales de comunicación con clientes. Cada canal tiene inbound (recibir) y outbound (enviar).

| Canal | Inbound | Outbound | Prioridad |
|---|---|---|---|
| WhatsApp | Webhook → adapter → ConversationMessage | ChannelResponse → payload WhatsApp API | Alta (ya existe, bypasea IE) |
| Telegram | Webhook → adapter → ConversationMessage | ChannelResponse → payload Telegram API | Media |
| Facebook Messenger | Webhook → adapter → ConversationMessage | ChannelResponse → payload Messenger API | Media |
| Instagram | Webhook → adapter → ConversationMessage | ChannelResponse → payload Instagram API | Baja |
| Web Chat | WebSocket/HTTP → adapter → ConversationMessage | ChannelResponse → JSON Web Chat | Alta |
| Email | IMAP/POP3/webhook → adapter → ConversationMessage | ChannelResponse → SMTP/API | Media |
| SMS | Webhook/API → adapter → ConversationMessage | ChannelResponse → API SMS provider | Baja |

### 4.2 CRM

Sistemas de gestión de relaciones con clientes. Consulta y actualización de datos de clientes, leads, oportunidades.

| Sistema | Uso esperado | Prioridad |
|---|---|---|
| HubSpot | Consultar/crear contactos, deals | Media (fase MVP+) |
| Salesforce | Consultar/crear leads, oportunidades | Baja |
| Zoho CRM | Sincronización de clientes | Baja |
| API propia del cliente | Endpoint personalizado | Media |

### 4.3 ERP / Backoffice

Sistemas de gestión empresarial. Consulta de productos, stock, pedidos, facturación.

| Sistema | Uso esperado | Prioridad |
|---|---|---|
| API de inventario | Consultar stock, precios | Alta (consulta de conocimiento) |
| API de pedidos | Crear/consultar pedidos | Media |
| Pasarela de pago | Iniciar/verificar pagos | Media |

### 4.4 Notificaciones / Email

Envío de notificaciones transaccionales.

| Sistema | Uso esperado | Prioridad |
|---|---|---|
| SendGrid / Mailgun | Envío de emails transaccionales | Media |
| Twilio | SMS, WhatsApp (canal alternativo) | Baja |
| Push notifications | Mobile/Web push | Baja |

### 4.5 Almacenamiento (Storage)

Gestión de archivos, imágenes, documentos.

| Sistema | Uso esperado | Prioridad |
|---|---|---|
| AWS S3 / Cloud Storage | Almacenar/enviar archivos multimedia | Baja |
| CDN | Entrega de contenido estático | Baja |

### 4.6 Procesadores de Lenguaje Natural (LLM / IA)

Proveedores de IA externos.

| Sistema | Uso esperado | Prioridad |
|---|---|---|
| OpenAI / GPT | Generación de lenguaje natural (cuando el determinista no alcance) | Alta (post MVP) |
| Proveedor específico | Embeddings, clasificación IA | Media |

### 4.7 Analítica / Tracking

Envío de datos de uso y métricas.

| Sistema | Uso esperado | Prioridad |
|---|---|---|
| Google Analytics / Mixpanel | Eventos de producto | Baja |
| Log externo | Logs centralizados | Baja |

### 4.8 Health Check de Proveedores

No es una integración de negocio, sino operativa.

| Proveedor | Uso esperado | Prioridad |
|---|---|---|
| Proveedor de mensajería | Verificar conectividad antes de enviar | Alta |
| Proveedor de CRM | Verificar disponibilidad | Media |

### 4.9 Mapa de Capacidades vs. Proveedores

```
Capacidad                     Proveedores posibles
─────────────────────────────────────────────────────
messaging_send               WhatsApp, Telegram, Messenger,
(canal outbound)             Instagram, Web Chat, Email, SMS

messaging_receive             WhatsApp, Telegram, Messenger,
(canal inbound/webhook)      Instagram, Web Chat, Email, SMS

crm_contact_query             HubSpot, Salesforce, Zoho, API propia

crm_contact_create            HubSpot, Salesforce, Zoho, API propia

inventory_query               API de inventario, ERP

order_create                  API de pedidos, ERP

payment_process               Pasarela de pago

email_send                    SendGrid, Mailgun, SMTP

llm_generate                  OpenAI, Anthropic, proveedor local

storage_get/put               S3, Cloud Storage, CDN

analytics_event               GA4, Mixpanel, PostHog
```

---

## 5. Eventos

### 5.1 Eventos que el Integration Engine CONSUME

Según D-012 y el análisis de flujo, el Integration Engine no consume directamente eventos de otros Engines. En su lugar, recibe **IntegrationRequests** como llamadas directas.

Sin embargo, en un modelo orientado a eventos futuro:

| Evento de Dominio | Fuente | Cuándo lo consume el IE |
|---|---|---|
| `Decisión tomada` | Business Brain | Si la decisión requiere acción externa (enviar mensaje, consultar CRM). En el modelo actual esto se transmite como `BusinessDecision` → `ResponseComposer` → `ChannelResponse`, no como evento. |
| `Automatización ejecutada` | Automation Engine | Si la automatización requiere integración externa. |
| `Conocimiento no encontrado` | Knowledge Engine | Para consultar fuente externa como fallback. |

En la arquitectura actual, estos flujos son síncronos y no usan eventos.

### 5.2 Eventos que el Integration Engine PUBLICA

Según D-012-07 (Integration Monitor):

| Evento | Cuándo | Payload esperado |
|---|---|---|
| `integration.started` | Al iniciar una integración | integration_id, capability, tenant_id, timestamp |
| `integration.completed` | Al finalizar con éxito | integration_id, capability, latency_ms, result_summary |
| `integration.failed` | Al fallar la integración | integration_id, capability, error_type, error_message, attempt |
| `integration.timeout` | Al exceder timeout | integration_id, capability, timeout_seconds |
| `integration.retry` | Al reintentar | integration_id, capability, attempt, delay_ms |
| `provider.health_check.failed` | Health check de proveedor | provider_id, tenant_id, error |

### 5.3 Integración con el sistema de eventos existente

El proyecto actual tiene:
- `BusinessEventPublisher` (en `app/core/business/`) — publica eventos en DB.
- `AutomationEventPublisher` (en `app/core/automation/`) — publica eventos en DB.

El Integration Monitor debería publicar sus propios `IntegrationEvent`. Esto puede reutilizar el modelo `BusinessEventModel` existente o definir su propio mecanismo. Es una decisión de diseño que no se resuelve aquí.

---

## 6. Estado Actual — Blueprint vs. Código

### 6.1 Mapeo completo

| Componente del Blueprint | Estado en Código | Dónde | Observaciones |
|---|---|---|---|
| **Integration Engine** (ENG-005) | **AUSENTE** | — | No existe como Engine. No hay paquete `app/core/integration/`. |
| **Integration Gateway** | AUSENTE | — | No hay validación centralizada de solicitudes de integración. |
| **Provider Resolver** | AUSENTE | — | No hay selección de proveedor. Los proveedores están hardcodeados. |
| **Integration Adapter** | AUSENTE | — | No existe el concepto de adaptador de integración. |
| **Integration Monitor** | AUSENTE | — | No hay monitoreo de integraciones externas. |
| **Response Normalizer** | AUSENTE | — | No hay normalización de respuestas externas. |
| **IntegrationRequest** | AUSENTE | — | No existe el modelo de dominio. |
| **IntegrationResponse** | AUSENTE | — | No existe el modelo de dominio. |
| **IntegrationEvent** | AUSENTE | — | No existe como concepto de dominio. |
| **IntegrationResult** | AUSENTE | — | No existe el modelo de dominio. |

### 6.2 Componentes existentes que se relacionan con el dominio

| Componente | Estado | Ubicación | Relación con IE |
|---|---|---|---|
| `ChannelAdapter` (abstract) | **PARCIAL** | `app/core/conversation/channel_adapter.py` | Predecesor conceptual del Integration Adapter. Solo tiene `adapt(response)`. Un solo método. Una sola implementación (`HttpChannelAdapter`). |
| `HttpChannelAdapter` | **PARCIAL** | `app/core/conversation/channel_adapter.py` | Devuelve `ChannelResponse` directamente. No llama a APIs externas. No es un adaptador de integración real. |
| WhatsApp webhook endpoint | **IMPLEMENTADO** (bypasea IE) | `app/channels/whatsapp/webhook.py` | Recibe webhook de Meta, adapta a ConversationMessage, llama a ConversationService. Luego envía respuesta via WhatsAppSender. **No pasa por Integration Engine.** |
| `WhatsAppAdapter` | **IMPLEMENTADO** (local a channel) | `app/channels/whatsapp/adapter.py` | Convierte WebhookPayload → ConversationMessage. Es un adaptador específico de WhatsApp, no un Integration Adapter reutilizable. |
| `WhatsAppSender` | **IMPLEMENTADO** (local a channel) | `app/channels/whatsapp/sender.py` | Toma ChannelResponse, convierte a payload WhatsApp API, envía via HTTP. Esto es lo que debería hacer un Integration Adapter. |
| `WhatsAppClient` | **IMPLEMENTADO** (local a channel) | `app/channels/whatsapp/client.py` | Cliente HTTP para Meta Graph API. Esto debería ser un Provider Client dentro del IE. |
| `BusinessEventPublisher` | **IMPLEMENTADO** | `app/core/business/event_publisher.py` | Podría servir como referencia para IntegrationMonitor. |
| `AutomationEventPublisher` | **IMPLEMENTADO** | `app/core/automation/event_publisher.py` | Similar. Publica eventos en BusinessEventModel. |
| Channel routing en ConversationService | **PARCIAL** | `app/core/conversation/service.py` | `_adapters: Mapping[str, ChannelAdapter]` permite registrar adaptadores por nombre de canal. Es un embrión del Provider Resolver pero limitado a un solo proposito (respuesta conversacional). |
| Provider config en Settings | **PARCIAL** | `app/infrastructure/settings.py` | WhatsApp config (token, phone number ID, API version). Solo existe para WhatsApp. No hay modelo de configuración de proveedores. |

### 6.3 Resumen de brecha

| Aspecto | Blueprint (D-012) | Código actual |
|---|---|---|
| Arquitectura | Engine independiente con pipeline de 5 etapas | No existe como Engine. Lógica distribuida entre `app/channels/`, `app/core/conversation/`, y `app/api/`. |
| Abstracción | Integration Adapter por proveedor | WhatsAppAdapter específico + WhatsAppSender específico. Sin abstracción compartida. |
| Multi-proveedor | Provider Resolver selecciona según tenant | Proveedor hardcodeado (WhatsApp). No hay resolución. |
| Contratos canónicos | IntegrationRequest, IntegrationResponse, ProviderContext | No existen. Se usan `ConversationMessage` y `ChannelResponse` como canales de facto. |
| Monitoreo | Integration Monitor con eventos y métricas | No existe. Errores de WhatsApp solo se loggean. |
| Seguridad | Gestión centralizada de autenticación | Token de WhatsApp en Settings, pasado directamente a client. |
| Desacoplamiento | Core nunca conoce proveedores | ConversationService conoce adaptadores. WhatsAppSender conoce URL de Meta. |

---

## 7. Riesgos Arquitectónicos

### 🔴 R1 — Inexistencia del Integration Engine como abstracción

**Descripción:** Todo el flujo de integración con WhatsApp (el único canal real) bypasea completamente cualquier Engine de integración. El webhook llama directamente a `ConversationService`, y el envío usa `WhatsAppClient` → API de Meta directamente.

**Consecuencia:** Agregar Telegram, web chat, o cualquier segundo canal requiere:
- Nuevo webhook endpoint en `app/main.py`
- Nuevo adaptador específico (como `WhatsAppAdapter`)
- Nuevo sender específico (como `WhatsAppSender`)
- Nueva configuración en `Settings`
- Posible modificación de `ConversationService`, `dependencies.py`, routes

No hay un punto único de entrada/salida para integraciones externas.

**Severidad:** Crítica. Viola el principio arquitectónico "toda comunicación externa pasa por el Integration Engine."

### 🔴 R2 — Canalización inconsistente inbound vs. outbound

**Descripción:**

- **Inbound (WhatsApp → Core):** Webhook → adapter → `ConversationService.handle_message()` (correcto, pasa por CE).
- **Outbound (Core → WhatsApp):** `ConversationService` → `ChannelResponse` → `WhatsAppSender` → API de Meta (bypasea todo Engine de integración).

El outbound no pasa ni siquiera por el `ChannelAdapter` abstracto de Conversation Engine. El sender es invocado directamente desde el webhook después de recibir la respuesta del servicio.

**Consecuencia:** No hay trazabilidad del outbound. No hay reintentos, no hay monitoreo, no hay normalización de errores. El `WhatsAppSender` solo loggea errores y los ignora.

**Severidad:** Alta.

### 🟡 R3 — Ausencia de modelo de configuración de proveedores

**Descripción:** La configuración de proveedores está hardcodeada en `Settings` como variables de entorno planas (`WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, etc.). No existe:
- Modelo de dominio para configuración de proveedor
- Repositorio de configuraciones por tenant
- Gestión de credenciales (secrets)
- Políticas de fallback entre proveedores

**Consecuencia:** Multi-tenant imposible sin reescribir. Cada tenant necesitaría su propio conjunto de settings. No hay forma de tener dos cuentas de WhatsApp para dos empresas diferentes.

**Severidad:** Alta.

### 🟡 R4 — Ausencia de Integration Monitor

**Descripción:** No existe registro centralizado de:
- Qué integraciones se ejecutaron
- Cuánto tardaron
- Cuántos reintentos ocurrieron
- Cuáles fallaron y por qué

El `BusinessEventPublisher` existe pero solo registra eventos del Business Brain. El `WhatsAppSender` captura errores pero no los persiste como eventos de integración.

**Consecuencia:** Imposible auditar, depurar o mejorar las integraciones. Ciegos ante fallos de proveedor.

**Severidad:** Alta.

### 🟡 R5 — ChannelAdapter en el Engine equivocado

**Descripción:** `ChannelAdapter` (abstracto + HttpChannelAdapter) vive dentro de `app/core/conversation/`. Según D-012, la adaptación a canales es responsabilidad del Integration Engine, no del Conversation Engine.

**Consecuencia:** Violación de ownership. El CE no debería conocer adaptadores de canales. Su responsabilidad termina en `ChannelResponse` (canónico). La traducción a protocolo específico pertenece al IE.

**Severidad:** Media. No es un bug hoy, pero será una duplicidad cuando exista el IE.

### 🟡 R6 — Dependencia directa de HTTP sin abstracción

**Descripción:** `WhatsAppClient` usa `httpx.AsyncClient` directamente. No hay:
- Abstracción de cliente HTTP
- Timeout management centralizado
- Rate limiting
- Circuit breaker
- Retry policy

**Consecuencia:** Cada nuevo proveedor replicará el mismo patrón. Vulnerable a timeout de red, saturación, fallos en cascada.

**Severidad:** Media.

### 🟢 R7 — Secretos en Settings

**Descripción:** `whatsapp_access_token` está en `Settings` como string plana. No hay gestión de secretos (vault, AWS Secrets Manager, etc.). El token se inyecta directamente en el cliente HTTP.

**Consecuencia:** Rotación de credenciales requiere reinicio. Exposición en logs o errores posible. Sin aislamiento por tenant.

**Severidad:** Media-baja para Starter, alta para producción multi-tenant.

### 🟢 R8 — Sin modelo de capacidades

**Descripción:** No existe el concepto de "capacidad de integración" (messaging, crm, email, storage). Cada proveedor se integra de forma ad-hoc. No hay un catálogo de capacidades que el Core pueda consultar.

**Consecuencia:** Imposible para el Provider Resolver seleccionar un proveedor basado en capacidad. Toda resolución sería hardcodeada.

**Severidad:** Media.

---

## 8. Preparación para Múltiples Canales

### 8.1 Evaluación de la arquitectura actual

Se evalúa si agregar WhatsApp, Telegram, Instagram, Facebook Messenger, Web Chat, y Email puede hacerse **sin modificar los Engines existentes** (ENG-001 a ENG-004).

| Canal | Modificaciones requeridas HOY | ¿Requiere cambios en Engines? |
|---|---|---|
| **WhatsApp** | Ya existe. Webhook + adapter + sender + client | No requiere hoy, pero el patrón es incorrecto (bypasea IE). |
| **Telegram** | Nueva ruta webhook, nuevo adapter, nuevo sender, nuevo client, nueva entry en `dependencies.py:adapters`, posible modificación de `ConversationService` | **SÍ.** `ConversationService` necesita registrar el nuevo adapter. `dependencies.py` necesita instanciarlo. `main.py` necesita incluir la ruta. |
| **Instagram** | Idem Telegram. | **SÍ.** Mismos cambios. |
| **Facebook Messenger** | Idem Telegram. | **SÍ.** Mismos cambios. |
| **Web Chat** | Nuevo endpoint HTTP (o WebSocket), nuevo adapter, nuevo sender, registro en `dependencies.py:adapters` | **SÍ.** Mismos cambios. |
| **Email** | Configuración IMAP/SMTP, adapter para inbound + outbound, registro en `dependencies.py:adapters` | **SÍ.** Mismos cambios + posiblemente `ConversationStateManager` (los estados por email son distintos: esperando reply, reenviado, etc.) |

### 8.2 Puntos de acoplamiento específicos

Cada nuevo canal toca **como mínimo** estos archivos:

| Archivo | Por qué |
|---|---|
| `app/main.py:29` | `app.include_router(whatsapp_router)` — hay que agregar un router por canal |
| `app/api/dependencies.py:180-182` | `adapters: dict[str, HttpChannelAdapter]` — hay que agregar cada nuevo adapter |
| `app/core/conversation/service.py:75-76` | `self._get_adapter(message.channel)` — el adaptador se selecciona aquí |
| `app/core/conversation/channel_adapter.py` | `ChannelAdapter` actual solo tiene `adapt()`. Cada canal necesita su propio adapter. |
| `app/infrastructure/settings.py` | Cada canal requiere sus propias settings (token, endpoint, etc.) |
| `app/channels/` | Nuevo paquete por canal con adapter, sender, client, models, webhook |

### 8.3 ¿Qué debería ser responsabilidad del IE y no del CE?

| Responsabilidad | Dueño actual | Dueño correcto (D-012) |
|---|---|---|
| Traducir `ChannelResponse` a payload específico | `app/channels/whatsapp/mapper.py` | Integration Adapter dentro de IE |
| Enviar HTTP a API externa | `app/channels/whatsapp/client.py` | Provider Client dentro de IE |
| Gestionar credenciales de proveedor | `app/infrastructure/settings.py` | Provider Config + Auth dentro de IE |
| Manejar errores de API externa | `app/channels/whatsapp/sender.py` | Integration Monitor dentro de IE |
| Reintentar envíos fallidos | No implementado | Integration Monitor dentro de IE |
| Seleccionar canal según tenant | No implementado (hardcodeado) | Provider Resolver dentro de IE |
| Validar solicitud de integración | No implementado | Integration Gateway dentro de IE |

### 8.4 Conclusión sobre multi-canal

**La arquitectura actual NO soporta agregar nuevos canales sin modificar Engines existentes.** Específicamente:

1. **Conversation Engine** debe modificarse cada vez (nuevos adaptadores, nuevo routing).
2. **dependencies.py** (API layer) debe modificarse cada vez.
3. **main.py** (bootstrap) debe modificarse cada vez.

Para lograr el desacoplamiento total que exige D-012, se necesita:

1. Extraer `ChannelAdapter` de `app/core/conversation/` al Integration Engine.
2. Que `ConversationService` entregue `ChannelResponse` al IE en lugar de seleccionar un adaptador internamente.
3. Que el IE tenga su propio punto de entrada para webhooks (un único webhook receiver que distribuya según el canal detectado, o routers específicos que deleguen en el IE).
4. Que la configuración de canales viva en el IE, no en `Settings` global ni en `dependencies.py`.

### 8.5 Estado ideal (post IE)

```
Cada nuevo canal requiere SOLO:
  ┌───────────────────────────────────────────────┐
  │ 1. IntegrationAdapter (traducir canónico ↔    │
  │    protocolo del proveedor)                    │
  │ 2. ProviderConfig (endpoint, credenciales)     │
  │ 3. ProviderClient (cliente HTTP/gRPC/SDK)     │
  │ 4. Registrar en Provider Resolver config       │
  └───────────────────────────────────────────────┘

  SIN modificar: ConversationEngine, BusinessBrain,
  KnowledgeEngine, AutomationEngine, API layer,
  main.py, dependencies.py
```
