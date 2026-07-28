# I4 — Response Composer: Technical Plan

**Implementation status:** Implemented / Closed  
**Closure evidence:** `app/core/conversation/response_composer.py`, `app/domain/conversation/response.py`, `BusinessDecision` without response text ownership, `tests/test_response_composer.py`, and full Core quality gates passing.  
**Historical note:** This document is retained as the original implementation plan.

**Blueprint:** D-009-08  
**Resoluciones:** AR-001 (BusinessResponse → CE), AR-003 (CE↔BB contrato, eliminar `message` de BusinessDecision)  
**Incremento:** 4 de 5  
**Dependencias:** I1 (State Manager) + I2 (Context Builder) — no depende de I3 (Topic Detector)  
**Pipeline blueprint:** `Business Brain → Response Composer → Channel Adapter`

---

## 1. BusinessResponse — Contrato

### 1.1 Nuevo contrato de dominio

Archivo nuevo: `app/domain/conversation/response.py`

```python
class BusinessResponse(BaseModel):
    message: str                        # texto de respuesta conversacional
    status: str                         # "accepted" | "rejected" | "escalated"
    tone: str = "neutral"               # perfil comunicacional de la respuesta
```

**Engine propietario:** Conversation Engine (AR-001).

**Responsabilidad:** Representa la respuesta conversacional completa que será adaptada al canal destino por el Channel Adapter (o su predecesor `ConversationMapper`).

**Regla:** Contiene solo la respuesta. No contiene lógica de negocio, no contiene la decisión original. Si el Channel Adapter necesita datos de la decisión, `BusinessDecision` sigue disponible en el pipeline.

### 1.2 Relación con objetos existentes

| Objeto | Rol en pipeline I4 |
|---|---|
| `BusinessDecision` | Entrada del Response Composer. **Sin `message`**. |
| `BusinessResponse` | Salida del Response Composer. Entrada del `ConversationMapper`. |
| `ChannelResponse` | Salida del `ConversationMapper`. Contiene `status` + `message` para el API. |

---

## 2. BusinessDecision — Modificación del contrato

### 2.1 Cambios en `app/domain/business/contracts.py`

```python
# BusinessDecision ACTUAL:
class BusinessDecision(BaseModel):
    status: str
    intent: str
    message: str           # ← ELIMINAR (AR-003)
    confidence: str
    needs_knowledge: bool = False

# BusinessDecision DESPUÉS DE I4:
class BusinessDecision(BaseModel):
    status: str
    intent: str
    confidence: str
    needs_knowledge: bool = False
    knowledge_content: str | None = None   # NUEVO: texto desde Knowledge Engine
```

**`message` eliminado** — El Business Brain ya no produce texto conversacional. Cumple AR-003.

**`knowledge_content` agregado** — Cuando el Knowledge Engine encuentra contenido relevante, el BB lo pasa al CE vía este campo. El Response Composer usa `knowledge_content` como mensaje prioritario (por encima de templates determinísticas).

### 2.2 Impacto en el pipeline

| Antes | Después |
|---|---|
| `BB → BusinessDecision(message="Hola...") → Mapper → ChannelResponse` | `BB → BusinessDecision(sin message) → ResponseComposer → BusinessResponse("Hola...") → Mapper → ChannelResponse` |

---

## 3. ResponseComposer

### 3.1 Interfaz

Archivo nuevo: `app/core/conversation/response_composer.py`

```python
class ResponseComposer:
    def compose(
        self,
        decision: BusinessDecision,
        context: ConversationContext,
    ) -> BusinessResponse:
        """Transforma una Business Decision en una Business Response.
        
        Entradas:
          - decision: BusinessDecision (sin message)
          - context: ConversationContext enriquecido (state, history, topics)
        
        Salida:
          - BusinessResponse (message + tone + status)
        
        Algoritmo (I4, determinístico):
          1. Si decision.knowledge_content existe → usarlo como message
          2. Si no → seleccionar template según decision.intent
          3. Determinar tone según intent + topics disponibles
          4. Retornar BusinessResponse
        """
```

**Responsabilidad (D-009-08):** Transformar una `Business Decision` en una respuesta clara, natural y alineada con la identidad comunicacional de la empresa.

**Regla (D-009-08):** Solo el Response Composer puede transformar una Business Decision en una Business Response.

**Principios (D-009-08):** Natural, consistente, personalizable, multilingüe, independiente del canal.

### 3.2 Templates — migración desde BusinessPolicy

Las templates de texto se **mueven** de `BusinessPolicy` (ENG-001) al `ResponseComposer` (ENG-002).

