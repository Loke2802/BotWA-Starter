# B3 — Intent Analyzer Upgrade: Technical Plan

**Blueprint:** D-008-05 — Intent Analyzer  
**Incremento:** 3 de 7  
**Dependencias:** B1 (Domain Contracts — BusinessIntent), B2 (Context Interpreter — BusinessContext enriquecido)  
**Estado actual:** I5 cerrado, B1 cerrado, B2 cerrado

---

## 1. Estado actual del IntentClassifier

### 1.1 Código

```python
class IntentClassifier:
    _KEYWORDS: dict[str, list[str]] = {
        "greeting": ["hola", "buenos", "saludos", "hey", "buen día", "que tal"],
        "farewell": ["adiós", "chao", "hasta luego", "nos vemos", "hasta pronto"],
        "price_inquiry": ["precio", "cuánto", "costo", "tarifa", "valor", "cuesta"],
        "thanks": ["gracias", "agradezco", "thanks", "thank you"],
        "support": ["ayuda", "soporte", "problema", "error", "falla", "no funciona"],
    }

    def classify(self, content: str) -> str:
        # 1. empty → "unknown"
        # 2. if "?" in text → match keywords or "question"
        # 3. else → match keywords or "unknown"
```

**Archivo:** `app/core/business/intent_classifier.py` (26 líneas, 0 dependencias externas)

### 1.2 Cómo se usa

`BusinessBrainService.process()` (service.py:29-31):
```python
context = self._enrich_context(request)           # B2
intent = self._intent_classifier.classify(request.content)  # str → str
context = context.model_copy(update={"intent": intent})
```

### 1.3 Consumidores del output (`intent: str`)

| Componente | Cómo usa `intent` | Archivo |
|---|---|---|
| `BusinessContext.intent` | Campo `str` del contexto enriquecido | `contracts.py:20` |
| `DecisionEngine.evaluate()` | Lee `context.intent` para pasarlo a `BusinessPolicy` | `decision_engine.py:10` |
| `BusinessPolicy.get_response()` | Dispatchea por `intent` key → `{status, confidence, needs_knowledge}` | `policy.py:7` |
| `BusinessDecision.intent` | Copia `context.intent` al resultado | `decision_engine.py:13` |
| `ResponseComposer.compose()` | Usa `decision.intent` para seleccionar template y tone | `response_composer.py:39-42` |
| `KnowledgeService.query()` | Recibe `intent` en `KnowledgeQuery` | `service.py:42` |
| `EventPublisher.publish()` | `intent` viaja como kwarg en eventos | `service.py:34,45,48,57,59` |

### 1.4 Tests existentes

| Archivo | Tests | ¿Qué cubren? |
|---|---|---|
| `tests/test_intent_classifier.py` | 8 | greeting, farewell, price_inquiry, thanks, support, question-with-keyword, question-without-keyword, unknown, empty |
| `tests/test_business_brain_service.py` | 5 | greeting, unknown, price_inquiry+knowledge, knowledge-fallback, context-interpreter |
| `tests/test_vs1_integration.py` | 10 | Flujo completo endpoint (greeting, farewell, horario, envío, pago, fallback, unknown, empty, price_inquiry) |

### 1.5 Desviaciones respecto al Blueprint D-008-05

| Dimensión | Blueprint D-008-05 | Código actual | Severidad |
|---|---|---|---|
| **Nombre** | Intent Analyzer | `IntentClassifier` | Baja (cosmético) |
| **Entrada** | `Business Context` | `str` (texto crudo) | **Alta** |
| **Salida** | `Business Intent` (objeto de dominio) | `str` | **Alta** |
| **Intents clasificados** | Business intents: price_inquiry, support, question | greeting, farewell, thanks, price_inquiry, support, question, unknown | **Media** (contaminación con topics + "thanks" no es business intent) |
| **Principio** | "No interpreta lenguaje directamente" | Keyword matching directo sobre texto crudo | **Media** |
| **Contexto** | Recibe Business Context enriquecido | Trabaja sobre texto sin estado, perfil, ni metadata | **Alta** |

### 1.6 Dependencias existentes del `IntentClassifier`

```
IntentClassifier (no dependencias externas)
    ↑
BusinessBrainService (dependencia directa: self._intent_classifier)
    ↑
dependencies.py (instancia: IntentClassifier())
    ↑
MessageRouter → ConversationService (no sabe que existe)
    ↑
Endpoint /messages
```

