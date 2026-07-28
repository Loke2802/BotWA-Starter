# B4 — Rule Evaluator: Technical Plan

**Blueprint:** D-008-06 — Rule Evaluator  
**Incremento:** 4 de 7  
**Dependencias:** B1 (Domain Contracts — BusinessConstraints), B2 (Context Interpreter — BusinessContext), B3 (Intent Analyzer — BusinessIntent)  
**Estado:** I5 cerrado, B1 cerrado, B2 cerrado, B3 en implementación

---

## 1. Responsabilidad del Rule Evaluator

### 1.1 Definición (D-008-06)

| Atributo | Valor |
|---|---|
| **Pregunta** | ¿Qué está permitido hacer? |
| **Responsabilidad** | Evaluar las reglas de negocio contra el contexto y la intención, produciendo restricciones estructuradas |
| **Entradas** | `BusinessContext`, `BusinessIntent` |
| **Salidas** | `BusinessConstraints` |
| **Principios** | Determinístico, auditable, independiente de IA, independiente del canal |
| **Regla blueprint** | Todas las reglas del negocio deben evaluarse exclusivamente dentro del Rule Evaluator |

### 1.2 Qué NO hace

| Excluido | Responsable futuro |
|---|---|
| NO toma decisiones finales (status, confidence, needs_knowledge) | Decision Maker (B5) |
| NO genera Business Options | Decision Maker (B5) |
| NO evalúa confianza de la decisión | Confidence Evaluator (B5) |
| NO crea Action Plans | Action Planner (B6) |
| NO publica eventos | Event Publisher (B7) |
| NO produce texto conversacional | Response Composer (CE, I4) |
| NO clasifica intents | Intent Analyzer (B3) |
| NO enriquece contexto | Context Interpreter (B2) |

### 1.3 Lugar en el pipeline (después de B4)

```
Context Interpreter (B2)
    ↓ BusinessContext
Intent Analyzer (B3)
    ↓ BusinessIntent
Rule Evaluator (B4)      ← NUEVO
    ↓ BusinessConstraints
DecisionMaker (B5 futuro) / DecisionEngine (actual)
    ↓ BusinessDecision
Action Planner (B6 futuro)
    ↓ BusinessActionPlan
Event Publisher (B7 futuro)
```

---

## 2. Estado actual: BusinessPolicy

### 2.1 Código actual

```python
class BusinessPolicy:
    def get_response(self, intent: str) -> dict[str, Any]:
        policies = {
            "greeting":    {"status": "accepted", "confidence": "high",   "needs_knowledge": False},
            "farewell":    {"status": "accepted", "confidence": "high",   "needs_knowledge": False},
            "price_inquiry":{"status": "accepted","confidence": "medium", "needs_knowledge": True},
            "thanks":      {"status": "accepted", "confidence": "high",   "needs_knowledge": False},
            "support":     {"status": "accepted", "confidence": "medium", "needs_knowledge": True},
            "question":    {"status": "accepted", "confidence": "medium", "needs_knowledge": True},
            "unknown":     {"status": "accepted", "confidence": "low",    "needs_knowledge": False},
        }
        return policies.get(intent, policies["unknown"])
```

### 2.2 Quién lo usa

| Componente | Llamada | Propósito |
|---|---|---|
| `DecisionEngine.evaluate(context)` | `self._policy.get_response(context.intent)` | Obtener status, confidence, needs_knowledge para construir BusinessDecision |
| `tests/test_decision_engine.py` | `DecisionEngine(policy=BusinessPolicy())` | Inyección de dependencia |
| `tests/test_business_policy.py` | `policy.get_response("greeting")` | Tests directos del policy |
| `tests/test_business_brain_service.py` | `policy = BusinessPolicy()` | Construcción del DecisionEngine |

### 2.3 Lo que BusinessPolicy NO tiene (vs. blueprint)

