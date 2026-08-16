# BotWA Starter

## Estado actual - Phase 3 / PRD-022 CLOSED; PRD-023 IMPLEMENTED — PENDING CTO REVIEW

Quality Gates (validación técnica PRD-023):

| Gate | Resultado |
|------|-----------|
| `pytest` | **907 passed, 36 skipped, 1 warning** |
| PRD-023 focalizadas | **16 passed** |
| PostgreSQL CI matrix | **36 passed, 0 skipped** |
| Dependency lock and vulnerability audit | **PASS** |
| Container smoke and Trivy HIGH/CRITICAL policy | **PASS** |
| `ruff check app tests scripts` | **All checks passed** |
| `black --check app tests scripts` | **491 files would be left unchanged** |
| `mypy app tests` | **Success: no issues found in 486 source files** |
| `git diff --check` | **PASS** |
| Alembic | **20260813_0022 (head)** |

La base actual incluye 5 Engines:

| Engine | Componentes |
|--------|-------------|
| **Conversation** | router, context builder, state manager, topic detector, response composer, channel adapter, service |
| **Business Brain** | context interpreter, intent classifier, rule evaluator, decision maker, confidence evaluator, action planner, event publisher, service |
| **Knowledge** | retriever (in-memory / DB), normalizer, resolver, validator, publisher, DB catalog, seed data, service |
| **Automation** | request builder, workflow planner, task registry, task orchestrator, execution monitor (in-memory / persistent), event publisher, service |
| **Integration** | gateway, provider resolver, provider registry, provider clients (HTTP, WhatsApp, SMS, Email), configuration/credential providers, rate limiter, circuit breaker, monitor, health checker, factory, service |

> **Nota de runtime:** El código tiene `BOTWA_USE_DATABASE=true` como default interno. Los tests locales fuerzan `BOTWA_USE_DATABASE=false` para correr en modo in-memory sin Docker/PostgreSQL. La validación de cierre de Phase 2 fue ejecutada contra Docker/PostgreSQL real.

Estado oficial: **PRD-001 a PRD-022 CLOSED; PRD-023 está IMPLEMENTED — PENDING CTO REVIEW.**

PRD-023 implementa CI/CD reproducible con checks estables `quality`, `tests`,
`postgresql` y `container-security`; locks pip exactos con hashes; Actions
pinneadas; PostgreSQL 17 y gates Alembic; imagen OCI Python 3.13.15 multi-stage,
non-root e identificada por merge SHA/digest; publicación GHCR solo desde
`master`; y contratos/runbooks provider-neutral de despliegue, rollback,
recuperación, secretos y procesos. No añade migración y Alembic sigue en
`20260813_0022`. El hosting permanece **NOT FROZEN** y no se ha desplegado
staging ni producción.

PRD-022 añade Observability v1 vendor-neutral: `X-Correlation-ID` UUID
request-scoped, logs JSON seguros, registros Prometheus aislados por app, métricas
HTTP/proveedor/dominio con cardinalidad cerrada, `/metrics` protegido y health
separado en liveness y readiness PostgreSQL. No añade persistencia ni migración,
no convierte proveedores externos en dependencias globales y no inicia PRD-023.
La instalación de Prometheus/Grafana/colectores/alertas, el aprovisionamiento del
token y las políticas TLS/red pertenecen a PRD-023.

PRD-022 cerró después del merge normal aprobado vía PR #36, merge commit
`134b649ac058ec74c287f77e1825aae61ed4f8b1`, con head final aprobado
`e261a4c5be1fde08d4da90f23cfbda4b9885174c`. Alembic permanece en un solo head
`20260813_0022`: PRD-022 no añadió migración, tablas ni persistencia de
observabilidad. Este cierre no implica que Prometheus/Grafana, collectors,
dashboards, alertas, retención, token de métricas, políticas TLS/red o despliegue
estén provisionados; pertenecen a PRD-023, que sigue sin iniciar. Los smokes
reales de Meta, Google y Mercado Pago continúan como gates externos previos a la
habilitación de cada integración.

