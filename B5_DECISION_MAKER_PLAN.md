# B5 — Decision Maker + Confidence Evaluator: Technical Plan

**Blueprint:** D-008-07 — Decision Maker + Confidence Evaluator  
**Incremento:** 5 de 7  
**Dependencias:** B1 (BusinessOptions, BusinessOption), B2 (BusinessContext), B3 (BusinessIntent), B4 (RuleEvaluator → BusinessConstraints)  
**Estado:** I5 cerrado, B1–B4 cerrados

---

## 1. Responsabilidades

### 1.1 Decision Maker (D-008-07)

| Atributo | Valor |
|---|---|
| **Pregunta** | ¿Qué es lo mejor que se puede hacer? |
| **Responsabilidad** | Construir opciones válidas, evaluarlas y seleccionar la mejor |
| **Entradas** | `BusinessContext`, `BusinessIntent`, `BusinessConstraints` |
| **Salida** | `BusinessOptions` con opciones evaluadas y seleccionada |
| **Principios** | Determinístico, auditable, basado en contexto y restricciones |
| **Regla** | Solo el Decision Maker puede generar un `BusinessDecision` |

### 1.2 Confidence Evaluator (D-008-07)

| Atributo | Valor |
|---|---|
| **Pregunta** | ¿Cuán seguro estamos de esta decisión? |
| **Responsabilidad** | Evaluar la confianza de la decisión usando reglas objetivas |
| **Entradas** | `BusinessContext`, `BusinessIntent`, `BusinessConstraints`, `BusinessOptions`, opción seleccionada |
| **Salida** | `"high"` \| `"medium"` \| `"low"` |
| **Principios** | Consistente, explicable, auditable, independiente de IA |

### 1.3 Qué NO hacen (en B5)

| Excluido | Responsable futuro |
|---|---|
| NO generan Action Plans | Action Planner (B6) |
| NO publican eventos | Event Publisher (B7) |
| NO escriben texto conversacional | Response Composer (CE) |
| NO modifican contratos CE↔BB | — |

---

## 2. Estado actual

### 2.1 Pipeline actual (B4)

```
BusinessBrainService.process(request):
    1. ContextInterpreter.enrich(request)        → BusinessContext
    2. IntentClassifier.classify(content)         → str
    3. model_copy(update={"intent": str})
    4. RuleEvaluator.evaluate(context, intent)    → BusinessConstraints
    5. DecisionEngine.evaluate(context)           → BusinessDecision
       5a. BusinessPolicy.get_response(intent)    → {status, confidence, needs_knowledge}
       5b. BusinessDecision(status=..., intent=..., confidence=..., needs_knowledge=...)
    6. (KnowledgeService opcional)
    7. Return BusinessDecision
```

### 2.2 DecisionEngine (16 líneas)

```python
class DecisionEngine:
    def __init__(self, policy: BusinessPolicy) -> None:
        self._policy = policy

    def evaluate(self, context: BusinessContext) -> BusinessDecision:
        response = self._policy.get_response(context.intent)
        return BusinessDecision(
            status=response["status"],
            intent=context.intent,
            confidence=response["confidence"],
            needs_knowledge=response["needs_knowledge"],
        )
```

### 2.3 BusinessPolicy (43 líneas)

```python
class BusinessPolicy:
    def get_response(self, intent: str) -> dict[str, Any]:
        policies = {
            "greeting":     {"status": "accepted", "confidence": "high",   "needs_knowledge": False},
            "farewell":     {"status": "accepted", "confidence": "high",   "needs_knowledge": False},
            "price_inquiry":{"status": "accepted", "confidence": "medium", "needs_knowledge": True},
            "thanks":       {"status": "accepted", "confidence": "high",   "needs_knowledge": False},
            "support":      {"status": "accepted", "confidence": "medium", "needs_knowledge": True},
            "question":     {"status": "accepted", "confidence": "medium", "needs_knowledge": True},
            "unknown":      {"status": "accepted", "confidence": "low",    "needs_knowledge": False},
        }
        return policies.get(intent, policies["unknown"])
```

### 2.4 Problemas identificados en el Gap Analysis

