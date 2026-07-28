# ENG-005 — Integration Engine: Master Implementation Plan

**Proyecto:** BotWA Starter
**Engine ID:** ENG-005
**Versión:** 1.0
**Estado:** Plan propuesto, pendiente de aprobación CTO
**Fuentes:** D-012 (8 capítulos), ADR-003, ADR-005, ADR-006, ADR-007, ADR-009, CONTEXT_FOR_AI.md, BOTWA_ARCHITECTURE_MILESTONE_REVIEW.md, ENG005_DOMAIN_ANALYSIS.md, ENG005_CTO_DECISIONS.md, código actual

---

## Decisiones del CTO vinculantes (Source of Truth)

| ID | Decisión | Resolución |
|---|---|---|
| D1 | Modelo Inbound/Outbound | **B — IE outbound-only.** Inbound sigue en channel routers. Migración a proxy bidireccional en iteración futura. |
| D2 | ChannelAdapter Ownership | **C — Dos niveles.** CE tiene `ChannelAdapter` (BusinessResponse → ChannelResponse). IE tiene `IntegrationAdapter` (canónico → protocolo externo). |
| D3 | IntegrationRequest Model | **C — Híbrido Generic[T].** Envoltorio genérico con payload tipado. |
| D4 | Provider Registry | **A — Estático en código.** Mismo patrón que `TaskRegistry` del AE. Migrar a DB después. |
| D5 | Multi-tenant Configuration | **A — Global env.** Interfaz `ConfigurationProvider` preparada para migración futura a DB. |
| D6 | Authentication | **A/B — Env vars (dev) + DB encriptado (prod).** `CredentialProvider` como abstracción. |
| D7 | Retry Strategy | **C — Exponential backoff + jitter.** Configurable por adaptador. |
| D8 | Timeout Management | **B — Por capacidad.** Cada capacidad define su timeout. |
| D9 | Circuit Breaker | **B — Simple.** Closed → Open → Half-Open. Migrar a métricas después. |
| D10 | Health Checks | **B + C — Bajo demanda + periódico.** HealthChecker combinado. |
| D11 | Rate Limiting | **B — Token bucket.** Por proveedor. |
| D12 | Observabilidad | **B — Logs + IntegrationEvents.** Métricas en memoria. Persistencia en IntegrationEventModel. |
| D13 | Sync vs Async | **A — Sync only.** Llamada bloqueante. Async en iteración futura. |
| D14 | Webhook Ingestion | **C — Per-channel routers + IE delegation.** Los routers existen pero delegan outbound al IE. Migrar a single receiver después. |
| D15 | Error Propagation | **A — IntegrationResult.** El caller checkea éxito/fallo en el resultado. |
| D16 | IE Pipeline Architecture | **A — Dependencia directa.** Los Engines importan `IntegrationService`. Migrar a standalone después. |
| D17 | Capability Modeling | **B — Enum.** `Capability` enum tipado. |
| D18 | Integration Monitor Storage | **B — IntegrationEventModel.** Tabla separada para eventos de integración. |
| D19 | Provider Client Abstraction | **B — BaseProviderClient.** Clase base con hooks `before_request` / `after_response`. |
| D20 | IE Package Structure | **A — `app/core/integration/`.** Hermano de business, conversation, knowledge, automation. |

---

## 1. Arquitectura completa

### 1.1 Diagrama de componentes

```
┌────────────────────────────────────────────────────────────────────────────┐
│                         INTEGRATION ENGINE                                 │
│                                  │                                         │
│  ┌──────────────────────────────┴──────────────────────────────────────┐   │
│  │                       IntegrationService                             │   │
│  │  execute(request) → pipeline completo → IntegrationResult            │   │
│  └──────┬─────────────────────────┬───────────────────────┬────────────┘   │
│         │                         │                       │                │
│         ▼                         ▼                       ▼                │
│  ┌─────────────┐        ┌──────────────────┐    ┌─────────────────────┐   │
│  │ Integration │        │  ProviderResolver │    │  IntegrationMonitor │   │
│  │   Gateway   │        │                   │    │                     │   │
│  │             │        │  - Resuelve       │    │  - Registra inicio  │   │
│  │  - Valida   │        │    proveedor      │    │  - Mide latencia    │   │
│  │    request  │        │    según          │    │  - Publica eventos  │   │
│  │  - Rechaza  │        │    capability +   │    │  - Métricas en      │   │
│  │    inválido │        │    tenant         │    │    memoria          │   │
│  └─────────────┘        └────────┬─────────┘    └─────────────────────┘   │
│                                  │                                         │
│                                  ▼                                         │
│  ┌────────────────────────────────────────────────────────────────────┐   │
│  │                     IntegrationAdapter                             │   │
│  │  (abstract — una implementación por proveedor)                     │   │
│  │  execute(provider_context, request) → IntegrationResponse          │   │
│  └────────────────────────────────────────────────────────────────────┘   │
│                                  │                                         │
│                                  ▼                                         │
│  ┌────────────────────────────────────────────────────────────────────┐   │
│  │                       BaseProviderClient                            │   │
│  │                                                                      │   │
│  │  ┌──────────┐  ┌──────────┐  ┌─────────────┐  ┌──────────────────┐ │   │
│  │  │ Retry    │  │ Circuit  │  │ RateLimiter │  │ TimeoutManager   │ │   │
│  │  │ Manager  │  │ Breaker  │  │ (token      │  │ (por capacidad)  │ │   │
│  │  │ (exp     │  │ (simple) │  │  bucket)    │  │                  │ │   │
│  │  │  backoff)│  │          │  │             │  │                  │ │   │
│  │  └──────────┘  └──────────┘  └─────────────┘  └──────────────────┘ │   │
│  │                                                                      │   │
│  │  ┌──────────────────────────────────────────────────────────────┐   │   │
│  │  │  HTTP call (httpx) → External System ← Response             │   │   │
│  │  └──────────────────────────────────────────────────────────────┘   │   │
│  └────────────────────────────────────────────────────────────────────┘   │
│                                                                           │
│  ┌──────────────────────────┐  ┌──────────────────────────────────┐      │
│  │    ProviderRegistry      │  │    HealthChecker                 │      │
│  │                          │  │                                  │      │
│  │  (estático, como         │  │  - On-demand health check        │      │
│  │   TaskRegistry del AE)   │  │  - Periodic health check (BG)   │      │
│  └──────────────────────────┘  └──────────────────────────────────┘      │
│                                                                           │
│  ┌──────────────────────────────────────────────────────────────────┐    │
│  │  ConfigurationProvider (interfaz)     CredentialProvider (interfaz) │  │
│  │  ├─ EnvConfigProvider (ahora)         ├─ EnvCredentialProvider     │  │
│  │  └─ DbConfigProvider (futuro)         └─ DbCredentialProvider      │  │
│  └──────────────────────────────────────────────────────────────────┘    │
└────────────────────────────────────────────────────────────────────────────┘
```

### 1.2 Responsabilidades de cada componente