PRD-021 cierra los seis findings HIGH con startup de producción fail-closed,
algoritmo JWT cerrado, claves dedicadas, autenticación normalizada y limitada,
apagado de APIs legacy/bootstrap, bloqueo de Organization inactiva, rate limiter
PostgreSQL multi-worker con retención acotada (defaults 48 horas/200 filas),
límites ASGI streaming, TrustedHost/CORS/headers, redacción OAuth, invariantes
Owner concurrentes y Audit sensible en la misma transacción. Alembic avanza a
`20260813_0022`. Los smokes reales Meta/Mercado
Pago y los controles operativos de despliegue permanecen gates externos.

PRD-021 cerró tras el merge normal del PR #34 en
`b4a9c3d682f88526f3fc9eef7ceb3d42c0d48981`, con head final aprobado
`0eb2b6de48f3c86f0308c8d4933dcc4c2e382cc5`. Este cierre no implica que las
credenciales, TLS/proxy, smoke real de Meta, sandbox comercial de Mercado Pago,
MFA de Platform Admin o automatización de PRD-023 ya estén provisionados.

PRD-020 implementa Onboarding v1 como workflow histórico mínimo tenant-scoped y
readiness actual derivada desde los Sources of Truth. Expone GET/start/complete,
usa RBAC y Audit transaccional, selecciona el Bot inicial de forma determinista y
mantiene WhatsApp condicional, Knowledge/Integrations opcionales y
BusinessCalendar no bloqueante. No duplica CRUD, no hace llamadas externas, no
activa recursos ni bloquea runtimes. Su migración es `20260813_0021`.

PRD-020 cerró después del merge aprobado vía PR #32, merge commit
`47b589df54282145ddce7b745ef208bb80321143`, con head final aprobado
`15564c245067952a74f19987370b6d5037de65a1`.

PRD-019 añade Billing SaaS provider-agnostic, tenant-scoped y PostgreSQL-only.
Incluye Mercado Pago detrás de un adaptador, fake determinista, checkout hosted,
webhook firmado/deduplicado, reconcile autoritativo, cancelación al fin de período
con no-renovación inmediata confirmada por el proveedor, downgrade con guard de
fecha y confirmación de precio, due-transition processor one-shot para cron externo,
y aplicación transaccional de Plan/Audit. Billing está deshabilitado por defecto,
no contiene seeds comerciales y no captura PAN/CVV. El smoke sandbox real de
Mercado Pago y el commercial go-live permanecen bloqueados hasta disponer de
credenciales y configuración aprobadas. Este gate comercial permanece separado
de PRD-020.

PRD-019 cerró después del merge normal aprobado vía PR #30, merge commit
`5a87ffc32be4315ebb6f9e64826bdb96f36ada58`, con head final aprobado
`2a15b7f022c2989d73bb97d9b964495dba961778`. El cierre técnico no habilita
Billing comercial: `BOTWA_BILLING_ENABLED=false` sigue siendo el default y el
cutover permanece bloqueado hasta completar configuración comercial, scheduler
externo de due-transitions y smoke sandbox real de Mercado Pago.

PRD-018 añade catálogo técnico de planes y assignment 1:1 tenant-scoped, features
booleanas, límites duros calculados desde los Sources of Truth operacionales,
enforcement transaccional con lock de Organization, optimistic concurrency,
RBAC/API segura y Audit PRD-017 en la misma transacción. El plan `default` preserva
el comportamiento previo con features habilitadas y límites ilimitados. Downgrade
no destruye recursos ni detiene runtimes. Billing, subscriptions, pricing,
metered usage, cuotas de mensajes y overage permanecen en PRD-019.

PRD-018 cerró después del merge aprobado vía PR #28, merge commit
`63f2fc79444e6b3f85b516b917860fb17fa8f779`, con head final aprobado
`2776a1b2ca6082142f14862c4eac4cf889eea631`. El hardening final exige
`PlanEnforcementService` obligatorio y fail-closed en toda ruta gated de
producción, usando la misma sesión/transacción y preservando reducing actions,
Audit writes y runtimes existentes.

