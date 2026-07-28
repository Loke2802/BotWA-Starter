# B7 — Event Publisher (Formalizar)

## Responsabilidad

Transformar el estado completo del pipeline (`BusinessContext`, `BusinessIntent`, `BusinessConstraints`, `BusinessDecision`, `BusinessActionPlan`) en una lista determinística de `BusinessEvent` del dominio. El pipeline **finaliza** publicando estos eventos, cumpliendo la regla del blueprint D-008-09: *"Todo Decision Pipeline finaliza publicando uno o más Business Events"*.

El Event Publisher no ejecuta acciones, no modifica decisiones, no interactúa con el Conversation Engine.

## Entrada

- `context: BusinessContext`
- `business_intent: BusinessIntent`
- `constraints: BusinessConstraints`
- `decision: BusinessDecision`
- `action_plan: BusinessActionPlan`

## Salida

- `list[BusinessEvent]` — lista inmutable de eventos de dominio, ya persistidos

## Eventos producidos por intent

Cada ejecución del pipeline produce **3 eventos base** + **1 evento condicional** (knowledge):

| Orden | Event Type | Payload | Siempre |
|---|---|---|---|
| 1 | `business_intent.detected` | `{intent, status, is_feasible}` | ✓ |
| 2 | `business_decision.made` | `{intent, status, confidence, is_feasible}` | ✓ |
| 3 | `business_action.plan` | `{intent, steps: [{action, target, order}]}` | ✓ |
| 4 (cond) | `knowledge.queried` | `{intent, found: bool, content_length: int}` | Solo si `decision.needs_knowledge=true` |

### Matriz por intent

| Intent | Status | Events |
|---|---|---|
| `greeting` | accepted | intent.detected, decision.made, action.plan |
| `farewell` | accepted | intent.detected, decision.made, action.plan |
| `thanks` | accepted | intent.detected, decision.made, action.plan |
| `price_inquiry` (con knowledge) | accepted | intent.detected, decision.made, **knowledge.queried(found)** , action.plan |
| `price_inquiry` (sin knowledge) | accepted | intent.detected, decision.made, **knowledge.queried(not_found)** , action.plan |
| `support` (con knowledge) | accepted | intent.detected, decision.made, **knowledge.queried(found)** , action.plan |
| `support` (sin knowledge) | accepted | intent.detected, decision.made, **knowledge.queried(not_found)** , action.plan |
| `question` (con knowledge) | accepted | intent.detected, decision.made, **knowledge.queried(found)** , action.plan |
| `question` (sin knowledge) | accepted | intent.detected, decision.made, **knowledge.queried(not_found)** , action.plan |
| `unknown` | rejected | intent.detected, decision.made(status=rejected), action.plan(escalate) |

**Todas las reglas son determinísticas.** No hay variabilidad por confianza o score.

## Integración en el pipeline

```
ContextInterpreter
↓
IntentClassifier
↓
RuleEvaluator
↓
DecisionMaker
↓
ConfidenceEvaluator
↓
BusinessDecision
↓
KnowledgeService (si necesita)
↓
ActionPlanner
↓
BusinessActionPlan
↓
EventPublisher.publish_events(...) → list[BusinessEvent]  ← NUEVO
↓
return BusinessDecision  (contrato CE↔BB intacto)
```

Los eventos intermedios actuales (`objetivo_identificado`, `reglas_evaluadas`, `consulta_conocimiento`, `conocimiento_encontrado`, `conocimiento_no_encontrado`, `plan_generado`, `respuesta_generada`) se mantienen como side-effect logging vía `structlog`. No se eliminan para mantener compatibilidad, pero dejan de ser el mecanismo formal de publicación.

## Archivos nuevos

### `tests/test_event_publisher.py`

Test unitario del nuevo método `publish_events()`:

| Test | Intent | Status | Events esperados |
|---|---|---|---|
| `test_publish_greeting` | greeting | accepted | 3 eventos: intent.detected, decision.made, action.plan |
| `test_publish_price_inquiry_with_knowledge` | price_inquiry | accepted | 4 eventos: + knowledge.queried(found) |
| `test_publish_price_inquiry_without_knowledge` | price_inquiry | accepted | 4 eventos: + knowledge.queried(not_found) |
| `test_publish_unknown_rejected` | unknown | rejected | 3 eventos: decision.made status=rejected |
| `test_publish_events_have_conversation_id` | greeting | accepted | Todos los eventos tienen conversation_id |
| `test_publish_events_are_frozen` | greeting | accepted | BusinessEvent es frozen (inmutable) |

## Archivos modificados

### `app/core/business/event_publisher.py`

Agregar nuevo método:

```python
def publish_events(
    self,
    context: BusinessContext,
    business_intent: BusinessIntent,
    constraints: BusinessConstraints,
    decision: BusinessDecision,
    action_plan: BusinessActionPlan,
) -> list[BusinessEvent]:
```

- Construye lista de `BusinessEvent` según matriz de eventos
- Cada evento incluye `conversation_id` desde `context.request.conversation_id`
- Persiste cada evento vía `event_repo` si está disponible
- Conserva el método `publish(event_type, **kwargs)` existente para logging intermedio

### `app/core/business/service.py` — `BusinessBrainService`

1. Agregar `self._last_events: list[BusinessEvent] | None = None`
2. Después de la llamada a `ActionPlanner` (línea ~133), invocar:

```python
if self._event_publisher is not None:
    self._last_events = self._event_publisher.publish_events(
        context, business_intent, constraints, decision, self._last_action_plan,
    )
```

3. El `_publish()` intermedio se mantiene como está (structlog logging + persistencia legacy)

### `tests/test_business_brain_service.py`

| Test existente | Cambio |
|---|---|
| `test_business_brain_stores_constraints` | Agregar `assert service._last_events is not None` |
| Nuevo: `test_business_brain_greeting_produces_events` | greeting → 3 eventos publicados |
| Nuevo: `test_business_brain_unknown_produces_rejected_event` | unknown rejected → event status=rejected |
| Nuevo: `test_business_brain_price_inquiry_produces_knowledge_event` | price_inquiry → knowledge.queried presente |

## Contratos afectados

**Ninguno.** `BusinessEvent` ya existe como contrato de dominio desde B1. El contrato CE↔BB (`BusinessDecision`) no se modifica.

## Dependencias

- `app/core/business/event_publisher.py` → `app/domain/business/contracts.py` (BusinessEvent, etc.)
- `app/core/business/service.py` → `app/core/business/event_publisher.py` (ya existe)
- `app/infrastructure/repositories/business_event_repository.py` → persistencia (ya existe)

## Compatibilidad

### Conversation Engine
Sin impacto. El CE recibe `BusinessDecision` como siempre. Los eventos son internos del BB.

### Knowledge Engine
Sin impacto. La consulta a KE ocurre antes de EventPublisher. El resultado (found/not found) se refleja en el evento `knowledge.queried`.

### VS1
Sin cambios. VS1 verifica `BusinessDecision` y respuestas HTTP. Los eventos son un detalle interno. Todos los tests VS1 existentes siguen pasando sin modificación.

## Resolución de errores mypy pre-existentes

Dos errores mypy heredados deben corregirse para cerrar el Engine con 0 errores:

### Error 1: `tests/test_business_contracts.py:145`

```python
intent.name = "question"  # mypy: Property "name" is read-only
```

El test verifica que `BusinessIntent` es frozen. mypy detecta que la propiedad es de solo lectura. **Solución**: agregar `# type: ignore[attr-defined]` en la línea 145.

### Error 2: `tests/test_business_brain_service.py:109`

```python
assert "horario" in decision.knowledge_content.lower()
# mypy: Item "None" of "str | None" has no attribute "lower"
```

`knowledge_content` puede ser `None` según el tipo. **Solución**: cambiar a:

```python
assert decision.knowledge_content is not None
assert "horario" in decision.knowledge_content.lower()
```

## Riesgos

| Riesgo | Mitigación |
|---|---|
| Duplicación de eventos entre `_publish()` legacy y `publish_events()` nuevo | `_publish()` legacy usa `**kwargs` y no produce `BusinessEvent` de dominio. No hay duplicación conceptual. La persistencia en DB ocurre SOLO en `publish_events()`. |
| EventPublisher falle silenciosamente si no hay repositorio | El método `publish_events()` debe retornar los eventos incluso sin repo (modo in-memory). Ya existe patrón similar en `_publish()`. |
| knowledge.queried event exponga contenido completo del knowledge | El payload de `knowledge.queried` solo incluye `content_length: int`, no el contenido textual. |
| Regresión en tests existentes al modificar `event_publisher.py` | El método `publish()` legacy no se modifica. Solo se agrega `publish_events()`. Tests existentes no se rompen. |

## Lo que NO se hace en B7

- No se modifica el contrato `BusinessDecision`
- No se elimina el método `publish()` legacy
- No se toca el Conversation Engine
- No se tocan Blueprints/ADRs
- No se adelanta funcionalidad futura (B7 es el último incremento del BB)

## Calidad esperada

| Gate | Objetivo |
|---|---|
| `pytest` | 200+ passed (190 actual + ~10 nuevos) |
| `ruff` | 0 errors |
| `black --check` | 0 files reformatted |
| `mypy` | 0 errors (99 source files) — se corrigen los 2 pre-existentes |
| VS1 | 10/10 sin cambios |