#### IntegrationService
- **Responsabilidad:** Orquestar el pipeline completo del Integration Engine.
- **Entrada:** `IntegrationRequest[T]`
- **Salida:** `IntegrationResult`
- **Pipeline interno:**
  1. Gateway.validate(request)
  2. ProviderResolver.resolve(capability, tenant_id) → Provider
  3. IntegrationAdapter.execute(provider, request) → IntegrationResponse
  4. IntegrationMonitor.record(request, result, duration)
  5. Compilar IntegrationResult
- **NO hace:** Llamar a APIs externas, traducir protocolos, gestionar credenciales.

#### IntegrationGateway
- **Responsabilidad:** Validar y normalizar todo IntegrationRequest antes de procesarlo.
- **Entrada:** `IntegrationRequest[T]`
- **Salida:** `ValidatedIntegrationRequest[T]` (o rechazo con error)
- **Validaciones:** capability existe, payload no vacío, tenant_id presente, campos requeridos según capability.
- **NO hace:** Seleccionar proveedor, ejecutar llamadas externas, decidir reintentos.

#### ProviderResolver
- **Responsabilidad:** Seleccionar el proveedor adecuado según capability + tenant.
- **Entrada:** `ValidatedIntegrationRequest[T]`
- **Salida:** `ProviderContext` (provider, endpoint, credentials, config)
- **Lógica:** Consulta `ProviderRegistry` para encontrar adaptadores que soporten la capability. Si hay múltiples, aplica política de selección del tenant (hoy: primero disponible).
- **NO hace:** Ejecutar llamadas externas, traducir protocolos.

#### ProviderRegistry
- **Responsabilidad:** Registrar y resolver adaptadores de integración por capability.
- **Patrón:** Idéntico a `TaskRegistry` del AE. Registro estático en memoria durante startup.
- **Métodos:** `register(capability, adapter)`, `resolve(capability) → list[IntegrationAdapter]`
- **NO hace:** Persistir configuraciones, autenticar.

#### IntegrationAdapter (abstracto)
- **Responsabilidad:** Traducir un IntegrationRequest canónico al protocolo específico del proveedor.
- **Entrada:** `ProviderContext`, `IntegrationRequest[T]`
- **Salida:** `IntegrationResponse`
- **Implementaciones:**
  - `WhatsAppIntegrationAdapter`: Traduce MessagingPayload a JSON de Meta Graph API. Usa `BaseProviderClient` para el HTTP call.
  - `HttpIntegrationAdapter`: Adapter genérico para APIs REST. Toma URL, method, headers, body del payload.
- **Principio:** Un adapter por proveedor. Sin lógica de negocio.
- **NO hace:** Reintentar, decidir timeouts, gestionar rate limits (todo eso lo hace BaseProviderClient).

#### BaseProviderClient
- **Responsabilidad:** Abstracción de cliente HTTP con retry, circuit breaker, rate limiting, timeout.
- **Método abstracto:** `do_call(request_data) → response_data`
- **Hooks:** `before_request()` (inyectar auth, iniciar métricas), `after_response()` (registrar métricas, decidir retry).
- **Comportamiento envuelto:**
  - `RetryManager`: Exponential backoff + jitter. Configurable por adapter.
  - `CircuitBreaker`: Por proveedor. Closed → N fallos → Open → M segundos → Half-Open.
  - `RateLimiter`: Token bucket por proveedor. N requests/segundo.
  - `TimeoutManager`: Timeout por capability (messaging=10s, CRM=30s, etc.).
- **NO hace:** Traducir payloads, conocer modelos de dominio.

#### IntegrationMonitor
- **Responsabilidad:** Registrar, medir y publicar todo lo que ocurre en cada integración.
- **Eventos que publica:** `integration.started`, `integration.completed`, `integration.failed`, `integration.timeout`, `integration.retry`.
- **Métricas en memoria:** Latencia (última, promedio, p50/p95/p99), tasa de error, throughput, contador de reintentos.
- **Persistencia:** Escribe `IntegrationEventModel` en DB.
- **NO hace:** Ejecutar integraciones, tomar decisiones.

#### RetryManager
- **Responsabilidad:** Implementar la política de reintentos con exponential backoff + jitter.
- **Configuración:** `max_attempts`, `base_delay_seconds`, `backoff_multiplier`, `max_delay_seconds`.
- **Comportamiento:** Tras cada fallo, espera `base_delay * (backoff_multiplier ^ attempt) + random_jitter`. Máximo `max_delay`.
- **NO hace:** Decidir si un error es reintentable (eso lo define el adapter o el caller).

#### CircuitBreaker
- **Responsabilidad:** Proteger al sistema de llamadas a proveedores caídos.
- **Estados:** `CLOSED` (funcionando), `OPEN` (fallando, rechazar requests), `HALF_OPEN` (probando).
- **Configuración:** `failure_threshold` (N fallos para abrir), `recovery_timeout` (segundos para half-open), `success_threshold` (N éxitos en half-open para cerrar).
- **NO hace:** Reintentar requests, decidir timeouts.

#### RateLimiter
- **Responsabilidad:** Limitar la tasa de requests a un proveedor.
- **Algoritmo:** Token bucket. N tokens por segundo. Bucket tamaño máximo M.
- **Comportamiento:** Si no hay tokens, el request espera o falla (configurable).
- **NO hace:** Reintentar, circuit break.

#### TimeoutManager
- **Responsabilidad:** Aplicar timeout por capacidad de integración.
- **Configuración:** Mapa `Capability → timeout_seconds`. Default 30s.
- **Comportamiento:** Cancela el request si excede el timeout. Publica `integration.timeout`.
- **NO hace:** Reintentar, traducir protocolos.

#### HealthChecker
- **Responsabilidad:** Verificar conectividad con proveedores externos.
- **Modos:**
  - **On-demand:** Llamado por el endpoint `/health` del sistema. Verifica proveedores y reporta estado.
  - **Periódico:** Worker en background que revisa cada N segundos y actualiza estado en memoria.
- **Método abstracto en adapters:** `health_check() → HealthCheckResult`.
- **NO hace:** Ejecutar integraciones de negocio, tomar decisiones.

#### ConfigurationProvider (interfaz)
- **Responsabilidad:** Proveer configuración de integración por tenant.
- **Implementaciones:**
  - `EnvConfigurationProvider`: Lee de variables de entorno (hoy). Una sola config.
  - `DbConfigurationProvider`: Lee de DB (futuro). Multi-tenant.
- **Método:** `get_config(tenant_id, provider_id) → IntegrationConfiguration`

#### CredentialProvider (interfaz)
- **Responsabilidad:** Proveer credenciales de forma segura.
- **Implementaciones:**
  - `EnvCredentialProvider`: Lee de env vars (dev).
  - `DbCredentialProvider`: Lee de DB encriptado (prod).
- **Método:** `get_credentials(tenant_id, provider_id) → AuthCredential`

---