| Problema | Descripción | Se resuelve en B5 |
|---|---|---|
| **Brecha 1** — Sin BusinessOptions | El DecisionMaker debe construir opciones antes de decidir | ✅ Se implementa |
| **Brecha 2** — Sin BusinessConstraints como entrada | El DecisionMaker debe recibir restricciones | ✅ Ya lo recibe (B4 las produce) |
| **Brecha 3** — Fusionado con RuleEvaluator | DecisionEngine llama a BusinessPolicy directamente | ✅ Se separa: RuleEvaluator produce constraints, DecisionMaker decide |
| **Brecha 4** — Fusionado con ConfidenceEvaluator | La confianza es un valor hardcodeado en BusinessPolicy | ✅ Se crea ConfidenceEvaluator con reglas objetivas |

---

## 3. Diseño objetivo

### 3.1 DecisionMaker

#### Interfaz

```python
class DecisionMaker:
    def decide(
        self,
        context: BusinessContext,
        business_intent: BusinessIntent,
        constraints: BusinessConstraints,
    ) -> BusinessOptions:
        """Construye opciones, las evalúa y selecciona la mejor."""
        options = self._build_options(context, business_intent, constraints)
        selected = self._select_best(options)
        return BusinessOptions(options=options, selected_index=selected)
```

#### Construcción de opciones

Para cada intent + constraints, el DecisionMaker construye entre 1 y 2 opciones:

| Opción | Condición | Score | rationale |
|---|---|---|---|
| `respond` | Siempre presente | Según scoring (abajo) | `"Responder al cliente con acción para {intent}"` |
| `query_knowledge` | `BR-KNOWLEDGE-REQUIRED.applies == True` | `0.85` | `"Consultar knowledge base para {intent}"` |

Para intents que NO requieren knowledge (greeting, farewell, thanks, unknown), solo se genera la opción `respond`.

Para intents que SÍ requieren knowledge (price_inquiry, support, question), se generan dos opciones: `respond` + `query_knowledge`.

#### Scoring de la opción `respond`

| Condición | Score |
|---|---|
| `constraints.is_feasible == True` y `business_intent.name != "unknown"` | `0.90` |
| `constraints.is_feasible == True` y `business_intent.name == "unknown"` | `0.50` |
| `constraints.is_feasible == False` | `0.30` |

#### Scoring de la opción `query_knowledge`

| Condición | Score |
|---|---|
| `BR-KNOWLEDGE-REQUIRED.applies == True` | `0.85` |
| `BR-KNOWLEDGE-REQUIRED.applies == False` | No se genera |

#### Selección

`selected_index = argmax(options, key=lambda o: o.score)`

El índice de la opción con mayor score se almacena en `BusinessOptions.selected_index`. Si hay empate (mismo score), gana la primera (menor índice).

#### Ejemplos concretos

| Escenario | Opciones | Scores | selected_index |
|---|---|---|---|
| greeting + factible | `[respond]` | `[0.90]` | `0` |
| price_inquiry + factible | `[respond, query_knowledge]` | `[0.90, 0.85]` | `0` (respond gana) |
| unknown + factible | `[respond]` | `[0.50]` | `0` |
| unknown + no factible | `[respond]` | `[0.30]` | `0` |

### 3.2 ConfidenceEvaluator

#### Interfaz

```python
class ConfidenceEvaluator:
    def evaluate(
        self,
        context: BusinessContext,
        business_intent: BusinessIntent,
        constraints: BusinessConstraints,
        selected_option: BusinessOption | None,
    ) -> str:
        """Evalúa la confianza de la decisión usando reglas objetivas.
        
        Retorna: "high" | "medium" | "low"
        """
```

#### Reglas de evaluación

Evaluación secuencial (primera regla que coincide determina el resultado):

| Orden | Regla | Condición | Resultado |
|---|---|---|---|
| 1 | Intento no factible | `not constraints.is_feasible` | `"low"` |
| 2 | Intento desconocido | `business_intent.name == "unknown"` | `"low"` |
| 3 | Sin opción seleccionada | `selected_option is None` | `"low"` |
| 4 | Score alto | `selected_option.score >= 0.80` | `"high"` |
| 5 | Score medio | `selected_option.score >= 0.50` | `"medium"` |
| 6 | Score bajo | `selected_option.score < 0.50` | `"low"` |

