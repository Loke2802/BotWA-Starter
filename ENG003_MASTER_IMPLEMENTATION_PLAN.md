# ENG-003 — Knowledge Engine — Master Implementation Plan

**Blueprint:** D-010
**Engine ID:** ENG-003
**Estado:** Plan maestro

---

## 1. Blueprint Breakdown

### Pipeline completo (D-010-03)

```
Knowledge Source
→ Knowledge Retriever     (¿Dónde está el conocimiento?)
→ Knowledge Normalizer    (¿Cómo lo representamos uniformemente?)
→ Knowledge Resolver      (¿Cuál es la versión correcta?)
→ Knowledge Validator     (¿Es apto para publicar?)
→ Knowledge Publisher     (¿Cómo lo ponemos a disposición?)
→ Knowledge Catalog       (Activo reutilizable)
→ Knowledge Consumer      (BB, CE, etc.)
```

| Componente | Responsabilidad | Entradas | Salidas | Dependencias |
|---|---|---|---|---|
| **Knowledge Source** | Definir fuentes autorizadas | Config/metadata | Source ID, type, trust level | — |
| **Knowledge Retriever** | Recuperar información desde fuentes | Knowledge Query | Knowledge Items | Sources |
| **Knowledge Normalizer** | Convertir al Canonical Knowledge Model | Knowledge Items | Normalized Items | Retriever |
| **Knowledge Normalizer** | Convertir al Canonical Knowledge Model | Knowledge Items | Normalized Items | Retriever |
| **Knowledge Resolver** | Resolver conflictos entre fuentes | Normalized Items + Metadata | Resolved Item | Normalizer |
| **Knowledge Validator** | Validar calidad antes de publicar | Resolved Item + Policies | Validated Item | Resolver |
| **Knowledge Publisher** | Publicar al catálogo | Validated Item | Knowledge Response + Catalog update | Validator |
| **Knowledge Catalog** | Catálogo de conocimiento gobernado | — | Queryable knowledge store | Publisher |

### Objetos del blueprint (D-010-10)

| Objeto | Existe hoy? | Descripción |
|---|---|---|
| Knowledge Source | ✗ | Fuente autorizada con metadatos (ID, type, trust, status, retention) |
| Knowledge Query | ✓ | `app/domain/knowledge/contracts.py` — content, intent, customer_id, company_id |
| Knowledge Item | ✗ | Resultado crudo de una fuente: source_id, content, confidence, raw_metadata |
| Normalized Knowledge Item | ✗ | Versión canónica: source_id, canonical_content, fields, confidence, timestamp |
| Resolved Knowledge Item | ✗ | Versión única tras resolver conflictos: source, priority, resolution_strategy |
| Validated Knowledge Item | ✗ | Aprobado con health_score, validity_status, validated_at |
| Knowledge Response | ✗ | Respuesta final para consumidores: found, content, confidence, sources[] |
| Knowledge Catalog | ✗ | Repositorio de conocimiento publicado, versionado, trazable |

---

## 2. Estado actual del código

```
app/core/knowledge/
├── __init__.py              ✓  Package marker
├── service.py               ✓  KnowledgeService.query() — thin wrapper
├── provider.py              ✓  KnowledgeProvider ABC (search method only)
├── orchestrator.py          ✓  KnowledgeOrchestrator — iterates, first-match
└── in_memory_provider.py    ✓  Keyword-based matching, 4 hardcoded items

app/domain/knowledge/
├── __init__.py              ✓  Package marker
└── contracts.py             ✓  KnowledgeQuery, KnowledgeContext, KnowledgeResult

tests/
├── test_knowledge_contracts.py   ✓  5 tests
├── test_knowledge_service.py     ✓  2 tests
└── test_knowledge_orchestrator.py ✓  3 tests

app/api/dependencies.py     ✓  Wire: InMemoryProvider → Orchestrator → Service

app/infrastructure/
├── models/                  ✗  No knowledge ORM models
├── repositories/            ✗  No knowledge repositories
└── database.py              —  (shared, no knowledge-specific)

app/core/business/service.py
→ Line 105-124: BB calls KnowledgeService.query() DIRECTLY (inline, outside pipeline)
→ No pipeline stages, no events for pipeline stages, no catalog
```

### Gap Analysis vs Blueprint

