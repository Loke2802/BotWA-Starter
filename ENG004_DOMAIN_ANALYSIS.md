# ENG-004 — Automation Engine: Domain Analysis

**Proyecto:** BotWA Starter  
**Documento:** Domain Analysis previo a definición de Macro Blocks  
**Versión:** 1.0  
**Fuentes:** D-011 (8 capítulos), ADR-004, ADR-005, ADR-006, ADR-007, ADR-008, ADR-009, CONTEXT_FOR_AI.md, código actual

---

## 1. Responsabilidad del Engine

### 1.1 ¿Qué problema resuelve?

BotWA tiene un Business Brain que **decide qué debe hacerse**, pero no implementa mecanismos para **ejecutar procesos que requieren más de una acción**, involucran asincronía, dependencias entre pasos, reintentos, programación futura, o coordinación de workflows multi-paso.

El Automation Engine resuelve:

- **Ejecución multi-acción:** convertir `BusinessActionPlan` (lista plana de `ActionStep`) en un execution plan concreto, ejecutable y trazable.
- **Orquestación de procesos:** ejecutar secuencias de tareas con dependencias, paralelismo y condiciones.
- **Resiliencia operativa:** reintentar operaciones fallidas, manejar timeouts, gestionar delays programados.
- **Trazabilidad de ejecución:** registrar cada paso, cada error, cada reintento.
- **Desacople decisión-ejecución:** el BB decide el *qué*; el AE decide el *cómo* de la ejecución.
- **Eventualidad:** el pipeline del BB es síncrono; el AE debe soportar ejecución diferida y asincrónica.

### 1.2 ¿Qué NO debe hacer?

Según D-011-01, D-011-08 y ADR-008:

- **No tomar decisiones de negocio.** Eso pertenece al Business Brain (ENG-001).
- **No interpretar conversaciones.** Eso pertenece al Conversation Engine (ENG-002).
- **No comunicarse con el cliente.** Eso pertenece al CE.
- **No consultar conocimiento empresarial.** Eso pertenece al Knowledge Engine (ENG-003).
- **No aplicar reglas de negocio.** Eso pertenece al BB.
- **No acceder directamente a sistemas externos.** Eso pertenece al Integration Engine (ENG-005, Fase 4).
- **No modificar el contrato CE↔BB** (`BusinessDecisionRequest` → `BusinessDecision`).
- **No crear nuevos objetos de dominio que otros Engines deban modificar** (ADR-005).
- **No fusionar lógica de integración con lógica de automatización.**

### 1.3 Frontera BB ↔ AE

| Actividad | Engine |
|---|---|
| Clasificar intención del mensaje | BB |
| Evaluar reglas de negocio | BB |
| Decidir acción | BB |
| Planificar acciones (qué hacer) | BB (`ActionPlanner`) |
| **Ejecutar el plan (cómo hacerlo)** | **AE** |
| Consultar conocimiento | KE (invocado por BB) |
| Publicar eventos de negocio | BB (`BusinessEventPublisher`) |
| Comunicar respuesta al cliente | CE (`ResponseComposer`) |
| Integrar con sistemas externos | Integration Engine |

**Punto de integración crítico:** El `BusinessActionPlan` actual del BB produce `ActionStep` planos con campos `action`, `target`, `parameters`, `order`. El AE debe consumir este `BusinessActionPlan` y convertirlo en un `AutomationRequest`.

---

## 2. Objetos de dominio

Extraídos directamente del Blueprint D-011. Se listan los objetos que necesita el Engine, no necesariamente todos son contratos públicos.

