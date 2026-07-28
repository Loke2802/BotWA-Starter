# ENG-004 — Automation Engine: Master Implementation Plan

**Proyecto:** BotWA Starter  
**Engine ID:** ENG-004  
**Versión:** 1.0  
**Estado:** Plan propuesto, pendiente de aprobación CTO  
**Fuentes:** D-011 (8 capítulos), ADR-004, ADR-005, ADR-006, ADR-007, ADR-008, ADR-009, CONTEXT_FOR_AI.md, ENG004_DOMAIN_ANALYSIS.md, ENG004_CTO_DECISIONS.md, código actual

---

## Decisiones del CTO vinculantes (Source of Truth)

| ID | Decisión | Resolución |
|---|---|---|
| D01 | Sincronía de ejecución | **A3 — Híbrido:** invocación asíncrona (background task) desde pipeline síncrono del BB. Fase 1 usa background task; futuro evoluciona a cola dedicada. |
| D02 | Punto de inyección | **A1 — En BusinessBrainService:** el AE se invoca desde `BusinessBrainService.process()` después de generar el `BusinessActionPlan`. |
| D03 | Dependencia Integration Engine | **A2 — Adaptador HTTP directo temporal:** componente interno del AE con interfaz estándar. Se depreca cuando ENG-005 exista. |
| D04 | Definiciones de Workflow | **A1 — Programático Fase 1:** el `WorkflowPlanner` contiene la lógica en código. Sin definiciones externas. |
| D05 | Alcance Fase 1 | **A2 — Acciones actuales + scheduling simple:** `respond`, `query_knowledge`, `escalate`, `delay`. |
| D06 | Persistencia de ejecuciones | **A3 — Eventos + estado actual en DB:** tabla de estado para consultas rápidas + eventos para trazabilidad histórica. |
| D07 | Esquema de eventos | **A1 — Namespace prefijo por Engine:** eventos del AE usan `ae.*`. Eventos del BB existentes se mantienen sin prefijo. |

---

## 1. Arquitectura completa

### 1.1 Componentes

```
┌──────────────────────────────────────────────────────────────────┐
│                    AUTOMATION ENGINE                             │
│                                                                  │
│  ┌─────────────────────┐    ┌──────────────────────────┐        │
│  │ AutomationRequest    │    │    Workflow Planner      │        │
│  │ Builder              │───▶│                          │        │
│  │                      │    │  (programático, D04-A1)  │        │
│  │ Entrada:             │    │                          │        │
│  │  - BusinessDecision  │    │  Salida: ExecutionPlan   │        │
│  │  - BusinessActionPlan│    └───────────┬──────────────┘        │
│  │  - BusinessContext   │                │                       │
│  └─────────────────────┘                ▼                       │
│                               ┌──────────────────────────┐       │
│                               │    Task Orchestrator      │       │
│                               │                          │       │
│                               │  - Ejecuta tareas        │       │
│                               │  - Coordina dependencias │       │
│                               │  - Paralelismo           │       │
│                               │  - Scheduling (D05-A2)   │       │
│                               │  - HTTP adaptador (D03)  │       │
│                               │  - Retry                 │       │
│                               │                          │       │
│                               │  Salida: ExecutionStatus │       │
│                               └───────────┬──────────────┘       │
│                                           ▼                       │
│                               ┌──────────────────────────┐       │
│                               │    Execution Monitor      │       │
│                               │                          │       │
│                               │  - Registra estado       │       │
│                               │  - Detecta errores       │       │
│                               │  - Publica eventos       │       │
│                               │  - Persiste (D06-A3)     │       │
│                               │                          │       │
│                               │  Salida: AutomationResult│       │
│                               │         + BusinessEvent  │       │
│                               └──────────────────────────┘       │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │   AutomationService (orquestador del pipeline AE)        │    │
│  │   execute(plan) → lanza background task                  │    │
│  │   → pipeline AE corre en background (D01-A3)             │    │
│  └──────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────┘
```

### 1.2 Responsabilidades

#### AutomationRequestBuilder
- **Responsabilidad:** Transformar `BusinessDecision` + `BusinessActionPlan` + `BusinessContext` en un `AutomationRequest`.
- **Validaciones:** Decision válida, plan disponible, información mínima completa, consistencia de contrato.
- **NO hace:** Modificar la decisión, interpretar reglas de negocio, consultar conocimiento, ejecutar procesos.
- **Entradas:** `BusinessDecision`, `BusinessActionPlan`, `BusinessContext`
- **Salida:** `AutomationRequest`

#### WorkflowPlanner
- **Responsabilidad:** Construir el `ExecutionPlan` a partir del `AutomationRequest`.
- **El ExecutionPlan define:** Tareas, orden de ejecución, dependencias, ejecución secuencial o paralela, políticas de reintento, condiciones de finalización.
- **Programático (D04-A1):** La lógica de planificación está en código. Para cada `ActionStep` del plan del BB, el planner genera una o más `Task` con políticas por defecto.
- **NO hace:** Ejecutar tareas, tomar decisiones, consultar conocimiento, comunicarse con sistemas externos.
- **Entrada:** `AutomationRequest`
- **Salida:** `ExecutionPlan`

