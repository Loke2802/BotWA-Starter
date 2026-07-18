# BotWA Starter

Asistente conversacional multicanal con integración WhatsApp Cloud API, motor de conocimiento y persistencia.

## Arquitectura

```
┌─────────────────────────────────────────────────────────┐
│                     Channels (app/channels/)              │
│  ┌────────────────────────────────────────────────────┐  │
│  │  WhatsApp (app/channels/whatsapp/)                  │  │
│  │  ┌──────────┐  ┌──────────┐  ┌──────┐  ┌──────┐  │  │
│  │  │ webhook  │→│ adapter  │→│ mapper│  │client│  │  │
│  │  │ (GET/POST)│  │          │  │       │  │      │  │  │
│  │  └──────────┘  └──────────┘  └──────┘  └──────┘  │  │
│  │  ┌──────────┐                                      │  │
│  │  │ sender   │                                      │  │
│  │  └──────────┘                                      │  │
│  └────────────────────────────────────────────────────┘  │
└──────────────────────┬──────────────────────────────────┘
                       │ ConversationMessage / ChannelResponse
                       ▼
┌─────────────────────────────────────────────────────────┐
│               Conversation Engine (app/core/conversation/)│
│  ┌──────────────┐    ┌──────────────┐    ┌────────────┐│
│  │     Router    │───→│    Mapper    │───→│  Service   ││
│  └──────┬───────┘    └──────────────┘    └────────────┘│
│         │                                               │
│         ▼                                               │
│  ┌────────────────────────────────────────────────┐    │
│  │         Business Brain (app/core/business/)      │    │
│  │  ┌────────────────┐  ┌────────────────┐        │    │
│  │  │IntentClassifier│─→│ DecisionEngine │        │    │
│  │  └────────────────┘  └───────┬────────┘        │    │
│  │                              │                  │    │
│  │  ┌──────────────┐  ┌────────▼───────┐          │    │
│  │  │EventPublisher│  │ BusinessPolicy │          │    │
│  │  └──────────────┘  └────────────────┘          │    │
│  └────────────────────────────────────────────────┘    │
│         │                                               │
│         ▼                                               │
│  ┌────────────────────────────────────────────────┐    │
│  │       Knowledge Engine (app/core/knowledge/)     │    │
│  │  ┌────────────────┐  ┌────────────────────┐    │    │
│  │  │ Orchestrator   │─→│ InMemoryProvider   │    │    │
│  │  └────────────────┘  └────────────────────┘    │    │
│  └────────────────────────────────────────────────┘    │
└──────────────────────┬──────────────────────────────────┘
                       │ Modelos ORM
                       ▼
┌─────────────────────────────────────────────────────────┐
│            Infrastructure (app/infrastructure/)           │
│  ┌──────────┐  ┌────────────────────┐  ┌──────────────┐ │
│  │ database │  │ models/            │  │ repositories/│ │
│  │ settings │  │  Conversation      │  │  BaseRepo    │ │
│  │ logging  │  │  Message           │  │  Conversation│ │
│  │          │  │  BusinessEvent     │  │  Message     │ │
│  └──────────┘  └────────────────────┘  │  BusinessEvent│ │
│                                        └──────────────┘ │
└─────────────────────────────────────────────────────────┘
```

## Estructura del Proyecto

```
app/
├── api/                          # Capa HTTP (FastAPI)
│   ├── dependencies.py           # DI: ConversationService
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
│   ├── business/                 # Business Brain
│   │   ├── decision_engine.py    # Evalúa contexto + policy
│   │   ├── event_publisher.py    # Publica eventos de negocio (structlog + DB)
│   │   ├── intent_classifier.py  # Clasificador por keywords
│   │   ├── policy.py             # Reglas de negocio por intent
│   │   └── service.py            # BusinessBrainService (orquestador)
│   ├── conversation/             # Conversation Engine
│   │   ├── mapper.py             # BusinessDecision → ChannelResponse
│   │   ├── router.py             # ConversationContext → BusinessRequest
│   │   └── service.py            # ConversationService (orquestador + persistencia)
│   └── knowledge/                # Knowledge Engine
│       ├── in_memory_provider.py # Proveedor en memoria
│       ├── orchestrator.py       # Recorre providers hasta encontrar match
│       ├── provider.py           # ABC KnowledgeProvider
│       └── service.py            # KnowledgeService
├── domain/                       # Contratos (Pydantic puro, sin dependencias externas)
│   ├── business/contracts.py     # BusinessRequest, BusinessContext, BusinessDecision
│   ├── conversation/contracts.py # ConversationMessage, ConversationContext, ChannelResponse
│   ├── knowledge/contracts.py    # KnowledgeQuery, KnowledgeContext, KnowledgeResult
│   └── persistence/repository.py # IRepository[T] (interfaz abstracta)
├── infrastructure/
│   ├── database.py               # SQLAlchemy engine, session factory, Base
│   ├── logging.py                # Configuración structlog
│   ├── settings.py               # Settings centralizados (Pydantic)
│   ├── models/                   # Modelos ORM
│   │   ├── business_event.py     # BusinessEventModel
│   │   ├── conversation.py       # ConversationModel
│   │   └── message.py            # MessageModel
│   └── repositories/             # Implementaciones de repositorios
│       ├── base.py               # BaseRepository[T] genérico
│       ├── business_event_repository.py
│       ├── conversation_repository.py
│       └── message_repository.py
├── main.py                       # Creación de la app FastAPI
└── shared/stubs/                 # Stubs (e.g. Business Brain stub)
```