#### Mapeo con la confianza actual (BusinessPolicy)

| Intent | Confianza actual (hardcodeada) | Confianza nueva (evaluada) | ¿Cambia? |
|---|---|---|---|
| greeting, farewell, thanks | high | high (score 0.90) | No |
| price_inquiry, support, question | medium | high (score 0.90) | **Sí** — sube a high |
| unknown | low | low (score 0.50) | No |

**Cambio detectado:** `price_inquiry`, `support`, `question` pasan de `"medium"` a `"high"`. Esto se debe a que el ConfidenceEvaluator evalúa la confianza según el score de la opción seleccionada (no según el intent). Si la opción `respond` tiene score 0.90, la confianza es `"high"`. Este cambio es intencional y está alineado con el blueprint (la confianza debe reflejar la solidez de la decisión, no ser un valor fijo por intent).

### 3.3 Pipeline después de B5

```
BusinessBrainService.process(request):

    1. ContextInterpreter.enrich(request)
       → BusinessContext

    2. IntentClassifier.classify(request.content)
       → str → BusinessIntent(name=str)

    3. RuleEvaluator.evaluate(context, business_intent)
       → BusinessConstraints

    4. DecisionMaker.decide(context, business_intent, constraints)
       → BusinessOptions (opciones + selección)

    5. Extraer selected_option de BusinessOptions
    6. ConfidenceEvaluator.evaluate(context, intent, constraints, selected_option)
       → "high" | "medium" | "low"

    7. Construir BusinessDecision:
       status = "accepted"
       intent = business_intent.name
       confidence = resultado de ConfidenceEvaluator
       needs_knowledge = BR-KNOWLEDGE-REQUIRED.applies

    8. (KnowledgeService opcional — sin cambios)

    9. Return BusinessDecision
```

---

## 4. Integración y compatibilidad

### 4.1 BusinessPolicy se elimina

`BusinessPolicy.get_response()` ya no es necesario. El DecisionMaker decide qué opciones construir, y el ConfidenceEvaluator determina la confianza. La lógica de `status`, `confidence` y `needs_knowledge` se distribuye entre:

| Salida actual de BusinessPolicy | Nuevo responsable |
|---|---|
| `status` | Siempre `"accepted"` en B5 (el rejection/escalation se implementa en B6 con ActionPlanner) |
| `confidence` | `ConfidenceEvaluator.evaluate()` |
| `needs_knowledge` | `BR-KNOWLEDGE-REQUIRED.applies` desde `BusinessConstraints` |

### 4.2 DecisionEngine se elimina

`DecisionEngine.evaluate()` es reemplazado por `DecisionMaker.decide()` + `ConfidenceEvaluator.evaluate()`. El `BusinessBrainService` construye `BusinessDecision` directamente.

### 4.3 Compatibilidad con el constructor de BusinessBrainService

```python
# ANTES (B4)
BusinessBrainService(
    intent_classifier=...,
    decision_engine=decision_engine,         # ← se elimina
    context_interpreter=...,
    rule_evaluator=...,
    knowledge_service=...,
    event_publisher=...,
)

# DESPUÉS (B5)
BusinessBrainService(
    intent_classifier=...,
    decision_maker=decision_maker,           # ← NUEVO (reemplaza decision_engine)
    confidence_evaluator=confidence_evaluator, # ← NUEVO
    context_interpreter=...,
    rule_evaluator=...,
    knowledge_service=...,
    event_publisher=...,
)
```

### 4.4 BusinessOptions viaja como atributo de instancia

```python
class BusinessBrainService:
    def __init__(self, ..., decision_maker, confidence_evaluator):
        ...
        self._last_constraints: BusinessConstraints | None = None
        self._last_options: BusinessOptions | None = None       # NUEVO
        self._last_confidence: str | None = None                 # NUEVO

    def process(self, request):
        ...
        self._last_options = self._decision_maker.decide(...)
        self._last_confidence = self._confidence_evaluator.evaluate(...)
        ...
```