PRD-017 añade un Audit Log administrativo tenant-scoped y append-only. Registra
solo acciones exitosas con actor, rol efectivo, acción/recurso allowlisted,
timestamp, correlación UUID opcional y metadata tipada sin PII ni secretos en la
misma transacción que la mutación. Expone consulta read-only con `audit.read`,
rango UTC acotado y cursor keyset firmado. No sustituye domain histories, logs ni
Analytics; no incluye backfill, denials, OAuth callback, Analytics export,
retención automática, UI ni PRD-018.

PRD-017 cerró después del merge aprobado vía PR #26, merge commit
`01c809c909360f4a31a6b26b1d4126a1c98e9c8b`, con head final aprobado
`3f7808da24d0dc1e3b5d6f3d337ee4562f5398b6`. El hardening final exige
`AuditWriter` fail-closed en toda ruta de producción, incluida auto-reapertura
WhatsApp y el worker de Automation, usando la misma sesión/transacción. La
métrica `audit_append_attempts_total` describe aceptación/rechazo por el unit of
work, no persistencia durable.

PRD-014 añade `GET /organizations/{organization_id}/dashboard`, un read model
operacional tenant-scoped y opcionalmente filtrable por bot. Compone agregados SQL
read-only de Bots, Conversations, Human Handoff, Automation, Integrations,
Contacts y Business Hours sin tablas Dashboard, PII, side effects, frontend ni
alcance de PRD-016.

PRD-014 cerró después del merge aprobado vía PR #22, merge commit
`04256eb0cb17e3d1fdb548edeae143578606d508`, con head final aprobado
`8b836d7bb7b12fcf82ffb5bb8bbada4f3db758c6`.

PRD-015 añade calendarios operativos tenant-scoped, horarios semanales,
excepciones, feriados, cierres parciales, overrides, precedencia determinista,
zonas IANA/DST, RBAC, auditoría e idempotencia transaccional. Google Calendar no
forma parte del dominio y permanece como adaptador futuro.

PRD-016 añade ledgers históricos para cierres de Conversation Management y ciclos
de Human Handoff, una proyección diaria PostgreSQL reconstruible/idempotente,
consultas day/week/month, comparación contra periodo anterior y CSV agregado sin
PII. Usa un único reporting timezone organizacional, respeta DST y no reemplaza
los Sources of Truth operacionales.

PRD-016 cerró después del merge aprobado vía PR #24, merge commit
`601499071f39aad85dc4d9595fc04425f40a3962`, con head final aprobado
`6cafee11a0f807e07a9277eae98e128ab68aa711`. Conversation/Handoff history empieza
en PRD-016; Automation representa el outcome terminal vigente, no un attempt
ledger; `Bot.created_at < bucket_end_utc` define cobertura; el watermark es un
cutoff, no un snapshot; Contacts sigue organization-scoped. No incluye PRD-017,
frontend, scheduler, PDF ni XLSX.

PRD-013 añade conexiones externas tenant-scoped, credenciales cifradas, OAuth
Google real con state firmado/single-use, Google Calendar metadata/free-busy,
health on-demand, RBAC y persistencia PostgreSQL. No cambia Core Automation ni
implementa escritura de events, booking o providers adicionales.

PRD-013 cerró después del merge final de seguridad vía PR #20, merge commit
`be52bbc49c6b34fc6b515e915564810068a74da3`, con final review head
`beb3a6a01c5a983ab5d83a485f268dfc3202fa3b`. El smoke real de Google permanece
`SKIPPED` por falta de credenciales externas aprobadas. Antes de habilitar Google
Calendar en staging o producción deben validarse OAuth consent, callback,
refresh, Calendar List y FreeBusy; es un gate operativo, no un bloqueo del cierre.

PRD-011 añade Contact como Source of Truth tenant-safe: identidad normalizada por
canal, HMAC segmentado por organización, cifrado en reposo, enlace inbound a
Conversation, API administrativa con RBAC y backfill explícito por lotes
(`python -m app.operations.backfill_contacts`). No cambia los cinco Core Engines.