#### De BusinessPolicy (se eliminan):

```python
# business/policy.py — ELIMINAR todos los campos "message"
"greeting": {
    "status": "accepted",
    "message": "¡Hola! ¿En qué puedo ayudarte hoy?",  # ← MOVER a ResponseComposer
    "confidence": "high",
    "needs_knowledge": False,
},
```

#### A ResponseComposer:

```python
class ResponseComposer:
    _TEMPLATES: dict[str, str] = {
        "greeting": "¡Hola! ¿En qué puedo ayudarte hoy?",
        "farewell": "Gracias por contactarnos. Que tengas un buen día.",
        "price_inquiry": "Gracias por tu interés. Un asesor te contactará con los precios.",
        "thanks": "¡De nada! Estamos aquí para ayudarte.",
        "support": "Cuéntame más sobre el problema para poder ayudarte.",
        "question": "Déjame revisar la información para responder tu consulta.",
        "unknown": "Gracias por tu mensaje. Estamos procesando tu solicitud.",
    }

    _TONE_MAP: dict[str, str] = {
        "greeting": "friendly",
        "farewell": "cordial",
        "price_inquiry": "professional",
        "thanks": "grateful",
        "support": "helpful",
        "question": "informative",
        "unknown": "neutral",
    }

    _DEFAULT_MESSAGE: str = "Gracias por tu mensaje. Estamos procesando tu solicitud."
```

**Nota:** Todos los textos son idénticos a los actuales en `BusinessPolicy`. El contenido semántico de la respuesta no cambia en I4 — solo cambia **dónde** se genera.

### 3.3 Algoritmo (I4, determinístico)

```
1. Recibir BusinessDecision + ConversationContext
2. Determinar message:
   a. Si decision.knowledge_content is not None:
        message = decision.knowledge_content
   b. Si no:
        template_key = decision.intent  # "greeting", "farewell", etc.
        message = _TEMPLATES.get(template_key, _DEFAULT_MESSAGE)
3. Determinar tone:
   a. tone = _TONE_MAP.get(decision.intent, "neutral")
   b. (Futuro: si context.topics está disponible, podría refinarse)
4. Retornar BusinessResponse(message=message, tone=tone, status=decision.status)
```

**Caso conocimiento encontrado:** El mensaje del Knowledge Engine reemplaza al template. Esto replica el comportamiento actual donde `decision.message` se sobreescribe con `result.content` dentro de `BusinessBrainService.process()`.

**Caso conocimiento no encontrado:** Se usa el template correspondiente al `intent`. Replica el fallback actual a `BusinessPolicy`.

### 3.4 Tone — nuevo concepto

`tone` en `BusinessResponse` representa el perfil comunicacional. En I4 es un campo poblado pero **no consumido** por el `ConversationMapper` (que solo usa `message` y `status`). Queda disponible para el Channel Adapter formal (I5) y para futuras personalizaciones.

---

## 4. Integración en el pipeline

### 4.1 Pipeline oficial (D-009-03)

```
Context Builder
    ↓
Topic Detector
    ↓
Business Brain
    ↓
Response Composer    ← NUEVO
    ↓
Channel Adapter
    ↓
ChannelResponse
```

### 4.2 Pipeline implementado (I1+I2+I3+I4)

```
StateManager.get_or_create()
    ↓
ContextBuilder.build(message, state)
    ↓
TopicDetector.detect(context)
    ↓
StateManager.transition("awaiting_brain")
    ↓
Router.route(context) → BusinessDecision (sin message)
    ↓
ResponseComposer.compose(decision, context)  ← NUEVO BusinessResponse
    ↓
StateManager.transition("in_progress")
    ↓
Mapper.to_channel_response(business_response)  ← MODIFICADO: recibe BusinessResponse
    ↓
Persist(message, business_response.message)  ← MODIFICADO: message de BusinessResponse
```

### 4.3 Ubicación exacta en ConversationService

```python
# ACTUAL (I3):
context = self._context_builder.build(message, state)
context = self._topic_detector.detect(context)
business_response = self._router.route(context)          # ← BusinessDecision
self._state_manager.transition(message.conversation_id, "in_progress")
response = self._mapper.to_channel_response(business_response)   # ← recibe BusinessDecision
self._persist(message, business_response.message)

# DESPUÉS DE I4:
context = self._context_builder.build(message, state)
context = self._topic_detector.detect(context)
business_decision = self._router.route(context)                  # ← BusinessDecision (sin message)
self._state_manager.transition(message.conversation_id, "in_progress")
business_response = self._response_composer.compose(             # ← NUEVO
    business_decision, context,
)
response = self._mapper.to_channel_response(business_response)   # ← recibe BusinessResponse
self._persist(message, business_response.message)
```