### 1.7 AR-002 y la frontera Topic vs Intent

AR-002 establece:

| Concepto | Topic (ENG-002) | Intent (ENG-001) |
|---|---|---|
| greeting | ✅ Topic Detector lo detecta | ❌ No es Business Intent |
| farewell | ✅ Topic Detector lo detecta | ❌ No es Business Intent |
| price_inquiry | ✅ (información de producto) | ✅ Business Intent |
| support | ✅ (soporte técnico) | ✅ Business Intent |
| question | ✅ (información general) | ✅ Business Intent |
| thanks | ❌ No es topic ni intent | ⚠️ Es acknowledgment conversacional |

**Resolución completa de AR-002** requeriría modificar el Conversation Engine (TopicDetector) para absorber greeting/farewell/thanks. Esto **está fuera del alcance de B3** por la restricción "No modificar Conversation Engine". El CTO lo confirma: "No resolver todavía AR-002 si requiere cambios fuera del alcance."

**Implicación concreta:** Los intents greeting/farewell/thanks **se mantienen** en el IntentAnalyzer durante B3. El sistema sigue clasificándolos y el pipeline los procesa igual que hoy. La remoción ocurrirá en un incremento futuro que incluya al CE.

---

## 2. Diseño objetivo

### 2.1 Nombre y responsabilidad

```
INTENT ANALYZER (D-008-05)

Responsabilidad: Determinar qué quiere lograr realmente el cliente.

Principios:
- No interpreta lenguaje directamente (usa Business Context enriquecido)
- No aplica reglas de negocio (es responsabilidad del Rule Evaluator — B4)
- No toma decisiones (es responsabilidad del Decision Maker — B5)
- Solo el Intent Analyzer genera un Business Intent

Entrada:  Business Context (desde Context Interpreter — B2)
Salida:   Business Intent (contrato creado en B1)
```

### 2.2 Entrada: `BusinessContext`

```python
class BusinessContext(BaseModel):
    request: BusinessRequest              # request original
    intent: str = ""                      # ← se sigue poblando por backward compat
    customer_profile: dict[str, object]   # perfil del cliente (B2)
    channel_metadata: dict[str, object]   # metadata del canal (B2)
```

El IntentAnalyzer recibe el contexto completo. Internamente puede usar cualquier campo (`request.content`, `customer_profile`, `channel_metadata`) para mejorar la clasificación. En B3 se usa `request.content` como fuente principal, pero la **interfaz** ya acepta el contexto completo para evoluciones futuras.

### 2.3 Salida: `BusinessIntent`

```python
class BusinessIntent(BaseModel):
    model_config = ConfigDict(frozen=True)
    name: str            # "greeting" | "farewell" | "price_inquiry" | "thanks" | "support" | "question" | "unknown"
    confidence: str = "medium"  # "high" | "medium" | "low"
```

Contrato exactamente como fue creado en B1. No se modifica. El campo `name` mantiene los mismos valores que retornaba `IntentClassifier.classify()` para asegurar compatibilidad total con los consumidores downstream.

### 2.4 Interfaz

```python
class IntentAnalyzer:
    _KEYWORDS: dict[str, list[str]] = { ... }  # misma taxonomía que IntentClassifier

    def analyze(self, context: BusinessContext) -> BusinessIntent:
        """Analiza el Business Context y produce un Business Intent."""
        content = context.request.content       # fuente principal en B3
        # (idéntica lógica de matching que IntentClassifier.classify)
        name = self._classify(content)
        confidence = self._compute_confidence(name)
        return BusinessIntent(name=name, confidence=confidence)

    def _classify(self, content: str) -> str:
        """Idéntico algoritmo al IntentClassifier.classify()."""

    def _compute_confidence(self, name: str) -> str:
        """Mapeo intent → confianza (idéntico a BusinessPolicy actual)."""
```

### 2.5 `BusinessIntent.confidence`

El IntentAnalyzer produce `BusinessIntent.confidence` como la confianza **en la clasificación del intent**. Este valor es independiente de `BusinessDecision.confidence` (confianza en la decisión final).

| Intent | confidence |
|---|---|
| greeting | high |
| farewell | high |
| price_inquiry | medium |
| thanks | high |
| support | medium |
| question | medium |
| unknown | low |

### 2.6 Responsabilidades explícitas