## API Endpoints

| Método | Ruta | Descripción | Tags |
|--------|------|-------------|------|
| GET | `/health` | Health check | system |
| GET | `/version` | Versión y entorno | system |
| POST | `/conversation/message` | Enviar mensaje al Conversation Engine | conversation |
| POST | `/messages` | VS1 Endpoint (alias de /conversation/message) | vs1 |
| GET | `/webhooks/whatsapp` | Verificación de webhook Meta | whatsapp |
| POST | `/webhooks/whatsapp` | Recepción de eventos WhatsApp | whatsapp |

## Contratos del Dominio

### ConversationMessage (input)
```json
{
  "content": "Hola, buenos días",
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
  "message": "¡Hola! ¿En qué puedo ayudarte hoy?"
}
```

## Intents y Políticas

| Intent | Palabras clave | Mensaje | Knowledge |
|--------|---------------|---------|-----------|
| greeting | hola, buenos, saludos, hey, buen día, que tal | ¡Hola! ¿En qué puedo ayudarte hoy? | No |
| farewell | adiós, chao, hasta luego, nos vemos, hasta pronto | Gracias por contactarnos. Que tengas un buen día. | No |
| price_inquiry | precio, cuánto, costo, tarifa, valor, cuesta | Gracias por tu interés. Un asesor te contactará con los precios. | Sí |
| thanks | gracias, agradezco, thanks, thank you | ¡De nada! Estamos aquí para ayudarte. | No |
| support | ayuda, soporte, problema, error, falla, no funciona | Cuéntame más sobre el problema para poder ayudarte. | Sí |
| question | cualquier texto con `?` | Déjame revisar la información para responder tu consulta. | Sí |
| unknown | (sin match) | Gracias por tu mensaje. Estamos procesando tu solicitud. | No |

## Configuración (variables de entorno)

El archivo `.env.example` es el **contrato oficial de configuración** del proyecto.
Copiar a `.env` y ajustar según el entorno:

```bash
cp .env.example .env
```

Todas las variables usan prefijo `BOTWA_`:

| Sección | Variable | Default | Descripción |
|---------|----------|---------|-------------|
| App | `BOTWA_APP_NAME` | `BotWA Starter` | Nombre de la aplicación |
| App | `BOTWA_ENVIRONMENT` | `local` | Entorno (local, dev, prod) |
| App | `BOTWA_LOG_LEVEL` | `INFO` | Nivel de log |
| App | `BOTWA_API_VERSION` | `v1` | Versión de la API |
| DB | `BOTWA_DATABASE_URL` | `postgresql+psycopg://botwa:botwa@db:5432/botwa` | URL de base de datos |
| DB | `BOTWA_USE_DATABASE` | `false` | Habilita persistencia en DB |
| WhatsApp | `BOTWA_WHATSAPP_WEBHOOK_VERIFY_TOKEN` | `botwa_verify_token` | Token de verificación Meta |
| WhatsApp | `BOTWA_WHATSAPP_ACCESS_TOKEN` | (vacío) | Token de acceso a Meta Graph API |
| WhatsApp | `BOTWA_WHATSAPP_PHONE_NUMBER_ID` | (vacío) | ID del número de teléfono en Meta |
| WhatsApp | `BOTWA_WHATSAPP_API_VERSION` | `v22.0` | Versión de Meta Graph API |

## Persistencia (Opcional)

Cuando `BOTWA_USE_DATABASE=true`, al recibir un mensaje se persiste:
1. **Conversation**: datos de la conversación (company, customer, channel, status)
2. **Message**: mensaje del usuario + respuesta del asistente
3. **BusinessEvent**: eventos del Business Brain (objetivo_identificado, consulta_conocimiento, etc.)

