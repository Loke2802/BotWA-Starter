# B1 — Business Domain Contracts: Technical Plan

**Blueprint:** D-008 — Business Brain Engine  
**Incremento:** 1 de 7  
**Dependencias:** Ninguna (es el primer incremento del Business Brain)  
**Referencia:** ENG001_BUSINESS_BRAIN_GAP_ANALYSIS.md (sección 6 — B1)

---

## 1. Objetos de dominio faltantes

### 1.1 Blueprint vs código actual

| Objeto blueprint | ¿Existe? | Estado actual |
|---|---|---|
| `Business Context` | Sí | `BusinessContext` — solo `request` + `intent: str` |
| `Business Intent` | **No** | El intent es un `str` dentro de `BusinessContext` |
| `Business Constraints` | **No** | No existe representación de restricciones |
| `Business Options` | **No** | No existe representación de alternativas |
| `Business Decision` | Sí | `BusinessDecision` — sin `ActionPlan` asociado |
| `Business Action Plan` | **No** | No existe plan de acción |
| `Business Event` | **No** | Existe `BusinessEventModel` ORM, no contrato de dominio |

### 1.2 Nuevos contratos a crear

#### BusinessIntent

Representa el objetivo de negocio identificado (D-008-05).

```python
class BusinessIntent(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str                              # "price_inquiry" | "support" | "question"
    confidence: str = "medium"             # "high" | "medium" | "low"
```

- **name:** El nombre del intent de negocio (solo business intents, no topics)
- **confidence:** Nivel de confianza en la clasificación
- **Propósito:** Reemplazar el `str` actual como tipo formal cuando se refactorice el IntentAnalyzer (B3)

#### BusinessConstraint + BusinessConstraints

Representa las restricciones y condiciones válidas para el caso de negocio (D-008-06).

```python
class BusinessConstraint(BaseModel):
    model_config = ConfigDict(frozen=True)

    rule_id: str                           # identificador de la regla de negocio
    description: str                       # descripción legible
    applies: bool                          # si la regla aplica en este caso
    reason: str = ""                       # justificación


class BusinessConstraints(BaseModel):
    model_config = ConfigDict(frozen=True)

    constraints: list[BusinessConstraint] = Field(default_factory=list)
    is_feasible: bool = True               # si es viable continuar
```

- **Propósito:** Output formal del RuleEvaluator (B4). Antes de decidir, el sistema sabe qué está permitido.
- **`is_feasible`:** Si es `False`, la decisión debe ser "rejected" o "escalated". El DecisionMaker no debería continuar.

#### BusinessOption + BusinessOptions

Representa las alternativas válidas que el DecisionMaker evalúa antes de decidir (D-008-07).

```python
class BusinessOption(BaseModel):
    model_config = ConfigDict(frozen=True)

    action: str                            # descripción de la alternativa
    score: float = 0.0                     # puntuación según criterios de negocio
    confidence: str = "low"                # confianza en esta alternativa
    rationale: str = ""                    # justificación textual


class BusinessOptions(BaseModel):
    model_config = ConfigDict(frozen=True)

    options: list[BusinessOption] = Field(default_factory=list)
    selected_index: int | None = None      # índice de la opción seleccionada (si se decidió)
```

- **Propósito:** El DecisionMaker construye opciones antes de decidir. `selected_index` queda `None` hasta que se decida.
- **Nota:** BusinessOptions NO referencia a BusinessDecision para evitar acoplamiento circular. Las opciones son candidatos, no decisiones finales.

#### ActionStep + BusinessActionPlan

Representa el plan de ejecución de una decisión (D-008-08).

```python
class ActionStep(BaseModel):
    model_config = ConfigDict(frozen=True)

    action: str                            # "respond" | "escalate" | "wait" | "query_knowledge" | ...
    target: str = ""                       # destinatario o sistema destino
    parameters: dict[str, object] = Field(default_factory=dict)
    order: int = 0                         # orden de ejecución


class BusinessActionPlan(BaseModel):
    model_config = ConfigDict(frozen=True)

    steps: list[ActionStep] = Field(default_factory=list)
    total_steps: int = 0
```

- **Propósito:** Output formal del ActionPlanner (B6). Describe qué acciones ejecutar.
- **`action`:** Valores iniciales predefinidos: `"respond"` (responder al cliente), `"escalate"` (escalar a humano), `"wait"` (esperar más información), `"query_knowledge"` (consultar knowledge base).
- **`total_steps`:** Conveniencia, puede derivarse de `len(steps)`.

#### BusinessEvent

Representa un evento de negocio publicado por el pipeline (D-008-09).