**SÍ hace:**
- Recibir `BusinessContext` como entrada
- Analizar `context.request.content` (y en el futuro: perfil, metadata)
- Producir `BusinessIntent` como objeto de dominio
- Poblar `BusinessIntent.name` con el intent identificado
- Poblar `BusinessIntent.confidence` con la confianza de clasificación
- Soportar todos los intents actuales (incluyendo greeting/farewell/thanks) para no romper AR-002

**NO hace:**
- NO modifica `BusinessContext` (el caller hace `model_copy(update=...)`)
- NO aplica reglas de negocio (B4)
- NO toma decisiones (B5)
- NO interactúa con Knowledge Engine
- NO publica eventos
- NO depende del Conversation Engine

---

## 3. Estrategia de migración

### 3.1 Principio: coexistencia sin refactor masivo

El cambio se limita a **un nuevo archivo + modificaciones localizadas**. No se refactoriza `DecisionEngine`, `BusinessPolicy`, `ResponseComposer` ni ningún componente del CE.

### 3.2 Pipeline antes de B3

```
BusinessBrainService.process(request):
    1. ContextInterpreter.enrich(request)              → BusinessContext (intent="")
    2. IntentClassifier.classify(request.content)      → str
    3. context = context.model_copy(update={"intent": str})
    4. DecisionEngine.evaluate(context)                → BusinessDecision
```

### 3.3 Pipeline después de B3

```
BusinessBrainService.process(request):
    1. ContextInterpreter.enrich(request)              → BusinessContext (intent="")
    2. IntentAnalyzer.analyze(context)                 → BusinessIntent
    3. context = context.model_copy(update={
           "intent": business_intent.name              ← mismo str de siempre
       })
    4. DecisionEngine.evaluate(context)                → BusinessDecision (sin cambios)
```

**Cambio exacto en service.py (líneas 29-31):**
```python
# ANTES
intent = self._intent_classifier.classify(request.content)
context = context.model_copy(update={"intent": intent})

# DESPUÉS
business_intent = self._intent_analyzer.analyze(context)
context = context.model_copy(update={"intent": business_intent.name})
```

### 3.4 Compatibilidad total garantizada

| Aspecto | Antes | Después | ¿Ruptura? |
|---|---|---|---|
| `context.intent` | `str` con nombre del intent | `str` con nombre del intent | **No** — mismo valor |
| `decision.intent` | `str` del classifier | `str` del `business_intent.name` | **No** — mismo valor |
| `BusinessPolicy.get_response(intent)` | Recibe `str` | Recibe `str` | **No** |
| `ResponseComposer._TEMPLATES[key]` | Key es `str` | Key es `str` | **No** |
| `KnowledgeService.query()` | Recibe `intent: str` | Recibe `intent: str` | **No** |
| Eventos publicados | `intent="greeting"` | `intent="greeting"` | **No** |
| Tests existentes | Todos pasan | Todos pasan | **No** |

### 3.5 Coexistencia de contratos (intent: str vs BusinessIntent)

```
B3:      IntentAnalyzer.analyze() → BusinessIntent
         context.intent = business_intent.name  ← str para consumidores legacy

B4 (Rule Evaluator):  recibe BusinessIntent + BusinessContext
B5 (Decision Maker):  recibe BusinessIntent + BusinessConstraints
Bn+:                  context.intent (str) se depreca y eventualmente se elimina
```

El `BusinessIntent` está disponible en el `BusinessBrainService.process()` para ser usado por incrementos futuros (B4+). Hoy solo se usa su `.name` para poblar el `context.intent` legacy.

### 3.6 ¿Qué pasa con el IntentClassifier original?

Se elimina. El reemplazo es completo:
- `IntentAnalyzer` tiene idéntica taxonomía de keywords
- Idéntico algoritmo de matching
- Mismos nombres de intent (greeting, farewell, thanks, etc.)
- Solo cambia la envoltura: input es `BusinessContext`, output es `BusinessIntent`

**No hay desactivación gradual.** Se reemplaza en un solo commit porque:
- Es un cambio de interfaz, no de lógica
- Todos los tests del classifier se replican en el nuevo analyzer
- No hay código externo que importe `IntentClassifier` directamente (solo `BusinessBrainService` + `dependencies.py`)

---

## 4. Cambios necesarios

### 4.1 Archivos nuevos (1)

| Archivo | Clase | Líneas | Propósito |
|---|---|---|---|
| `app/core/business/intent_analyzer.py` | `IntentAnalyzer` | ~35 | Reemplazo completo de `IntentClassifier` |

