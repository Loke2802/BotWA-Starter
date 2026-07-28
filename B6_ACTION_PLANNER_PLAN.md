# B6 — Action Planner

## Responsabilidad

Transformar `BusinessDecision` (ya enriquecida con `BusinessContext`, `BusinessIntent`, `BusinessConstraints`, y opcionalmente `knowledge_content`) en un `BusinessActionPlan` que describe **qué pasos debe ejecutar el sistema** para materializar la decisión.

El Action Planner **no ejecuta acciones**. Solo organiza tareas secuenciales con su target y parámetros.

## Entrada

- `context: BusinessContext`
- `business_intent: BusinessIntent`
- `constraints: BusinessConstraints`
- `decision: BusinessDecision` (después de knowledge query)

## Salida

- `BusinessActionPlan` con una lista de `ActionStep` ordenados

## Reglas de generación de pasos (`plan()`)

| Intent | Condición | Steps generados |
|---|---|---|
| `greeting` / `farewell` / `thanks` | Siempre | `[respond(intent)]` |
| `price_inquiry` | `decision.needs_knowledge` y `decision.knowledge_content` presente | `[respond(intent)]` |
| `price_inquiry` | `decision.needs_knowledge` y `knowledge_content` ausente | `[query_knowledge, respond(intent)]` |
| `support` / `question` | `decision.needs_knowledge` y `decision.knowledge_content` presente | `[respond(intent)]` |
| `support` / `question` | `decision.needs_knowledge` y `knowledge_content` ausente | `[query_knowledge, respond(intent)]` |
| `unknown` | `decision.status == "rejected"` | `[respond(intent, parameters={reason: "intent_not_recognized"})]` |
| `unknown` | `decision.status == "accepted"` | `[respond(intent)]` |
| Cualquier intent | `not constraints.is_feasible` | `[escalate(intent, reason)]` (sobrescribe) |

**Nota**: Para intents que requieren conocimiento, si `knowledge_content` ya fue resuelto (B5 knowledge query success), se genera solo `respond`. Si no se encontró conocimiento, se genera `query_knowledge + respond` para que el ejecutor lo reintente o use fallback.

## Archivos nuevos

### `app/core/business/action_planner.py`

```python
class ActionPlanner:
    def plan(
        self,
        context: BusinessContext,
        business_intent: BusinessIntent,
        constraints: BusinessConstraints,
        decision: BusinessDecision,
    ) -> BusinessActionPlan:
        ...
```

- Lógica de reglas según tabla arriba
- Cada step con `action`, `target` (ej. `"conversation_service"`), `parameters` (intent, content, reason, etc.), `order` secuencial

## Archivos modificados

### `app/core/business/service.py` — `BusinessBrainService`

1. Agregar `action_planner: ActionPlanner | None = None` en `__init__`
2. Agregar `self._last_action_plan: BusinessActionPlan | None = None`
3. Después de `decision = BusinessDecision(...)` (línea ~98) o después del bloque knowledge, llamar `ActionPlanner.plan()` y almacenar en `_last_action_plan`
4. Publicar evento `"plan_generado"`

Pipeline final:

```
ContextInterpreter → IntentClassifier → RuleEvaluator → DecisionMaker → ConfidenceEvaluator
→ BusinessDecision → KnowledgeService (si necesita) → ActionPlanner → BusinessActionPlan → BusinessDecision (return)
```

**Decisión de diseño**: `BusinessActionPlan` se almacena internamente y se devuelve `BusinessDecision` como contrato CE↔BB. No se modifica el contrato externo.

### `app/api/dependencies.py`

- Importar `ActionPlanner`
- Agregar `action_planner=ActionPlanner()` en el constructor de `BusinessBrainService`

## Tests

### `tests/test_action_planner.py`

| Test | Descripción | Steps esperados |
|---|---|---|
| `test_greeting_plan` | greeting | `[respond]` |
| `test_price_inquiry_with_knowledge_plan` | price_inquiry con knowledge | `[respond]` |
| `test_price_inquiry_without_knowledge_plan` | price_inquiry sin knowledge | `[query_knowledge, respond]` |
| `test_unknown_rejected_plan` | unknown + rejected | `[respond]` con reason |
| `test_support_without_knowledge_plan` | support sin knowledge | `[query_knowledge, respond]` |
| `test_all_intents_covered` | Verifica que todos los intents conocidos tengan plan | Parametrize con listado completo |

### `tests/test_business_brain_service.py`

| Test existente | Cambio |
|---|---|
| `test_business_brain_stores_constraints` | Agregar `assert service._last_action_plan is not None`. Verificar steps según intent. |
| Test nuevo: `test_business_brain_known_intent_has_action_plan` | greeting → verificar action plan tiene respond |
| Test nuevo: `test_business_brain_price_inquiry_has_query_knowledge_step` | price_inquiry sin knowledge → verificar query_knowledge step |

## Riesgos

| Riesgo | Mitigación |
|---|---|
| ActionPlanner genere steps contradictorios con el decision status | La regla de `is_feasible` sobrescribe todo con `[escalate]` |
| Duplicación de `query_knowledge` si ya fue ejecutado | Si `decision.needs_knowledge` está en True y `knowledge_content` no es None, se salta `query_knowledge` step |
| The B6 plan devuelva más steps de los necesarios | Se limita a 2 steps máx por plan (query_knowledge + respond, o solo respond, o solo escalate) |

## Calidad

- `pytest`: mantener 171+ pasando, nuevos tests suman ~10
- `ruff`: 0 errores
- `black`: sin cambios de formato forzados
- `mypy`: 0 errores en 66+ source files (1 nuevo)
- VS1: 10/10 sin cambios (el contrato CE↔BB no cambia)

## Criterios de aceptación

1. Todo intent conocido genera un `BusinessActionPlan` con al menos 1 step
2. Unknown + rejected tiene step `respond` con `reason="intent_not_recognized"`
3. Intents con `not is_feasible` generan `[escalate]`
4. `_last_action_plan` se almacena en `BusinessBrainService`
5. No se modifica el contrato `BusinessDecision` (CE↔BB intacto)
6. No se modifican Blueprint, ADRs, Conversation Engine
7. No se ejecutan acciones, no se publican eventos duplicados
8. Todos los quality gates pasan
