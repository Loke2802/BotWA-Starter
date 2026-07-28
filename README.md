# BotWA Starter

## Estado actual — Core v1.0.0 / Fase 2 cerrada

Quality Gates (2026-07-28):

| Gate | Resultado |
|------|-----------|
| `pytest` | **470 passed** |
| `ruff check app tests` | **clean** |
| `black --check app tests` | **clean** |
| `mypy app tests` | **clean** |

La base actual incluye 5 Engines:

| Engine | Componentes |
|--------|-------------|
| **Conversation** | router, context builder, state manager, topic detector, response composer, channel adapter, service |
| **Business Brain** | context interpreter, intent classifier, rule evaluator, decision maker, confidence evaluator, action planner, event publisher, service |
| **Knowledge** | retriever (in-memory / DB), normalizer, resolver, validator, publisher, DB catalog, seed data, service |
| **Automation** | request builder, workflow planner, task registry, task orchestrator, execution monitor (in-memory / persistent), event publisher, service |
| **Integration** | gateway, provider resolver, provider registry, provider clients (HTTP, WhatsApp, SMS, Email), configuration/credential providers, rate limiter, circuit breaker, monitor, health checker, factory, service |

> **Nota de runtime:** El código tiene `BOTWA_USE_DATABASE=true` como default interno. Los tests locales fuerzan `BOTWA_USE_DATABASE=false` para correr en modo in-memory sin Docker/PostgreSQL. La validación de cierre de Phase 2 fue ejecutada contra Docker/PostgreSQL real.

Estado oficial del proyecto: **Core v1.0.0 — Phase 2 Closed**.

Próximo objetivo oficial: **Phase 3 — Product Development Preparation** → CTO review → PRD-001 Organizations. WhatsApp real/live permanece `BLOCKED — EXTERNAL CREDENTIALS REQUIRED`.

Asistente conversacional multicanal con integración WhatsApp Cloud API, motor de conocimiento y persistencia.

## Arquitectura

```
┌─────────────────────────────────────────────────────────┐
│                  Channels (app/channels/)                │
│  ┌───────────────────────────────────────────────────┐  │
│  │  WhatsApp (app/channels/whatsapp/)                │  │
│  │  ┌──────────┐  ┌──────────┐  ┌──────┐  ┌──────┐  │  │
│  │  │ webhook  │→ │ adapter  │→ │mapper│  │client│  │  │
│  │  │(GET/POST)│  │          │  │      │  │      │  │  │
│  │  └──────────┘  └──────────┘  └──────┘  └──────┘  │  │
│  │  ┌──────────┐                                     │  │
│  │  │ sender   │                                     │  │
│  │  └──────────┘                                     │  │
│  └───────────────────────────────────────────────────┘  │
└─────────────────────────┬───────────────────────────────┘
                          │ ConversationMessage / ChannelResponse
                          ▼
┌─────────────────────────────────────────────────────────┐
│           Conversation Engine (app/core/conversation/)   │
│  ┌────────────┐    ┌──────────────┐    ┌────────────┐   │
│  │  Router    │───→│ContextBuilder│───→│  Service   │   │
│  │  Topic     │    │StateManager  │    │ Channel    │   │
│  │  Detector  │    │ResponseComp. │    │ Adapter    │   │
│  └────────────┘    └──────────────┘    └────────────┘   │
└─────────────────────────┬───────────────────────────────┘
                          ▼
┌─────────────────────────────────────────────────────────┐
│              Business Brain (app/core/business/)         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐   │
│  │IntentClassif.│→ │DecisionMaker │→ │EventPublisher│   │
│  │ContextInterp.│  │Confid.Eval.  │  │              │   │
│  │RuleEvaluator │  │ActionPlanner │  │              │   │
│  └──────────────┘  └──────────────┘  └──────────────┘   │
│         │                    │                           │
│         ▼                    ▼                           │
│  ┌──────────────────────────────────────────┐            │
│  │       Automation Engine (app/core/autom.) │           │
│  │  RequestBuilder → WorkflowPlanner →       │           │
│  │  SequentialTaskOrchestrator + Monitor     │           │
│  └──────────────────────────────────────────┘            │
└─────────────────────────┬───────────────────────────────┘
                          ▼
┌─────────────────────────────────────────────────────────┐
│           Knowledge Engine (app/core/knowledge/)         │
│  ┌────────────┐  ┌────────────┐  ┌──────────────┐       │
│  │ Retriever  │→ │ Normalizer │→ │  Resolver    │       │
│  │ (mem/DB)   │  │ Validator  │  │  Publisher   │       │
│  └────────────┘  └────────────┘  └──────────────┘       │
└─────────────────────────┬───────────────────────────────┘
                          ▼
┌─────────────────────────────────────────────────────────┐
│          Integration Engine (app/core/integration/)      │
│  Gateway + ProviderResolver + ProviderClient +          │
│  CircuitBreaker + RateLimiter + Monitor + HealthChecker │
└─────────────────────────┬───────────────────────────────┘
                          │ Modelos ORM + Eventos
                          ▼
┌─────────────────────────────────────────────────────────┐
│            Infrastructure (app/infrastructure/)          │
│  ┌──────────┐  ┌────────────────────┐  ┌────────────┐   │
│  │ database │  │  models/           │  │repositories│   │
│  │ settings │  │  Conversation      │  │  BaseRepo  │   │
│  │ logging  │  │  Message           │  │  Conv/Msg  │   │
│  │          │  │  BusinessEvent     │  │  BizEvent  │   │
│  │          │  │  AutomationExec    │  │  AutoExec  │   │
│  │          │  │  KnowledgeCatalog  │  │  KCatalog  │   │
│  │          │  │  IntegrationEvent  │  │  IntEvent  │   │
│  └──────────┘  └────────────────────┘  └────────────┘   │
└─────────────────────────────────────────────────────────┘
```