### 4.2 Archivos eliminados (1)

| Archivo | Razón |
|---|---|
| `app/core/business/intent_classifier.py` | Reemplazado por `IntentAnalyzer` |

### 4.3 Archivos modificados (3)

| Archivo | Cambio |
|---|---|
| `app/core/business/service.py` | `IntentClassifier` → `IntentAnalyzer`. `classify(content)` → `analyze(context)`. Parámetro renombrado de `intent_classifier` a `intent_analyzer`. |
| `app/api/dependencies.py` | `IntentClassifier()` → `IntentAnalyzer()`. Parámetro renombrado en constructor de `BusinessBrainService`. |
| `tests/test_intent_classifier.py` | **Renombrar** a `test_intent_analyzer.py` con los mismos 8 tests adaptados a la nueva interfaz. |

### 4.4 Archivos NO modificados

| Archivo | Razón |
|---|---|
| `app/core/business/decision_engine.py` | No depende de `IntentClassifier`. Usa `context.intent` (str). Sin cambios. |
| `app/core/business/policy.py` | No depende de `IntentClassifier`. Usa `intent` (str). Sin cambios. |
| `app/core/conversation/response_composer.py` | Usa `decision.intent` (str). Sin cambios. |
| `app/core/conversation/router.py` | No depende de `IntentClassifier`. Sin cambios. |
| `app/core/conversation/service.py` | No depende de `IntentClassifier`. Sin cambios. |
| `app/domain/business/contracts.py` | `BusinessIntent` ya existe desde B1. Sin cambios. |
| `tests/test_business_brain_service.py` | Los tests existentes crean `BusinessBrainService` con `intent_classifier=...`. Se actualiza el nombre del parámetro. |
| `tests/test_vs1_integration.py` | Sin cambios (flujo completo, no conoce al classifier). |
| `tests/test_business_policy.py` | Sin cambios. |
| `tests/test_decision_engine.py` | Sin cambios. |

### 4.5 Dependencias nuevas y eliminadas

| Dependencia | Tipo | Estado |
|---|---|---|
| `IntentAnalyzer` → `BusinessContext` | Import | **Nueva** (antes `IntentClassifier` no importaba nada) |
| `IntentAnalyzer` → `BusinessIntent` | Import | **Nueva** (contrato de B1) |
| `BusinessBrainService` → `IntentAnalyzer` | Constructor param | **Reemplaza** a `IntentClassifier` |
| `dependencies.py` → `IntentAnalyzer` | Import + instancia | **Reemplaza** a `IntentClassifier` |

---

## 5. Tests

### 5.1 Taxonomía completa de tests

| Grupo | Archivo | Tests | Nuevos/Modificados |
|---|---|---|---|
| Unitarios — IntentAnalyzer | `tests/test_intent_analyzer.py` | 8 | **Nuevos** (renombrado desde `test_intent_classifier.py`) |
| Integración — BusinessBrainService | `tests/test_business_brain_service.py` | 5 | **Modificados** (cambio de parámetro constructor) |
| Integración — VS1 | `tests/test_vs1_integration.py` | 10 | **Sin cambios** |
| Contratos | `tests/test_business_contracts.py` | 18 | **Sin cambios** |
| Otros BB | `tests/test_business_policy.py`, `tests/test_decision_engine.py` | 6 | **Sin cambios** |
| CE | Todos los de Conversation Engine | ~100 | **Sin cambios** |

### 5.2 Tests unitarios — IntentAnalyzer (8 tests, renombrados desde classifier)

Modificar `tests/test_intent_classifier.py` → `tests/test_intent_analyzer.py`

Todos los tests actuales se mantienen con la misma lógica pero adaptados a la nueva interfaz:

| # | Test actual (IntentClassifier) | Nuevo test (IntentAnalyzer) | Cambio |
|---|---|---|---|
| 1 | `test_classify_greeting` | `test_analyze_greeting` | `classify("Hola...")` → `analyze(context)` |
| 2 | `test_classify_farewell` | `test_analyze_farewell` | ídem |
| 3 | `test_classify_price_inquiry` | `test_analyze_price_inquiry` | ídem |
| 4 | `test_classify_thanks` | `test_analyze_thanks` | ídem |
| 5 | `test_classify_support` | `test_analyze_support` | ídem |
| 6 | `test_classify_question_with_keyword` | `test_analyze_question_with_keyword` | ídem |
| 7 | `test_classify_question_without_keyword` | `test_analyze_question_without_keyword` | ídem |
| 8 | `test_classify_unknown` | `test_analyze_unknown` | ídem |
| 9 | `test_classify_empty_returns_unknown` | `test_analyze_empty_returns_unknown` | ídem |