#### TaskOrchestrator
- **Responsabilidad:** Coordinar la ejecución del `ExecutionPlan` de forma ordenada y controlada.
- **Funciones:**
  - Iniciar tareas según orden y dependencias.
  - Ejecutar tareas paralelas cuando no hay dependencias.
  - Gestionar reintentos según `RetryPolicy`.
  - Manejar `delay` / scheduling simple (D05-A2).
  - Invocar adaptador HTTP para tareas externas (D03-A2).
  - Detectar bloqueos (dependencias circulares, stalled tasks).
  - Reportar `ExecutionStatus` en vivo.
- **NO hace:** Diseñar workflows, modificar el `ExecutionPlan`, tomar decisiones de negocio, consultar conocimiento.
- **Entrada:** `ExecutionPlan`
- **Salida:** `ExecutionStatus`

#### ExecutionMonitor
- **Responsabilidad:** Supervisar el ciclo de vida completo de cada automatización. Registrar inicio, progreso, errores, reintentos, cancelaciones y finalización.
- **Funciones:**
  - Persistir estado actual en DB (tabla `automation_execution` + `task_execution`) — D06-A3.
  - Publicar eventos `ae.*` (D07-A1).
  - Detectar errores y actualizar estado.
  - Generar `AutomationResult`.
- **NO hace:** Ejecutar tareas, modificar el plan, tomar decisiones, diseñar workflows.
- **Entrada:** `ExecutionStatus`
- **Salidas:** `AutomationResult`, `BusinessEvent` con prefijo `ae.*`

#### AutomationService
- **Responsabilidad:** Orquestar el pipeline completo del AE. Punto de entrada para el BB.
- **Funciones:**
  - Recibir `BusinessDecision` + `BusinessActionPlan` + `BusinessContext`.
  - Invocar `AutomationRequestBuilder`.
  - Invocar `WorkflowPlanner`.
  - Lanzar `TaskOrchestrator` + `ExecutionMonitor` en background task (D01-A3).
  - Retornar inmediatamente al BB.
- **Entrada:** `BusinessDecision`, `BusinessActionPlan`, `BusinessContext`
- **Salida:** `execution_id` (para tracking) + ejecución asíncrona

### 1.3 Dependencias entre componentes

```
AutomationService
  ├── AutomationRequestBuilder
  │     └── domain contracts
  ├── WorkflowPlanner
  │     └── domain contracts
  ├── TaskOrchestrator
  │     ├── WorkflowPlanner (recibe ExecutionPlan)
  │     └── domain contracts
  └── ExecutionMonitor
        ├── TaskOrchestrator (recibe ExecutionStatus)
        └── domain contracts
```

---

## 2. Pipeline completo

```
BusinessBrainService.process()
  │
  │   BusinessDecision + BusinessActionPlan + BusinessContext
  │
  ▼
AutomationService.execute(decision, plan, context)
  │
  ├── 1. AutomationRequestBuilder.build(decision, plan, context)
  │     → AutomationRequest
  │
  ├── 2. WorkflowPlanner.plan(request)
  │     → ExecutionPlan
  │     └── [sincrónico, rápido]
  │
  ├── 3. Lanzar background task (D01-A3):
  │     asyncio.create_task(_run_execution(plan))
  │
  │   ┌─────────────────────────────────────────────────────┐
  │   │  Background: _run_execution(plan)                    │
  │   │                                                     │
  │   │  4. ExecutionMonitor.on_start(plan)                  │
  │   │     → persiste estado: PENDING                      │
  │   │     → publica: ae.execution.started                 │
  │   │                                                     │
  │   │  5. TaskOrchestrator.execute(plan)                   │
  │   │     → para cada Task según orden/dependencias:      │
  │   │                                                     │
  │   │   5a. ExecutionMonitor.on_task_start(task)           │
  │   │       → persiste: TASK_RUNNING                      │
  │   │       → publica: ae.task.started                    │
  │   │                                                     │
  │   │   5b. Ejecutar task:                                │
  │   │       ┌──────────────┬──────────────┬───────────┐   │
  │   │       │ respond      │ respond to   │ síncrono  │   │
  │   │       │              │ conversation │           │   │
  │   │       ├──────────────┼──────────────┼───────────┤   │
  │   │       │ query_       │ query KE     │ síncrono  │   │
  │   │       │ knowledge    │ (ya resuelto │           │   │
  │   │       │              │ por BB)      │           │   │
  │   │       ├──────────────┼──────────────┼───────────┤   │
  │   │       │ escalate     │ notify       │ síncrono  │   │
  │   │       │              │ human        │           │   │
  │   │       ├──────────────┼──────────────┼───────────┤   │
  │   │       │ delay        │ esperar N    │ async     │   │
  │   │       │              │ segundos     │ sleep     │   │
  │   │       ├──────────────┼──────────────┼───────────┤   │
  │   │       │ http_call    │ llamar API   │ async     │   │
  │   │       │              │ externa      │ HTTP      │   │
  │   │       └──────────────┴──────────────┴───────────┘   │
  │   │                                                     │
  │   │   5c. Si éxito:                                     │
  │   │       → ExecutionMonitor.on_task_complete(task)     │
  │   │       → persiste: TASK_COMPLETED                    │
  │   │       → publica: ae.task.completed                  │
  │   │                                                     │
  │   │   5d. Si falla y retry disponible:                  │
  │   │       → ExecutionMonitor.on_task_retry(task, n)     │
  │   │       → persiste: TASK_RETRYING                     │
  │   │       → publica: ae.task.retrying                   │
  │   │       → esperar delay según RetryPolicy             │
  │   │       → reintentar (step 5b)                        │
  │   │                                                     │
  │   │   5e. Si falla sin retry o agotado:                 │
  │   │       → ExecutionMonitor.on_task_failed(task, err)  │
  │   │       → persiste: TASK_FAILED                       │
  │   │       → publica: ae.task.failed                     │
  │   │                                                     │
  │   │   5f. Repetir hasta completar todas las tareas      │
  │   │                                                     │
  │   │  6. ExecutionMonitor.on_complete(status, result)     │
  │   │     → persiste: COMPLETED / FAILED / CANCELLED      │
  │   │     → publica: ae.execution.completed               │
  │   │               / ae.execution.failed                 │
  │   │     → genera: AutomationResult                      │
  │   └─────────────────────────────────────────────────────┘
  │
  └── Retorna execution_id al BB → CE responde al usuario
```