**Cambios puntuales:**
1. `business_response` → `business_decision` (ahora es realmente un `BusinessDecision`)
2. Nueva línea: `business_response = self._response_composer.compose(business_decision, context)`
3. `self._persist(message, business_response.message)` — `business_response` ahora es `BusinessResponse` (sin cambiar la línea, porque `BusinessResponse` también tiene `.message`)

---

## 5. Cambios necesarios

### 5.1 Archivos nuevos (2)

| Archivo | Contenido | Líneas |
|---|---|---|
| `app/domain/conversation/response.py` | `BusinessResponse` contract | ~15 |
| `app/core/conversation/response_composer.py` | `ResponseComposer` class con templates + algoritmo | ~60 |

### 5.2 Archivos modificados (6)

| Archivo | Cambio |
|---|---|
| `app/domain/business/contracts.py` | Eliminar `message` de `BusinessDecision`. Agregar `knowledge_content: str \| None = None`. |
| `app/core/business/policy.py` | Eliminar campo `message` de cada política. Solo retorna `status`, `confidence`, `needs_knowledge`. |
| `app/core/business/decision_engine.py` | Dejar de pasar `response["message"]` a `BusinessDecision`. |
| `app/core/business/service.py` | Cuando se encuentra knowledge: crear `BusinessDecision` con `knowledge_content=result.content` en lugar de `message=result.content`. |
| `app/core/conversation/mapper.py` | Cambiar input de `BusinessDecision` a `BusinessResponse`. `message = response.message`, `status = response.status`. |
| `app/core/conversation/service.py` | Inyectar `ResponseComposer`. Agregar llamada a `compose()` entre `route()` y `to_channel_response()`. |
| `app/api/dependencies.py` | Instanciar `ResponseComposer()`. Pasar a `ConversationService`. |

**Total:** 2 archivos nuevos + 7 modificados ≈ 9 archivos.

### 5.3 Archivos no modificados

| Archivo | Razón |
|---|---|
| `router.py` | Sigue llamando a `BusinessBrainService.process()` y retornando `BusinessDecision`. Sin cambios. |
| `intent_classifier.py` | No se toca (AR-002 incompleto). |
| `state_manager.py` | I1 intacto. |
| `context_builder.py` | I2 intacto. |
| `topic_detector.py` | I3 intacto. |
| `domain/knowledge/contracts.py` | Sin cambios. |
| `channels/whatsapp/*` | Sin cambios. |

### 5.4 Dependencias

| Clase | Depende de | Existe desde |
|---|---|---|
| `ResponseComposer` | `BusinessDecision`, `ConversationContext` (stateless) | I4 |
| `ConversationMapper` | `BusinessResponse` (reemplaza `BusinessDecision`) | I1 (modificado en I4) |
| `ConversationService` | `ResponseComposer` | I1 (modificado en I4) |
| `DecisionEngine` | `BusinessPolicy` (sin `message`) | I1 (modificado en I4) |
| `BusinessBrainService` | `BusinessDecision` (sin `message`) | I1 (modificado en I4) |

`ResponseComposer` es completamente stateless — no depende de DB, repositorios ni estado externo.

---

## 6. Compatibilidad temporal con Business Brain actual

### 6.1 Conviviencia

| Componente | Antes de I4 | Durante I4 | Después de I4 |
|---|---|---|---|
| `BusinessPolicy` | Retorna `message` + `status` + `confidence` + `needs_knowledge` | **Elimina** `message`. Solo `status` + `confidence` + `needs_knowledge` | Ídem |
| `DecisionEngine` | Construye `BusinessDecision` con `message` | Construye `BusinessDecision` **sin** `message` | Ídem |
| `BusinessBrainService` | Sobrescribe `message` con `result.content` | Pone `knowledge_content=result.content` | Ídem |
| `ConversationMapper` | Lee `decision.message` | Lee `response.message` (de `BusinessResponse`) | Ídem |

**No hay período de coexistencia** — el cambio es atómico en el commit de I4:
1. Se modifica `BusinessDecision` (pierde `message`)
2. Se modifica `BusinessPolicy` (pierde `message`)  
3. Se modifica `DecisionEngine` (no pasa `message`)
4. Se modifica `BusinessBrainService` (usa `knowledge_content`)
5. Se crea `ResponseComposer` (produce `message`)
6. Se modifica `ConversationMapper` (lee `BusinessResponse`)
7. Se modifica `ConversationService` (inyecta composer, cambia pipeline)
8. Se modifican tests (ver sección 7)