PRD-008, PRD-009, PRD-010 y PRD-011 están cerrados. PRD-009 extendió la
administración multi-tenant de conversaciones y mensajes; PRD-010 añadió Human
Handoff. La validación contra Meta real sigue bloqueada por credenciales externas.

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
│   ├── access/contracts.py       # Roles y permisos
│   ├── automation/contracts.py   # Plan, Task, Execution
│   ├── bot/contracts.py          # Bot Management
│   ├── business_configuration/   # Configuración de negocio por bot
│   ├── business/contracts.py     # BusinessRequest, Context, Decision
│   ├── conversation/
│   │   ├── contracts.py          # ConversationMessage, ChannelResponse
│   │   ├── response.py           # BusinessResponse
│   │   ├── state.py              # ConversationState
│   │   └── topics.py             # Tópicos
│   ├── integration/contracts.py  # IntegrationRequest, Result, Provider, CB/RL
│   ├── organization/contracts.py # Organizaciones
│   ├── persistence/repository.py # IRepository[T] (interfaz abstracta)
│   └── user/contracts.py         # Usuarios y autenticación
├── infrastructure/
│   ├── database.py               # SQLAlchemy engine, session factory, Base
│   ├── logging.py                # Configuración structlog
│   ├── settings.py               # Settings centralizados (Pydantic)
│   ├── models/                   # Modelos ORM
│   │   ├── __init__.py
│   │   ├── automation_execution.py
│   │   ├── automation_task_execution.py
│   │   ├── bot.py
│   │   ├── business_configuration.py
│   │   ├── business_event.py
│   │   ├── conversation.py
│   │   ├── conversation_state_history.py
│   │   ├── integration_event.py
│   │   ├── knowledge_catalog_entry.py
│   │   ├── knowledge_query_log.py
│   │   ├── knowledge_source.py
│   │   ├── message.py
│   │   ├── organization.py
│   │   └── user.py
│   └── repositories/             # Implementaciones de repositorios
│       ├── base.py               # BaseRepository[T] genérico
│       ├── automation_execution_repository.py
│       ├── automation_task_execution_repository.py
│       ├── bot_repository.py
│       ├── business_configuration_repository.py
│       ├── business_event_repository.py
│       ├── conversation_repository.py
│       ├── integration_event_repository.py
│       ├── knowledge_catalog_repository.py
│       ├── knowledge_query_log_repository.py
│       ├── knowledge_source_repository.py
│       ├── message_repository.py
│       ├── organization_repository.py
│       └── user_repository.py
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
| POST | `/organizations` | Crear organización | organizations |
| GET | `/organizations` | Listar organizaciones | organizations |
| GET | `/organizations/{organization_id}` | Consultar organización | organizations |
| PATCH | `/organizations/{organization_id}` | Actualizar organización | organizations |
| POST | `/organizations/{organization_id}/deactivate` | Desactivar organización | organizations |
| POST | `/users` | Crear usuario bootstrap o autenticado | users |
| GET | `/users` | Listar usuarios de la organización autenticada | users |
| GET | `/users/{user_id}` | Consultar usuario visible | users |
| PATCH | `/users/{user_id}` | Actualizar perfil básico | users |
| POST | `/users/{user_id}/deactivate` | Desactivar usuario | users |
| POST | `/auth/login` | Autenticar email/password y emitir token Bearer | auth |
| GET | `/auth/me` | Consultar identidad autenticada | auth |
| POST | `/auth/change-password` | Cambiar contraseña e invalidar tokens previos | auth |
| GET | `/roles` | Listar roles y permisos | roles |
| GET | `/permissions/me` | Consultar permisos efectivos | roles |
| PATCH | `/users/{user_id}/role` | Asignar rol | roles |
| POST | `/bots` | Crear bot en una organización activa | bots |
| GET | `/bots` | Listar bots según alcance del usuario | bots |
| GET | `/bots/{bot_id}` | Consultar bot visible | bots |
| PATCH | `/bots/{bot_id}` | Actualizar metadata del bot | bots |
| POST | `/bots/{bot_id}/activate` | Activar bot de forma idempotente | bots |
| POST | `/bots/{bot_id}/deactivate` | Desactivar bot de forma idempotente | bots |
| POST | `/bots/{bot_id}/business-configuration` | Crear configuración de negocio del bot | business-configuration |
| GET | `/bots/{bot_id}/business-configuration` | Consultar configuración de negocio visible | business-configuration |
| PATCH | `/bots/{bot_id}/business-configuration` | Actualizar configuración de negocio | business-configuration |
| POST | `/organizations/{organization_id}/bots/{bot_id}/knowledge` | Crear entrada draft | knowledge-management |
| GET | `/organizations/{organization_id}/bots/{bot_id}/knowledge` | Listar con filtros y paginación | knowledge-management |
| GET | `/organizations/{organization_id}/bots/{bot_id}/knowledge/{knowledge_id}` | Consultar entrada | knowledge-management |
| PATCH | `/organizations/{organization_id}/bots/{bot_id}/knowledge/{knowledge_id}` | Actualizar entrada | knowledge-management |
| DELETE | `/organizations/{organization_id}/bots/{bot_id}/knowledge/{knowledge_id}` | Eliminar entrada | knowledge-management |
| POST | `/organizations/{organization_id}/bots/{bot_id}/knowledge/{knowledge_id}/publish` | Publicar draft | knowledge-management |
| POST | `/organizations/{organization_id}/bots/{bot_id}/knowledge/{knowledge_id}/archive` | Archivar entrada | knowledge-management |
| POST | `/organizations/{organization_id}/bots/{bot_id}/whatsapp-configurations` | Crear configuración WhatsApp draft | whatsapp-configuration |
| GET | `/organizations/{organization_id}/bots/{bot_id}/whatsapp-configurations` | Listar configuraciones con filtros/paginación | whatsapp-configuration |
| GET | `/organizations/{organization_id}/bots/{bot_id}/whatsapp-configurations/{configuration_id}` | Consultar configuración segura | whatsapp-configuration |
| PATCH | `/organizations/{organization_id}/bots/{bot_id}/whatsapp-configurations/{configuration_id}` | Actualizar campos no sensibles | whatsapp-configuration |
| DELETE | `/organizations/{organization_id}/bots/{bot_id}/whatsapp-configurations/{configuration_id}` | Eliminar configuración | whatsapp-configuration |
| POST | `/organizations/{organization_id}/bots/{bot_id}/whatsapp-configurations/{configuration_id}/activate` | Activar configuración | whatsapp-configuration |
| POST | `/organizations/{organization_id}/bots/{bot_id}/whatsapp-configurations/{configuration_id}/deactivate` | Desactivar configuración | whatsapp-configuration |
| POST | `/organizations/{organization_id}/bots/{bot_id}/whatsapp-configurations/{configuration_id}/rotate-secrets` | Rotar secretos | whatsapp-configuration |
| GET | `/organizations/{organization_id}/conversations` | Listar conversaciones paginadas y filtradas | conversation-management |
| GET | `/organizations/{organization_id}/conversations/{conversation_id}` | Consultar detalle seguro | conversation-management |
| GET | `/organizations/{organization_id}/conversations/{conversation_id}/messages` | Consultar historial paginado con permiso de contenido | conversation-management |
| POST | `/organizations/{organization_id}/conversations/{conversation_id}/close` | Cerrar lifecycle administrativo | conversation-management |
| POST | `/organizations/{organization_id}/conversations/{conversation_id}/reopen` | Reabrir lifecycle administrativo | conversation-management |
| POST | `/organizations/{organization_id}/conversations/{conversation_id}/archive` | Archivar lifecycle administrativo | conversation-management |
| GET | `/webhooks/whatsapp/{public_webhook_id}` | Verificar challenge por configuración | whatsapp-configuration |
| POST | `/webhooks/whatsapp/{public_webhook_id}` | Procesar mensajes y estados firmados | whatsapp-live-messaging |
| POST | `/webhooks/whatsapp/{public_webhook_id}/validate-signature` | Validar HMAC sin procesar mensajes | whatsapp-configuration |
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
| WhatsApp | `BOTWA_WHATSAPP_SECRET_ENCRYPTION_KEY` | (vacÃ­o) | Clave Fernet primaria para secretos de configuraciones |
| WhatsApp | `BOTWA_WHATSAPP_SECRET_PREVIOUS_ENCRYPTION_KEYS` | (vacÃ­o) | Claves Fernet anteriores para rotaciÃ³n |
| WhatsApp | `BOTWA_WHATSAPP_LIVE_CLIENT_MODE` | `disabled` | Cliente live: `disabled`, `fake` o `meta` |
| WhatsApp | `BOTWA_WHATSAPP_WEBHOOK_MAX_BODY_BYTES` | `1048576` | Tamaño máximo del webhook POST |
| WhatsApp | `BOTWA_WHATSAPP_WEBHOOK_MAX_EVENTS` | `100` | Eventos máximos por webhook |
| WhatsApp | `BOTWA_WHATSAPP_OUTBOUND_MAX_TEXT_CHARS` | `4096` | Tamaño máximo por fragmento saliente |
| WhatsApp | `BOTWA_WHATSAPP_OUTBOUND_MAX_ATTEMPTS` | `3` | Intentos máximos persistidos |
| WhatsApp | `BOTWA_WHATSAPP_OUTBOUND_RETRY_BASE_SECONDS` | `1` | Base del backoff |
| WhatsApp | `BOTWA_WHATSAPP_OUTBOUND_RETRY_MAX_SECONDS` | `60` | Tope del backoff |
| WhatsApp | `BOTWA_WHATSAPP_META_TIMEOUT_SECONDS` | `10` | Timeout del cliente Meta |
| Auth | `BOTWA_AUTH_SECRET_KEY` | local placeholder | Secret para firmar JWT; usar secreto fuerte fuera de git |
| Auth | `BOTWA_AUTH_ALGORITHM` | `HS256` | Algoritmo JWT |
| Auth | `BOTWA_AUTH_ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | Expiración del access token |
| Auth | `BOTWA_AUTH_PASSWORD_MIN_LENGTH` | `12` | Longitud mínima de contraseña |

## Persistencia

Cuando `BOTWA_USE_DATABASE=true`, al recibir un mensaje se persiste:
1. **Conversation**: datos de la conversaciÃ³n (company, customer, channel, status)
2. **Message**: mensaje del usuario + respuesta del asistente
3. **BusinessEvent**: eventos del Business Brain (objetivo_identificado, consulta_conocimiento, etc.)
4. **ConversationStateHistory**: transiciones de estado de conversación
5. **KnowledgeQueryLog**: consultas procesadas por Knowledge Engine
6. **AutomationExecution / AutomationTaskExecution**: ejecuciones persistidas de Automation Engine
7. **IntegrationEvent**: eventos persistibles de Integration Engine
8. **Organization / User / Bot / BusinessConfiguration / KnowledgeEntry / WhatsAppChannelConfiguration**: capacidades de producto Phase 3 con persistencia PostgreSQL
9. **InboundMessageReceipt / OutboundMessageAttempt**: idempotencia y entrega técnica PRD-008 con contenido sensible cifrado
10. **Conversation / Message**: administración PRD-009 tenant-scoped, lifecycle y contenido cifrado enlazado a transporte

### Modelos ORM

- `conversation` - `id`, `company_id`, `customer_id`, `channel`, `status`, `extra_data` (JSON), timestamps
- `message` - `id`, `conversation_id` (FK), `role` (user/assistant), `content`, `extra_data` (JSON)
- `business_event` - `id`, `event_type` (indexed), `conversation_id`, `payload` (JSON), `source`
- `conversation_state_history` - historial de transiciones
- `knowledge_source`, `knowledge_catalog_entry`, `knowledge_query_log` - Knowledge Engine DB catalog/log
- `automation_execution`, `automation_task_execution` - Automation Engine persistence
- `integration_event` - Integration Engine event persistence
- `organization` - PRD-001 organization records
- `app_user` - PRD-002 user identity records with Argon2 password hash and auth version
- `bot` - PRD-004 bot records scoped by organization
- `business_configuration` - PRD-005 business configuration records scoped by bot
- `knowledge_entry` - PRD-006 manual knowledge scoped by organization and bot
- `whatsapp_channel_configuration` - PRD-007 configuraciones por tenant/bot con secretos cifrados
- `inbound_message_receipt` - recibos idempotentes por canal y mensaje externo, sin texto
- `outbound_message_attempt` - entrega, reintento y estado de proveedor con destinatario/texto cifrados
- `conversation` - fuente de verdad existente extendida con tenant/bot, lifecycle administrativo, actividad y contadores
- `message` - fuente de verdad existente extendida con dirección, estado, texto cifrado y enlaces técnicos opcionales

### Migraciones Alembic

```
alembic/versions/
├── 20260710_0001_initial_foundation.py
├── 20260712_0001_create_conversation_message_event.py
├── 20260718_0001_add_conversation_state_history.py
├── 20260722_0001_create_knowledge_tables.py
├── 20260722_0002_add_source_trust_level.py
├── 20260728_0001_create_automation_integration_tables.py
├── 20260728_0002_create_organization_table.py
├── 20260728_0003_create_user_table.py
├── 20260728_0004_add_user_roles.py
├── 20260728_0005_create_bot_table.py
├── 20260728_0006_create_business_configuration_table.py
├── 20260729_0007_create_knowledge_entry_table.py
├── 20260730_0008_create_whatsapp_channel_configuration_table.py
├── 20260730_0009_create_whatsapp_message_transport_tables.py
└── 20260730_0010_create_conversation_management_tables.py
```

## Authentication and Users

PRD-002 adds basic identity without roles or advanced authorization.

- Password hashing uses maintained `argon2-cffi` Argon2id defaults.
- Access tokens use JWT via `PyJWT`.
- JWT includes user id, expiration, and `auth_version`.
- Password changes and deactivation invalidate previous tokens.
- `password_hash` is never exposed by API responses.
- Email uniqueness is global.
- Bootstrap is temporary: the first user of an active organization may be created without auth; later users require an authenticated active user from the same organization.
- PRD-003 replaces bootstrap with explicit roles/authorization.

## Roles and Permissions

PRD-003 adds basic RBAC without custom persisted roles.

- Roles: `platform_admin`, `organization_owner`, `organization_admin`, `operator`, `viewer`.
- Permissions are derived from a central matrix in `app/domain/access/contracts.py`.
- First user of an active organization becomes `organization_owner`.
- Later users default to `viewer`.
- Protected endpoints check current database role on every request.
- `platform_admin` can operate across organizations.
- Organization users are tenant-scoped.
- Last active `organization_owner` cannot be downgraded or deactivated.

## Bot Management and Business Configuration

PRD-004 and PRD-005 add tenant-scoped product administration on top of the Core.

- Each bot belongs to one organization.
- Bot slugs are unique inside the organization, not globally.
- Each bot can have one active Business Configuration record.
- Business Configuration stores commercial identity, hours, timezone, services, payment methods, policies, service instructions, and handoff settings.
- Business hours, services, policies, email, website, timezone, and handoff keywords are validated by domain contracts.
- `organization_owner` and `organization_admin` can create/update inside their organization.
- `operator` and `viewer` can read only.
- `platform_admin` can operate across organizations.
- Bots from inactive organizations cannot have configuration modified.
- Inactive bots can retain and expose their configuration.

## Knowledge Management

PRD-006 adds an administrative knowledge layer without replacing or changing
the Knowledge Engine.

- Each entry is scoped by both organization and bot.
- States are `draft`, `published`, and `archived`.
- Valid transitions are draft to published, draft to archived, and published to
  archived. Restoration and published-to-draft are not supported.
- Title is limited to 200 characters and content to 20,000 characters.
- Lists filter in SQL by tenant and bot, support status/basic text search, and
  return `items`, `total`, `page`, and `page_size`; maximum page size is 100.
- `viewer` reads; `operator` reads, creates, and updates; owner/admin have full
  control; `platform_admin` uses the existing cross-tenant mechanism.
- `BotKnowledgeProvider` requires explicit organization and bot IDs and returns
  only published entries.

PRD-007 resolves `phone_number_id` into a generic `ResolvedChannelContext`.
PRD-008 consumes that identity, queries `BotKnowledgeProvider`, and executes the
existing `ConversationService` through a generic channel handler.

## Multichannel And WhatsApp Configuration

BotWA is multichannel. WhatsApp is the first production adapter, but shared
application flow depends on generic `ChannelIdentity`, `ChannelResolver`, and
`ResolvedChannelContext` contracts rather than Meta identifiers.

- Configuration lifecycle: `draft`, `active`, `inactive`.
- Runtime resolution accepts only active, webhook-enabled configurations.
- Secrets use Fernet authenticated encryption from environment-provided keys.
- API responses expose configured flags, never secrets or ciphertext.
- `phone_number_id` and `public_webhook_id` are globally unique.
- Viewer reads; operator creates configuration shells and updates non-sensitive
  fields; owner/admin control activation, deletion, and secret rotation.
- Webhook challenge uses constant-time token comparison.
- Signature validation uses `X-Hub-Signature-256` and HMAC SHA-256 over raw body.
- PRD-007 remains responsible for configuration and identity resolution.
- PRD-008 adds the configured live-compatible transport without changing Core.

## WhatsApp Cloud API

### Recepcion configurada (Webhook)

```
GET /webhooks/whatsapp/{public_webhook_id}
  -> verifica el token de la configuracion y devuelve el challenge