| Aspecto | Blueprint D-010 | Código actual | Brecha |
|---|---|---|---|
| **Pipeline** | 6 etapas secuenciales | 0 etapas (llamada directa) | **Crítica** |
| **Knowledge Source** | Fuentes gobernadas con ciclo de vida | No existe | **Total** |
| **Knowledge Retriever** | Busca en fuentes autorizadas | Existe como Orchestrator + Provider (simplificado) | **Parcial** |
| **Knowledge Normalizer** | Transformación al modelo canónico | No existe | **Total** |
| **Knowledge Resolver** | Resuelve conflictos entre fuentes | No existe (first-match-wins implícito en Orchestrator) | **Parcial** |
| **Knowledge Validator** | Valida calidad, health score | No existe | **Total** |
| **Knowledge Publisher** | Publica al catálogo | No existe | **Total** |
| **Knowledge Catalog** | Repositorio gobernado, versionado | No existe | **Total** |
| **Knowledge Item** | Objeto completo con metadatos | No existe (solo KnowledgeResult crudo) | **Total** |
| **Knowledge Response** | Respuesta con trazabilidad de fuentes | No existe (solo KnowledgeResult) | **Total** |
| **Eventos de pipeline** | Cada etapa publica eventos | 0 eventos de KE | **Total** |
| **Persistence** | DB para catálogo y fuentes | No existe | **Total** |
| **Integración BB** | A través del pipeline formal | Inline directo | **Crítica** |

---

## 3. Arquitectura objetivo

### Pipeline completo del Knowledge Engine

```
                    Knowledge Consumer (BB)
                            │
                     Knowledge Query
                            │
                            ▼
┌─────────────────────────────────────────────────────┐
│                Knowledge Service                     │
│                                                      │
│  Knowledge Query                                     │
│       │                                              │
│       ▼                                              │
│  Knowledge Retriever  →  KnowledgeItem[]             │
│       │                                              │
│       ▼                                              │
│  Knowledge Normalizer  →  NormalizedKnowledgeItem[]  │
│       │                                              │
│       ▼                                              │
│  Knowledge Resolver   →  ResolvedKnowledgeItem       │
│       │                                              │
│       ▼                                              │
│  Knowledge Validator  →  ValidatedKnowledgeItem      │
│       │                                              │
│       ▼                                              │
│  Knowledge Publisher  →  KnowledgeResponse           │
│       │                                              │
│       ▼                                              │
│  Knowledge Catalog    (store + retrieve)              │
│                                                      │
└─────────────────────────────────────────────────────┘
                            │
                     Knowledge Response
                            │
                            ▼
                    Knowledge Consumer (BB)
```

### Flujo de objetos

```
KnowledgeQuery → [Retriever] → KnowledgeItem[]
→ [Normalizer] → NormalizedKnowledgeItem[]
→ [Resolver]   → ResolvedKnowledgeItem
→ [Validator]  → ValidatedKnowledgeItem
→ [Publisher]  → KnowledgeResponse + → Catalog
```

### Integración con Business Brain

```
BusinessBrainService.process():
  ...
  ActionPlanner → BusinessActionPlan
  ↓
  KnowledgeService (antes inline, ahora pipeline formal)
    → KnowledgeRetriever
    → KnowledgeNormalizer
    → KnowledgeResolver
    → KnowledgeValidator
    → KnowledgePublisher → KnowledgeResponse
  ↓
  EventPublisher (eventos de pipeline KE)
  ↓
  return BusinessDecision (CE↔BB intacto)
```

### Integración con Event Publisher

Cada etapa del pipeline KE produce un `BusinessEvent`:
- `knowledge.retrieved`
- `knowledge.normalized`
- `knowledge.resolved`
- `knowledge.validated`
- `knowledge.published`

---

## 4. Dependency Graph