| Ausente | Blueprint D-008-06 |
|---|---|
| Reglas de dominio identificables (BR-XXX) | "Reglas del Dominio (BR-XXX)" |
| Configuración de empresa | "Configuración de la empresa" |
| Evaluación contextual (perfil del cliente, metadata) | Recibe Business Context completo |
| BusinessConstraints como salida estructurada | Produce `Business Constraints` |
| Determinismo auditable | "Determinístico, auditable" |

### 2.4 Lo que BusinessPolicy SÍ tiene (pero no debería)

El `BusinessPolicy` actual contiene lógica que el blueprint asigna a **tres componentes distintos**:

| Lógica en BusinessPolicy | Blueprint dice que pertenece a |
|---|---|
| `status: "accepted"` para todo intent | Rule Evaluator (¿está permitido?) + Decision Maker (decide) |
| `confidence: "high"` / `"medium"` / `"low"` | Confidence Evaluator (B5) |
| `needs_knowledge: True/False` | Decision Maker (needs_knowledge es una decisión, no una restricción) |

En B4 solo se extrae la parte correspondiente al Rule Evaluator: **¿qué reglas aplican?** Las decisiones sobre status, confidence y needs_knowledge permanecen en `DecisionEngine` + `BusinessPolicy` hasta B5.

---

## 3. Diseño objetivo

### 3.1 Entrada

```python
# BusinessContext (desde B2)
context = BusinessContext(
    request=request,
    intent="price_inquiry",             # poblado por B3
    customer_profile={"customer_id": "c1", "name": "Cliente"},
    channel_metadata={},
)

# BusinessIntent (desde B3)
business_intent = BusinessIntent(
    name="price_inquiry",
    confidence="medium",
)
```

### 3.2 Salida

```python
# BusinessConstraints (contrato B1)
BusinessConstraints(
    constraints=[
        BusinessConstraint(
            rule_id="BR-INTENT-KNOWN",
            description="La intención del cliente es reconocible",
            applies=True,
            reason="price_inquiry es un intent válido",
        ),
        BusinessConstraint(
            rule_id="BR-CUSTOMER-ACTIVE",
            description="El cliente tiene cuenta activa",
            applies=True,
            reason="customer_profile presente",
        ),
        BusinessConstraint(
            rule_id="BR-KNOWLEDGE-REQUIRED",
            description="El intent requiere consulta a knowledge base",
            applies=True,
            reason="price_inquiry típicamente requiere información de productos",
        ),
    ],
    is_feasible=True,
)
```

### 3.3 Interfaz

```python
class RuleEvaluator:
    """Evalúa reglas de negocio contra BusinessContext + BusinessIntent.
    
    Principios:
    - Determinístico: mismas entradas → mismas salidas
    - Auditable: cada regla tiene rule_id, descripción y razón
    - Independiente de IA: reglas explícitas (BR-XXX)
    - Independiente del canal: no usa channel_metadata
    """

    def evaluate(
        self,
        context: BusinessContext,
        business_intent: BusinessIntent,
    ) -> BusinessConstraints:
        """Evalúa todas las reglas y produce BusinessConstraints."""
```

### 3.4 Reglas de dominio (BR-XXX) en B4

#### BR-INTENT-KNOWN

| Atributo | Valor |
|---|---|
| **ID** | `BR-INTENT-KNOWN` |
| **Descripción** | La intención del cliente es reconocible por el sistema |
| **Evaluación** | `business_intent.name != "unknown"` |
| **Pasa** → | `applies=True`, `reason="<intent> es un intent válido"` |
| **Falla** → | `applies=False`, `reason="La intención no pudo ser determinada"` |

#### BR-CUSTOMER-ACTIVE

| Atributo | Valor |
|---|---|
| **ID** | `BR-CUSTOMER-ACTIVE` |
| **Descripción** | El cliente tiene un perfil válido en el sistema |
| **Evaluación** | `context.customer_profile` no está vacío |
| **Pasa** → | `applies=True`, `reason="customer_profile presente"` |
| **Falla** → | `applies=False`, `reason="No se encontró perfil del cliente"` |