## Estructura del Proyecto

```
app/
├── api/                          # Capa HTTP (FastAPI)
│   ├── dependencies.py           # DI: todos los servicios
│   ├── routes.py                 # Endpoints REST
│   └── schemas.py                # Schemas de respuesta
├── channels/
│   └── whatsapp/                 # Integración WhatsApp Cloud API
│       ├── adapter.py            # WhatsApp → ConversationMessage
│       ├── client.py             # Cliente HTTP para Meta Graph API
│       ├── mapper.py             # ChannelResponse → payload WhatsApp
│       ├── models.py             # Modelos Pydantic del webhook de Meta
│       ├── sender.py             # Envío de mensajes a WhatsApp
│       └── webhook.py            # GET y POST /webhooks/whatsapp
├── core/
│   ├── automation/               # Automation Engine
│   │   ├── request_builder.py    # Construye solicitudes de automatización
│   │   ├── workflow_planner.py   # Planifica flujos de trabajo
│   │   ├── task_registry.py      # Registro de tareas disponibles
│   │   ├── task_orchestrator.py  # Orquestación secuencial de tareas
│   │   ├── execution_monitor.py  # Monitoreo en memoria
│   │   ├── persistent_monitor.py # Monitoreo con persistencia DB
│   │   ├── event_publisher.py    # Publicación de eventos de automatización
│   │   └── service.py            # AutomationService
│   ├── business/                 # Business Brain
│   │   ├── action_planner.py     # Planificador de acciones
│   │   ├── confidence_evaluator.py # Evaluador de confianza
│   │   ├── context_interpreter.py # Intérprete de contexto
│   │   ├── customer_profile_provider.py # Perfiles de cliente
│   │   ├── decision_maker.py     # Toma de decisiones
│   │   ├── event_publisher.py    # Publica eventos de negocio (structlog + DB)
│   │   ├── intent_classifier.py  # Clasificador por keywords
│   │   ├── rule_evaluator.py     # Evaluador de reglas de negocio
│   │   └── service.py            # BusinessBrainService
│   ├── conversation/             # Conversation Engine
│   │   ├── channel_adapter.py    # BusinessResponse → ChannelResponse
│   │   ├── context_builder.py    # Construye ConversationContext
│   │   ├── response_composer.py  # Compone la respuesta final
│   │   ├── router.py             # Enrutador de mensajes
│   │   ├── service.py            # ConversationService
│   │   ├── state_manager.py      # Gestor de estado de conversación
│   │   └── topic_detector.py     # Detector de tópicos
│   └── integration/              # Integration Engine
│       ├── channel_adapter.py    # ChannelAdapter ABC + HttpChannelAdapter
│       ├── circuit_breaker.py    # Circuit Breaker (CLOSED/OPEN/HALF_OPEN)
│       ├── configuration_provider.py # Provider de config
│       ├── credential_provider.py    # Provider de credenciales
│       ├── gateway.py            # IntegrationGateway (CB + RL + Monitor)
│       ├── health_checker.py     # HealthChecker periódico
│       ├── monitor.py            # IntegrationMonitor + ProviderMetrics
│       ├── provider_client.py    # ProviderClient ABC + HTTP/WhatsApp/SMS/Email
│       ├── provider_registry.py  # IntegrationAdapterRegistry
│       ├── provider_resolver.py  # ProviderResolver
│       ├── rate_limiter.py       # TokenBucket + RateLimiter
│       ├── factory.py            # Factory de componentes
│       └── service.py            # IntegrationService
├── domain/                       # Contratos (Pydantic puro)
│   ├── automation/contracts.py   # Plan, Task, Execution
│   ├── business/contracts.py     # BusinessRequest, Context, Decision
│   ├── conversation/
│   │   ├── contracts.py          # ConversationMessage, ChannelResponse
│   │   ├── response.py           # BusinessResponse
│   │   ├── state.py              # ConversationState
│   │   └── topics.py             # Tópicos
│   ├── integration/contracts.py  # IntegrationRequest, Result, Provider, CB/RL
│   └── persistence/repository.py # IRepository[T] (interfaz abstracta)
├── infrastructure/
│   ├── database.py               # SQLAlchemy engine, session factory, Base
│   ├── logging.py                # Configuración structlog
│   ├── settings.py               # Settings centralizados (Pydantic)
│   ├── models/                   # Modelos ORM
│   │   ├── __init__.py
│   │   ├── automation_execution.py
│   │   ├── automation_task_execution.py
│   │   ├── business_event.py
│   │   ├── conversation.py
│   │   ├── conversation_state_history.py
│   │   ├── integration_event.py
│   │   ├── knowledge_catalog_entry.py
│   │   ├── knowledge_query_log.py
│   │   ├── knowledge_source.py
│   │   └── message.py
│   └── repositories/             # Implementaciones de repositorios
│       ├── base.py               # BaseRepository[T] genérico
│       ├── automation_execution_repository.py
│       ├── automation_task_execution_repository.py
│       ├── business_event_repository.py
│       ├── conversation_repository.py
│       ├── integration_event_repository.py
│       ├── knowledge_catalog_repository.py
│       ├── knowledge_query_log_repository.py
│       ├── knowledge_source_repository.py
│       └── message_repository.py
├── main.py                       # Creación de la app FastAPI
└── shared/stubs/                 # Stubs
```