```
Macro Block A (Foundation)
├── Domain Contracts (todos los objetos del blueprint)
├── KnowledgeItem + NormalizedKnowledgeItem
├── KnowledgeSource (definición)
├── KnowledgeResponse
├── Retriever refactor (item-aware, multi-source)
├── Normalizer (identity/pass-through inicial)
├── Resolver (first-match, passthrough para single source)
├── Validator (always-valid passthrough)
├── Publisher (return-result passthrough)
├── Catalog (in-memory)
├── Service refactor (pipeline secuencial)
├── BB integration (call pipeline en vez de inline)
├── Events en cada etapa
├── Dependencies wire
└── Tests

Macro Block B (Persistence)
├── ORM models (KnowledgeItem, KnowledgeSource, Catalog)
├── Alembic migrations
├── Repositories
├── DB-backed Catalog
├── Admin APIs (CRUD sources, view catalog)
└── Tests

Macro Block C (Quality + Governance)
├── Normalizer real (field mapping, format conversion)
├── Resolver real (priority, trust score, freshness)
├── Validator real (health score, relevance, validity window)
├── Publisher real (versioning, status tracking)
├── Knowledge Source lifecycle (active→review→quarantine→archive)
├── Provider connector pattern (DB-backed provider registry)
└── Tests
```

**Orden de construcción:** A → B → C. No hay paralelismo posible porque B depende de los contratos de A, y C depende de la persistencia de B.

---

## 5. Riesgos

| Riesgo | Impacto | Mitigación |
|---|---|---|
| **Overengineering** — El starter kit NO necesita un pipeline completo de 6 etapas para VS1 | Esfuerzo innecesario, retraso en entrega | Las etapas Normalizer/Resolver/Validator comienzan como passthrough en Bloque A. Solo se implementan con lógica real en Bloque C si el caso de uso lo justifica. |
| **Rotura de la integración BB↔KE** — El contrato `BusinessDecision` no debe cambiar | Regresión en VS1 | El pipeline KE se integra en el mismo punto donde hoy está la llamada inline. `BusinessDecision` no se modifica. |
| **Duplicación de eventos** — EventPublisher de BB ya produce eventos de knowledge | Eventos duplicados o inconsistentes | Los eventos de pipeline KE son nuevos (`knowledge.retrieved`, `knowledge.normalized`, etc.). Los eventos legacy de BB (`consulta_conocimiento`, etc.) se mantienen para compatibilidad. |
| **Pérdida de la simplicidad actual** — El KE actual es 3 clases (Service, Orchestrator, Provider) | Complejidad innecesaria | Cada bloque mantiene la interfaz pública (`KnowledgeService.query()`) idéntica. El pipeline es interno. Ningún consumidor nota la diferencia. |
| **DB migrations sin datos existentes** — No hay datos KE en DB | Bajo | Las migraciones son limpias. Seed data opcional para VS1. |
| **Resolver sin conflictos reales** — VS1 usa 1 provider | Feature muerta | Resolver se implementa como passthrough (first-match) en Bloque A. La lógica real se activa solo con múltiples fuentes. |

---

## 6. Propuesta de implementación

### Macro Block A — Foundation (Core Pipeline)

**Objetivo:** Implementar el pipeline KE completo con todas las etapas, cada una como passthrough o con lógica mínima. Reemplazar la llamada inline de BB por el pipeline formal. Mantener 100% compatibilidad.

**Qué se implementa:**

#### A1 — Domain Contracts (nuevos)

Crear los objetos de dominio faltantes en `app/domain/knowledge/contracts.py`:

| Objeto | Campos clave |
|---|---|
| `KnowledgeSource` | `source_id, name, type, trust_level, status, retention_policy` |
| `KnowledgeItem` | `source_id, content, confidence, raw_metadata, retrieved_at` |
| `NormalizedKnowledgeItem` | `source_id, canonical_content, normalized_fields, confidence, normalized_at` |
| `ResolvedKnowledgeItem` | `sources[], content, confidence, resolution_strategy, resolved_at` |
| `ValidatedKnowledgeItem` | `source, health_score, validity_status, validated_at, valid_until` |
| `KnowledgeResponse` | `found, content, confidence, sources[]` |

`KnowledgeQuery`, `KnowledgeContext`, `KnowledgeResult` se mantienen (compatibilidad), pero `KnowledgeResult` queda deprecado en favor de `KnowledgeResponse`.

#### A2 — Knowledge Retriever (refactor)

- `KnowledgeRetriever` ABC con `retrieve(query) → list[KnowledgeItem]`
- `InMemoryKnowledgeProvider` → refactor a `InMemoryKnowledgeRetriever` que implementa `KnowledgeRetriever`
- Mantener compatibilidad con el `KnowledgeProvider` ABC legacy (o eliminarlo)
- Soporte multi-fuente (el actual Orchestrator se fusiona en Retriever)