Cada test crea un `BusinessRequest` con el `content` de prueba, luego un `BusinessContext(request=...)`, y llama a `analyzer.analyze(context)`. Verifica `business_intent.name` en vez del `str` directo.

**Ejemplo:**
```python
# ANTES
def test_classify_greeting():
    classifier = IntentClassifier()
    assert classifier.classify("Hola, buenos días") == "greeting"

# DESPUÉS
def test_analyze_greeting():
    analyzer = IntentAnalyzer()
    request = BusinessRequest(
        content="Hola, buenos días",
        customer_id="c1", company_id="co1", conversation_id=uuid4(),
    )
    context = BusinessContext(request=request)
    result = analyzer.analyze(context)
    assert result.name == "greeting"
    assert isinstance(result, BusinessIntent)
```

### 5.3 Tests de integración — BusinessBrainService (modificar)

Cambiar el nombre del parámetro en los 5 tests existentes:

```python
# ANTES
service = BusinessBrainService(
    intent_classifier=intent_classifier,
    ...
)

# DESPUÉS
service = BusinessBrainService(
    intent_analyzer=intent_analyzer,
    ...
)
```

### 5.4 Tests de regresión

| Suite | Tests | Esperado |
|---|---|---|
| `tests/test_vs1_integration.py` | 10 | ✅ Todos pasan sin cambios |
| `tests/test_conversation_service.py` | 1 | ✅ Sin cambios |
| `tests/test_conversation_state*.py` | 16 | ✅ Sin cambios |
| `tests/test_conversation_context_builder.py` | 8 | ✅ Sin cambios |
| `tests/test_topic_detector.py` | 11 | ✅ Sin cambios |
| `tests/test_channel_adapter.py` | 5 | ✅ Sin cambios |
| `tests/test_response_composer.py` | 7 | ✅ Sin cambios |
| `tests/test_customer_profile_provider.py` | 3 | ✅ Sin cambios |
| `tests/test_context_interpreter.py` | 6 | ✅ Sin cambios |
| `tests/test_business_contracts.py` | 18 | ✅ Sin cambios |
| `tests/test_business_policy.py` | 4 | ✅ Sin cambios |
| `tests/test_decision_engine.py` | 2 | ✅ Sin cambios |
| `tests/test_knowledge*.py` | ~47 | ✅ Sin cambios |
| `tests/test_infrastructure*.py` | ~10 | ✅ Sin cambios |
| **Total regresión** | **~156 tests** | |

### 5.5 Comandos de verificación

```bash
pytest -q                                              # 154+ passed
ruff check .                                           # 0 errors
black --check .                                        # 93 files unchanged
mypy app/                                              # 0 errors (65 source files)
pytest tests/test_vs1_integration.py -q                # 10/10 passed
```

---

## 6. Riesgos

### R1 — Ruptura silenciosa por nombre de parámetro en constructor

| Escenario | Impacto | Probabilidad | Mitigación |
|---|---|---|---|
| `BusinessBrainService` cambia el nombre del parámetro constructor de `intent_classifier` a `intent_analyzer`. Cualquier código externo (tests, scripts, dependencias.py) que use el nombre antiguo falla en runtime con TypeError. | Error de importación o TypeError difícil de depurar porque el error está en el constructor, no en el pipeline. | **Baja** (solo 3 lugares usan el constructor: `dependencies.py` y `test_business_brain_service.py`). | Todos los lugares que instancian `BusinessBrainService` están identificados y se modifican en el mismo commit. `ruff`/`mypy` detectan argumentos no válidos en constructores. |

### R2 — `BusinessIntent` es un objeto congelado, no se puede modificar después de creado

| Escenario | Impacto | Probabilidad | Mitigación |
|---|---|---|---|
| Si en el futuro el pipeline necesita modificar `BusinessIntent` después de creado, el `model_config = ConfigDict(frozen=True)` lo impide. | Error de runtime si alguien intenta `business_intent.name = "..."`. | **Nula para B3** (no se modifica después de creado). | El `BusinessIntent` se crea en el `IntentAnalyzer.analyze()` y viaja inmutable por el resto del pipeline. No hay modificación posterior. |