#### BR-KNOWLEDGE-REQUIRED

| Atributo | Valor |
|---|---|
| **ID** | `BR-KNOWLEDGE-REQUIRED` |
| **Descripción** | El intent requiere consulta a la knowledge base |
| **Evaluación** | `business_intent.name` en `{"price_inquiry", "support", "question"}` |
| **Pasa** → | `applies=True`, `reason="<intent> típicamente requiere información"` |
| **Falla** → | `applies=False`, `reason="<intent> no requiere conocimiento adicional"` |

#### BR-GREETING-ONLY-CONVERSATIONAL (documental — no bloquea)

| Atributo | Valor |
|---|---|
| **ID** | `BR-GREETING-CONVERSATIONAL` |
| **Descripción** | El intent greeting/farewell/thanks es conversacional, no de negocio |
| **Evaluación** | `business_intent.name in {"greeting", "farewell", "thanks"}` |
| **Propósito** | Regla documental que identifica intents no-comerciales. No bloquea el flujo. |

### 3.5 `is_feasible`

`BusinessConstraints.is_feasible` se calcula como:

```
is_feasible = BR-INTENT-KNOWN.applies AND BR-CUSTOMER-ACTIVE.applies
```

Si alguna regla mandatoria falla, `is_feasible = False`. El DecisionMaker (B5) usará este flag para decidir si continúa, solicita más información o escala.

### 3.6 Algoritmo completo

```
RuleEvaluator.evaluate(context, business_intent):
    1. Inicializar lista vacía de constraints
    2. Evaluar BR-INTENT-KNOWN:
       - intent conocido → constraint(applies=True)
       - intent unknown  → constraint(applies=False)
    3. Evaluar BR-CUSTOMER-ACTIVE:
       - customer_profile presente → constraint(applies=True)
       - sin perfil → constraint(applies=False)
    4. Evaluar BR-KNOWLEDGE-REQUIRED:
       - intent en lista de knowledge → constraint(applies=True)
       - intent no requiere knowledge → constraint(applies=False)
    5. Calcular is_feasible:
       - BR-INTENT-KNOWN.applies AND BR-CUSTOMER-ACTIVE.applies
    6. Retornar BusinessConstraints(constraints=..., is_feasible=...)
```

---

## 4. Integración con el pipeline B1-B3

### 4.1 Pipeline después de B4

```
BusinessBrainService.process(request):
    1. ContextInterpreter.enrich(request)        → BusinessContext
    2. IntentAnalyzer.analyze(context)           → BusinessIntent
    3. context = model_copy(update={"intent": business_intent.name})
    4. RuleEvaluator.evaluate(context, business_intent)  → BusinessConstraints  ← NUEVO
    5. DecisionEngine.evaluate(context)          → BusinessDecision (sin cambios)
    6. (KnowledgeService si necesita)
    7. Return BusinessDecision
```

### 4.2 Cambio exacto en `BusinessBrainService.process()`

```python
# ANTES (B3)
def process(self, request: BusinessRequest) -> BusinessDecision:
    context = self._enrich_context(request)
    business_intent = self._intent_analyzer.analyze(context)
    context = context.model_copy(update={"intent": business_intent.name})
    self._publish("objetivo_identificado", intent=business_intent.name)
    decision = self._decision_engine.evaluate(context)
    ...

# DESPUÉS (B4)
def process(self, request: BusinessRequest) -> BusinessDecision:
    context = self._enrich_context(request)
    business_intent = self._intent_analyzer.analyze(context)
    context = context.model_copy(update={"intent": business_intent.name})
    self._publish("objetivo_identificado", intent=business_intent.name)

    constraints = self._rule_evaluator.evaluate(context, business_intent)  # NUEVO
    self._publish("reglas_evaluadas",
        intent=business_intent.name,
        is_feasible=str(constraints.is_feasible),
    )

    decision = self._decision_engine.evaluate(context)
    ...
```