```python
class BusinessEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    event_type: str                        # "objetivo_identificado" | "respuesta_generada" | ...
    source: str                            # "business_brain" | "conversation_engine"
    payload: dict[str, object] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    conversation_id: UUID | None = None
```

- **Propósito:** Representar formalmente los eventos de negocio. El `BusinessEventPublisher` será refactorizado en B7 para usar este contrato.
- **Nota:** Existe `BusinessEventModel` ORM en `app/infrastructure/models/business_event.py`. Este contrato es independiente del ORM. La relación entre ambos se establecerá en B7.

---

## 2. Archivos nuevos

| Archivo | Contenido | Líneas |
|---|---|---|
| `app/domain/business/contracts.py` | **Modificado** — se agregan 7 nuevas clases al archivo existente | ~60 adicionales |

**No se crean archivos nuevos.** Todos los contratos se agregan al archivo `contracts.py` existente. Esto evita crear abstracciones innecesarias y mantiene el patrón actual del proyecto (todos los contratos de negocio en un solo archivo).

---

## 3. Archivos modificados

| Archivo | Cambio | Líneas |
|---|---|---|
| `app/domain/business/contracts.py` | Agregar `BusinessIntent`, `BusinessConstraint`, `BusinessConstraints`, `BusinessOption`, `BusinessOptions`, `ActionStep`, `BusinessActionPlan`, `BusinessEvent` | ~60 |
| `app/domain/business/__init__.py` | Sin cambios (no es necesario) | 0 |

**No se modifican archivos fuera de `app/domain/business/`.**

---

## 4. Compatibilidad con el código existente

### 4.1 Cero modificaciones a contratos existentes

Los contratos actuales (`BusinessRequest`, `BusinessContext`, `BusinessDecision`) **no se tocan**:

```python
# EXISTENTE — NO SE MODIFICA
class BusinessDecision(BaseModel):
    status: str
    intent: str                   # ← sigue siendo str por ahora
    confidence: str
    needs_knowledge: bool = False
    knowledge_content: str | None = None
```

Los nuevos contratos (`BusinessIntent`, `BusinessConstraints`, etc.) se agregan al mismo archivo sin alterar ninguna línea existente. Esto garantiza:

- **0 archivos rotos** en CE, BB, KE, tests, o infraestructura.
- **0 cambios de import** en ningún archivo existente.
- **0 cambios de lógica** en ningún componente.
- **VS1 intacto** — los nuevos contratos no se usan en el pipeline actual.

### 4.2 Las 4 importaciones existentes siguen funcionando

| Archivo | Importa | ¿Se rompe? |
|---|---|---|
| `app/core/business/service.py` | `BusinessContext`, `BusinessDecision`, `BusinessRequest` | **No** — sin cambios |
| `app/core/business/decision_engine.py` | `BusinessContext`, `BusinessDecision` | **No** — sin cambios |
| `app/core/conversation/router.py` | `BusinessDecision`, `BusinessRequest` | **No** — sin cambios |
| `app/core/conversation/response_composer.py` | `BusinessDecision` | **No** — sin cambios |

---

## 5. Estrategia de migración

### 5.1 Coexistencia

| Incremento | Contrato usado | Contrato creado |
|---|---|---|
| **B1** (actual) | `intent: str` | `BusinessIntent` existe pero NO se usa |
| **B3** (IntentAnalyzer refactor) | `intent: str` + `BusinessIntent` | El IntentAnalyzer produce ambos |
| **B5+** (post-IntentAnalyzer) | Solo `BusinessIntent` | `intent: str` se depreca |

Los contratos nuevos son **semilla para incrementos futuros**. Nadie los consume todavía. No hay código muerto porque no hay código que los referencie — son definiciones de tipo.

### 5.2 Orden de adopción por componente

| Nuevo contrato | Incremento que lo usará |
|---|---|
| `BusinessIntent` | B3 — IntentAnalyzer refactor |
| `BusinessConstraint`, `BusinessConstraints` | B4 — RuleEvaluator |
| `BusinessOption`, `BusinessOptions` | B5 — DecisionMaker |
| `ActionStep`, `BusinessActionPlan` | B6 — ActionPlanner |
| `BusinessEvent` | B7 — EventPublisher formal |

### 5.3 Zero-debt guarantee

Los contratos se crean en B1. Si el CTO decide no continuar con B2-B7, los contratos existen pero no afectan el comportamiento. No hay código inactivo que consuma recursos, no hay imports huérfanos, no hay lógica condicional.

---

## 6. Tests

### 6.1 Tests unitarios — nuevos contratos