---

## 3. Objetos de dominio

### 3.1 Contratos — `app/domain/automation/contracts.py`

```python
# === AUTOMATION REQUEST (entrada del pipeline) ===

class AutomationRequest(BaseModel):
    """Solicitud de automatización generada por el AutomationRequestBuilder."""
    request_id: UUID
    decision: BusinessDecision
    action_plan: BusinessActionPlan
    context: BusinessContext
    created_at: datetime


# === EXECUTION PLAN (salida del WorkflowPlanner) ===

class RetryPolicy(BaseModel):
    """Política de reintento para una tarea."""
    max_attempts: int = 3
    delay_seconds: float = 1.0
    backoff_multiplier: float = 2.0


class Task(BaseModel):
    """Unidad atómica de ejecución dentro de un ExecutionPlan."""
    task_id: UUID
    action: str                          # respond, query_knowledge, escalate, delay, http_call
    target: str = ""                     # conversation_service, knowledge_service, human_support
    parameters: dict[str, object] = {}
    order: int = 0
    dependencies: list[UUID] = []        # task_ids que deben completarse antes
    retry_policy: RetryPolicy = RetryPolicy()
    timeout_seconds: float = 30.0


class ExecutionPlan(BaseModel):
    """Plan de ejecución estructurado generado por el WorkflowPlanner."""
    plan_id: UUID
    request_id: UUID
    tasks: list[Task] = []
    created_at: datetime


# === EXECUTION STATUS (estado en vivo) ===

class TaskExecutionStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"
    SKIPPED = "skipped"


class ExecutionStatusType(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskExecution(BaseModel):
    """Estado de una tarea individual durante la ejecución."""
    task_id: UUID
    status: TaskExecutionStatus = TaskExecutionStatus.PENDING
    attempt: int = 0
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: str | None = None
    result_data: dict[str, object] = {}


class ExecutionStatus(BaseModel):
    """Estado de la ejecución completa en un momento dado."""
    execution_id: UUID
    plan_id: UUID
    status: ExecutionStatusType = ExecutionStatusType.PENDING
    tasks: dict[UUID, TaskExecution] = {}
    started_at: datetime | None = None
    updated_at: datetime | None = None
    error_count: int = 0


# === AUTOMATION RESULT (resultado final) ===

class AutomationResult(BaseModel):
    """Resultado final de una ejecución de automatización."""
    execution_id: UUID
    status: ExecutionStatusType
    completed_tasks: list[UUID] = []
    failed_tasks: list[UUID] = []
    errors: list[str] = []
    duration_ms: int = 0
    result_data: dict[str, object] = {}
    finished_at: datetime
```

### 3.2 Eventos

Los eventos se publican usando `BusinessEvent` existente con:

```python
event_type = "ae.execution.started"       # D07-A1: prefijo ae.*
event_type = "ae.execution.completed"
event_type = "ae.execution.failed"
event_type = "ae.task.started"
event_type = "ae.task.completed"
event_type = "ae.task.failed"
event_type = "ae.task.retrying"
event_type = "ae.execution.cancelled"
```

`source = "automation_engine"`  
`payload` incluye: `execution_id`, `plan_id`, `task_id` (para eventos de tarea).

---

## 4. Dependency Graph

```
Nivel 0 (sin dependencias):
  └── automation/contracts.py

Nivel 1 (depende solo de contracts):
  ├── automation/request_builder.py
  ├── automation/workflow_planner.py
  └── automation/execution_monitor.py (interfaz)

Nivel 2 (depende de contracts + componentes nivel 1):
  └── automation/task_orchestrator.py
        └── depende de: contracts, workflow_planner

Nivel 3 (depende de todos los anteriores):
  ├── automation/service.py
  │     └── depende de: request_builder, workflow_planner,
  │                     task_orchestrator, execution_monitor
  └── automation/adapters/http_task_handler.py
        └── depende de: contracts

Nivel 4 (infraestructura):
  ├── infrastructure/models/automation_execution.py
  │     └── depende de: contracts
  ├── infrastructure/repositories/automation_repository.py
  │     └── depende de: models
  └── api/dependencies.py (wiring)
        └── depende de: todo lo anterior
```