### 4.3 BusinessConstraints en `BusinessBrainService`

El `BusinessBrainService` **almacena** el `BusinessConstraints` como atributo de instancia para que incrementos futuros (B5+) puedan acceder a él sin modificar el pipeline:

```python
class BusinessBrainService:
    def __init__(self, ..., rule_evaluator: RuleEvaluator | None = None):
        self._rule_evaluator = rule_evaluator
        self._last_constraints: BusinessConstraints | None = None  # NUEVO

    def process(self, request: BusinessRequest) -> BusinessDecision:
        ...
        if self._rule_evaluator:
            self._last_constraints = self._rule_evaluator.evaluate(
                context, business_intent,
            )
        ...
```

**Nota:** En B4, `_last_constraints` se almacena pero **no se consume** en el pipeline. La `BusinessDecision` se construye igual que antes. El `BusinessConstraints` está disponible para:
- Tests que verifiquen su contenido
- Eventos publicados (contienen resumen de reglas)
- B5, donde el DecisionMaker lo consumirá

### 4.4 `BusinessPolicy` no se modifica

`BusinessPolicy.get_response(intent)` sigue funcionando exactamente igual. No se toca. La separación real ocurrirá en B5 cuando el DecisionMaker use `BusinessConstraints` en lugar de llamar a `BusinessPolicy`.

| Componente | B4 | B5 (futuro) |
|---|---|---|
| `RuleEvaluator` | ✅ Produce `BusinessConstraints` | ✅ Produce `BusinessConstraints` |
| `BusinessPolicy` | ✅ Sin cambios (sigue siendo llamado por DecisionEngine) | ❌ Se elimina o refactoriza |
| `DecisionEngine` | ✅ Sin cambios (sigue llamando a BusinessPolicy) | 🔄 Refactor: recibe BusinessConstraints |
| `BusinessConstraints` | ✅ Se genera, no se consume en decisión | ✅ Se consume en decisión |

### 4.5 Compatibilidad con el constructor de `BusinessBrainService`

```python
# B3 (constructor)
BusinessBrainService(
    intent_analyzer=intent_analyzer,
    decision_engine=decision_engine,
    context_interpreter=context_interpreter,
    knowledge_service=knowledge_service,
    event_publisher=event_publisher,
)

# B4 (constructor, nuevo parámetro opcional)
BusinessBrainService(
    intent_analyzer=intent_analyzer,
    decision_engine=decision_engine,
    rule_evaluator=rule_evaluator,               # NUEVO opcional
    context_interpreter=context_interpreter,
    knowledge_service=knowledge_service,
    event_publisher=event_publisher,
)
```

`rule_evaluator` es opcional (`None` por defecto) para no romper tests o configuraciones que no lo inyecten.

---

## 5. Archivos nuevos y modificados

### 5.1 Archivos nuevos (1)

| Archivo | Clase | Líneas | Propósito |
|---|---|---|---|
| `app/core/business/rule_evaluator.py` | `RuleEvaluator` | ~60 | Evaluación de reglas de negocio, produce `BusinessConstraints` |

### 5.2 Archivos modificados (3)

| Archivo | Cambio | Líneas |
|---|---|---|
| `app/core/business/service.py` | Importar `RuleEvaluator`. Agregar parámetro `rule_evaluator` al constructor. Llamar `evaluate()` en `process()`. Almacenar `_last_constraints`. | ~10 |
| `app/api/dependencies.py` | Importar `RuleEvaluator`. Instanciar y pasar a `BusinessBrainService`. | ~3 |
| `tests/test_business_brain_service.py` | Agregar test que verifique que `_last_constraints` se genera. Los tests existentes no requieren cambios (parámetro opcional). | ~15 |