#### A3 — Knowledge Normalizer (nuevo)

- `KnowledgeNormalizer` ABC con `normalize(items) → list[NormalizedKnowledgeItem]`
- `IdentityNormalizer` (passthrough): convierte cada `KnowledgeItem` → `NormalizedKnowledgeItem` copiando campos
- Sin transformación real en Bloque A

#### A4 — Knowledge Resolver (nuevo)

- `KnowledgeResolver` ABC con `resolve(items) → ResolvedKnowledgeItem`
- `FirstMatchResolver`: selecciona el primer item (comportamiento actual del Orchestrator)
- Traza la fuente seleccionada y la estrategia usada

#### A5 — Knowledge Validator (nuevo)

- `KnowledgeValidator` ABC con `validate(item) → ValidatedKnowledgeItem`
- `AlwaysValidValidator`: aprueba todo con health_score=1.0
- Sin lógica de caducidad, relevancia o integridad real

#### A6 — Knowledge Publisher (nuevo)

- `KnowledgePublisher` ABC con `publish(item) → KnowledgeResponse`
- `InMemoryKnowledgePublisher`: registra en catálogo in-memory, retorna response
- `KnowledgeCatalog` (in-memory): `list[ValidatedKnowledgeItem]`, queryable por keywords

#### A7 — KnowledgeService (refactor)

- `KnowledgeService` pasa de ser un wrapper de Orchestrator a orquestar el pipeline completo:

```
query → Retriever → Normalizer → Resolver → Validator → Publisher → Response
```

- Cada etapa publica un evento via callback/injection (`knowledge.retrieved`, etc.)
- Método `query()` retorna `KnowledgeResponse` (compatible con `KnowledgeResult` por ahora)

#### A8 — BB Integration (refactor service.py)

- Reemplazar el bloque inline (líneas 105-124) por:

```python
if decision.needs_knowledge and self._knowledge_service:
    response = self._knowledge_service.query(query)
    if response.found:
        decision.model_copy(update={
            "knowledge_content": response.content,
            "confidence": response.confidence,
        })
```

- `KnowledgeResponse` es compatible con `KnowledgeResult` (tiene `found`, `content`, `confidence`)
- `BusinessDecision` sin cambios (CE↔BB intacto)

#### A9 — Events

- Cada etapa del pipeline publica evento vía `EventPublisher` (inyectado):
  - `knowledge.retrieved` — sources consultados, items count
  - `knowledge.normalized` — items normalizados
  - `knowledge.resolved` — fuente seleccionada
  - `knowledge.validated` — health_score, status
  - `knowledge.published` — catalog entry

#### A10 — Tests

| Archivo | Tests | Lo que cubre |
|---|---|---|
| `tests/test_knowledge_contracts.py` | +5 | KnowledgeSource, KnowledgeItem, NormalizedItem, ResolvedItem, ValidatedItem, KnowledgeResponse |
| `tests/test_knowledge_retriever.py` | +4 | Retriever multi-source, empty result, source metadata |
| `tests/test_knowledge_normalizer.py` | +2 | Identity passthrough |
| `tests/test_knowledge_resolver.py` | +3 | First-match, single source, traceability |
| `tests/test_knowledge_validator.py` | +2 | Always-valid passthrough |
| `tests/test_knowledge_publisher.py` | +3 | Publish to catalog, response, catalog query |
| `tests/test_knowledge_service.py` | +4 | Pipeline integration, events, found/not-found |
| `tests/test_business_brain_service.py` | — | Sin cambios (contrato intacto) |

**Total tests Bloque A:** ~23 nuevos

#### A11 — Archivos