## API Endpoints

| MÃ©todo | Ruta | DescripciÃ³n | Tags |
|--------|------|-------------|------|
| GET | `/health` | Health check | system |
| GET | `/version` | VersiÃ³n y entorno | system |
| POST | `/conversation/message` | Enviar mensaje al Conversation Engine | conversation |
| POST | `/messages` | VS1 Endpoint (alias de /conversation/message) | vs1 |
| GET | `/webhooks/whatsapp` | VerificaciÃ³n de webhook Meta | whatsapp |
| POST | `/webhooks/whatsapp` | RecepciÃ³n de eventos WhatsApp | whatsapp |

## Contratos del Dominio

### ConversationMessage (input)
```json
{
  "content": "Hola, buenos dÃ­as",
  "customer_id": "customer-1",
  "company_id": "company-1",
  "conversation_id": "uuid(opcional)",
  "received_at": "ISO datetime(opcional)"
}
```

### ChannelResponse (output)
```json
{
  "status": "accepted",
  "message": "Â¡Hola! Â¿En quÃ© puedo ayudarte hoy?"
}
```

## Intents y PolÃ­ticas

| Intent | Palabras clave | Mensaje | Knowledge |
|--------|---------------|---------|-----------|
| greeting | hola, buenos, saludos, hey, buen dÃ­a, que tal | Â¡Hola! Â¿En quÃ© puedo ayudarte hoy? | No |
| farewell | adiÃ³s, chao, hasta luego, nos vemos, hasta pronto | Gracias por contactarnos. Que tengas un buen dÃ­a. | No |
| price_inquiry | precio, cuÃ¡nto, costo, tarifa, valor, cuesta | Gracias por tu interÃ©s. Un asesor te contactarÃ¡ con los precios. | SÃ­ |
| thanks | gracias, agradezco, thanks, thank you | Â¡De nada! Estamos aquÃ­ para ayudarte. | No |
| support | ayuda, soporte, problema, error, falla, no funciona | CuÃ©ntame mÃ¡s sobre el problema para poder ayudarte. | SÃ­ |
| question | cualquier texto con `?` | DÃ©jame revisar la informaciÃ³n para responder tu consulta. | SÃ­ |
| unknown | (sin match) | Gracias por tu mensaje. Estamos procesando tu solicitud. | No |