| # | Objeto | Descripción | Propietario |
|---|---|---|---|
| 1 | **AutomationRequest** | Solicitud de automatización generada por el *Automation Request Builder* a partir de una `BusinessDecision` + `BusinessActionPlan`. Contiene la intención, las acciones planificadas, el contexto de negocio, las políticas de retry y scheduling. | AE |
| 2 | **ExecutionPlan** | Plan de ejecución estructurado generado por el *Workflow Planner*. Define tareas individuales, orden (secuencial/paralelo), dependencias entre tareas, políticas de reintento por tarea, condiciones de finalización. Es la versión ejecutable del `BusinessActionPlan`. | AE |
| 3 | **Task** | Unidad atómica de ejecución dentro del `ExecutionPlan`. Representa una operación individual (responder, consultar API, enviar notificación, etc.). Contiene: `task_id`, `action`, `target`, `parameters`, `retry_policy`, `dependencies`, `status`. | AE |
| 4 | **ExecutionStatus** | Estado de una ejecución en curso. Contiene: `execution_id`, `plan_id`, `current_task`, `overall_status` (pending/running/completed/failed/cancelled), `task_statuses`, `started_at`, `updated_at`, `error_count`. | AE |
| 5 | **AutomationResult** | Resultado final de una ejecución. Contiene: `execution_id`, `overall_status`, `completed_tasks`, `failed_tasks`, `errors`, `duration_ms`, `result_data`. | AE |
| 6 | **BusinessEvent** | Evento publicado al finalizar o durante la ejecución. No es propiedad exclusiva del AE — BB ya publica eventos (`BusinessEventPublisher`). El AE publica eventos *operativos* propios de la ejecución. | AE + BB |

**Objetos existentes en el código que el AE debe consumir:**

| Objeto | Fuente | Propósito en AE |
|---|---|---|
| `BusinessDecision` | `app/domain/business/contracts.py` | Entrada del pipeline AE (vía `AutomationRequestBuilder`) |
| `BusinessActionPlan` | `app/domain/business/contracts.py` | Contiene `steps: list[ActionStep]` → se transforma en `ExecutionPlan` |
| `ActionStep` | `app/domain/business/contracts.py` | Cada step se mapea a una `Task` |
| `BusinessContext` | `app/domain/business/contracts.py` | Contexto de negocio de la solicitud original |
| `BusinessEvent` | `app/domain/business/contracts.py` | Publicado por AE como resultado de ejecución |

### 2.1 Observations on domain objects

- `BusinessActionPlan` actualmente contiene solo una lista plana de `ActionStep` con `order`. No expresa dependencias complejas, paralelismo, ni condiciones de ejecución. El AE debe enriquecer esta semántica en su `ExecutionPlan`.
- No existe actualmente un contrato `AutomationRequest` ni `ExecutionPlan` en el codebase. Son enteramente por crear.
- `ExecutionStatus` y `AutomationResult` no existen. Son nuevos.
- `BusinessEvent` ya existe y es publicado por el BB. El AE debe publicar sus propios eventos de dominio de ejecución.

---

## 3. Pipeline conceptual

```
Business Brain (ENG-001)
│
│   BusinessDecision + BusinessActionPlan
│   (decide qué hacer + acciones planificadas)
│
▼
┌─────────────────────────────────────────────────┐
│            AUTOMATION ENGINE                    │
│                                                 │
│  1. Automation Request Builder                  │
│     BusinessDecision + BusinessActionPlan       │
│     + BusinessContext                           │
│     → AutomationRequest (contrato interno)      │
│                                                 │
│  2. Workflow Planner                            │
│     AutomationRequest                           │
│     → Execution Plan                            │
│     (tasks, orden, dependencias, retry policy)  │
│                                                 │
│  3. Task Orchestrator                           │
│     Execution Plan                              │
│     → Execution Status (en vivo)                │
│     (coordina ejecución secuencial/paralela,    │
│      maneja dependencias, detecta bloqueos,     │
│      ejecuta reintentos)                        │
│                                                 │
│  4. Execution Monitor                           │
│     Execution Status                            │
│     → Automation Result                         │
│     → Business Event                            │
│     (registra todo, detecta errores,            │
│      publica resultado, cierra execution)       │
│                                                 │
└─────────────────────────────────────────────────┘
│
▼
Business Event → Conversation Engine / Integration Engine / Log
```

### 3.1 Flujo completo (desde mensaje hasta automatización ejecutada)