### 4.5 BusinessDecision.status permanece "accepted"

El `status` en `BusinessDecision` se mantiene como `"accepted"` para todas las decisiones en B5. El uso de `constraints.is_feasible` para determinar `status` (rejected, escalated) se implementa en B6 junto con el ActionPlanner. Esto garantiza que VS1 no cambie.

### 4.6 knowledge_content

El flujo de `knowledge_content` no cambia. Cuando `needs_knowledge=True` y `KnowledgeService` encuentra contenido, se reconstruye `BusinessDecision` con `knowledge_content` (exactamente como hoy en service.py líneas 56-75). La única diferencia es que `needs_knowledge` ahora se obtiene de `constraints` en lugar de `BusinessPolicy`.

---

## 5. Cambios necesarios

### 5.1 Archivos nuevos (2)

| Archivo | Clase | Líneas | Propósito |
|---|---|---|---|
| `app/core/business/decision_maker.py` | `DecisionMaker` | ~70 | Construye BusinessOptions, evalúa scores, selecciona mejor opción |
| `app/core/business/confidence_evaluator.py` | `ConfidenceEvaluator` | ~35 | Evalúa confianza con reglas objetivas |

### 5.2 Archivos eliminados (2)

| Archivo | Razón |
|---|---|
| `app/core/business/decision_engine.py` | Reemplazado por DecisionMaker + ConfidenceEvaluator |
| `app/core/business/policy.py` | Lógica distribuida: scoring en DecisionMaker, confianza en ConfidenceEvaluator, needs_knowledge en constraints |

### 5.3 Archivos modificados (3)

| Archivo | Cambio | Líneas |
|---|---|---|
| `app/core/business/service.py` | Eliminar `decision_engine`. Agregar `decision_maker` + `confidence_evaluator`. Pipeline: evaluate constraints → decide → evaluate confidence → build BusinessDecision. | ~25 |
| `app/api/dependencies.py` | Eliminar `BusinessPolicy`, `DecisionEngine`. Agregar `DecisionMaker`, `ConfidenceEvaluator`. | ~10 |
| `tests/test_business_brain_service.py` | Reemplazar `DecisionEngine` por `DecisionMaker` + `ConfidenceEvaluator`. Agregar test de confidence evaluado + options almacenados. | ~30 |

### 5.4 Archivos renombrados (2)

| Archivo viejo | Archivo nuevo | Contenido |
|---|---|---|
| `tests/test_decision_engine.py` | `tests/test_decision_maker.py` | Tests adaptados para DecisionMaker |
| `tests/test_business_policy.py` | (eliminado) | Tests reemplazados por tests de ConfidenceEvaluator + DecisionMaker |

### 5.5 Archivos NO modificados

| Archivo | Razón |
|---|---|
| `app/domain/business/contracts.py` | BusinessOptions, BusinessOption ya existen desde B1. Sin cambios. |
| `app/core/business/rule_evaluator.py` | B4 ya implementado. Sin cambios. |
| `app/core/business/context_interpreter.py` | B2 ya implementado. Sin cambios. |
| `app/core/business/intent_classifier.py` | Sin cambios (se reemplazará en B3). |
| `app/core/conversation/*` | CE no se modifica. |
| `app/channels/*` | Canales no se modifican. |
| `app/core/business/event_publisher.py` | Sin cambios. |
| `tests/test_vs1_integration.py` | Sin cambios (comportamiento observable idéntico). |
| `tests/test_rule_evaluator.py` | Sin cambios (B4). |

---

## 6. Tests

### 6.1 Tests unitarios — DecisionMaker (7 tests)

Nuevo archivo: `tests/test_decision_maker.py`

| # | Test | Descripción |
|---|---|---|
| 1 | `test_decide_returns_business_options` | Llama `decide()` y verifica que retorna `BusinessOptions` |
| 2 | `test_decide_creates_respond_option_for_greeting` | greeting → opción `respond` con score 0.90 |
| 3 | `test_decide_creates_respond_and_query_for_price_inquiry` | price_inquiry + knowledge required → 2 opciones: respond (0.90) y query_knowledge (0.85) |
| 4 | `test_decide_respond_selected_for_high_score_intents` | greeting → selected_index=0 (respond gana) |
| 5 | `test_decide_respond_selected_even_with_knowledge` | price_inquiry → selected_index=0 (respond 0.90 > query_knowledge 0.85) |
| 6 | `test_decide_unknown_score` | unknown + factible → respond score 0.50 |
| 7 | `test_decide_not_feasible_score` | unknown + no factible → respond score 0.30 |