Modificar: `tests/test_business_contracts.py` (agregar tests al archivo existente)

| Test | Descripción |
|---|---|
| `test_business_intent_holds_name_and_confidence` | Crear `BusinessIntent(name="price_inquiry", confidence="high")` |
| `test_business_intent_default_confidence` | `BusinessIntent(name="question")` → confidence="medium" |
| `test_business_intent_is_frozen` | Intentar modificar → `ValidationError` |
| `test_business_constraint_holds_rule_id_and_status` | `BusinessConstraint(rule_id="BR-001", description="test", applies=True)` |
| `test_business_constraints_default_is_feasible` | `BusinessConstraints()` → `is_feasible=True`, constraints `[]` |
| `test_business_constraints_with_multiple_rules` | Agregar 2 constraints, verificar lista |
| `test_business_option_holds_action_and_score` | `BusinessOption(action="respond", score=0.95)` |
| `test_business_options_selected_index_default_none` | `BusinessOptions()` → `selected_index is None` |
| `test_action_step_holds_action_and_order` | `ActionStep(action="respond", order=1)` |
| `test_business_action_plan_holds_steps` | Crear con 2 steps, verificar `total_steps` |
| `test_business_event_holds_type_and_source` | `BusinessEvent(event_type="test", source="bb")` |
| `test_business_event_generates_timestamp` | Timestamp se genera automáticamente |

**Total tests nuevos:** ~12

### 6.2 Tests de regresión (sin cambios)

| Archivo | Tests |
|---|---|
| `tests/test_vs1_integration.py` | 10 tests |
| `tests/test_conversation_endpoint.py` | 2 tests |
| `tests/test_conversation_service.py` | 1 test |
| `tests/test_business_contracts.py` | 5 tests (existentes, sin modificar) |
| `tests/test_business_policy.py` | 4 tests |
| `tests/test_business_brain_service.py` | 4 tests |
| `tests/test_decision_engine.py` | 2 tests |
| `tests/test_intent_classifier.py` | 8 tests |
| Otros | ~92 tests |
| Total regresión | **~128 tests** |

---

## 7. Riesgos

### R1 — Contratos creados pero no usados (código muerto temporal)

| Escenario | Impacto | Probabilidad | Mitigación |
|---|---|---|---|
| Los contratos existen pero ningún código los referencia hasta B3+ | Posible confusión: "¿esto se usa?" | **Alta** (es el diseño) | Documentado en el plan (sección 5.2). Cada contrato tiene un consumidor planeado en incrementos futuros. No hay código muerto — son definiciones de tipo. |

### R2 — `BusinessIntent.confidence` duplica información con `BusinessDecision.confidence`

| Escenario | Impacto | Probabilidad | Mitigación |
|---|---|---|---|
| Durante B3, el IntentAnalyzer produce `BusinessIntent(confidence="high")` y luego el ConfidenceEvaluator produce `BusinessDecision(confidence="high")` | Duplicación de datos de confianza en dos niveles distintos | **Media** | No es duplicación: `BusinessIntent.confidence` es la confianza en la clasificación del intent. `BusinessDecision.confidence` es la confianza en la decisión final. Son conceptos distintos en el blueprint (D-008-05 vs D-008-07). |

### R3 — `BusinessConstraints` cambia de forma cuando se implemente RuleEvaluator

| Escenario | Impacto | Probabilidad | Mitigación |
|---|---|---|---|
| Al implementar B4, se descubre que `BusinessConstraints` necesita campos adicionales | El contrato de B1 queda incompleto | **Baja** | El diseño actual es mínimo y extensible. Los campos `constraints: list[BusinessConstraint]` y `is_feasible` cubren el caso base. Nuevos campos se agregan en B4. Pydantic permite campos adicionales sin romper B1. |

### R4 — `BusinessEvent` duplica `BusinessEventModel` ORM

| Escenario | Impacto | Probabilidad | Mitigación |
|---|---|---|---|
| El contrato de dominio `BusinessEvent` coexiste con `BusinessEventModel` ORM sin relación explícita | Dos representaciones del mismo concepto | **Media** | Es intencional. El contrato de dominio es independiente del ORM. La relación entre ambos se establecerá en B7 cuando se refactorice el EventPublisher. ADR-005 (Domain Object Ownership) respalda esta separación. |

---

## Resumen de archivos

| Tipo | Archivos | Líneas |
|---|---|---|
| Modificar (1) | `app/domain/business/contracts.py` | ~60 adicionales |
| Tests modificar (1) | `tests/test_business_contracts.py` | ~80 adicionales |
| Regresión | ~128 tests | Sin cambios |