## 2. Pipeline completo (los 5 Engines)

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│ FLUJO COMPLETO: INBOUND → CORE → OUTBOUND                                                │
│                                                                                           │
│ INBOUND                                                                                   │
│                                                                                           │
│ Cliente envía mensaje por WhatsApp                                                        │
│   │                                                                                       │
│   ▼                                                                                       │
│ [1] WhatsApp Webhook (app/channels/whatsapp/webhook.py) — D14-C                           │
│   │  Recibe payload JSON de Meta                                                          │
│   │  WhatsAppAdapter.to_conversation_message(payload) → ConversationMessage              │
│   │  (NO pasa por Integration Engine en inbound — D1-B)                                  │
│   │                                                                                       │
│   ▼                                                                                       │
│ [2] CONVERSATION ENGINE (app/core/conversation/service.py)                                │
│   │  ConversationService.handle_message(message)                                          │
│   │    ├─ StateManager.get_or_create()                                                    │
│   │    ├─ StateManager.transition("awaiting_brain")                                       │
│   │    ├─ ContextBuilder.build(message, state) → ConversationContext                      │
│   │    ├─ TopicDetector.detect(context)                                                   │
│   │    ├─ MessageRouter.route(context) → BusinessDecision                                 │
│   │    │     └─ Llama a BUSINESS BRAIN                                                    │
│   │    └─ StateManager.transition("in_progress")                                          │
│   │                                                                                       │
│   ▼                                                                                       │
│ [3] BUSINESS BRAIN (app/core/business/service.py)                                         │
│   │  BusinessBrainService.process(request)                                                │
│   │    ├─ IntentClassifier.classify() → BusinessIntent                                    │
│   │    ├─ ContextInterpreter.interpret() → BusinessContext                                │
│   │    ├─ RuleEvaluator.evaluate() → BusinessConstraints                                  │
│   │    ├─ DecisionMaker.decide() → BusinessOptions                                        │
│   │    ├─ ConfidenceEvaluator.evaluate() → confidence                                     │
│   │    ├─ (opcional) KNOWLEDGE ENGINE → KnowledgeService.query()                          │
│   │    ├─ ActionPlanner.plan() → BusinessActionPlan                                       │
│   │    ├─ (opcional) AUTOMATION ENGINE → AutomationService.execute()                      │
│   │    └─ RETURN BusinessDecision                                                         │
│   │                                                                                       │
│   ▼                                                                                       │
│ [4] CONVERSATION ENGINE (response composition)                                            │
│   │  ResponseComposer.compose(decision, context) → BusinessResponse                       │
│   │  ChannelAdapter.adapt(response) → ChannelResponse   ← D2-C (CE-level, formato interno)│
│   │  _persist(message, response_message)                                                  │
│   │  RETURN ChannelResponse                                                               │
│   │                                                                                       │
│   ▼                                                                                       │
│ OUTBOUND                                                                                  │
│                                                                                           │
│ [5] INTEGRATION ENGINE (app/core/integration/) — D1-B (outbound-only)                     │
│   │  El webhook (o un nuevo orquestador) construye IntegrationRequest:                    │
│   │    IntegrationRequest[MessagingPayload](                                              │
│   │      capability=Capability.SEND_MESSAGE,                                              │
│   │      tenant_id=message.company_id,                                                    │
│   │      payload=MessagingPayload(                                                        │
│   │        channel="whatsapp",                                                            │
│   │        to=customer_id,                                                                │
│   │        message=channel_response.message,                                              │
│   │      )                                                                                │
│   │    )                                                                                  │
│   │                                                                                       │
│   │  IntegrationService.execute(request):                                                 │
│   │    ├─ [5a] IntegrationGateway.validate(request) → ValidatedIntegrationRequest         │
│   │    │     - Valid contract?                                                            │
│   │    │     - Capability exists?                                                         │
│   │    │     - Payload complete?                                                          │
│   │    │     - Register start with IntegrationMonitor                                     │
│   │    │                                                                                  │
│   │    ├─ [5b] ProviderResolver.resolve(capability, tenant_id) → ProviderContext          │
│   │    │     - Query ProviderRegistry for capability=SEND_MESSAGE                         │
│   │    │     - Resolve provider: WhatsApp (según tenant config)                           │
│   │    │     - Look up credentials via CredentialProvider                                 │
│   │    │     - Look up config via ConfigurationProvider                                   │
│   │    │                                                                                  │
│   │    ├─ [5c] WhatsAppIntegrationAdapter.execute(provider_ctx, request)                  │
│   │    │     - Translate MessagingPayload → WhatsApp API JSON                             │
│   │    │     - Call BaseProviderClient.post(url, headers, json)                           │
│   │    │     │    ├─ RateLimiter.acquire() — esperar si necesario                         │
│   │    │     │    ├─ CircuitBreaker.allow_request() — rechazar si OPEN                    │
│   │    │     │    ├─ TimeoutManager.start(capability)                                     │
│   │    │     │    ├─ RetryManager.execute():                                              │
│   │    │     │    │     ├─ attempt 1: HTTP call via httpx                                 │
│   │    │     │    │     ├─ si falla: esperar backoff + jitter → attempt 2                │
│   │    │     │    │     └─ si todos fallan: reportar error                                │
│   │    │     │    ├─ CircuitBreaker.record_success/failure()                              │
│   │    │     │    └─ TimeoutManager.stop()                                                │
│   │    │     - Parse response → IntegrationResponse                                       │
│   │    │                                                                                  │
│   │    └─ [5d] IntegrationMonitor.record(request, result, duration)                       │
│   │          - Publica IntegrationEvent (started/completed/failed/timeout/retry)          │
│   │          - Persiste en IntegrationEventModel                                          │
│   │          - Actualiza métricas en memoria                                              │
│   │                                                                                       │
│   │  RETURN IntegrationResult                                                             │
│   │    ├─ success: bool                                                                   │
│   │    ├─ data: IntegrationResponse | None                                                │
│   │    ├─ error: str | None                                                               │
│   │    ├─ attempts: int                                                                   │
│   │    └─ latency_ms: int                                                                 │
│   │                                                                                       │
│   ▼                                                                                       │
│ [6] Webhook responde HTTP 200 a Meta                                                      │
│   │  (El resultado del envío se loggea. Si falló, se registró en IntegrationEvent.)       │
│   │                                                                                       │
└─────────────────────────────────────────────────────────────────────────────────────────┘
```

### 2.1 Puntos exactos de entrada/salida de cada Engine

| Engine | Entra en paso | Sale en paso | Contrato |
|---|---|---|---|
| Conversation Engine | 2 | 4 | `ConversationMessage` → `ChannelResponse` |
| Business Brain | 3 | 3 | `BusinessRequest` → `BusinessDecision` |
| Knowledge Engine | 3 (opcional) | 3 | `KnowledgeQuery` → `KnowledgeResponse` |
| Automation Engine | 3 (opcional) | 3 | `BusinessActionPlan` → dispara background task |
| Integration Engine | 5 | 5 | `IntegrationRequest[T]` → `IntegrationResult` |

---

## 3. Objetos de dominio

### 3.1 Contratos extraídos de D-012

#### IntegrationRequest[T]
```
app/domain/integration/contracts.py

IntegrationRequest[T](BaseModel, Generic[T]):
  - request_id: UUID
  - capability: Capability (enum)
  - tenant_id: str
  - payload: T (genérico, tipado por capacidad)
  - metadata: dict[str, object] (opcional)
  - created_at: datetime
```

#### IntegrationResponse
```
IntegrationResponse(BaseModel):
  - success: bool
  - data: dict[str, object] | None
  - provider_response: dict[str, object] | None (respuesta cruda del proveedor)
  - normalized_at: datetime