**Orden de construcción obligatorio:**
1. `contracts.py` (nivel 0)
2. `request_builder.py`, `workflow_planner.py`, interfaces de `task_orchestrator.py`, `execution_monitor.py` (nivel 1)
3. Implementación de `task_orchestrator.py` (nivel 2)
4. Implementación de `execution_monitor.py` (nivel 2)
5. `service.py` (nivel 3)
6. `http_task_handler.py`, models, repositories, wiring (nivel 4)

---

## 5. Macro Blocks

Máximo 3 bloques. La división sigue el dependency graph.

---

### Macro Block A — Foundation

#### Objetivo
Establecer la base del Engine: contratos, interfaces, pipeline esqueleto, y el punto de integración con el Business Brain.

#### Componentes a crear

| Componente | Archivo | Descripción |
|---|---|---|
| Domain contracts | `app/domain/automation/__init__.py` | Package |
| Domain contracts | `app/domain/automation/contracts.py` | `AutomationRequest`, `ExecutionPlan`, `Task`, `RetryPolicy`, `ExecutionStatus`, `TaskExecution`, `TaskExecutionStatus`, `ExecutionStatusType`, `AutomationResult` |
| Request Builder | `app/core/automation/request_builder.py` | `AutomationRequestBuilder` — transforma BB contracts → `AutomationRequest` |
| Request Builder interface | `app/core/automation/request_builder.py` | ABC + impl concreta |
| Workflow Planner | `app/core/automation/workflow_planner.py` | `WorkflowPlanner` — programaático (D04-A1): mapea `ActionStep` → `Task` con políticas default |
| Workflow Planner interface | `app/core/automation/workflow_planner.py` | ABC + impl concreta |
| Orchestrator interface | `app/core/automation/task_orchestrator.py` | ABC `TaskOrchestrator` — solo interfaz |
| Monitor interface | `app/core/automation/execution_monitor.py` | ABC `ExecutionMonitor` — solo interfaz |
| Service skeleton | `app/core/automation/service.py` | `AutomationService` — orquestador del pipeline AE. Invoca builder → planner → lanza background task |
| Tests contracts | `tests/test_automation_contracts.py` | Validación de todos los contratos (frozen, defaults, types) |
| Tests builder | `tests/test_automation_request_builder.py` | Builder transforma correctamente BB contracts |
| Tests planner | `tests/test_automation_workflow_planner.py` | Planner genera ExecutionPlan desde AutomationRequest |
| Tests service | `tests/test_automation_service.py` | Service orquesta pipeline |

#### Contratos que expone (inter-engine)

| Contrato | Dirección | Propósito |
|---|---|---|
| `AutomationService.execute(decision, plan, context)` → `execution_id` | BB → AE | Punto de entrada del Engine |

#### Archivos modificados

| Archivo | Cambio |
|---|---|
| `app/core/business/service.py` | Inyectar `AutomationService` y llamar a `execute()` después de generar `BusinessActionPlan` (D02-A1) |
| `app/api/dependencies.py` | Wire `AutomationService` + sus dependencias |

#### Tests

| Archivo | Tests estimados |
|---|---|
| `tests/test_automation_contracts.py` | 12 (cada contrato) |
| `tests/test_automation_request_builder.py` | 5 (build, empty plan, invalid decision, etc.) |
| `tests/test_automation_workflow_planner.py` | 8 (respond, query_knowledge, escalate, delay, multiple steps, dependencies, empty) |
| `tests/test_automation_service.py` | 5 (execute, background launch, error handling) |

**Total estimado: 30 tests nuevos.**

#### Criterio de cierre

- Domain contracts definidos y testeados.
- `AutomationRequestBuilder` funcional.
- `WorkflowPlanner` programático funcional.
- `AutomationService` orquesta pipeline y lanza background task.
- BB invoca AE después de generar plan.
- VS1 sigue funcionando (el AE es invocado pero no ejecuta nada visible).
- pytest, ruff, black, mypy = 0 errores.

---

### Macro Block B — Core Orchestration

#### Objetivo
Implementar los componentes centrales de ejecución: TaskOrchestrator y ExecutionMonitor. El AE ejecuta realmente tareas.

#### Componentes a crear

| Componente | Archivo | Descripción |
|---|---|---|
| Task Orchestrator | `app/core/automation/task_orchestrator.py` | Implementación concreta: ejecuta tareas secuencial/paralelo, dependencias, retry, delay |
| Execution Monitor | `app/core/automation/execution_monitor.py` | Implementación concreta: registra estado, publica eventos `ae.*`, genera `AutomationResult` |
| HTTP Task Handler | `app/core/automation/adapters/http_task_handler.py` | Adaptador HTTP temporal (D03-A2) para tareas externas |
| Task Registry | `app/core/automation/task_registry.py` | Registry de handlers de tareas: action → handler mapping |

#### Archivos modificados