### 6.2 Tests unitarios — ConfidenceEvaluator (6 tests)

Nuevo archivo: `tests/test_confidence_evaluator.py`

| # | Test | Descripción |
|---|---|---|
| 1 | `test_evaluate_returns_high` | `selected_option.score=0.90` → `"high"` |
| 2 | `test_evaluate_returns_medium` | `selected_option.score=0.50` → `"medium"` |
| 3 | `test_evaluate_returns_low` | `selected_option.score=0.30` → `"low"` |
| 4 | `test_evaluate_low_when_not_feasible` | `constraints.is_feasible=False` → `"low"` |
| 5 | `test_evaluate_low_when_unknown` | `business_intent.name="unknown"` → `"low"` |
| 6 | `test_evaluate_low_when_no_option` | `selected_option=None` → `"low"` |

### 6.3 Tests de integración — BusinessBrainService

Modificar: `tests/test_business_brain_service.py`

| # | Test | Cambio |
|---|---|---|
| 1 | `test_business_brain_returns_decision_for_greeting` | `DecisionEngine` → `DecisionMaker` + `ConfidenceEvaluator`. Assert `decision.intent`, `decision.status`, `decision.confidence` igual que antes. |
| 2 | `test_business_brain_with_context_interpreter` | Idéntico cambio de wiring. |
| 3 | `test_business_brain_returns_decision_for_unknown` | Idéntico cambio de wiring. Confidence cambia a `"low"` (era `"low"` — se mantiene). |
| 4 | `test_business_brain_queries_knowledge_for_price_inquiry` | Idéntico cambio de wiring. Confidence cambia a `"high"` (era `"high"` porque KnowledgeService devuelve confidence="high"). |
| 5 | `test_business_brain_stores_constraints` | **Se expande**: también verifica `service._last_options` y `service._last_confidence`. |
| 6 | `test_business_brain_falls_back_to_policy_when_no_knowledge_found` | Idéntico cambio de wiring. |

### 6.4 Tests de regresión

| Suite | Tests | Esperado |
|---|---|---|
| `tests/test_vs1_integration.py` | 10 | ✅ Sin cambios (comportamiento observable idéntico) |
| `tests/test_rule_evaluator.py` | 9 | ✅ Sin cambios (B4) |
| `tests/test_intent_classifier.py` | 8 | ✅ Sin cambios |
| `tests/test_context_interpreter.py` | 6 | ✅ Sin cambios (B2) |
| `tests/test_customer_profile_provider.py` | 3 | ✅ Sin cambios (B2) |
| `tests/test_business_contracts.py` | 18 | ✅ Sin cambios (B1) |
| Tests de CE, KE, infra | ~100 | ✅ Sin cambios |
| **Total** | **~154 + 13 nuevos - 6 eliminados = ~161 tests** | |

### 6.5 Tests eliminados

| Archivo | Tests | Razón |
|---|---|---|
| `tests/test_decision_engine.py` | 2 | Reemplazado por `test_decision_maker.py` |
| `tests/test_business_policy.py` | 4 | Reemplazado por `test_confidence_evaluator.py` + `test_decision_maker.py` |

### 6.6 Cambios en valores de confianza (VS1-compatibles)

| Flujo VS1 | Confianza actual | Confianza nueva | ¿VS1 se rompe? |
|---|---|---|---|
| greeting | high | high | No |
| farewell | high | high | No |
| horario (question + knowledge match) | high (de KnowledgeService) | high (de KnowledgeService) | No |
| envío (question + knowledge match) | high (de KnowledgeService) | high (de KnowledgeService) | No |
| pago (question + knowledge match) | high (de KnowledgeService) | high (de KnowledgeService) | No |
| fallback (question sin knowledge) | medium | **high** (score 0.90) | **No** — VS1 no assert confidence en fallback |
| unknown | low | low | No |
| price_inquiry (sin knowledge) | medium | **high** (score 0.90) | **No** — VS1 no assert confidence |
| price_inquiry (con knowledge) | high (de KnowledgeService) | high (de KnowledgeService) | No |