```

#### IntegrationResult
```
IntegrationResult(BaseModel):
  - request_id: UUID
  - capability: Capability
  - success: bool
  - response: IntegrationResponse | None
  - error: IntegrationError | None
  - attempts: int
  - latency_ms: int
  - circuit_breaker_open: bool
  - rate_limited: bool
  - finished_at: datetime

IntegrationError(BaseModel):
  - code: str (PROVIDER_UNAVAILABLE, AUTH_FAILED, RATE_LIMITED, TIMEOUT, INVALID_REQUEST)
  - message: str
  - details: dict[str, object] | None
  - attempt: int
```

#### IntegrationEvent
```
IntegrationEvent(BaseModel):
  - event_id: UUID
  - event_type: str (started, completed, failed, timeout, retry)
  - capability: Capability
  - provider_id: str
  - tenant_id: str
  - request_id: UUID
  - success: bool
  - latency_ms: int
  - attempt: int
  - error: IntegrationError | None
  - timestamp: datetime
```

#### Provider
```
Provider(BaseModel):
  - provider_id: str
  - name: str
  - capability: Capability
  - status: ProviderStatus (ACTIVE, INACTIVE, DEGRADED)
  - health: HealthStatus | None
```

#### Capability (enum)
```
Capability(StrEnum):
  SEND_MESSAGE = "send_message"
  HTTP_REQUEST = "http_request"
  # Futuras: QUERY_CRM, CREATE_ORDER, SEND_EMAIL, etc.
```

#### ProviderContext
```
ProviderContext(BaseModel):
  - provider: Provider
  - base_url: str
  - credentials: AuthCredential | None
  - config: IntegrationConfiguration
  - resolved_at: datetime
```

#### AuthCredential
```
AuthCredential(BaseModel):
  - type: str (bearer_token, basic_auth, api_key, oauth2)
  - value: str (token encriptado o referencia a secret store)
  - expires_at: datetime | None
```

#### IntegrationConfiguration
```
IntegrationConfiguration(BaseModel):
  - provider_id: str
  - tenant_id: str
  - base_url: str
  - timeout_seconds: int
  - retry_max_attempts: int
  - retry_base_delay: float
  - rate_limit_max_per_second: int
  - rate_limit_bucket_size: int
  - circuit_breaker_failure_threshold: int
  - circuit_breaker_recovery_timeout: int
  - headers: dict[str, str] (opcional)
```

#### IntegrationExecution
```
IntegrationExecution(BaseModel):
  - execution_id: UUID
  - request_id: UUID
  - capability: Capability
  - provider_id: str
  - status: ExecutionStatusType (PENDING, RUNNING, COMPLETED, FAILED)
  - started_at: datetime
  - completed_at: datetime | None
  - attempts: int
  - result: IntegrationResult | None
```

#### HealthCheckResult
```
HealthCheckResult(BaseModel):
  - provider_id: str
  - status: ProviderStatus
  - latency_ms: int
  - error: str | None
  - checked_at: datetime
```

### 3.2 Contratos específicos por capacidad (Messaging)

```
MessagingPayload(BaseModel):
  - channel: str (whatsapp, telegram, etc.)
  - to: str (identificador del destinatario)
  - message: str (texto a enviar)
  - metadata: dict[str, object] (opcional)

MessagingResponse(BaseModel):
  - provider_message_id: str | None
  - status: str (sent, failed, queued)
  - raw_response: dict[str, object] | None
```

### 3.3 Ownership (ADR-005)

Todos los objetos de dominio del Integration Engine (`app/domain/integration/`) son propiedad exclusiva del Integration Engine. Ningún otro Engine los crea, modifica o elimina. Los Engines solicitantes construyen `IntegrationRequest[T]` usando sus propios objetos de dominio como payload.

---

## 4. Componentes — Mapa completo

| Componente | Archivo | Depende de | Dependencia de otros Engines |
|---|---|---|---|
| `IntegrationService` | `core/integration/service.py` | Gateway, ProviderResolver, Monitor | Ninguno |
| `IntegrationGateway` | `core/integration/gateway.py` | domain.contracts | Ninguno |
| `ProviderResolver` | `core/integration/provider_resolver.py` | Registry, ConfigurationProvider, CredentialProvider | Ninguno |
| `ProviderRegistry` | `core/integration/provider_registry.py` | domain.contracts | Ninguno |
| `IntegrationAdapter` (abstract) | `core/integration/adapter.py` | domain.contracts | Ninguno |
| `WhatsAppIntegrationAdapter` | `core/integration/adapters/whatsapp.py` | Adapter, BaseProviderClient | CE (ChannelResponse, via MessagingPayload) |
| `HttpIntegrationAdapter` | `core/integration/adapters/http.py` | Adapter, BaseProviderClient | Ninguno |
| `BaseProviderClient` | `core/integration/base_client.py` | RetryManager, CircuitBreaker, RateLimiter, TimeoutManager | Ninguno |
| `RetryManager` | `core/integration/retry.py` | domain.contracts | Ninguno |
| `CircuitBreaker` | `core/integration/circuit_breaker.py` | domain.contracts | Ninguno |
| `RateLimiter` | `core/integration/rate_limiter.py` | domain.contracts | Ninguno |
| `TimeoutManager` | `core/integration/timeout.py` | domain.contracts | Ninguno |
| `IntegrationMonitor` | `core/integration/monitor.py` | domain.contracts, IntegrationEventModel | Infra (model) |
| `HealthChecker` | `core/integration/health_checker.py` | ProviderRegistry, adapters | Infra (DB para persistencia) |
| `ConfigurationProvider` (interface) | `core/integration/configuration_provider.py` | domain.contracts | Ninguno |
| `EnvConfigurationProvider` | `core/integration/configuration_provider.py` | ConfigurationProvider, Settings | Infra (settings) |
| `CredentialProvider` (interface) | `core/integration/credential_provider.py` | domain.contracts | Ninguno |
| `EnvCredentialProvider` | `core/integration/credential_provider.py` | CredentialProvider, Settings | Infra (settings) |

---

## 5. Dependency Graph — Orden de construcción

```
Macro Block A ──────────────────────────────────────────────────────
  │
  ├── 1. app/domain/integration/contracts.py
  │     (IntegrationRequest[T], IntegrationResponse, IntegrationResult,
  │      IntegrationEvent, Capability, Provider, ProviderContext,
  │      AuthCredential, IntegrationConfiguration, IntegrationExecution,
  │      HealthCheckResult, MessagingPayload, MessagingResponse,
  │      IntegrationError, ProviderStatus)
  │     [0 dependencias de código]
  │
  ├── 2. app/domain/integration/__init__.py
  │     [0 dependencias]
  │
  ├── 3. app/core/integration/provider_registry.py
  │     (ProviderRegistry — mismo patrón que TaskRegistry)
  │     [depende de: domain.contracts.Capability]
  │
  ├── 4. app/core/integration/configuration_provider.py
  │     (ConfigurationProvider interface + EnvConfigurationProvider)
  │     [depende de: domain.contracts, infra.settings]
  │
  ├── 5. app/core/integration/credential_provider.py
  │     (CredentialProvider interface + EnvCredentialProvider)
  │     [depende de: domain.contracts, infra.settings]
  │
  ├── 6. app/core/integration/gateway.py
  │     (IntegrationGateway)
  │     [depende de: domain.contracts]
  │
  └── 7. app/core/integration/provider_resolver.py
        (ProviderResolver)
        [depende de: domain.contracts, provider_registry,
         configuration_provider, credential_provider]
  │