| Archivo | Cambio |
|---|---|
| `app/core/automation/service.py` | Background task invoca Orchestrator + Monitor |
| `app/core/business/service.py` | Sin cambios (ya integrado en Macro Block A) |
| `app/api/dependencies.py` | Wire Orchestrator, Monitor, Task Registry |

#### Task Registry

```python
class TaskRegistry:
    """Registry que mapea nombres de acción a handlers."""
    _handlers: dict[str, TaskHandler]

    def register(self, action: str, handler: TaskHandler) -> None
    def get_handler(self, action: str) -> TaskHandler
    def execute(self, task: Task) -> TaskResult
```

#### Task Handlers internos

| Handler | Acción | Comportamiento |
|---|---|---|
| `RespondHandler` | `respond` | Log + callback a CE (vía evento `ae.task.completed`). No modifica respuesta al usuario (ya fue enviada). |
| `KnowledgeQueryHandler` | `query_knowledge` | No ejecuta nada (el BB ya consultó KE). Marca como completada. |
| `EscalateHandler` | `escalate` | Notifica a humanos (log + evento + futuro: ticket system). |
| `DelayHandler` | `delay` | `asyncio.sleep(delay_seconds)`. Scheduling simple. |
| `HttpCallHandler` | `http_call` | HTTP client asíncrono a URL externa (D03-A2). |

#### Eventos que publica el ExecutionMonitor

| Evento | Cuándo |
|---|---|
| `ae.execution.started` | Inicio de ejecución |
| `ae.task.started` | Cada tarea antes de ejecutar |
| `ae.task.completed` | Tarea completada exitosamente |
| `ae.task.failed` | Tarea fallida sin más retry |
| `ae.task.retrying` | Tarea fallida con retry programado |
| `ae.execution.completed` | Todas las tareas completadas |
| `ae.execution.failed` | Ejecución fallida (tarea crítica falló) |
| `ae.execution.cancelled` | Ejecución cancelada |

#### Tests

| Archivo | Tests estimados |
|---|---|
| `tests/test_automation_task_orchestrator.py` | 15 (secuencial, paralelo, dependencias, retry, delay, fallo, timeout, cancelación, tarea externa HTTP) |
| `tests/test_automation_execution_monitor.py` | 10 (registro de estado, eventos, error detection, result generation) |
| `tests/test_automation_task_registry.py` | 5 (register, get, execute, unknown action) |
| `tests/test_automation_http_handler.py` | 5 (success, failure, timeout, invalid URL) |
| `tests/test_automation_service.py` (ampliado) | +5 (background execution completa, monitoreo en vivo) |

**Total estimado: 40 tests nuevos (15 nuevos + 25 ampliados).**

#### Criterio de cierre

- TaskOrchestrator ejecuta tareas secuenciales y paralelas.
- RetryPolicy funcional con backoff.
- Delay/scheduling simple funcional.
- ExecutionMonitor persiste estado en memoria y publica eventos.
- Adaptador HTTP temporal funcional.
- AE ejecuta `BusinessActionPlan` completo en background.
- VS1 sigue funcionando sin cambios visibles (el AE corre en background).
- pytest, ruff, black, mypy = 0 errores.

---

### Macro Block C — Production Readiness

#### Objetivo
Persistencia real en DB, scheduler persistente, observabilidad completa, integración final con el ecosistema.

#### Componentes a crear

| Componente | Archivo | Descripción |
|---|---|---|
| ORM Execution Model | `app/infrastructure/models/automation_execution.py` | `AutomationExecutionModel` + `TaskExecutionModel` |
| Migration | `alembic/versions/20260723_0001_create_automation_tables.py` | Crear tablas de ejecución |
| Repository | `app/infrastructure/repositories/automation_repository.py` | CRUD ejecuciones + consulta por estado |
| DB Execution Monitor | `app/core/automation/execution_monitor.py` | Evolución: escribe a DB vía repositorio (D06-A3) |
| DB Scheduler | `app/core/automation/scheduler.py` | Scheduler simple: ejecuta tareas `delay` pendientes que sobreviven restart |
| Observability | `app/core/automation/observability.py` | Métricas (contador de ejecuciones, duración, errores), logging estructurado |

#### Archivos modificados

| Archivo | Cambio |
|---|---|
| `app/core/automation/execution_monitor.py` | Persistir a DB (D06-A3). Estado actual en `automation_execution`, eventos como `BusinessEvent`. |
| `app/core/automation/service.py` | Recovery de ejecuciones pendientes al startup. |
| `app/api/dependencies.py` | Wire repositorio DB, scheduler. |
| `app/infrastructure/models/__init__.py` | Import `AutomationExecutionModel`, `TaskExecutionModel`. |
| `alembic/env.py` | Import de nuevos modelos. |

#### ORM Models

```python
class AutomationExecutionModel(Base):
    __tablename__ = "automation_execution"
    id: UUID (PK)
    plan_id: UUID
    request_id: UUID
    status: str (pending/running/completed/failed/cancelled)
    started_at: datetime
    finished_at: datetime | None
    error_count: int
    result_data: JSON
    created_at: datetime
    updated_at: datetime

class TaskExecutionModel(Base):
    __tablename__ = "task_execution"
    id: UUID (PK)
    execution_id: UUID (FK → automation_execution.id)
    task_id: UUID
    action: str
    status: str
    attempt: int
    started_at: datetime | None
    completed_at: datetime | None
    error: str | None
    result_data: JSON
    created_at: datetime
```