| Acción | Archivo |
|---|---|
| **Modificar** | `app/domain/knowledge/contracts.py` — +6 objetos |
| **Crear** | `app/core/knowledge/retriever.py` — `KnowledgeRetriever` ABC |
| **Crear** | `app/core/knowledge/in_memory_retriever.py` — refactor de `InMemoryKnowledgeProvider` |
| **Crear** | `app/core/knowledge/normalizer.py` — `KnowledgeNormalizer` ABC + `IdentityNormalizer` |
| **Crear** | `app/core/knowledge/resolver.py` — `KnowledgeResolver` ABC + `FirstMatchResolver` |
| **Crear** | `app/core/knowledge/validator.py` — `KnowledgeValidator` ABC + `AlwaysValidValidator` |
| **Crear** | `app/core/knowledge/publisher.py` — `KnowledgePublisher` ABC + `InMemoryKnowledgePublisher` + `KnowledgeCatalog` |
| **Modificar** | `app/core/knowledge/service.py` — pipeline orchestration |
| **Eliminar** | `app/core/knowledge/provider.py` — reemplazado por retriever.py |
| **Eliminar** | `app/core/knowledge/orchestrator.py` — lógica fusionada en service.py |
| **Modificar** | `app/core/knowledge/in_memory_provider.py` → refactor a retriever |
| **Modificar** | `app/core/business/service.py` — integrar pipeline KE |
| **Modificar** | `app/api/dependencies.py` — nuevo wiring |
| **Crear** | `tests/test_knowledge_retriever.py` |
| **Crear** | `tests/test_knowledge_normalizer.py` |
| **Crear** | `tests/test_knowledge_resolver.py` |
| **Crear** | `tests/test_knowledge_validator.py` |
| **Crear** | `tests/test_knowledge_publisher.py` |
| **Modificar** | `tests/test_knowledge_service.py` |
| **Modificar** | `tests/test_knowledge_orchestrator.py` → eliminar o refactor |

**Contratos afectados:** `KnowledgeQuery`, `KnowledgeContext`, `KnowledgeResult` — se mantienen (compatibilidad). `KnowledgeResponse` es nuevo. `BusinessDecision` — sin cambios.

---

### Macro Block B — Persistence

**Objetivo:** Agregar persistencia en base de datos para Knowledge Catalog, Knowledge Sources y Knowledge Items. Reemplazar implementaciones in-memory por DB-backed.

#### B1 — ORM Models

- `KnowledgeSourceModel` — source_id, name, type, trust_level, status, retention_policy, config (JSON), created_at, updated_at
- `KnowledgeCatalogEntryModel` — id, source_id, content_hash, content, confidence, health_score, valid_until, published_at, version
- `KnowledgeQueryLogModel` — id, query_text, intent, response_found, response_source, latency_ms, created_at (auditoría)

#### B2 — Alembic Migrations

- `20260722_0001_create_knowledge_source_table`
- `20260722_0002_create_knowledge_catalog_entry_table`
- `20260722_0003_create_knowledge_query_log_table`

#### B3 — Repositories

- `KnowledgeSourceRepository`
- `KnowledgeCatalogRepository`
- `KnowledgeQueryLogRepository`

#### B4 — DB-backed Implementations

- `DbKnowledgePublisher`: persiste items validados al catalog DB
- `DbKnowledgeRetriever`: busca en catalog DB (con fallback a providers)
- `DbKnowledgeCatalog`: queryable via SQL (full-text search básico)

#### B5 — Seed Data

- Insertar los 4 items actuales del `InMemoryKnowledgeProvider` como seed en catalog DB
- Marcar source como "seed_internal" con trust_level=1.0

#### B6 — Admin APIs (opcional, low priority)

- `GET /admin/knowledge/sources` — listar fuentes
- `POST /admin/knowledge/sources` — crear fuente
- `GET /admin/knowledge/catalog` — ver catálogo

#### B7 — Dependencies wire

- `dependencies.py` actualizado para usar repositorios DB cuando `settings.use_database=True`

#### B8 — Tests

| Archivo | Tests |
|---|---|
| `tests/test_infrastructure/test_knowledge_repositories.py` | +6 CRUD + query |
| `tests/test_knowledge_publisher.py` | +3 DB persistence |
| `tests/test_knowledge_catalog.py` | +4 DB-backed catalog |

---

### Macro Block C — Quality + Governance

**Objetivo:** Implementar lógica real en Normalizer, Resolver y Validator. Agregar ciclo de vida de fuentes y soporte multi-provider con detección de conflictos.

#### C1 — Real Normalizer

- `FieldMappingNormalizer`: mapea campos de diferentes formatos al Canonical Knowledge Model
- Soporte para: texto plano, JSON, CSV header mapping
- Normalización de fechas a ISO 8601, monedas a ISO 4217

#### C2 — Real Resolver