**VS1 no verifica `confidence` en ningún test.** Los únicos asserts son sobre `status` y `message`. Los 10 tests de VS1 pasan sin cambios.

---

## 7. Estrategia de migración

### 7.1 Reemplazo completo (no coexistencia)

A diferencia de B1→B3 (donde BusinessIntent coexistió sin usarse) o B4 (donde BusinessConstraints se generó sin consumirse), en B5 **el reemplazo es directo**:

| Componente | B4 | B5 |
|---|---|---|
| BusinessPolicy | Usado por DecisionEngine | **Eliminado** |
| DecisionEngine | Orquesta la decisión final | **Eliminado** |
| DecisionMaker | No existe | **Nuevo** — construye opciones |
| ConfidenceEvaluator | No existe | **Nuevo** — evalúa confianza |

### 7.2 Por qué se puede reemplazar directamente

| Razón | Explicación |
|---|---|
| BusinessPolicy solo lo usa DecisionEngine | Ningún otro componente importa BusinessPolicy |
| DecisionEngine solo lo usa BusinessBrainService | Ningún otro componente importa DecisionEngine |
| BusinessDecision no cambia | El contrato de salida es idéntico |
| BusinessOptions es nuevo y no se exporta | Solo se usa internamente en el pipeline |

### 7.3 Coexistencia de contracts

| Contrato | B4 | B5 |
|---|---|---|
| `BusinessContext` | ✅ Usado | ✅ Usado |
| `BusinessIntent` | ✅ Usado (en RuleEvaluator) | ✅ Usado (en RuleEvaluator + DecisionMaker) |
| `BusinessConstraints` | ✅ Producido, no consumido | ✅ Producido y consumido por DecisionMaker |
| `BusinessOptions` | ❌ No usado | ✅ Nuevo: producido por DecisionMaker |
| `BusinessDecision` | ✅ Producido | ✅ Producido (sin cambios en el contrato) |

### 7.4 Orden de implementación

```
1. Crear DecisionMaker (decision_maker.py)
2. Crear ConfidenceEvaluator (confidence_evaluator.py)
3. Modificar service.py: reemplazar DecisionEngine por DecisionMaker + ConfidenceEvaluator
4. Modificar dependencies.py: reemplazar wiring
5. Eliminar decision_engine.py y policy.py
6. Crear tests/test_decision_maker.py (7 tests)
7. Crear tests/test_confidence_evaluator.py (6 tests)
8. Modificar tests/test_business_brain_service.py (5 tests adaptados + 1 expandido)
9. Eliminar tests/test_decision_engine.py (2 tests)
10. Eliminar tests/test_business_policy.py (4 tests)
11. Ejecutar quality gates
```

---

## 8. Riesgos

### R1 — `price_inquiry`, `support`, `question` cambian de confidence "medium" → "high"

| Escenario | Impacto | Probabilidad | Mitigación |
|---|---|---|---|
| El ConfidenceEvaluator evalúa score 0.90 (respond) como "high". BusinessPolicy asignaba "medium" a estos intents. | `BusinessDecision.confidence` cambia de "medium" a "high" para price_inquiry, support, question (cuando no hay knowledge match). | **100%** (es el diseño) | Este cambio es **intencional y correcto** según el blueprint. La confianza debe reflejar la solidez de la decisión, no ser un valor fijo por intent. El ConfidenceEvaluador evalúa: intent conocido + factible + opción con score 0.90 = "high". Los tests de VS1 no verifican confidence. Los tests unitarios se actualizan. |

### R2 — `DecisionEngine` se elimina, no hay gradualidad