```
Usuario envía mensaje
  → CE: Message Receiver → Context Builder → Topic Detector → State Manager
    → Router → Business Request
      → BB: Intent Classifier → Rule Evaluator → Decision Maker
        → Confidence Evaluator → Action Planner (BusinessActionPlan)
          → Event Publisher → Business Decision
            → CE: Response Composer → Channel Adapter → Response
              → AE: Automation Request Builder
                → Workflow Planner
                  → Task Orchestrator
                    → Execution Monitor → Business Event
```

**Nota:** El flujo actual del BB es **síncrono**. La llamada al AE debe ocurrir después de que el CE entrega la respuesta al usuario (o en paralelo), porque:
- Las automatizaciones pueden ser asincrónicas (programar envío, consultar API externa).
- El usuario no debe esperar a que termine una automatización para recibir su respuesta conversacional.

---

## 4. Integraciones

### 4.1 Con Conversation Engine (ENG-002)

| Dirección | Contrato | Cuándo |
|---|---|---|
| CE → AE | No directo. CE llama a BB, BB genera `BusinessActionPlan`, AE consume. | El CE no invoca al AE. El AE recibe el plan del BB. |
| AE → CE | `BusinessEvent` con resultado de ejecución. El CE no lo consume hoy; puede consumirlo en futuro (ej: notificar estado al usuario). | Post-ejecución asincrónica. |

**Observación:** Actualmente no hay integración directa CE↔AE ni está prevista en el blueprint. El CE se comunica con el BB; el BB se comunica con el AE vía contrato. El AE publica eventos que el CE podría consumir opcionalmente.

### 4.2 Con Business Brain (ENG-001)

| Dirección | Contrato | Cuándo |
|---|---|---|
| BB → AE | `BusinessDecision` + `BusinessActionPlan` + `BusinessContext` | Después de que BB genera `BusinessDecision` y `BusinessActionPlan` (línea 134 de `service.py`) |
| AE → BB | `BusinessEvent` | Fin de ejecución |

**Observación:** El punto de inyección ideal es después de `self._last_action_plan = self._action_planner.plan(...)` y `self._last_events = self._event_publisher.publish_events(...)` en `BusinessBrainService.process()`, o bien desde el `ConversationService` después de recibir la `BusinessDecision`.

**Riesgo de acoplamiento temporal:** Si el AE se invoca sincrónicamente dentro del pipeline del BB, el tiempo de respuesta al usuario se degrada. El AE debería ejecutarse asincrónicamente (background task, cola, o schedule).

### 4.3 Con Knowledge Engine (ENG-003)

Sin integración directa. El AE no consulta conocimiento. Si una tarea del execution plan requiere conocimiento, debe ser resuelta por el BB antes de generar el plan, o por el Integration Engine si es una fuente externa.

### 4.4 Con Integration Engine (ENG-005)

| Dirección | Contrato | Cuándo |
|---|---|---|
| AE → IE | Llamada a integración externa (API, notificación, CRM) | Cuando un `Task.target` requiere integración externa |
| IE → AE | Resultado de integración (éxito/fracaso/datos) | Síncrono o asincrónico |

**Observación:** El Integration Engine (ENG-005) está en Fase 4, debe implementarse después del AE. Mientras no exista, el AE necesitará un adaptador provisional (ej: HTTP client directo) o saltar tareas que requieran integración externa.

---

## 5. Eventos

### 5.1 Eventos que consume

| Evento | Fuente | Contrato |
|---|---|---|
| Business Decision | BB (ENG-001) | `BusinessDecision` |
| Business Action Plan | BB (ENG-001) | `BusinessActionPlan` |

No consume eventos del CE ni del KE directamente.

### 5.2 Eventos que publica

Basado en D-011-07 (Execution Monitor) y D-011-08:

| Evento | Tipo | Propósito |
|---|---|---|
| `automation.started` | `BusinessEvent` | Se inicia la ejecución de un `ExecutionPlan` |
| `automation.task_completed` | `BusinessEvent` | Una `Task` individual se completa |
| `automation.task_failed` | `BusinessEvent` | Una `Task` falla (incluye información de retry) |
| `automation.completed` | `BusinessEvent` | El `ExecutionPlan` completo termina exitosamente |
| `automation.failed` | `BusinessEvent` | El `ExecutionPlan` completo falla |
| `automation.cancelled` | `BusinessEvent` | La ejecución es cancelada |