- `PriorityResolver`: usa `trust_level` de la fuente como criterio principal
- `FreshnessResolver`: usa fecha de actualización
- `ConsensusResolver`: mayoría entre fuentes independientes
- Estrategia configurable por intent/topic

#### C3 — Real Validator

- `HealthScoreValidator`: calcula Knowledge Health Score (0.0–1.0) basado en:
  - Freshness (0.3): días desde última actualización
  - Completeness (0.2): campos obligatorios presentes
  - Source trust (0.3): trust_level de la fuente
  - Relevance (0.2): match entre query e item
- Rechaza si health_score < threshold (configurable, default 0.5)
- Soporta cuarentena automática

#### C4 — Knowledge Source Lifecycle

- Estados: `active → review → quarantine → archived → deleted`
- Fuentes con trust_level bajo entran en cuarentena automática
- Items de fuentes en cuarentena no se sirven

#### C5 — Real Publisher

- Versionado automático (cada publicación incrementa versión)
- Soporte para deprecación: marcar items como `deprecated` con fecha de expiración
- Notificación de cambios via evento `knowledge.catalog.updated`

#### C6 — Tests

| Archivo | Tests |
|---|---|
| `tests/test_knowledge_normalizer.py` | +4 (field mapping, date format, CSV, JSON) |
| `tests/test_knowledge_resolver.py` | +6 (priority, freshness, consensus, mixed strategies) |
| `tests/test_knowledge_validator.py` | +6 (health score, thresholds, quarantine, auto-reject) |
| `tests/test_knowledge_source.py` | +4 (lifecycle transitions, trust-based quarantine) |
| `tests/test_knowledge_publisher.py` | +4 (versioning, deprecation, notifications) |

---

## 7. Resumen de archivos por bloque

### Macro Block A

| Tipo | Archivo | Acción |
|---|---|---|
| Domain | `app/domain/knowledge/contracts.py` | Modificar (+6 objetos) |
| Core | `app/core/knowledge/retriever.py` | Crear |
| Core | `app/core/knowledge/in_memory_retriever.py` | Crear |
| Core | `app/core/knowledge/normalizer.py` | Crear |
| Core | `app/core/knowledge/resolver.py` | Crear |
| Core | `app/core/knowledge/validator.py` | Crear |
| Core | `app/core/knowledge/publisher.py` | Crear |
| Core | `app/core/knowledge/service.py` | Modificar |
| Core | `app/core/knowledge/provider.py` | Eliminar |
| Core | `app/core/knowledge/orchestrator.py` | Eliminar |
| Core | `app/core/knowledge/in_memory_provider.py` | Modificar → refactor |
| BB | `app/core/business/service.py` | Modificar (integration) |
| API | `app/api/dependencies.py` | Modificar (wire) |
| Tests | `tests/test_knowledge_retriever.py` | Crear (+4) |
| Tests | `tests/test_knowledge_normalizer.py` | Crear (+2) |
| Tests | `tests/test_knowledge_resolver.py` | Crear (+3) |
| Tests | `tests/test_knowledge_validator.py` | Crear (+2) |
| Tests | `tests/test_knowledge_publisher.py` | Crear (+3) |
| Tests | `tests/test_knowledge_contracts.py` | Modificar (+5) |
| Tests | `tests/test_knowledge_service.py` | Modificar (+4) |

### Macro Block B

| Tipo | Archivo | Acción |
|---|---|---|
| Model | `app/infrastructure/models/knowledge_source.py` | Crear |
| Model | `app/infrastructure/models/knowledge_catalog.py` | Crear |
| Model | `app/infrastructure/models/knowledge_query_log.py` | Crear |
| Migration | `alembic/versions/20260722_0001_create_knowledge_source_table.py` | Crear |
| Migration | `alembic/versions/20260722_0002_create_knowledge_catalog_table.py` | Crear |
| Migration | `alembic/versions/20260722_0003_create_knowledge_query_log_table.py` | Crear |
| Repo | `app/infrastructure/repositories/knowledge_source_repository.py` | Crear |
| Repo | `app/infrastructure/repositories/knowledge_catalog_repository.py` | Crear |
| Repo | `app/infrastructure/repositories/knowledge_query_log_repository.py` | Crear |
| Core | `app/core/knowledge/db_retriever.py` | Crear (opcional) |
| Core | `app/core/knowledge/db_publisher.py` | Crear |
| Core | `app/core/knowledge/db_catalog.py` | Crear |
| API | `app/api/admin/knowledge_routes.py` | Crear (opcional) |
| API | `app/api/dependencies.py` | Modificar (DB wire) |
| Tests | `tests/test_infrastructure/test_knowledge_repositories.py` | Crear (+6) |
| Tests | `tests/test_knowledge_publisher.py` | Modificar (+3) |