### 5.3 Archivos NO modificados

| Archivo | Razón |
|---|---|
| `app/core/business/policy.py` | No se toca en B4. Seguirá siendo usado por `DecisionEngine`. |
| `app/core/business/decision_engine.py` | No se toca en B4. Sigue llamando a `BusinessPolicy`. |
| `app/core/business/intent_analyzer.py` | B3 ya implementado. Sin cambios. |
| `app/core/business/context_interpreter.py` | B2 ya implementado. Sin cambios. |
| `app/domain/business/contracts.py` | `BusinessConstraints` ya existe desde B1. Sin cambios. |
| `app/core/conversation/*` | CE no se modifica. |
| `app/channels/*` | Canales no se modifican. |
| `tests/test_business_policy.py` | `BusinessPolicy` no cambia. |
| `tests/test_decision_engine.py` | `DecisionEngine` no cambia. |
| `tests/test_vs1_integration.py` | Flujo completo sin cambios de comportamiento observable. |

### 5.4 Dependencias

| Clase | Depende de | Existe desde |
|---|---|---|
| `RuleEvaluator` | `BusinessContext`, `BusinessIntent`, `BusinessConstraints` | B4 (nuevo) |
| `BusinessBrainService` | `RuleEvaluator` (nuevo parámetro opcional) | B1 (modificado en B4) |

---

## 6. Tests

### 6.1 Tests unitarios — RuleEvaluator (9 tests)

Nuevo archivo: `tests/test_rule_evaluator.py`

| # | Test | Descripción |
|---|---|---|
| 1 | `test_evaluate_returns_business_constraints` | Llama `evaluate()` y verifica que retorna `BusinessConstraints` |
| 2 | `test_evaluate_intent_known_passes` | `BusinessIntent(name="price_inquiry")` → BR-INTENT-KNOWN.applies=True |
| 3 | `test_evaluate_intent_unknown_fails` | `BusinessIntent(name="unknown")` → BR-INTENT-KNOWN.applies=False |
| 4 | `test_evaluate_customer_active_passes` | Con `customer_profile` poblado → BR-CUSTOMER-ACTIVE.applies=True |
| 5 | `test_evaluate_customer_active_fails` | Sin `customer_profile` → BR-CUSTOMER-ACTIVE.applies=False |
| 6 | `test_evaluate_knowledge_required_for_price_inquiry` | `name="price_inquiry"` → BR-KNOWLEDGE-REQUIRED.applies=True |
| 7 | `test_evaluate_knowledge_not_required_for_greeting` | `name="greeting"` → BR-KNOWLEDGE-REQUIRED.applies=False |
| 8 | `test_evaluate_is_feasible_true` | Intent conocido + perfil presente → `is_feasible=True` |
| 9 | `test_evaluate_is_feasible_false` | Intent unknown → `is_feasible=False` |

### 6.2 Tests de integración — BusinessBrainService

Modificar: `tests/test_business_brain_service.py`

| # | Test | Descripción |
|---|---|---|
| 1 | `test_business_brain_stores_constraints` | Crear `BusinessBrainService` con `RuleEvaluator`. Ejecutar `process()`. Verificar `service._last_constraints` no es None y es `BusinessConstraints`. |

### 6.3 Tests de regresión

| Suite | Tests | Esperado |
|---|---|---|
| `tests/test_vs1_integration.py` | 10 | ✅ Sin cambios |
| `tests/test_business_policy.py` | 4 | ✅ Sin cambios |
| `tests/test_decision_engine.py` | 2 | ✅ Sin cambios |
| `tests/test_intent_analyzer.py` | 9 | ✅ Sin cambios (B3) |
| `tests/test_context_interpreter.py` | 6 | ✅ Sin cambios (B2) |
| `tests/test_customer_profile_provider.py` | 3 | ✅ Sin cambios (B2) |
| `tests/test_business_contracts.py` | 18 | ✅ Sin cambios (B1) |
| `tests/test_business_brain_service.py` | 6 (+1 nuevo) | ✅ 5 tests existentes sin cambios |
| Otros (~100 tests de CE, KE, infra) | ~100 | ✅ Sin cambios |
| **Total** | **~160 tests** | |