#### Scheduler (D05-A2 scheduling simple)

```python
class AutomationScheduler:
    def schedule_task(execution_id, task_id, delay_seconds)
    def process_pending()  # llamado al startup y periódicamente
    def cancel(execution_id)
```

Persiste tareas `delay` en DB para que sobrevivan restart. Al iniciar, carga tareas pendientes y las ejecuta.

#### Observabilidad

```python
class AutomationObservability:
    def record_execution_start(execution_id, plan_id)
    def record_execution_end(execution_id, status, duration_ms)
    def record_task_result(execution_id, task_id, status, attempt)
    def get_metrics()  # total, success_rate, avg_duration, error_distribution
```

#### Tests

| Archivo | Tests estimados |
|---|---|
| `tests/test_infrastructure/test_automation_repositories.py` | 8 (CRUD execution, CRUD task, query by status, query by plan) |
| `tests/test_automation_db.py` | 10 (persistencia, recovery, scheduler, observabilidad) |
| `tests/test_automation_scheduler.py` | 6 (schedule, execute after delay, cancel, recovery restart) |
| `tests/test_automation_observability.py` | 5 (metrics, logging) |

**Total estimado: 29 tests nuevos.**

#### Modelo de producción final

```
ConversationService.handle_message()
  → BusinessBrainService.process()
    → ActionPlanner.plan() → BusinessActionPlan
    → [NUEVO] AutomationService.execute(decision, plan, context)
      → AutomationRequestBuilder (síncrono)
      → WorkflowPlanner (síncrono)
      → asyncio.create_task(run_execution(plan))  ← background
        → ExecutionMonitor.on_start()
          → persiste en DB: automation_execution (PENDING)
          → publica: ae.execution.started
        → TaskOrchestrator.execute()
          → por cada Task:
            → ExecutionMonitor.on_task_start()
              → persiste en DB: task_execution (RUNNING)
              → publica: ae.task.started
            → ejecutar handler (según TaskRegistry)
            → si éxito: ExecutionMonitor.on_task_complete()
              → persiste: task_execution (COMPLETED)
              → publica: ae.task.completed
            → si falla: retry según RetryPolicy
              → ExecutionMonitor.on_task_retry()
              → persiste: task_execution (RETRYING)
              → publica: ae.task.retrying
              → reintentar
            → si falla sin retry: ExecutionMonitor.on_task_failed()
              → persiste: task_execution (FAILED)
              → publica: ae.task.failed
        → ExecutionMonitor.on_complete()
          → persiste: automation_execution (COMPLETED/FAILED)
          → publica: ae.execution.completed / ae.execution.failed
  → [RETURN] BusinessDecision → CE responde al usuario
```

#### Criterio de cierre

- Persistencia completa en DB (D06-A3).
- Scheduler sobrevive restart.
- Observabilidad implementada (métricas + logging).
- Eventos `ae.*` publicados correctamente.
- VS1 sigue funcionando — el AE corre en background sin afectar la respuesta al usuario.
- pytest, ruff, black, mypy = 0 errores.

---

## 6. Riesgos

### R1 — Background task no sobrevive restart (D01-A3)

**Realidad:** `asyncio.create_task` no persiste. Si el proceso se reinicia mientras una automatización está en ejecución, esa ejecución se pierde.

**Mitigación:** Macro Block C introduce scheduler + persistencia en DB. Las tareas `delay` y ejecuciones en curso se registran en DB y pueden recuperarse al startup. Para Fase 1 (Macro Block B), se acepta la pérdida de ejecuciones en vuelo ante restart.

### R2 — Adaptador HTTP temporal se vuelve permanente (D03-A2)

**Realidad:** El adaptador HTTP del AE puede convertirse en la forma "oficial" de hacer integraciones, posponiendo indefinidamente la creación del Integration Engine.

**Mitigación:** El adaptador se implementa con una interfaz `TaskHandler` claramente marcada como `@deprecated`. Cuando ENG-005 exista, los handlers se migran y el adaptador se elimina. Incluir una issue/ticket en el repo recordando la deuda técnica.

### R3 — Contaminación del BB con lógica de Automation Engine

**Realidad:** Inyectar `AutomationService` en `BusinessBrainService` agrega otra dependencia al BB (D02-A1). El BB ya conoce KE; ahora también conoce AE.

**Mitigación:** `BusinessBrainService.process()` solo llama a `AutomationService.execute()` y no procesa el resultado. No hay lógica de automatización en el BB. Es una invocación de una línea. Esto es aceptable y consistente con el rol del BB como coordinador de lógica de negocio.

### R4 — El AE no tiene valor visible hasta Macro Block C

**Realidad:** Macro Block A solo define contratos e interfaces. Macro Block B ejecuta en background pero sin DB ni scheduler persistente. El valor real (automatización que sobrevive restart, programable, observable) solo llega en Macro Block C.