Un commit único garantiza que ningún estado intermedio quede con tests fallando.

### 6.2 Compatibilidad con `ConversationService._persist()`

```python
# Actual (I3): self._persist(message, business_response.message)
#   business_response es BusinessDecision → business_response.message existe

# I4: self._persist(message, business_response.message)
#   business_response es BusinessResponse → business_response.message existe
```

La línea no cambia. `BusinessResponse.message` reemplaza a `BusinessDecision.message` semántica y sintácticamente.

### 6.3 Compatibilidad con VS1

Los tests VS1 verifican `data["message"]` contra los textos actuales. Como el `ResponseComposer` usa los **mismos textos** que `BusinessPolicy`, el output observable no cambia:

| Test VS1 | Expectativa | Origen actual | Origen I4 | ¿Cambia? |
|---|---|---|---|---|
| `test_vs1_greeting_flow` | `"Hola" in data["message"]` | `policy.py:greeting.message` | `ResponseComposer._TEMPLATES["greeting"]` | **No** |
| `test_vs1_farewell_flow` | `"Gracias" in data["message"]` | `policy.py:farewell.message` | `ResponseComposer._TEMPLATES["farewell"]` | **No** |
| `test_vs1_knowledge_horario_flow` | `"horario" in data["message"]` | `service.py:result.content` → `decision.message` | `BusinessDecision.knowledge_content` → `ResponseComposer` | **No** |
| `test_vs1_knowledge_fallback_flow` | `"Déjame revisar..."` | `policy.py:question.message` | `ResponseComposer._TEMPLATES["question"]` | **No** |
| `test_vs1_unknown_flow` | `"Gracias por tu mensaje..."` | `policy.py:unknown.message` | `ResponseComposer._TEMPLATES["unknown"]` | **No** |
| `test_vs1_price_inquiry_knowledge_flow` | `"Gracias por tu interés..."` | `policy.py:price_inquiry.message` | `ResponseComposer._TEMPLATES["price_inquiry"]` | **No** |

**Todos los textos visibles al cliente son idénticos.** El cambio es interno.

---

## 7. Tests

### 7.1 Tests unitarios — ResponseComposer (nuevo archivo)

Nuevo: `tests/test_response_composer.py`

| Test | Descripción |
|---|---|
| `test_compose_greeting_returns_friendly_response` | intent="greeting", sin knowledge → message="¡Hola!..." + tone="friendly" |
| `test_compose_knowledge_content_overrides_template` | knowledge_content="Nuestro horario..." → message usa knowledge, no template |
| `test_compose_unknown_returns_default` | intent="unknown" → message default |
| `test_compose_preserves_decision_status` | `BusinessResponse.status == decision.status` |
| `test_compose_invalid_intent_falls_back_to_default` | intent="nonexistent" → _DEFAULT_MESSAGE |
| `test_compose_with_topics_in_context` | context con topics → composición funciona (no usa topics aún, pero no falla) |
| `test_tone_maps_correctly` | Cada intent → tone esperado |

### 7.2 Tests unitarios — BusinessPolicy (modificado)

| Archivo | Cambio | Tests |
|---|---|---|
| `tests/test_business_policy.py` | Eliminar aserciones sobre `response["message"]` (4 tests, ~2 aserciones c/u) | 4 tests |
| `tests/test_decision_engine.py` | No referencian `decision.message`. Sin cambios. | 2 tests |
| `tests/test_business_contracts.py` | Modificar `test_business_decision_holds_*`: eliminar `message` de la creación. Agregar `knowledge_content=None`. | 2 tests modificados |
| `tests/test_business_brain_service.py` | Modificar tests que verifican `decision.message`: usar `decision.knowledge_content` o eliminar aserción según corresponda. | 4 tests, 2 modificados |

### 7.3 Tests de integración

| Archivo | Cambio |
|---|---|
| `tests/test_conversation_service.py` | Inyectar `ResponseComposer()`. Verificar que `response.message` sigue igual. |
| `tests/test_vs1_integration.py` | **Sin cambios.** (expectativas de output idénticas) |

### 7.4 Tests de regresión