Formato de publicación: `BusinessEvent.event_type`, `BusinessEvent.source="automation_engine"`, `BusinessEvent.payload` con datos de ejecución.

### 5.3 Eventos del BB que el AE podría reutilizar

El BB ya publica eventos como `objetivo_identificado`, `reglas_evaluadas`, `plan_generado`, `respuesta_generada` (en `BusinessEventPublisher.publish()`). El AE puede consumir estos eventos para trazabilidad, pero no debe depender de ellos para su pipeline.

---

## 6. Estado actual: Blueprint vs código

### 6.1 Automation Request Builder
| Aspecto | Blueprint | Código actual | Brecha |
|---|---|---|---|
| Automatización de entrada | `BusinessDecision` + `BusinessActionPlan` + `BusinessContext` | No existe | **Ausente.** No hay componente que transforme una decisión en automation request. |
| Objeto `AutomationRequest` | Definido en D-011-04 | No existe en `app/domain/automation/` (ni existe el package) | **Ausente.** |
| Validaciones | Decision válida, plan disponible, info mínima, consistencia de contrato | No implementado | **Ausente.** |

### 6.2 Workflow Planner
| Aspecto | Blueprint | Código actual | Brecha |
|---|---|---|---|
| Entrada | `AutomationRequest` | No existe | **Ausente.** |
| Salida | `ExecutionPlan` (tareas, orden, dependencias, políticas de reintento, condiciones de finalización) | No existe | **Ausente.** |
| Separación planificación/ejecución | Planificación no ejecuta | No aplica | N/A. |

### 6.3 Task Orchestrator
| Aspecto | Blueprint | Código actual | Brecha |
|---|---|---|---|
| Responsabilidad | Coordinar ejecución del plan | No existe | **Ausente.** |
| Gestión de dependencias | Debe respetar orden y paralelismo | No existe | **Ausente.** |
| Detección de bloqueos | Debe detectar deadlocks o tareas stalled | No existe | **Ausente.** |

### 6.4 Execution Monitor
| Aspecto | Blueprint | Código actual | Brecha |
|---|---|---|---|
| Registro de inicio/progreso/fin | Debe registrar todo | No existe | **Ausente.** |
| Detección de errores | Sí | No existe | **Ausente.** |
| Publicación de resultado | `AutomationResult` + `BusinessEvent` | No existe | **Ausente.** |

### 6.5 Componentes existentes que son tangentes

| Componente | Pertenece a | Relación con AE |
|---|---|---|
| `BusinessEventPublisher` | BB (`app/core/business/event_publisher.py`) | Publica eventos de negocio. El AE debería publicar eventos similares pero con `source="automation_engine"`. Podría compartir la clase o usar la misma interfaz. |
| `BusinessActionPlan` + `ActionStep` | BB (`app/domain/business/contracts.py`) | Es la entrada del AE. `ActionStep` tiene `action`, `target`, `parameters`, `order`. Suficiente para actions simples pero no expresa dependencias complejas. |
| `ConversationService` | CE (`app/core/conversation/service.py`) | Es quien orquesta el pipeline completo. Aquí es donde se debería invocar al AE después de la respuesta. |

### 6.6 Resumen de brechas

| Componente | Estado |
|---|---|
| `AutomationRequest` (objeto) | **Ausente** — crear `app/domain/automation/` |
| `ExecutionPlan` (objeto) | **Ausente** — nuevo objeto de dominio |
| `Task` (objeto) | **Ausente** — nuevo objeto de dominio |
| `ExecutionStatus` (objeto) | **Ausente** — nuevo objeto de dominio |
| `AutomationResult` (objeto) | **Ausente** — nuevo objeto de dominio |
| Automation Request Builder | **Ausente** — nuevo componente core |
| Workflow Planner | **Ausente** — nuevo componente core |
| Task Orchestrator | **Ausente** — nuevo componente core |
| Execution Monitor | **Ausente** — nuevo componente core |
| Pipelines de Automation Engine | **Ausente** — nuevo pipeline |
| Eventos de automation | **Ausente** — nuevos tipos de evento |
| Persistencia de ejecuciones | **Ausente** — ORM/repositorios por crear |