### R3 — `BusinessIntent` coexiste con `context.intent: str` (dos representaciones del mismo dato)

| Escenario | Impacto | Probabilidad | Mitigación |
|---|---|---|---|
| `BusinessIntent.name` y `context.intent` pueden desincronizarse. Por ejemplo, si un componente futuro modifica `context.intent` pero no el `BusinessIntent` correspondiente. | Comportamiento inconsistente: un componente lee `business_intent.name = "price_inquiry"` y otro lee `context.intent = "support"`. | **Media** (en el futuro). | En B3 ambos valores provienen del mismo `IntentAnalyzer.analyze()` y se asignan en la misma línea de `service.py`. No hay ventana de desincronización. En incrementos futuros (B4+), cuando se elimine `context.intent`, este riesgo desaparece. |

### R4 — Los 8 tests del classifier actual prueban la interfaz antigua (`classifier.classify(str)`) y deben migrar

| Escenario | Impacto | Probabilidad | Mitigación |
|---|---|---|---|
| Si un test del classifier se migra incorrectamente (ej: se olvida crear el contexto), el test falla. | Falso positivo o negativo durante la migración. | **Media** | Los 8 tests se migran uno a uno en el mismo commit. La aserción cambia de `== "greeting"` a `.name == "greeting"` y se verifica `isinstance(result, BusinessIntent)`. La lógica de matching es idéntica. |

### R5 — Diferencia semántica: `IntentAnalyzer` vs `IntentClassifier` en eventos publicados

| Escenario | Impacto | Probabilidad | Mitigación |
|---|---|---|---|
| Los eventos publicados por `BusinessBrainService` incluyen `intent` como kwarg. Si el nombre cambia (ej: "greeting" → "conversational"), los consumidores de eventos se rompen. | Ruptura en `BusinessEventPublisher` o en código que suscribe eventos por nombre de intent. | **Baja** (en B3 no cambia la taxonomía de intents). | B3 mantiene exactamente los mismos nombres de intent que antes. `BusinessIntent.name` tiene los mismos valores que retornaba `IntentClassifier.classify()`. |

### R6 — AR-002 no se resuelve (greeting/farewell/thanks siguen siendo intents)

| Escenario | Impacto | Probabilidad | Mitigación |
|---|---|---|---|
| El IntentAnalyzer sigue clasificando greeting/farewell/thanks como intents. Esto es una desviación del blueprint que se arrastra desde la implementación original. | El Business Brain procesa intents conversacionales que según AR-002 debería ignorar. No hay impacto funcional porque el pipeline los maneja correctamente. | **100%** (es intencional en B3). | Documentado en sección 1.7. Se resolverá en incremento futuro que incluya modificación al CE (TopicDetector). |

### R7 — El `IntentAnalyzer` importa `BusinessContext` y `BusinessIntent` que antes no se usaban en el classifier

| Escenario | Impacto | Probabilidad | Mitigación |
|---|---|---|---|
| Si `BusinessContext` o `BusinessIntent` cambian en incrementos futuros, el `IntentAnalyzer` podría necesitar actualización. | Dependencia de contracts que el classifier no tenía. | **Baja** (los contratos existen desde B1/B2 y están estabilizados). | Los contratos de dominio son frozen y estables. Cualquier cambio futuro sería un campo nuevo opcional, no una ruptura. |

---

## Resumen de archivos

| Tipo | Archivos | Líneas |
|---|---|---|
| Crear (1) | `app/core/business/intent_analyzer.py` | ~35 |
| Eliminar (1) | `app/core/business/intent_classifier.py` | ~-26 |
| Modificar (2) | `app/core/business/service.py`, `app/api/dependencies.py` | ~10 total |
| Renombrar (1) | `tests/test_intent_classifier.py` → `tests/test_intent_analyzer.py` | 0 (mismo contenido adaptado) |
| Modificar tests (1) | `tests/test_business_brain_service.py` | ~5 (renombrar parámetro) |
| No modificar | ~50 archivos | — |

**Total líneas netas agregadas:** ~20 (+35 analyzer, -26 classifier, +10 modificaciones, +5 tests)
**Total tests:** 154+ (mismos tests + adaptación de interfaz)
**VS1:** 10/10 sin cambios

---

## READY FOR CTO REVIEW