### 6.4 Comandos de verificación

```bash
pytest -q                                              # 160+ passed
ruff check .                                           # 0 errors
black --check .                                        # 93 files unchanged
mypy app/                                              # 0 errors (65 source files)
pytest tests/test_vs1_integration.py -q                # 10/10 passed
```

---

## 7. Estrategia de migración

### 7.1 Principio: BusinessPolicy permanece intacto

En B4, el `BusinessPolicy` no se modifica, no se elimina, no se refactoriza. `BusinessPolicy.get_response()` sigue siendo llamado por `DecisionEngine.evaluate()` exactamente como antes.

El `RuleEvaluator` es **paralelo y adicional**: produce `BusinessConstraints` como un artefacto que el pipeline genera pero que aún no consume en la decisión.

### 7.2 Coexistencia de contratos

```
B4:      RuleEvaluator.evaluate() → BusinessConstraints (producido, no consumido)
         DecisionEngine.evaluate() → BusinessDecision (construido sin constraints)

B5:      DecisionMaker.evaluate() → BusinessDecision (consumiendo constraints)
         BusinessPolicy se elimina o refactoriza
```

### 7.3 ¿Por qué no refactorizar BusinessPolicy ya?

Refactorizar `BusinessPolicy` requeriría modificar `DecisionEngine` — y el CTO dice explícitamente "No adelantar B5". `DecisionEngine` es el proto-DecisionMaker que será refactorizado en B5.

La separación actual de responsabilidades es:

| Componente actual en B4 | Responsabilidad real |
|---|---|
| `RuleEvaluator` (nuevo) | Determina qué reglas aplican y si es viable continuar |
| `BusinessPolicy` (existente) | Asigna status, confidence, needs_knowledge por intent |
| `DecisionEngine` (existente) | Toma la decisión final (BusinessDecision) combinando policy + knowledge |

En B5, `DecisionEngine` se refactorizará para recibir `BusinessConstraints` y `BusinessIntent`, y `BusinessPolicy` se eliminará.

### 7.4 Orden de implementación

```
1. Crear RuleEvaluator con las 3 reglas base (BR-INTENT-KNOWN, BR-CUSTOMER-ACTIVE, BR-KNOWLEDGE-REQUIRED)
2. Agregar RuleEvaluator a BusinessBrainService (constructor + process)
3. Agregar RuleEvaluator a dependencies.py
4. Crear tests unitarios (9 tests)
5. Agregar test de integración en test_business_brain_service.py (1 test)
6. Ejecutar quality gates
```

---

## 8. Riesgos

### R1 — `RuleEvaluator` produce `BusinessConstraints` que nadie consume

| Escenario | Impacto | Probabilidad | Mitigación |
|---|---|---|---|
| El B4 RuleEvaluator genera `BusinessConstraints` pero la `DecisionEngine` no lo usa. El output queda en `_last_constraints` sin efecto observable. | Posible confusión: código que ejecuta pero no afecta comportamiento. Confusión sobre si el Rule Evaluator "sirve para algo". | **Alta** (es el diseño de B4) | Documentado en secciones 4.4 y 7.2. El patrón es idéntico al de B1 (BusinessIntent creado en B1, consumido en B3). El CTO lo aprobó en B1 y está documentado como estrategia de siembra de contratos. |

### R2 — Las reglas BR-XXX en B4 son demasiado simples vs. el blueprint