**Conclusión:** Todo el Automation Engine está por construir. No hay código legacy que migrar. Es una pizarra en blanco.

---

## 7. Riesgos de diseño

### R1 — Acoplamiento síncrono BB → AE

**Problema:** Si el AE se invoca dentro del pipeline síncrono del `BusinessBrainService.process()`, el tiempo de respuesta del CE se degrada con el tiempo de ejecución de la automatización.

**Naturaleza:** Arquitectónico. El pipeline actual del BB es síncrono. El AE es inherentemente asincrónico (retry, scheduling, paralelismo).

**Impacto:** Degradación de UX (el usuario espera la respuesta mientras se ejecuta la automatización). Imposibilidad de ejecutar tareas programadas.

**Posible dirección:** El AE debe ejecutarse como un proceso desacoplado (cola de tareas, event-driven, background task) después de que el CE haya respondido al usuario.

### R2 — Contrato BusinessActionPlan insuficiente

**Problema:** `BusinessActionPlan` actualmente expresa solo `steps: list[ActionStep]` con `order`. No contempla:
- Dependencias entre pasos (más allá del orden lineal).
- Paralelismo.
- Ejecución condicional ("si falla, haz X").
- Políticas de retry por step.
- Timeout por step.
- Datos de contexto para la ejecución.

**Naturaleza:** Semántico. El plan que produce el BB es deliberadamente simple (solo responde o consulta conocimiento). Pero el AE necesita más semántica para ejecutar procesos complejos.

**Impacto:** El AE necesitará enriquecer el plan, posiblemente con configuraciones externas (workflow definitions, policies).

**Posible dirección:** Definir un `WorkflowDefinition` externo al BB que el AE consulte para enriquecer el plan, o evolucionar `BusinessActionPlan` para incluir metadata de ejecución. Considerar que modificar `BusinessActionPlan` (contrato del BB) requiere coordinación.

### R3 — Dependencia del Integration Engine

**Problema:** El blueprint dice que el AE no debe acceder directamente a sistemas externos. Pero el Integration Engine (ENG-005) está en Fase 4 y no existe.

**Naturaleza:** Dependencia externa. El AE necesita ejecutar tareas que probablemente requieran integraciones (enviar email, actualizar CRM, notificar a Slack).

**Impacto:** El AE no podrá ejecutar tareas con `target` externo hasta que exista el IE. Bloquea casos de uso reales.

**Posible dirección:** Implementar inicialmente solo las tareas que el AE puede ejecutar internamente (responder al CE, loguear, actualizar estado). Para tareas externas, crear un adaptador HTTP mínimo temporal hasta que el IE esté listo. Esta decisión debe quedar explícita.

### R4 — Ausencia de infraestructura asincrónica

**Problema:** Actualmente BotWA no tiene cola de mensajes, scheduler, task queue, ni event bus. El AE necesita al menos una de estas capacidades para ejecución asincrónica.

**Naturaleza:** Infraestructural. No existe mecanismo para "ejecutar esto más tarde" o "reintentar en 5 minutos".

**Impacto:** Sin infraestructura asincrónica, el AE solo puede ejecutar workflows estrictamente síncronos, lo que limita severamente su utilidad.

**Posible dirección:** Evaluar si se introduce una cola ligera (Redis queue, SQL-based job queue, o APScheduler) como dependencia del AE, o si se limita la primera versión a ejecución síncrona dentro del pipeline del BB.

### R5 — Eventos duplicados o inconsistentes

**Problema:** El BB ya publica eventos de negocio (`BusinessEventPublisher`). El AE también publicará eventos. Si ambos publican sobre la misma ejecución, puede haber duplicación, naming inconsistente, o confusión sobre la fuente de verdad.

**Naturaleza:** De coordinación. Dos engines publicando eventos similares sin coordinación.

**Impacto:** Dificultad para trazabilidad y auditoría.

**Posible dirección:** Definir claramente qué eventos publica cada Engine, con prefijos (`bb.*`, `ae.*`) y un `source` field obligatorio. El `BusinessEvent.source` actual permite esto.