| Archivo | Tests | ¿Cambia? |
|---|---|---|
| `tests/test_vs1_integration.py` | 10 tests | **No** |
| `tests/test_conversation_endpoint.py` | 2 tests | **No** |
| `tests/test_conversation_service.py` | 1 test | **Modificado** (inyectar composer) |
| `tests/test_conversation_contracts.py` | 3 tests | **No** |
| `tests/test_conversation_state.py` | 16 tests | **No** |
| `tests/test_conversation_context_builder.py` | 8 tests | **No** |
| `tests/test_topic_detector.py` | 11 tests | **No** |
| `tests/test_conversation_state_manager.py` | 0 (está dentro de state.py) | **No** |
| Total regresión | **~51 tests** | **0 cambios de expectativa** |

### 7.5 Resumen de cambios de tests

| Tipo | Archivos | Tests |
|---|---|---|
| Nuevo | `tests/test_response_composer.py` | ~6 tests |
| Modificar | `tests/test_business_policy.py` | 4 tests (eliminar aserciones `message`) |
| Modificar | `tests/test_business_contracts.py` | 2 tests (eliminar `message`, agregar `knowledge_content`) |
| Modificar | `tests/test_business_brain_service.py` | 2 tests (cambiar `decision.message` → `decision.knowledge_content`) |
| Modificar | `tests/test_conversation_service.py` | 1 test (inyectar `ResponseComposer`) |
| Sin cambios | `tests/test_vs1_integration.py` | 10 tests |

---

## 8. Riesgos

### R1 — Ruptura del contrato existing si se despliega parcialmente

| Escenario | Impacto | Probabilidad | Mitigación |
|---|---|---|---|
| Se modifica `BusinessDecision` (sin `message`) pero no se despliega `ResponseComposer` | `ConversationMapper.to_channel_response()` falla porque `decision.message` ya no existe | **Alta** si el despliegue no es atómico | Un solo commit implementa todos los cambios. Despliegue atómico. Todos los tests pasan juntos o no se despliega. |

### R2 — Pérdida de traza entre `knowledge_content` y el mensaje final

| Escenario | Impacto | Probabilidad | Mitigación |
|---|---|---|---|
| El `ResponseComposer` no usa `decision.knowledge_content` porque un desarrollador futuro cambia la lógica | El knowledge encontrado por el KE se pierde y se usa el template genérico | **Baja** | `knowledge_content` tiene prioridad explícita en el algoritmo (sección 3.3, paso 2a). Test `test_compose_knowledge_content_overrides_template` lo verifica. |

### R3 — `tone` es campo nuevo no consumido

| Escenario | Impacto | Probabilidad | Mitigación |
|---|---|---|---|
| El campo `tone` se agrega a `BusinessResponse` pero ningún componente lo usa | Inconsistencia temporal: el campo existe pero no tiene efecto visible | **Media** (riesgo de "campo muerto") | Documentado en plan (sección 3.4). El `tone` es preparación para I5 (Channel Adapter formal) donde será utilizado para adaptación al canal. No es un bug — es una capacidad diferida. |

### R4 — Regresión en tests de Business Brain si no se actualizan

| Escenario | Impacto | Probabilidad | Mitigación |
|---|---|---|---|
| `test_business_brain_service.py` usa `decision.message` y falla después del cambio | Tests de BB fallan bloqueando CI | **Media** | Modificar los 2 tests que referencian `decision.message` a `decision.knowledge_content`. Plan detallado en sección 7.2. |

### R5 — Knowledge content se pierde si el ResponseComposer no recibe el campo

| Escenario | Impacto | Probabilidad | Mitigación |
|---|---|---|---|
| `BusinessBrainService` es modificado pero el `ResponseComposer` espera `knowledge_content` que no llega | El mensaje de knowledge no aparece en la respuesta — se usa template en su lugar | **Baja** (el contrato `BusinessDecision` se modifica en el mismo commit) | Un solo commit. `BusinessDecision.knowledge_content` y `ResponseComposer.compose()` se implementan juntos. |

---

## Resumen de archivos

| Tipo | Archivos | Líneas |
|---|---|---|
| Crear (2) | `app/domain/conversation/response.py`, `app/core/conversation/response_composer.py` | ~75 |
| Modificar (7) | `business/contracts.py`, `business/policy.py`, `business/decision_engine.py`, `business/service.py`, `conversation/mapper.py`, `conversation/service.py`, `api/dependencies.py` | ~50 total |
| Tests nuevos (1) | `tests/test_response_composer.py` | ~70 |
| Tests modificar (4) | `test_business_policy.py`, `test_business_contracts.py`, `test_business_brain_service.py`, `test_conversation_service.py` | ~10 líneas |
| Regresión | ~51 tests | Sin cambios |