Macro Block B ──────────────────────────────────────────────────────
  │
  ├── 8. app/core/integration/retry.py
  │     (RetryManager — exponential backoff + jitter)
  │     [depende de: domain.contracts]
  │
  ├── 9. app/core/integration/circuit_breaker.py
  │     (CircuitBreaker — simple 3-state)
  │     [depende de: domain.contracts]
  │
  ├── 10. app/core/integration/rate_limiter.py
  │      (RateLimiter — token bucket)
  │      [depende de: domain.contracts]
  │
  ├── 11. app/core/integration/timeout.py
  │      (TimeoutManager — por capability)
  │      [depende de: domain.contracts]
  │
  ├── 12. app/core/integration/base_client.py
  │      (BaseProviderClient)
  │      [depende de: retry, circuit_breaker, rate_limiter, timeout]
  │
  ├── 13. app/core/integration/adapter.py
  │      (IntegrationAdapter abstract + Response Normalizer)
  │      [depende de: domain.contracts]
  │
  ├── 14. app/core/integration/adapters/http.py
  │      (HttpIntegrationAdapter)
  │      [depende de: adapter, base_client]
  │
  ├── 15. app/core/integration/adapters/whatsapp.py
  │      (WhatsAppIntegrationAdapter)
  │      [depende de: adapter, base_client, domain (MessagingPayload)]
  │
  ├── 16. app/core/integration/monitor.py
  │      (IntegrationMonitor — eventos + métricas en memoria)
  │      [depende de: domain.contracts]
  │
  └── 17. app/core/integration/service.py
        (IntegrationService — orquestador)
        [depende de: gateway, provider_resolver, adapter, monitor]
  │
Macro Block C ──────────────────────────────────────────────────────
  │
  ├── 18. app/infrastructure/models/integration_event.py
  │      (IntegrationEventModel — SQLAlchemy)
  │      [depende de: infra.database]
  │
  ├── 19. app/infrastructure/repositories/integration_event_repository.py
  │      (IntegrationEventRepository)
  │      [depende de: infra.models.integration_event]
  │
  ├── 20. app/core/integration/health_checker.py
  │      (HealthChecker — on-demand + periodic)
  │      [depende de: provider_registry, adapters, monitor]
  │
  ├── 21. app/core/integration/factory.py
  │      (create_default_registry — registra adapters por capability)
  │      [depende de: provider_registry, adapters]
  │
  ├── 22. Modificar: app/core/conversation/service.py
  │      (Inyectar IntegrationService para outbound messaging)
  │      [depende de: core/integration/service, CE existente]
  │
  ├── 23. Modificar: app/channels/whatsapp/webhook.py
  │      (Delegar outbound a IntegrationService en vez de WhatsAppSender directo)
  │      [depende de: core/integration/service, whatsapp existente]
  │
  ├── 24. Modificar: app/api/dependencies.py
  │      (Wiring completo del IE)
  │      [depende de: todos los componentes del IE]
  │
  └── 25. Tests end-to-end
        [depende de: todo lo anterior]