### Macro Block C

| Tipo | Archivo | Acción |
|---|---|---|
| Core | `app/core/knowledge/normalizer.py` | Modificar (+FieldMappingNormalizer) |
| Core | `app/core/knowledge/resolver.py` | Modificar (+PriorityResolver, FreshnessResolver, ConsensusResolver) |
| Core | `app/core/knowledge/validator.py` | Modificar (+HealthScoreValidator, quarantine) |
| Core | `app/core/knowledge/publisher.py` | Modificar (+versioning, deprecation) |
| Core | `app/core/knowledge/source_manager.py` | Crear (lifecycle) |
| Tests | `tests/test_knowledge_normalizer.py` | Modificar (+4) |
| Tests | `tests/test_knowledge_resolver.py` | Modificar (+6) |
| Tests | `tests/test_knowledge_validator.py` | Modificar (+6) |
| Tests | `tests/test_knowledge_source.py` | Crear (+4) |
| Tests | `tests/test_knowledge_publisher.py` | Modificar (+4) |

---

## 8. Quality Gates

### Gates obligatorios para cerrar ENG-003

| Gate | Comando | Criterio |
|---|---|---|
| **pytest** | `pytest -q` | Todos los tests pasan. Sin regresión en VS1 (10/10) ni en ENG-001 (204 tests) ni ENG-002. |
| **ruff** | `ruff check .` | 0 errores |
| **black** | `black --check .` | 0 files reformatted |
| **mypy** | `mypy .` | 0 errores en todos los source files |
| **VS1** | `pytest tests/test_vs1_integration.py -q` | 10/10, sin cambios |
| **ENG-001** | `pytest tests/test_business_* -q` | Todos pasan, sin cambios en contratos CE↔BB |
| **ENG-002** | `pytest tests/test_conversation_* tests/test_channel_* tests/test_whatsapp_* -q` | Todos pasan, sin cambios |

### Gates por bloque

| Bloque | Gates adicionales |
|---|---|
| **A** | `pytest tests/test_knowledge_* -q` — todos los tests KE nuevos pasan. Pipeline KE produce `KnowledgeResponse` correcto. BB sigue retornando `BusinessDecision` idéntica. |
| **B** | `pytest tests/test_infrastructure/test_knowledge_* -q` — repositorios CRUD pasan. Catálogo DB retorna mismos resultados que in-memory. Seed data presente. |
| **C** | `pytest tests/test_knowledge_* -q` — normalizer real transforma formatos, resolver selecciona por prioridad, validator calcula health score, publisher versiona. |

### VS1 verification post-ENG-003

VS1 debe seguir pasando sin modificación:

1. greeting → flujo completo, BusinessDecision con status="accepted"
2. farewell → flujo completo
3. "¿Cuál es el horario?" → knowledge encontrado (desde KE pipeline, no desde inline)
4. "¿Cómo hago para contactarlos?" → knowledge no encontrado
5. unknown → flujo rejected
6. price_inquiry → knowledge consultado vía pipeline KE

---

## 9. Contratos CE↔BB

**No se modifican.** El contrato sigue siendo:

```
BusinessRequest → Business Brain → BusinessDecision
```

El pipeline KE es interno del BB. Ningún cambio visible para el CE.

---

## Lo que NO se hace en ENG-003

- No se modifica ENG-001 (Business Brain) más allá del punto de integración (service.py línea 105)
- No se modifica ENG-002 (Conversation Engine)
- No se modifican Blueprints (D-010, D-009, D-008)
- No se modifican ADRs
- No se implementa IA/ML en el Resolver o Validator
- No se implementan conectores reales a APIs externas (solo pattern en Bloque C)
- No se implementa cache distribuida
- No se implementa full-text search engine (PostgreSQL `LIKE`/`tsvector` es suficiente)