POST /webhooks/whatsapp/{public_webhook_id}
  -> valida HMAC sobre bytes crudos antes de parsear
  -> resuelve tenant/bot por phone_number_id
  -> registra recibo idempotente
  -> ChannelConversationHandler -> ConversationService
  -> persiste el intento saliente cifrado
  -> cliente fake o Meta explicito
```

Los endpoints sin `public_webhook_id` se conservan por compatibilidad historica
y no forman parte del flujo multi-tenant configurado de PRD-008.

### Envio

```
WhatsAppChannelMessageSender
  -> carga la configuracion exacta organization/bot/channel
  -> descifra el access token solo en memoria
  -> WhatsAppCloudApiClient.send_text_message()
  -> registra provider_message_id y estado
```

### Manejo de errores de envio

- Timeout, red, HTTP 429 y HTTP 5xx producen reintento persistido y acotado.
- HTTP 400, autenticacion y configuracion invalida son no reintentables.
- Los estados `sent`, `delivered`, `read` y `failed` son idempotentes y no
  retroceden ante eventos antiguos.
- No se registran bodies de Meta, tokens, firmas, texto ni identificadores completos.

## Conversations Management

PRD-009 extiende las tablas existentes `conversation` y `message`; no crea un
historial paralelo. La identidad administrativa combina organización, bot, canal
e identidad externa. Los mensajes generados por canales se cifran en reposo y se
vinculan opcionalmente a receipts e intentos outbound sin sustituir sus
responsabilidades técnicas.

- Lifecycle administrativo: `open`, `closed`, `archived`.
- Un inbound puede reabrir una conversación cerrada; una archivada no se reabre.
- Los listados devuelven identificadores de cliente enmascarados.
- `conversation.read` permite metadatos; `conversation.read_content` controla el
  texto descifrado.
- El historial se pagina por `occurred_at` e `id`; no se descifra contenido para
  buscarlo en memoria.

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

**726 passed, 15 skipped, 2 warnings**. Ruff, Black y mypy están limpios sobre
400 archivos. Los tests locales usan modo in-memory sin Docker/PostgreSQL. PRD-009
fue validado con Docker/PostgreSQL real, migración `20260730_0010`, HMAC previo
al parseo, idempotencia secuencial/concurrente, persistencia cifrada, lifecycle
administrativo, RBAC de contenido y supervivencia tras reiniciar la API.

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
- **PRD-001 Organizations** Phase 3: contratos, servicio de aplicación, API, persistencia PostgreSQL, migración Alembic y tests

## PRD-010 Human Handoff (CLOSED)

PRD-001 through PRD-012 are closed. PRD-010 adds a tenant-scoped handoff
lifecycle, bot suppression, encrypted and attributed human replies through the
generic channel sender, idempotency, archive protection, and safe transport
errors. PRD-011 adds the Contact increment; Customer is deferred and CRM is not
implemented. PRD-012 through PRD-022 are closed; PRD-023 is implemented pending
CTO review. Real
Meta and Google validation need explicit external credentials.