```

---

## 6. Macro Blocks

### Macro Block A — Core Domain & Service Layer

**Objetivo:** Construir la base del Integration Engine: contratos de dominio, registro de proveedores, gateway de validación, resolución de proveedores, y abstracción de configuración/credenciales. Al final de este bloque, el IE puede recibir un `IntegrationRequest` y resolver a qué proveedor enviarlo, pero aún no ejecuta llamadas externas.

**Componentes:**

| Componente | Archivo | Propósito |
|---|---|---|
| Domain contracts | `app/domain/integration/contracts.py` | Todos los modelos de dominio del IE |
| Domain init | `app/domain/integration/__init__.py` | Exposición pública del paquete |
| ProviderRegistry | `app/core/integration/provider_registry.py` | Registro estático de adaptadores por capability |
| ConfigurationProvider | `app/core/integration/configuration_provider.py` | Interfaz + impl env para config de proveedores |
| CredentialProvider | `app/core/integration/credential_provider.py` | Interfaz + impl env para credenciales |
| IntegrationGateway | `app/core/integration/gateway.py` | Validación de IntegrationRequest |
| ProviderResolver | `app/core/integration/provider_resolver.py` | Resolución de proveedor + contexto |

**Archivos a crear:**
- `app/domain/integration/__init__.py`
- `app/domain/integration/contracts.py`
- `app/core/integration/__init__.py`
- `app/core/integration/gateway.py`
- `app/core/integration/provider_registry.py`
- `app/core/integration/provider_resolver.py`
- `app/core/integration/configuration_provider.py`
- `app/core/integration/credential_provider.py`

**Archivos a modificar:** Ninguno.

**Tests:**
- `tests/test_integration_contracts.py` — Validar todos los contratos (creación, frozen, serialización)
- `tests/test_integration_gateway.py` — Validar request válido, inválido, campos requeridos
- `tests/test_integration_provider_registry.py` — Registrar y resolver adaptadores, error si no existe
- `tests/test_integration_provider_resolver.py` — Resolver proveedor por capability, config + credentials
- `tests/test_integration_configuration_provider.py` — EnvConfigurationProvider lectura correcta
- `tests/test_integration_credential_provider.py` — EnvCredentialProvider lectura correcta

**Criterio de éxito:**
- Todos los tests de Macro Block A pasan
- 0 errores ruff, mypy, black
- Un `IntegrationRequest` puede construirse, validarse por Gateway, y resolverse a un `ProviderContext`

---

### Macro Block B — Providers & Operational Infrastructure

**Objetivo:** Implementar la capacidad de ejecución del IE: adaptadores, cliente HTTP base con retry/CB/RL/timeout, adaptadores concretos (WhatsApp, HTTP), monitor de integraciones, y el servicio orquestador. Al final de este bloque, el IE puede ejecutar una integración completa: validar → resolver → adaptar → enviar → monitorear.

**Componentes:**

| Componente | Archivo | Propósito |
|---|---|---|
| RetryManager | `app/core/integration/retry.py` | Exponential backoff + jitter |
| CircuitBreaker | `app/core/integration/circuit_breaker.py` | Simple 3-state |
| RateLimiter | `app/core/integration/rate_limiter.py` | Token bucket |
| TimeoutManager | `app/core/integration/timeout.py` | Timeout por capability |
| BaseProviderClient | `app/core/integration/base_client.py` | Cliente HTTP abstracto con todos los wrappers |
| IntegrationAdapter | `app/core/integration/adapter.py` | Abstracto + Response Normalizer |
| HttpIntegrationAdapter | `app/core/integration/adapters/http.py` | Adapter REST genérico |
| WhatsAppIntegrationAdapter | `app/core/integration/adapters/whatsapp.py` | Adapter para Meta Graph API |
| IntegrationMonitor | `app/core/integration/monitor.py` | Eventos + métricas en memoria |
| IntegrationService | `app/core/integration/service.py` | Orquestador del pipeline |

**Archivos a crear:**
- `app/core/integration/retry.py`
- `app/core/integration/circuit_breaker.py`
- `app/core/integration/rate_limiter.py`
- `app/core/integration/timeout.py`
- `app/core/integration/base_client.py`
- `app/core/integration/adapter.py`
- `app/core/integration/adapters/__init__.py`
- `app/core/integration/adapters/http.py`
- `app/core/integration/adapters/whatsapp.py`
- `app/core/integration/monitor.py`
- `app/core/integration/service.py`
- `app/core/integration/factory.py` (create_default_registry para el IE)

**Archivos a modificar:** Ninguno (aún no se integra con los otros Engines).

**Tests:**
- `tests/test_integration_retry.py` — Retry exitoso, fallo total, backoff timing, jitter range
- `tests/test_integration_circuit_breaker.py` — Closed → Open, Open → Half-Open, Half-Open → Closed/Open
- `tests/test_integration_rate_limiter.py` — Token bucket, consumo, espera, rechazo
- `tests/test_integration_timeout.py` — Timeout por capability, tiempo exacto, excepción
- `tests/test_integration_base_client.py` — HTTP call exitoso, retry en fallo, CB open, RL active
- `tests/test_integration_adapter_http.py` — HTTP adapter: request genérico, response normalizado
- `tests/test_integration_adapter_whatsapp.py` — WhatsApp adapter: traducción de MessagingPayload a JSON
- `tests/test_integration_monitor.py` — Eventos publicados, métricas actualizadas
- `tests/test_integration_service.py` — Pipeline completo exitoso, fallo en gateway, fallo en provider
- `tests/test_integration_factory.py` — Registro por defecto contiene WhatsApp + HTTP

**Criterio de éxito:**
- Todos los tests de Macro Block A + B pasan
- 0 errores ruff, mypy, black
- `IntegrationService.execute()` puede completar un ciclo completo usando adaptadores mock
- RetryManager, CircuitBreaker, RateLimiter, TimeoutManager funcionan independientemente

---

### Macro Block C — Migration & Wiring

**Objetivo:** Integrar el IE con el resto del sistema: migrar el outbound de WhatsApp para que use el IE, conectar con ConversationService, implementar health checks, persistir IntegrationEvents, y wirear todo en dependencies.py. Al final de este bloque, ENG-005 está completo y el outbound de BotWA pasa por el Integration Engine.

**Componentes:**

| Componente | Archivo | Propósito |
|---|---|---|
| IntegrationEventModel | `app/infrastructure/models/integration_event.py` | Modelo SQLAlchemy para eventos de integración |
| IntegrationEventRepository | `app/infrastructure/repositories/integration_event_repository.py` | Repositorio para IntegrationEventModel |
| HealthChecker | `app/core/integration/health_checker.py` | Health checks on-demand + periódico |
| Alembic migration | `alembic/versions/` | Migración para IntegrationEventModel |

**Archivos a crear:**
- `app/core/integration/health_checker.py`
- `app/infrastructure/models/integration_event.py`
- `app/infrastructure/repositories/integration_event_repository.py`
- `alembic/versions/XXXX_add_integration_event.py`

**Archivos a modificar:**

| Archivo | Cambio |
|---|---|
| `app/core/conversation/service.py` | Añadir `IntegrationService` como dependencia. El método `handle_message()` u orquestador externo puede invocar IE para outbound. |
| `app/core/conversation/channel_adapter.py` | **Sin cambios** (se mantiene el CE-level adapter). Se documenta que la responsabilidad del CE termina en `ChannelResponse`. |
| `app/channels/whatsapp/webhook.py` | Delegar outbound a `IntegrationService.execute()` en vez de llamar a `WhatsAppSender.send()` directamente. |
| `app/channels/whatsapp/sender.py` | **Deprecado.** La lógica de envío se migra al `WhatsAppIntegrationAdapter`. El archivo puede eliminarse o marcarse como deprecado. |
| `app/channels/whatsapp/client.py` | **Deprecado.** El cliente HTTP pasa al `BaseProviderClient`. |
| `app/api/dependencies.py` | Añadir wiring completo del IE: `ProviderRegistry`, `IntegrationGateway`, `ProviderResolver`, `ConfigurationProvider`, `CredentialProvider`, adapters (WhatsApp, HTTP), `RetryManager`, `CircuitBreaker`, `RateLimiter`, `TimeoutManager`, `BaseProviderClient`, `IntegrationMonitor`, `IntegrationService`, `HealthChecker`. |
| `app/api/routes.py` o `app/main.py` | Añadir endpoint `/health` mejorado que use `HealthChecker` para reportar estado de proveedores. |

**Tests:**
- `tests/test_integration_health_checker.py` — On-demand HC, periodic HC (mock)
- `tests/test_integration_event_repository.py` — CRUD de IntegrationEventModel
- `tests/test_integration_whatsapp_migration.py` — Webhook usa IE para outbound, resultado correcto
- `tests/test_vs1_integration.py` — Extender VS1 existente para verificar que el outbound pasa por IE
- `tests/test_api_health.py` — Health endpoint reporta estado de proveedores

**Tests existentes que deben seguir pasando:**
- Todos los tests de ENG-001, ENG-002, ENG-003, ENG-004
- Todos los tests de Macro Block A + B

**Criterio de éxito:**
- Todos los tests (nuevos + existentes) pasan
- 0 errores ruff, mypy, black
- WhatsApp outbound pasa por IntegrationService (no por WhatsAppSender directo)
- `/health` reporta estado de proveedores
- IntegrationEvents se persisten en IntegrationEventModel
- ChannelAdapter permanece en CE (D2-C respetado)
- ProviderRegistry contiene WhatsApp + HTTP adapters

---

## 7. Integraciones con otros Engines

### 7.1 Conversation Engine

**Estado actual:**
- CE produce `BusinessResponse` → `ChannelAdapter.adapt()` → `ChannelResponse`
- El webhook llama a `WhatsAppSender.send()` directamente

**Después de ENG-005:**
- CE produce `ChannelResponse` exactamente como hoy (D2-C, sin cambios en CE)
- El webhook (o un nuevo orquestador) construye `IntegrationRequest[MessagingPayload]` con los datos del `ChannelResponse`
- `IntegrationService.execute(request)` gestiona todo el outbound
- El CE **no depende del IE** directamente. La integración ocurre en la capa del webhook/orquestador.
- **Archivos CE modificados:** Ninguno. Solo `dependencies.py` y `webhook.py`.

**Contrato CE → IE:**
```
ChannelResponse → (webhook construye) → MessagingPayload → IntegrationRequest[MessagingPayload]
```

### 7.2 Business Brain

**Estado actual:** BB no tiene relación con integraciones externas.
**Después de ENG-005:** Sin cambios. BB nunca llama al IE directamente (D-012). Si BB necesita datos externos, fluye a través de KE.
**Archivos BB modificados:** Ninguno.

### 7.3 Knowledge Engine

**Estado actual:** KE consulta fuentes internas (DB, in-memory).
**Después de ENG-005:** Sin cambios para Starter. La interfaz está preparada para que KE pueda llamar al IE cuando necesite fuentes externas de conocimiento, pero no se implementa en esta fase.
**Archivos KE modificados:** Ninguno.

### 7.4 Automation Engine

**Estado actual:** AE tiene `HttpCallHandler` que es un stub (no hace llamadas reales).
**Después de ENG-005:** El `HttpCallHandler` del AE puede refactorizarse para usar `IntegrationService.execute()` con `Capability.HTTP_REQUEST`. Esto permite que las automatizaciones hagan llamadas HTTP reales con retry, CB, RL, timeout. Pero no se implementa en esta fase — se documenta como punto de integración futuro.
**Archivos AE modificados:** Ninguno.

### 7.5 ChannelAdapter Migration (D2-C)

**Estrategia de dos niveles:**

```
Nivel 1 — Conversation Engine (sin cambios):
  ChannelAdapter (abstract, en app/core/conversation/)
    adapt(response: BusinessResponse) → ChannelResponse
  HttpChannelAdapter (impl, en app/core/conversation/)
    adapt() → ChannelResponse(status, message)