## ConfiguraciÃ³n (variables de entorno)

El archivo `.env.example` es el **contrato oficial de configuraciÃ³n** del proyecto.
Copiar a `.env` y ajustar segÃºn el entorno:

```bash
cp .env.example .env
```

Todas las variables usan prefijo `BOTWA_`:

| SecciÃ³n | Variable | Default | DescripciÃ³n |
|---------|----------|---------|-------------|
| App | `BOTWA_APP_NAME` | `BotWA Starter` | Nombre de la aplicaciÃ³n |
| App | `BOTWA_ENVIRONMENT` | `local` | Entorno (local, dev, prod) |
| App | `BOTWA_LOG_LEVEL` | `INFO` | Nivel de log |
| App | `BOTWA_API_VERSION` | `v1` | VersiÃ³n de la API |
| DB | `BOTWA_DATABASE_URL` | `postgresql+psycopg://botwa:botwa@db:5432/botwa` | URL de base de datos |
| DB | `BOTWA_USE_DATABASE` | `true` en codigo, `false` en `.env.example` local | Habilita persistencia en DB |
| WhatsApp | `BOTWA_WHATSAPP_WEBHOOK_VERIFY_TOKEN` | `botwa_verify_token` | Token de verificaciÃ³n Meta |
| WhatsApp | `BOTWA_WHATSAPP_ACCESS_TOKEN` | (vacÃ­o) | Token de acceso a Meta Graph API |
| WhatsApp | `BOTWA_WHATSAPP_PHONE_NUMBER_ID` | (vacÃ­o) | ID del nÃºmero de telÃ©fono en Meta |
| WhatsApp | `BOTWA_WHATSAPP_API_VERSION` | `v22.0` | VersiÃ³n de Meta Graph API |

## Persistencia

Cuando `BOTWA_USE_DATABASE=true`, al recibir un mensaje se persiste:
1. **Conversation**: datos de la conversaciÃ³n (company, customer, channel, status)
2. **Message**: mensaje del usuario + respuesta del asistente
3. **BusinessEvent**: eventos del Business Brain (objetivo_identificado, consulta_conocimiento, etc.)
4. **ConversationStateHistory**: transiciones de estado de conversación
5. **KnowledgeQueryLog**: consultas procesadas por Knowledge Engine
6. **AutomationExecution / AutomationTaskExecution**: ejecuciones persistidas de Automation Engine
7. **IntegrationEvent**: eventos persistibles de Integration Engine

### Modelos ORM

- `conversation` - `id`, `company_id`, `customer_id`, `channel`, `status`, `extra_data` (JSON), timestamps
- `message` - `id`, `conversation_id` (FK), `role` (user/assistant), `content`, `extra_data` (JSON)
- `business_event` - `id`, `event_type` (indexed), `conversation_id`, `payload` (JSON), `source`
- `conversation_state_history` - historial de transiciones
- `knowledge_source`, `knowledge_catalog_entry`, `knowledge_query_log` - Knowledge Engine DB catalog/log
- `automation_execution`, `automation_task_execution` - Automation Engine persistence
- `integration_event` - Integration Engine event persistence

### Migraciones Alembic

```
alembic/versions/
├── 20260710_0001_initial_foundation.py
├── 20260712_0001_create_conversation_message_event.py
├── 20260718_0001_add_conversation_state_history.py
├── 20260722_0001_create_knowledge_tables.py
├── 20260722_0002_add_source_trust_level.py
└── 20260728_0001_create_automation_integration_tables.py
```

## WhatsApp Cloud API

### RecepciÃ³n (Webhook)

```
GET /webhooks/whatsapp?hub.mode=subscribe&hub.verify_token=...&hub.challenge=...
  â†’ Verifica token, responde con challenge (PlainText)

POST /webhooks/whatsapp  (payload oficial de Meta)
  â†’ WhatsAppAdapter â†’ ConversationMessage
  â†’ ConversationService.handle_message() â†’ ChannelResponse
  â†’ WhatsAppSender.send() â†’ Meta Graph API
```

### EnvÃ­o