**Mitigación:** Comunicar claramente que el AE es un Engine de infraestructura. Su valor no es inmediatamente visible al usuario (como el KE), pero es crítico para la escalabilidad operativa. Los hitos de demostración deben planificarse para Block C.

### R5 — Complejidad de testing asíncrono

**Realidad:** El AE ejecuta tareas en background (`asyncio.create_task`). Los tests deben esperar a que la background task complete, usar timeouts, o mockear la ejecución.

**Mitigación:** 
- Tests unitarios: mockear `TaskOrchestrator` y `ExecutionMonitor` — probar solo la lógica de orquestación.
- Tests de integración: usar `asyncio.run()` con timeouts controlados.
- No introducir pytest-asyncio hasta que sea estrictamente necesario (Macro Block B).

---

## 7. Integraciones (según decisiones del CTO)

### 7.1 Con Business Brain (ENG-001)

| Aspecto | Detalle |
|---|---|
| **Contrato** | `AutomationService.execute(decision: BusinessDecision, plan: BusinessActionPlan, context: BusinessContext) → str (execution_id)` |
| **Punto de inyección** | `BusinessBrainService.process()`, línea ~135, después de generar `BusinessActionPlan` y publicar eventos (D02-A1) |
| **Tipo de llamada** | Síncrona, pero retorna inmediatamente. La ejecución real corre en background (D01-A3) |
| **Dependencia** | `AutomationService` se inyecta en `BusinessBrainService` como `automation_service: AutomationService \| None = None` |
| **Evento de retorno** | `ae.execution.completed` / `ae.execution.failed` — el BB puede consumirlo o ignorarlo |

### 7.2 Con Conversation Engine (ENG-002)

| Aspecto | Detalle |
|---|---|
| **Relación** | No directa. CE → BB → AE. El CE no conoce al AE. |
| **Eventos** | El AE publica eventos `ae.*`. El CE puede ignorarlos en Fase 1. En futuro, el CE podría consumir `ae.execution.completed` para notificar al usuario. |
| **Acción `respond`** | La tarea `respond` no modifica la respuesta ya enviada al usuario. Solo registra que la acción fue ejecutada. La respuesta conversacional la genera el CE antes de que el AE comience. |

### 7.3 Con Knowledge Engine (ENG-003)

| Aspecto | Detalle |
|---|---|
| **Relación** | No directa. El BB consulta al KE antes de generar el plan. El AE recibe el plan con `knowledge_content` ya resuelto. |
| **Acción `query_knowledge`** | Si aparece en el plan, el handler correspondiente verifica que el conocimiento ya fue consultado (en `BusinessDecision.knowledge_content`) y marca la tarea como completada sin ejecutar nada. |

### 7.4 Con Integration Engine (ENG-005)

| Aspecto | Detalle |
|---|---|
| **Relación** | El IE no existe. El AE usa adaptador HTTP temporal (D03-A2). |
| **Interfaz** | `HttpTaskHandler` implementa `TaskHandler`. Cuando el IE exista, los handlers se migran al IE. |
| **Acción `http_call`** | El `ActionPlanner` del BB no genera `http_call` hoy. Esta acción se reserva para uso futuro cuando el BB pueda planificar integraciones externas. El handler existe pero no se usa hasta que el BB o un workflow definition lo requiera. |

---

## 8. Producción

### 8.1 Modelo de ejecución

```
ConversationService.handle_message()
  → (síncrono) BB produce BusinessDecision + BusinessActionPlan
  → (síncrono) AutomationService.execute() → planning (rápido)
  → (síncrono) retorna execution_id
  → (síncrono) CE responde al usuario
  → (asíncrono) Background task ejecuta Automation pipeline
```

### 8.2 Scheduler

- **Fase 1 (Macro Block B):** `asyncio.sleep()` para delays. No sobrevive restart.
- **Fase 2 (Macro Block C):** Tareas `delay` persisten en `task_execision` con `status=scheduled` y `scheduled_at`. Al startup, el scheduler carga tareas pendientes y las ejecuta.

### 8.3 Background execution (D01-A3)

- **Mecanismo:** `asyncio.create_task()` dentro del event loop de FastAPI.
- **Riesgo:** No sobrevive restart del proceso.
- **Monitor:** El `ExecutionMonitor` actualiza el estado en DB. Si el proceso se cae, las ejecuciones quedan en `running`. Al startup, el servicio puede detectar ejecuciones huérfanas (running > 5 min sin update) y marcarlas como `failed`.

### 8.4 Persistencia (D06-A3)

| Tabla | Propósito |
|---|---|
| `automation_execution` | Estado actual de cada ejecución. Una fila por ejecución. |
| `task_execution` | Estado de cada tarea. Una fila por tarea por ejecución. |
| `business_event` (existente) | Eventos `ae.*` para trazabilidad histórica. |

### 8.5 Retry

- **Política por tarea:** `RetryPolicy(max_attempts=3, delay_seconds=1.0, backoff_multiplier=2.0)`.
- **Backoff:** 1s → 2s → 4s entre reintentos.
- **Límite global:** `TaskOrchestrator` tiene un `max_retry_seconds` global (ej: 300s) para evitar que una tarea reintente indefinidamente.
- **Registro:** Cada reintento se persiste como `TaskExecution(attempt=N, status=retrying)` y se publica `ae.task.retrying`.