Nivel 2 — Integration Engine (nuevo):
  IntegrationAdapter (abstract, en app/core/integration/)
    execute(provider_ctx, request: IntegrationRequest[T]) → IntegrationResponse
  WhatsAppIntegrationAdapter (impl, en app/core/integration/adapters/)
    execute() → traduce MessagingPayload → WhatsApp JSON → send → IntegrationResponse
  HttpIntegrationAdapter (impl, en app/core/integration/adapters/)
    execute() → HTTP call genérico → IntegrationResponse
```

**Qué cambia:**
- `HttpChannelAdapter` se mantiene en CE. Solo convierte `BusinessResponse` → `ChannelResponse`. Es formato interno, no protocolo externo.
- `WhatsAppSender` y `WhatsAppClient` se deprecan. Su lógica se migra a `WhatsAppIntegrationAdapter` + `BaseProviderClient`.
- `HttpChannelAdapter` **no** se migra al IE porque su responsabilidad es formatear la respuesta interna, no llamar a APIs externas.

**Qué NO cambia:**
- `ChannelAdapter` permanece en `app/core/conversation/channel_adapter.py`
- `ConversationService` no recibe nuevas dependencias del IE

---

## 8. Producción — Implementación de features operacionales

### 8.1 Provider Registry (D4-A)

- **Patrón:** Idéntico a `TaskRegistry` del AE. Registro estático en memoria.
- **Registro:** `create_default_integration_registry()` en `factory.py`:
  - `Capability.SEND_MESSAGE` → `WhatsAppIntegrationAdapter()`
  - `Capability.HTTP_REQUEST` → `HttpIntegrationAdapter()`
- **Resolución:** `ProviderRegistry.resolve(capability)` → lista de adapters que soportan esa capability.
- **Migración futura:** La interfaz permite swapping. Cuando se necesite DB, se crea `DbProviderRegistry` con la misma interface.

### 8.2 Health Checks (D10-B+C)

- **On-demand:** `HealthChecker.check_all()` → itera todos los proveedores del registry, llama a `adapter.health_check()`, devuelve `list[HealthCheckResult]`. Expuesto vía endpoint `/health`.
- **Periódico:** `HealthChecker.start_periodic_check(interval_seconds=60)` → thread en background que ejecuta `check_all()` cada N segundos y actualiza `Provider.status` en memoria.
- **Por adapter:** Cada `IntegrationAdapter` implementa `health_check() → HealthCheckResult`. Para WhatsApp, puede ser un GET al endpoint de Meta o verificar que el token es válido.
- **Sin persistencia:** Los resultados de health check se mantienen en memoria (atributo del Provider). Suficiente para Starter.

### 8.3 Retry (D7-C)

- **Algoritmo:** Exponential backoff + jitter.
  ```
  delay = min(base_delay * (backoff_multiplier ^ attempt), max_delay)
  delay += random.uniform(0, jitter_factor * delay)
  ```
- **Configuración por adapter:** `RetryPolicy(max_attempts=3, base_delay=1.0, backoff_multiplier=2.0, max_delay=30.0, jitter_factor=0.1)`
- **Errores reintentables:** Timeouts, HTTP 5xx, HTTP 429, connection errors.
- **Errores NO reintentables:** HTTP 4xx (excepto 429), auth failures, invalid requests.
- **Registro:** Cada reintento publica `integration.retry` event.

### 8.4 Circuit Breaker (D9-B)

- **Estados:** `CLOSED` (operando), `OPEN` (rechazando), `HALF_OPEN` (probando).
- **Transiciones:**
  - `CLOSED`: N fallos consecutivos → `OPEN`
  - `OPEN`: después de `recovery_timeout` segundos → `HALF_OPEN`
  - `HALF_OPEN`: primer request exitoso → `CLOSED`. Si falla → `OPEN`
- **Configuración por proveedor:** `failure_threshold=5`, `recovery_timeout=30`, `success_threshold=1`.
- **Comportamiento en OPEN:** `BaseProviderClient` rechaza el request inmediatamente con `IntegrationError(code="CIRCUIT_OPEN")`. No se intenta HTTP call.

### 8.5 Timeout (D8-B)

- **Configuración por capacidad:**
  - `Capability.SEND_MESSAGE` → 15s
  - `Capability.HTTP_REQUEST` → 30s
- **Mecanismo:** `asyncio.wait_for()` o `httpx.Timeout()` configurable. TimeoutManager.start() antes del call, stop() después.
- **Evento:** Si el timeout expira, se publica `integration.timeout` con la latencia exacta.

### 8.6 Multi-tenant (D5-A)

- **Hoy:** `EnvConfigurationProvider` y `EnvCredentialProvider` leen de variables de entorno. Una sola configuración global.
- **Preparación para futuro:** Ambos providers implementan interfaces (`ConfigurationProvider`, `CredentialProvider`). El `ProviderResolver` depende de las interfaces, no de las implementaciones concretas. Cuando se necesite multi-tenant, se crean `DbConfigurationProvider` y `DbCredentialProvider` sin modificar el resolver.
- **`tenant_id` en el request:** El `IntegrationRequest` incluye `tenant_id`. El `ProviderResolver` lo pasa a los providers. Hoy se ignora (misma config para todos). En el futuro, los providers lo usarán para lookup.

### 8.7 Credentials (D6-A/B)

- **Hoy (dev):** `EnvCredentialProvider` lee `WHATSAPP_ACCESS_TOKEN` de Settings. Token en texto plano en `.env`.
- **Producción:** `DbCredentialProvider` lee token encriptado de DB. Clave maestra en variable de entorno.
- **Abstracción:** `CredentialProvider.get_credentials(tenant_id, provider_id) → AuthCredential`. El `BaseProviderClient` llama a `before_request()` que inyecta el token en el header `Authorization`.

### 8.8 Rate Limiting (D11-B)

- **Algoritmo:** Token bucket.
  - `capacity`: máximo de requests en ráfaga (bucket size).
  - `refill_rate`: tokens por segundo.
- **Configuración por proveedor:** WhatsApp → 80 tokens/segundo (límite de Meta). HTTP genérico → 100 tokens/segundo.
- **Comportamiento:** `RateLimiter.acquire()` antes de cada request. Si no hay tokens disponibles, espera hasta que se rellene el bucket o falla si `timeout > 0`.
- **Integración con CB:** Si el rate limiter rejecta por mucho tiempo, el CB puede abrirse.

### 8.9 Observabilidad (D12-B)

- **Logs:** Cada etapa del pipeline loggea con structlog (event_type, provider, capability, latency, success).
- **Eventos:** `IntegrationMonitor` publica `IntegrationEvent` en cada hito (start, complete, fail, timeout, retry). Se persiste en `IntegrationEventModel` (tabla separada en DB).
- **Métricas en memoria:**
  - Latencia: última, promedio, p50/p95/p99 (por capability y provider)
  - Tasa de error: últimos 100 requests
  - Throughput: requests/segundo
  - Contador de reintentos, circuit breaker opens, rate limits alcanzados

---

## 9. Riesgos

### 🔴 R1 — Acoplamiento de dependencias circulares

**Contexto:** `ConversationService` es el orquestador principal del pipeline. Si el IE se inyecta en el CE para outbound messaging, existe el riesgo de que CE → IE → CE (por ejemplo, si el IE necesitara llamar al CE para algo). Aunque el diseño actual no contempla esto, es un riesgo si futuros desarrolladores introducen esa dependencia sin control.

**Mitigación:** El IE no depende del CE. La dependencia es unidireccional: CE (o webhook) → IE. Ningún componente del IE debe importar del CE. Esto debe enforced via lint rule o code review.

### 🔴 R2 — Thread safety del Circuit Breaker y Rate Limiter

**Contexto:** `CircuitBreaker` y `RateLimiter` mantienen estado en memoria. Si varios requests concurrentes (FastAPI async handles múltiples requests) acceden al mismo proveedor, puede haber race conditions.

**Mitigación:** Usar `asyncio.Lock` para operaciones atómicas en CB y RL. El `BaseProviderClient` debe ser thread-safe o usar lock por proveedor.

### 🟡 R3 — Complejidad de configuración

**Contexto:** El plan define 20+ configuraciones (timeout por capability, retry policy, CB thresholds, RL rates, etc.). El riesgo es que configurar correctamente cada proveedor requiera conocimientos profundos del equipo.

**Mitigación:** Valores default conservadores para todas las configuraciones. Documentar cada parámetro con su valor recomendado para cada proveedor. El 99% de los casos de uso Starter funcionan con defaults.

### 🟡 R4 — Latencia adicional en outbound

**Contexto:** El pipeline del IE (Gateway → Resolver → Adapter → Client → Monitor) añade overhead computacional a cada envío. Para messaging, donde la latencia esperada es <500ms, este overhead es medible.

**Mitigación:** Mantener el pipeline ligero. Gateway solo valida campos (sin IO). Resolver es lookup en memoria (sin DB). Monitor escribe eventos en DB de forma asíncrona (sin bloquear la respuesta). Medir latencia y optimizar si es necesario.

### 🟡 R5 — WhatsAppSender existente no se migra inmediatamente

**Contexto:** El plan define la migración de `WhatsAppSender`/`WhatsAppClient` al IE, pero durante la transición (Macro Block C), ambos sistemas coexistirán. Si hay un bug en el IE, el sistema podría intentar enviar dos veces o no enviar ninguna.

**Mitigación:** La migración debe ser atómica: el webhook deja de llamar a `WhatsAppSender` y comienza a llamar a `IntegrationService` en el mismo deploy. No hay período de coexistencia. El `WhatsAppSender` se depreca pero no se elimina hasta verificación en producción.

### 🟢 R6 — Sin inbound governance

**Contexto:** D1-B define IE como outbound-only. Los webhooks inbound (WhatsApp → Core) siguen sin pasar por el IE. Esto significa que la autenticación de webhooks, validación de payloads, y monitoreo de inbound sigue estando fuera del IE.

**Mitigación:** Aceptado por decisión del CTO (D1-B). Se documenta que el inbound se migrará al IE en una iteración futura (D1-A). Mientras tanto, los channel routers individuales son responsables de su propia validación.

---

## 10. Quality Gates

Para cerrar ENG-005, deben cumplirse todos los siguientes criterios:

### 10.1 Tests

| Gate | Criterio |
|---|---|
| `pytest` | 100% tests pasando (nuevos + existentes de ENG-001 a ENG-004) |
| Cobertura Macro Block A | ≥ 95% en contracts, gateway, provider_registry, provider_resolver |
| Cobertura Macro Block B | ≥ 90% en retry, circuit_breaker, rate_limiter, timeout, base_client, monitor, service |
| Cobertura Macro Block C | ≥ 85% en health_checker, migration code, webhook modification |
| VS1 existente | Sin regresión |

### 10.2 Calidad de código

| Gate | Criterio |
|---|---|
| `ruff check .` | 0 errores |
| `black --check .` | 0 archivos sin formatear |
| `mypy app/` | 0 errores |

### 10.3 Arquitectura

| Gate | Criterio |
|---|---|
| Dominio IE | Todos los contratos de D-012 implementados en `app/domain/integration/` |
| Pipeline IE | `IntegrationService.execute()` ejecuta Gateway → Resolver → Adapter → Client → Monitor |
| ProviderRegistry | Registro estático con al menos WhatsApp + HTTP adapters |
| Outbound WhatsApp | El webhook de WhatsApp usa `IntegrationService` para enviar mensajes (no llama a `WhatsAppSender` directamente) |
| ChannelAdapter | Permanece en `app/core/conversation/` (sin cambios). La adaptación a protocolo externo ocurre en `IntegrationAdapter` del IE. |
| IntegrationEvents | Se persisten en `IntegrationEventModel` (tabla separada) |
| Circuit Breaker | Implementado para cada proveedor. Closed/Open/Half-Open funcional. |
| Rate Limiter | Token bucket implementado por proveedor. |
| Retry | Exponential backoff + jitter implementado. |
| Timeout | Timeout por capability (SEND_MESSAGE=15s, HTTP_REQUEST=30s). |
| Health Checks | On-demand vía endpoint. Periódico en background. |
| Multi-tenant | `tenant_id` presente en `IntegrationRequest`. Interfaces preparadas para migración a DB. |
| Credentials | `CredentialProvider` abstracto. `EnvCredentialProvider` implementado. |

### 10.4 Documentación

| Gate | Criterio |
|---|---|
| README interno | Documentación de cómo agregar un nuevo proveedor (adapter + registry) |
| ADR-009 actualizado | (No modificar ADR existente. Verificar que el plan es compatible.) |
| ChannelAdapter doc | Documentar que CE-level adapter y IE-level adapter son responsabilidades distintas |

---

## Resumen de Macro Blocks

| Bloque | Archivos nuevos | Archivos modificados | Tests nuevos | Depende de |
|---|---|---|---|---|
| **A** — Core Domain & Service Layer | 8 | 0 | ~6 test files | Ninguno |
| **B** — Providers & Operational Infra | 12 | 0 | ~10 test files | Bloque A |
| **C** — Migration & Wiring | 3 | 5 | ~4 test files | Bloque A + B |

**Total:** ~23 archivos nuevos, ~5 archivos modificados, ~20 archivos de test.