```
WhatsAppSender.send(response, to=wa_id)
  â†’ to_whatsapp_text_payload() â†’ payload {
      "messaging_product": "whatsapp",
      "to": "15557654321",
      "type": "text",
      "text": {"body": "..."}
    }
  â†’ WhatsAppClient.send_message(payload)
    â†’ POST https://graph.facebook.com/v22.0/{phone_id}/messages
    â†’ Authorization: Bearer {access_token}
```

### Manejo de errores de envÃ­o

- Errores HTTP (4xx, 5xx): se loguean, no rompen el flujo del Core
- Errores de red/timeout: se loguean, no rompen el flujo del Core
- `SendResult.success` indica si se enviÃ³ correctamente

## Desarrollo

### Requisitos

- Python 3.13+
- Docker Desktop
- PostgreSQL (opcional, para persistencia local)

### InstalaciÃ³n

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
```

### Ejecutar (producciÃ³n)

```bash
scripts/start.ps1
```

Esto ejecuta el flujo estÃ¡ndar:

1. `docker compose up -d db` â†’ inicia PostgreSQL
2. `docker compose run --rm api alembic upgrade head` â†’ migraciones
3. `docker compose up` â†’ inicia BotWA + base de datos

### Ejecutar (desarrollo local, sin Docker)

```bash
.venv\Scripts\uvicorn app.main:app --reload
```

### Quality Gate

```bash
.venv\Scripts\python -m ruff check app tests
.venv\Scripts\python -m black --check app tests
.venv\Scripts\python -m mypy app tests
.venv\Scripts\python -m pytest
```

### Migraciones Alembic

```bash
# Generar migraciÃ³n
.venv\Scripts\python -m alembic revision --autogenerate -m "descripciÃ³n"

# Aplicar migraciones
.venv\Scripts\python -m alembic upgrade head
```

## Tests

**470 tests passing**. Los tests locales usan modo in-memory sin Docker/PostgreSQL. La validación Docker/PostgreSQL real de Phase 2 pasó con API y DB levantadas por `docker compose`.

| Area | Tests | Cobertura principal |
|------|-------|---------------------|
| System/API | 2 | `/health`, `/version` |
| WhatsApp | 18 | webhook verification, recepcion, outbound client/sender/mapper |
| Conversation Engine | 37 | contracts, context builder, state manager, topic detector, response composer, service, channel adapter |
| Business Brain | 67 | contracts, context interpreter, intent classifier, rule evaluator, decision maker, confidence evaluator, action planner, event publisher, service |
| Knowledge Engine | 44 | contracts, retriever, DB catalog/repositories, normalizer, resolver, validator, publisher, service |
| Automation Engine | 50 | contracts, service, production path, metrics, models, event publisher, execution monitor, task registry, task orchestrator |
| Integration Engine | 107 | contracts, gateway, provider clients, provider registry/resolver, configuration/credential providers, rate limiter, circuit breaker, monitor, health checker, factory, service |
| Infrastructure | 15 | repositories and SQLAlchemy models |
| Vertical Slice | 1 | VS1 end-to-end (requiere DB) |
| Endpoint integración | 1 | Test de endpoint HTTP (requiere DB) |

## Work Packages Completados

- **WP-002** Conversation Engine (Router, ContextBuilder, StateManager, TopicDetector, ResponseComposer, ChannelAdapter, Service)
- **WP-003** Business Brain (ContextInterpreter, IntentClassifier, RuleEvaluator, DecisionMaker, ConfidenceEvaluator, ActionPlanner, EventPublisher, Service)
- **WP-004** Knowledge Engine (Retriever, Normalizer, Resolver, Validator, Publisher, DB Catalog, KnowledgeService)
- **WP-005** Vertical Slice 1 (endpoint /messages, integración end-to-end)
- **WP-006** Persistencia v1 (Modelos ORM, Repositorios, BusinessEventPublisher extendido)
- **WP-007** WhatsApp Cloud API Módulo 2.1 (Recepción: Webhooks, Adapter, Models)
- **WP-008** WhatsApp Cloud API Módulo 2.2 (Envío: Client, Sender, Mapper)
- **ENG-004** Automation Engine (contratos, orquestación, monitoreo, persistencia)
- **ENG-005** Integration Engine (gateway, providers, resiliencia, monitoreo, health checks)
- **Sprint Estabilización** P0-P7 completado: configuracion tests/runtime, SQLAlchemy typing, async lifecycle, immutable contracts, generic typing, lint hygiene, documentacion y release hygiene
- **Core v1.0.0** Phase 2 Closed: Docker/PostgreSQL, migraciones, persistencia DB-backed, smoke tests y quality gates validados