### 8.6 Observabilidad

- **Logging estructurado:** Cada evento del pipeline se loggea con `structlog` (estándar del proyecto), incluyendo `execution_id`, `task_id`, `action`, `status`, `duration_ms`.
- **Métricas** (vía `AutomationObservability`):
  - `automation.executions.total` (counter)
  - `automation.executions.success_rate` (gauge)
  - `automation.executions.avg_duration_ms` (histogram)
  - `automation.tasks.by_action.{action}` (counter por tipo de tarea)
  - `automation.errors.total` (counter)
- **Health check:** Endpoint `GET /health` incluye estado del scheduler y ejecuciones stall.

---

## 9. Quality Gates

Para cerrar ENG-004, deben cumplirse:

| Gate | Criterio |
|---|---|
| **pytest** | Todos los tests pasando. VS1 (10 tests) sin cambios. Todos los nuevos tests del AE (estimado: ~99) pasando. |
| **ruff** | 0 errores en `app/` y `tests/` |
| **black --check** | 0 archivos reformateados |
| **mypy** | 0 errores en `app/` (strict mode) |
| **VS1** | 10/10 tests pasando sin modificación |
| **Cobertura de contracts** | Todos los objetos de dominio del AE testeados (frozen, defaults, types) |
| **Pipeline completo** | Test de integración que ejecuta el pipeline AE completo con `InMemoryTaskOrchestrator` e `InMemoryExecutionMonitor` |
| **Background execution** | Test que verifica que el AE corre en background y no bloquea el pipeline del BB |
| **Retry** | Test que verifica que una tarea fallida se reintenta según `RetryPolicy` |
| **Scheduling** | Test que verifica que una tarea `delay` se ejecuta después del tiempo especificado |
| **Eventos** | Test que verifica que cada evento `ae.*` se publica correctamente |
| **Persistencia** | Test que verifica que el estado de ejecución se persiste y puede recuperarse |

### Cobertura de tests estimada por Macro Block

| Macro Block | Tests nuevos | Archivos de test |
|---|---|---|
| A — Foundation | ~30 | `test_automation_contracts.py`, `test_automation_request_builder.py`, `test_automation_workflow_planner.py`, `test_automation_service.py` |
| B — Core Orchestration | ~40 | `test_automation_task_orchestrator.py`, `test_automation_execution_monitor.py`, `test_automation_task_registry.py`, `test_automation_http_handler.py` (ampliaciones) |
| C — Production Readiness | ~29 | `test_automation_repositories.py`, `test_automation_db.py`, `test_automation_scheduler.py`, `test_automation_observability.py` |
| **Total** | **~99** | |

---

## Resumen de archivos a crear

| Archivo | Macro Block |
|---|---|
| `app/domain/automation/__init__.py` | A |
| `app/domain/automation/contracts.py` | A |
| `app/core/automation/__init__.py` | A |
| `app/core/automation/request_builder.py` | A |
| `app/core/automation/workflow_planner.py` | A |
| `app/core/automation/task_orchestrator.py` | A (interfaz) + B (impl) |
| `app/core/automation/execution_monitor.py` | A (interfaz) + B (impl) + C (DB) |
| `app/core/automation/service.py` | A |
| `app/core/automation/task_registry.py` | B |
| `app/core/automation/adapters/http_task_handler.py` | B |
| `app/core/automation/scheduler.py` | C |
| `app/core/automation/observability.py` | C |
| `app/infrastructure/models/automation_execution.py` | C |
| `app/infrastructure/repositories/automation_repository.py` | C |
| `alembic/versions/20260723_0001_create_automation_tables.py` | C |
| `tests/test_automation_contracts.py` | A |
| `tests/test_automation_request_builder.py` | A |
| `tests/test_automation_workflow_planner.py` | A |
| `tests/test_automation_service.py` | A (extendido en B) |
| `tests/test_automation_task_orchestrator.py` | B |
| `tests/test_automation_execution_monitor.py` | B |
| `tests/test_automation_task_registry.py` | B |
| `tests/test_automation_http_handler.py` | B |
| `tests/test_automation_repositories.py` | C |
| `tests/test_automation_db.py` | C |
| `tests/test_automation_scheduler.py` | C |
| `tests/test_automation_observability.py` | C |

## Archivos a modificar

| Archivo | Macro Block | Cambio |
|---|---|---|
| `app/core/business/service.py` | A | Inyectar `AutomationService`, invocar `execute()` después de `action_planner.plan()` |
| `app/api/dependencies.py` | A | Wire AutomationService + dependencias |
| `app/infrastructure/models/__init__.py` | C | Import AutomationExecutionModel, TaskExecutionModel |
| `alembic/env.py` | C | Import nuevos modelos |

---

*Este plan está basado en D-011 (8 capítulos), ADR-004, ADR-005, ADR-006, ADR-008, ADR-009, CONTEXT_FOR_AI.md, ENG004_DOMAIN_ANALYSIS.md, ENG004_CTO_DECISIONS.md y el código actual del proyecto. No incluye código de implementación. Las 7 decisiones del CTO son vinculantes.*