### Modelos ORM

- `conversation` - `id`, `company_id`, `customer_id`, `channel`, `status`, `extra_data` (JSON), timestamps
- `message` - `id`, `conversation_id` (FK), `role` (user/assistant), `content`, `extra_data` (JSON)
- `business_event` - `id`, `event_type` (indexed), `conversation_id`, `payload` (JSON), `source`

### Migraciones Alembic

```
alembic/versions/
├── 20260710_0001_initial_foundation.py
└── 20260712_0001_create_conversation_message_event.py
```

## WhatsApp Cloud API

### Recepción (Webhook)

```
GET /webhooks/whatsapp?hub.mode=subscribe&hub.verify_token=...&hub.challenge=...
  → Verifica token, responde con challenge (PlainText)

POST /webhooks/whatsapp  (payload oficial de Meta)
  → WhatsAppAdapter → ConversationMessage
  → ConversationService.handle_message() → ChannelResponse
  → WhatsAppSender.send() → Meta Graph API
```

### Envío

```
WhatsAppSender.send(response, to=wa_id)
  → to_whatsapp_text_payload() → payload {
      "messaging_product": "whatsapp",
      "to": "15557654321",
      "type": "text",
      "text": {"body": "..."}
    }
  → WhatsAppClient.send_message(payload)
    → POST https://graph.facebook.com/v22.0/{phone_id}/messages
    → Authorization: Bearer {access_token}
```

### Manejo de errores de envío

- Errores HTTP (4xx, 5xx): se loguean, no rompen el flujo del Core
- Errores de red/timeout: se loguean, no rompen el flujo del Core
- `SendResult.success` indica si se envió correctamente

## Desarrollo

### Requisitos

- Python 3.13+
- Docker Desktop
- PostgreSQL (opcional, para persistencia local)

### Instalación

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
```

### Ejecutar (producción)

```bash
scripts/start.ps1
```

Esto ejecuta el flujo estándar:

1. `docker compose up -d db` → inicia PostgreSQL
2. `docker compose run --rm api alembic upgrade head` → migraciones
3. `docker compose up` → inicia BotWA + base de datos

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
# Generar migración
.venv\Scripts\python -m alembic revision --autogenerate -m "descripción"

# Aplicar migraciones
.venv\Scripts\python -m alembic upgrade head
```

## Tests

82 tests organizados por módulo:

| Archivo | Tests | Descripción |
|---------|-------|-------------|
| `test_business_brain_service.py` | 4 | BusinessBrainService |
| `test_business_contracts.py` | 6 | Validación de contratos |
| `test_business_policy.py` | 4 | Políticas de negocio |
| `test_conversation_contracts.py` | 3 | Validación de ConversationMessage |
| `test_conversation_endpoint.py` | 2 | Endpoint /conversation/message |
| `test_conversation_service.py` | 1 | ConversationService |
| `test_decision_engine.py` | 2 | DecisionEngine |
| `test_in_memory_provider.py` | 4 | InMemoryKnowledgeProvider |
| `test_infrastructure/test_repositories.py` | 8 | Repositorios con SQLite in-memory |
| `test_intent_classifier.py` | 9 | IntentClassifier |
| `test_knowledge_contracts.py` | 5 | Validación de KnowledgeQuery/Result |
| `test_knowledge_orchestrator.py` | 3 | KnowledgeOrchestrator |
| `test_knowledge_service.py` | 2 | KnowledgeService |
| `test_system_endpoints.py` | 2 | /health, /version |
| `test_vs1_integration.py` | 10 | End-to-end VS1 |
| `test_whatsapp_outbound.py` | 10 | Cliente, sender, mapper WhatsApp |
| `test_whatsapp_webhook.py` | 7 | Webhook verification y recepción |

## Work Packages Completados

- **WP-002** Conversation Engine (Router, Mapper, Service)
- **WP-003** Business Brain (IntentClassifier, DecisionEngine, BusinessPolicy)
- **WP-004** Knowledge Engine (Orchestrator, InMemoryProvider, KnowledgeService)
- **WP-005** Vertical Slice 1 (endpoint /messages, integración end-to-end)
- **WP-006** Persistencia v1 (Modelos ORM, Repositorios, BusinessEventPublisher extendido)
- **WP-007** WhatsApp Cloud API Módulo 2.1 (Recepción: Webhooks, Adapter, Models)
- **WP-008** WhatsApp Cloud API Módulo 2.2 (Envío: Client, Sender, Mapper)