| Escenario | Impacto | Probabilidad | Mitigación |
|---|---|---|---|
| El blueprint menciona "Reglas del Dominio (BR-XXX), Configuración de la empresa" como entradas. B4 implementa solo 3 reglas hardcodeadas sin configuración de empresa. | El Rule Evaluator no implementa el alcance completo del blueprint. | **100%** (es intencional) | B4 establece la estructura y el patrón de reglas (rule_id, descripción, applies, reason). Nuevas reglas se agregan sin cambiar la interfaz. La configuración de empresa se implementa en un incremento futuro. |

### R3 — `BusinessIntent.name` sigue incluyendo greeting/farewell/thanks (AR-002 no resuelto)

| Escenario | Impacto | Probabilidad | Mitigación |
|---|---|---|---|
| El RuleEvaluator recibe `BusinessIntent(name="greeting")`. La regla BR-KNOWLEDGE-REQUIRED lo evalúa como `applies=False` (correcto: greeting no requiere knowledge). Pero BR-INTENT-KNOWN lo evalúa como `applies=True` (técnicamente correcto: greeting es conocido). | Las reglas funcionan correctamente incluso con intents conversacionales. No hay impacto negativo. | **100%** | El RuleEvaluator trata greeting/farewell/thanks como intents válidos (pasan BR-INTENT-KNOWN). Cuando AR-002 se resuelva, estos intents desaparecerán y las reglas se ajustarán naturalmente. |

### R4 — `BusinessContext.intent` (str) se desincroniza de `BusinessIntent.name`

| Escenario | Impacto | Probabilidad | Mitigación |
|---|---|---|---|
| `BusinessContext.intent` se setea desde `business_intent.name` en service.py. Si un desarrollador futuro cambia solo uno de los dos, hay desincronización. | El DecisionEngine (que usa `context.intent`) y el RuleEvaluator (que usa `business_intent`) ven valores distintos. | **Baja** | Ambos se asignan en la misma función `process()` usando el mismo `business_intent.name`. No hay ventana de desincronización. `model_copy(update=...)` es inmutable — se crea un nuevo context, no se modifica. |

### R5 — `_last_constraints` es un atributo público no protegido

| Escenario | Impacto | Probabilidad | Mitigación |
|---|---|---|---|
| Código externo modifica `service._last_constraints` directamente. | El BusinessConstraints almacenado ya no refleja la última evaluación. | **Baja** | El atributo se usa solo en tests para verificar que la evaluación ocurrió. En producción nadie lo lee hasta B5, donde se accederá mediante un método específico. |

### R6 — DecisionEngine sigue sin conocer BusinessConstraints

| Escenario | Impacto | Probabilidad | Mitigación |
|---|---|---|---|
| RuleEvaluator detecta `is_feasible=False` (intent unknown + sin perfil), pero DecisionEngine continúa y produce `status="accepted"`. | Decisión inconsistente: las reglas dicen "no es viable" pero el sistema responde "aceptado". | **100%** en B4 | Es el diseño de B4: el RuleEvaluator produce la advertencia, pero el DecisionMaker (B5) es quien debe actuar sobre ella. En B4 no hay cambios en el flujo de decisión. Esto está documentado en la sección 7.2 y es análogo a cómo B1 creó BusinessIntent sin que nadie lo usara. |

---

## Resumen de archivos

| Tipo | Archivos | Líneas |
|---|---|---|
| Crear (1) | `app/core/business/rule_evaluator.py` | ~60 |
| Modificar (3) | `app/core/business/service.py`, `app/api/dependencies.py`, `tests/test_business_brain_service.py` | ~28 |
| Tests nuevos (1) | `tests/test_rule_evaluator.py` | ~90 |
| No modificar | ~55 archivos (incluyendo policy.py, decision_engine.py, contracts.py) | — |

**Total líneas netas agregadas:** ~150
**Total tests:** ~160 (9 nuevos + 1 nuevo integración + 150 regresión)
**VS1:** 10/10 sin cambios

---

## READY FOR CTO REVIEW