### R6 — Testing de flujos asincrónicos

**Problema:** Los tests actuales de BotWA son síncronos (pytest estándar). Si el AE introduce asincronía, los tests se vuelven más complejos (timeouts, polling, mocks de cola).

**Naturaleza:** De testing y calidad.

**Impacto:** Mayor esfuerzo de testing. Riesgo de regresiones no detectadas.

**Posible dirección:** Mantener la primera versión del AE síncrona pero diseñada para ser fácilmente adaptada a asincronía (patrón Command/Handler, con interfaces intercambiables). Aplazar testing async hasta que la infraestructura esté decidida.

---

## 8. Resumen de hallazgos

### Verde (sin riesgo, claro)
- Responsabilidad del AE está bien definida en D-011 y ADR-008.
- Frontera BB↔AE es clara: `BusinessDecision` + `BusinessActionPlan` → `AutomationResult` + `BusinessEvent`.
- El AE no toca conversación, conocimiento, ni reglas de negocio.
- Publicación de eventos es un mecanismo conocido y ya implementado en el BB.

### Amarillo (requiere decisión de diseño)
- R1: ¿El AE se ejecuta síncrono o asíncrono? Dirección recomendada: asíncrono, pero primera versión síncrona con diseño desacoplado.
- R2: ¿Se enriquece `BusinessActionPlan` o se definen `WorkflowDefinition` externos? Dirección recomendada: `WorkflowDefinition` externo para no acoplar BB.
- R5: Esquema de naming de eventos entre BB y AE.
- R6: Estrategia de testing para flujos asincrónicos.

### Rojo (requiere resolver antes de implementar)
- R3: El Integration Engine no existe. ¿Qué hacemos con tareas que requieren integración externa?
- R4: No hay infraestructura asincrónica. ¿Introducimos cola/scheduler o limitamos alcance?

---

## 9. Domain packages necesarios

Basado en la estructura actual del proyecto:

```
app/domain/automation/         (nuevo — objetos de dominio del AE)
    __init__.py
    contracts.py                → AutomationRequest, ExecutionPlan, Task,
                                  ExecutionStatus, AutomationResult
app/core/automation/           (nuevo — lógica del AE)
    __init__.py
    request_builder.py          → AutomationRequestBuilder
    workflow_planner.py         → WorkflowPlanner
    task_orchestrator.py        → TaskOrchestrator
    execution_monitor.py        → ExecutionMonitor
    service.py                  → AutomationService (orquestador del pipeline)
app/infrastructure/models/     (nuevos modelos ORM)
    automation_execution.py     → ExecutionModel, TaskExecutionModel
    automation_event.py         → (opcional, reutiliza BusinessEventModel)
app/infrastructure/repositories/
    automation_repository.py    → (persistencia de ejecuciones)
```

Nota: Estos son solo los paquetes necesarios. No constituyen una propuesta de Macro Blocks.

---

## 10. Preguntas abiertas para el CTO

1. **Sincronía:** ¿La primera versión del AE debe ser síncrona (ejecutar dentro del pipeline BB) o asíncrona (cola/task queue)?
2. **Integration Engine:** ¿Cómo manejamos tareas externas sin IE? ¿Skip, stub, HTTP directo temporal?
3. **Workflow definitions:** ¿Las definiciones de workflow deben ser configurables externamente (YAML/JSON) o el Workflow Planner debe ser 100% programático?
4. **Alcance Fase 1:** ¿Qué tipos de tareas debe soportar la primera versión? ¿Solo las que ya genera el `ActionPlanner` (respond, query_knowledge, escalate)?
5. **Persistencia:** ¿Cada ejecución debe persistirse en DB o el log de eventos es suficiente para trazabilidad?

---

*Este análisis fue elaborado a partir de los documentos D-011 (8 capítulos), ADR-004, ADR-005, ADR-006, ADR-007, ADR-008, ADR-009, CONTEXT_FOR_AI.md, y el código actual del proyecto. No incluye propuestas de implementación ni división en Macro Blocks.*