| Escenario | Impacto | Probabilidad | Mitigación |
|---|---|---|---|
| Si algo externo (scripts, herramientas, imports no detectados) usa `DecisionEngine` o `BusinessPolicy`, se rompe. | ImportError en runtime. | **Baja** | `grep -r "DecisionEngine\|BusinessPolicy"` en el código base muestra solo 4 archivos: `decision_engine.py`, `policy.py`, `service.py`, `dependencies.py` — todos modificados en el mismo commit. No hay otros consumidores. |

### R3 — `BusinessDecision.status` siempre "accepted" sin usar `is_feasible`

| Escenario | Impacto | Probabilidad | Mitigación |
|---|---|---|---|
| El ConfidenceEvaluator detecta `is_feasible=False` y asigna "low". Pero `status` sigue siendo "accepted". El sistema dice "aceptado con baja confianza" en vez de "rechazado". | Inconsistencia semántica: una decisión no-factible se reporta como aceptada. | **100%** (es el diseño de B5) | El uso de `is_feasible` para determinar `status` se implementa en B6 junto con el ActionPlanner. En B5, el ConfidenceEvaluator ya baja la confianza a "low", lo que es señal suficiente para que el CE (ResponseComposer) pueda tratar la respuesta con cautela. B6 completará la lógica de status. |

### R4 — `BusinessOptions.selected_index` puede ser `None` si no hay opciones

| Escenario | Impacto | Probabilidad | Mitigación |
|---|---|---|---|
| Si `_build_options()` retorna lista vacía (extremo: sin reglas, sin intents), `selected_index` es `None`. El ConfidenceEvaluator recibe `selected_option=None` y retorna "low". | Decisión con confianza "low" sin opción seleccionada. | **Nula** | El DecisionMaker siempre genera al menos la opción `respond`. La lista nunca está vacía. El ConfidenceEvaluator maneja `None` como caso de seguridad. |

### R5 — `needs_knowledge` ahora se obtiene de `BR-KNOWLEDGE-REQUIRED.applies`

| Escenario | Impacto | Probabilidad | Mitigación |
|---|---|---|---|
| Antes: `BusinessPolicy` definía `needs_knowledge` por intent. Ahora: se obtiene de `constraints`. Si la regla BR-KNOWLEDGE-REQUIRED cambia (B4 modificado), `needs_knowledge` cambia automáticamente. | `needs_knowledge` ahora es determinístico desde las reglas, no desde un dict hardcodeado. | **Baja** | BR-KNOWLEDGE-REQUIRED usa el mismo set de intents que antes (`price_inquiry`, `support`, `question`). El comportamiento es idéntico. Si se agregan reglas en el futuro, el cambio es explícito y trazable. |

### R6 — `BusinessOptions` se construye pero no persiste fuera de `_last_options`

| Escenario | Impacto | Probabilidad | Mitigación |
|---|---|---|---|
| El objeto `BusinessOptions` con las alternativas evaluadas se almacena en `_last_options` pero no se expone en el contrato CE↔BB (`BusinessDecision` no incluye options). | Las opciones consideradas se pierden después de la decisión. | **Alta** (es el diseño) | `_last_options` está disponible para eventos, logs y debugging. En B6 (ActionPlanner), el `BusinessDecision` podría extenderse con `action_plan` derivado de las opciones. Por ahora, las opciones son intra-pipeline. |

---

## Resumen de archivos

| Tipo | Archivos | Líneas |
|---|---|---|
| Crear (2) | `app/core/business/decision_maker.py`, `app/core/business/confidence_evaluator.py` | ~105 |
| Eliminar (2) | `app/core/business/decision_engine.py`, `app/core/business/policy.py` | ~ -59 |
| Modificar (3) | `app/core/business/service.py`, `app/api/dependencies.py`, `tests/test_business_brain_service.py` | ~65 |
| Tests nuevos (2) | `tests/test_decision_maker.py`, `tests/test_confidence_evaluator.py` | ~120 |
| Tests eliminar (2) | `tests/test_decision_engine.py`, `tests/test_business_policy.py` | ~ -71 |
| No modificar | ~55 archivos | — |

**Total líneas netas agregadas:** ~160
**Total tests:** ~161 (13 nuevos + 148 regresión)
**VS1:** 10/10 sin cambios

---

## READY FOR CTO REVIEW
