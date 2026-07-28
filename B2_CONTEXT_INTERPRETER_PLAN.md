# B2 — Context Interpreter: Technical Plan

**Blueprint:** D-008-04 (mencionado en D-008-03, documento no publicado)  
**Incremento:** 2 de 7  
**Dependencias:** B1 (Domain Contracts)  
**Pipeline:** `Evento → Context Interpreter → Intent Analyzer → Rule Evaluator → ...`

---

## 1. Responsabilidad del Context Interpreter

### 1.1 Definición

| Atributo | Valor |
|---|---|
| **Pregunta** | ¿En qué contexto llega esta solicitud? |
| **Responsabilidad** | Transformar el `BusinessRequest` entrante en un `BusinessContext` enriquecido con datos del cliente y metadata del canal |
| **Entradas** | `BusinessRequest` (desde Conversation Engine) |
| **Salidas** | `BusinessContext` enriquecido |
| **Principios** | Normaliza, enriquece, no decide, no clasifica, no aplica reglas |

### 1.2 Qué NO hace

- NO clasifica intents (es responsabilidad del IntentAnalyzer).
- NO aplica reglas de negocio (es responsabilidad del RuleEvaluator).
- NO toma decisiones (es responsabilidad del DecisionMaker).
- NO modifica el `BusinessRequest`.
- NO depende del Conversation Engine.

### 1.3 Lugar en el pipeline

```
CE → BusinessRequest
        ↓
  ContextInterpreter.enrich(request)
        ↓
  BusinessContext (enriquecido con customer_profile)
        ↓
  IntentAnalyzer (futuro B3) / IntentClassifier (actual)
        ↓
  RuleEvaluator → DecisionMaker → ...
```

---

## 2. Entrada y salida

### 2.1 Entrada: BusinessRequest (sin cambios)

`BusinessRequest` no se modifica. El contrato CE↔BB permanece intacto:
- `content`, `customer_id`, `company_id`, `conversation_id`

### 2.2 Salida: BusinessContext (modificado)

`BusinessContext` gana dos campos nuevos. `intent` se vuelve opcional (default `""`):

```python
# ANTES (B1)
class BusinessContext(BaseModel):
    request: BusinessRequest
    intent: str

# DESPUÉS (B2)
class BusinessContext(BaseModel):
    request: BusinessRequest
    intent: str = ""                        # ← ahora opcional
    customer_profile: dict[str, object] = Field(default_factory=dict)   # NUEVO
    channel_metadata: dict[str, object] = Field(default_factory=dict)   # NUEVO
```

**`intent` opcional:** El ContextInterpreter enriquece antes de que el IntentAnalyzer clasifique. Se necesita un `BusinessContext` válido sin intent. El default `""` permite crearlo sin intent, y el IntentAnalyzer lo produce luego con `model_copy(update={"intent": "..."})`.

**`customer_profile`:** Datos del cliente recuperados por el ContextInterpreter. En B2 se obtienen de un `CustomerProfileProvider`.

**`channel_metadata`:** Metadata del canal de origen. En B2 permanece vacío (el CE no pasa metadata de canal al BB por el contrato actual). Se poblará cuando el contrato CE↔BB se enriquezca en un incremento futuro.

### 2.3 Compatibilidad

| Código existente | Comportamiento |
|---|---|
| `BusinessContext(request=request, intent="greeting")` | **Sigue funcionando.** `intent` como keyword arg sigue válido. `customer_profile` y `channel_metadata` toman default `{}`. |
| `context.intent` (lectura) | **Sin cambios.** Sigue siendo `str`. |
| `context.customer_profile` (lectura) | **Nuevo.** Retorna `dict` vacío si no se pobló. |

---

## 3. CustomerProfileProvider

### 3.1 Nueva abstracción

```python
class CustomerProfileProvider(ABC):
    @abstractmethod
    def get_profile(self, customer_id: str) -> dict[str, object]:
        """Retorna el perfil del cliente.
        
        Mínimo esperado: {"customer_id": ..., "name": ...}
        Puede incluir: email, phone, segment, preferencias, etc.
        """
```

**Responsabilidad:** Abstraer la fuente de datos de clientes. Permite implementaciones en memoria, DB, API externa, etc.

**Principio:** Independencia tecnológica (D-008-02). El BB no debe depender de una fuente de datos específica.

### 3.2 InMemoryCustomerProfileProvider

```python
class InMemoryCustomerProfileProvider(CustomerProfileProvider):
    def get_profile(self, customer_id: str) -> dict[str, object]:
        return {
            "customer_id": customer_id,
            "name": "Cliente",
        }
```

- Implementación mínima para desarrollo y tests.
- Retorna datos básicos (nombre genérico).
- Extensible en el futuro: leer de DB, API de CRM, etc.

### 3.3 Ubicación

| Archivo | Clase |
|---|---|
| `app/core/business/customer_profile_provider.py` | `CustomerProfileProvider` (ABC), `InMemoryCustomerProfileProvider` |

Siguiendo el patrón de `app/core/knowledge/provider.py` + `app/core/knowledge/in_memory_provider.py`.

---

## 4. ContextInterpreter

### 4.1 Interfaz

```python
class ContextInterpreter:
    def __init__(
        self,
        customer_profile_provider: CustomerProfileProvider | None = None,
    ) -> None:
        self._profile_provider = customer_profile_provider

    def enrich(self, request: BusinessRequest) -> BusinessContext:
        profile = self._load_customer_profile(request.customer_id)
        return BusinessContext(
            request=request,
            intent="",                         # será poblado por IntentAnalyzer
            customer_profile=profile,
            channel_metadata={},               # pendiente de enriquecer contrato CE↔BB
        )

    def _load_customer_profile(self, customer_id: str) -> dict[str, object]:
        if self._profile_provider is not None:
            return self._profile_provider.get_profile(customer_id)
        return {"customer_id": customer_id}
```

### 4.2 Algoritmo (B2, determinístico)

```
1. Recibir BusinessRequest
2. Cargar customer_profile desde CustomerProfileProvider
3. Si no hay provider → customer_profile mínimo {customer_id}
4. Crear BusinessContext con request + customer_profile
5. intent = "" (será poblado por IntentAnalyzer después)
6. channel_metadata = {} (pendiente de enriquecimiento futuro)
7. Retornar BusinessContext
```

### 4.3 Ubicación

Nuevo archivo: `app/core/business/context_interpreter.py`

---

## 5. Integración con pipeline actual

### 5.1 Cambio en BusinessBrainService

```python
# ANTES (B1):
class BusinessBrainService:
    def process(self, request: BusinessRequest) -> BusinessDecision:
        intent = self._intent_classifier.classify(request.content)
        context = BusinessContext(request=request, intent=intent)
        ...

# DESPUÉS (B2):
class BusinessBrainService:
    def __init__(
        self,
        ...,
        context_interpreter: ContextInterpreter | None = None,    # NUEVO
    ):
        self._context_interpreter = context_interpreter

    def process(self, request: BusinessRequest) -> BusinessDecision:
        # 1. Enriquecer contexto
        context = self._context_interpreter.enrich(request)

        # 2. Clasificar intent (sobre contexto enriquecido)
        intent = self._intent_classifier.classify(request.content)
        context = context.model_copy(update={"intent": intent})

        # 3. Continuar pipeline (sin cambios)
        decision = self._decision_engine.evaluate(context)
        ...
```

**`model_copy(update=...)`:** Pydantic v2 soporta `model_copy()` en modelos frozen para crear una copia con campos actualizados. Es el mismo patrón usado en `TopicDetector.detect()` (CE).

### 5.2 Pipeline resultante

```
BusinessBrainService.process(request):
    1. ContextInterpreter.enrich(request)
       → BusinessContext con customer_profile, intent=""

    2. IntentClassifier.classify(request.content)
       → BusinessContext con intent poblado

    3. DecisionEngine.evaluate(context)
       → BusinessDecision

    4. (KnowledgeService si necesita)

    5. Return BusinessDecision
```

### 5.3 Sin cambios en CE

`MessageRouter.route()` sigue igual:
```python
request = BusinessRequest(
    content=context.message.content,
    customer_id=context.message.customer_id,
    company_id=context.message.company_id,
    conversation_id=context.message.conversation_id,
)
return self._business_brain.process(request)
```

El CE no sabe que el BB ahora enriquece el contexto internamente. El contrato CE↔BB no cambia.

---

## 6. Archivos necesarios

### 6.1 Archivos nuevos (2)

| Archivo | Contenido | Líneas |
|---|---|---|
| `app/core/business/customer_profile_provider.py` | `CustomerProfileProvider` (ABC), `InMemoryCustomerProfileProvider` | ~20 |
| `app/core/business/context_interpreter.py` | `ContextInterpreter` class | ~30 |

### 6.2 Archivos modificados (4)

| Archivo | Cambio |
|---|---|
| `app/domain/business/contracts.py` | `BusinessContext`: `intent` pasa a `str = ""`. Agregar `customer_profile` y `channel_metadata`. |
| `app/core/business/service.py` | Importar `ContextInterpreter`. Agregar al constructor. Llamar `enrich()` antes de `classify()`. Usar `model_copy(update=...)` para agregar intent. |
| `app/api/dependencies.py` | Importar `ContextInterpreter` e `InMemoryCustomerProfileProvider`. Instanciar y pasar a `BusinessBrainService`. |
| `tests/test_conversation_service.py` | Verificar que el flujo no se rompe (el CE no cambia, pero el test crea un `BusinessBrainService`). |

### 6.3 Archivos no modificados

| Archivo | Razón |
|---|---|
| `app/core/business/intent_classifier.py` | B3 refactoriza. B2 no lo toca. |
| `app/core/business/decision_engine.py` | B5 refactoriza. B2 no lo toca. |
| `app/core/business/policy.py` | B4 refactoriza. B2 no lo toca. |
| `app/core/conversation/*` | CE no se modifica. |
| `app/channels/*` | Canales no se modifican. |

### 6.4 Dependencias

| Clase | Depende de | Existe desde |
|---|---|---|
| `CustomerProfileProvider` | Ninguna (ABC) | B2 |
| `InMemoryCustomerProfileProvider` | `CustomerProfileProvider` | B2 |
| `ContextInterpreter` | `CustomerProfileProvider` (opcional), `BusinessRequest`, `BusinessContext` | B2 |
| `BusinessBrainService` | `ContextInterpreter` (nuevo parámetro opcional) | B1 (modificado en B2) |
| `BusinessContext` | (modificado) `customer_profile`, `channel_metadata` | B1 (modificado en B2) |

---

## 7. Tests

### 7.1 Tests unitarios — CustomerProfileProvider

Nuevo: `tests/test_customer_profile_provider.py`

| Test | Descripción |
|---|---|
| `test_in_memory_provider_returns_profile` | `get_profile("c1")` → dict con customer_id y name |
| `test_in_memory_provider_returns_name_cliente` | name == "Cliente" para cualquier ID |
| `test_customer_profile_provider_is_abstract` | No se puede instanciar directamente |

### 7.2 Tests unitarios — ContextInterpreter

Nuevo: `tests/test_context_interpreter.py`

| Test | Descripción |
|---|---|
| `test_enrich_returns_business_context` | `enrich(request)` → instancia de `BusinessContext` |
| `test_enrich_sets_request` | `context.request == request` |
| `test_enrich_sets_intent_empty` | `context.intent == ""` |
| `test_enrich_loads_customer_profile` | Con provider mock, `context.customer_profile` contiene datos del provider |
| `test_enrich_without_provider_returns_minimal_profile` | Sin provider, `customer_profile` tiene al menos `customer_id` |
| `test_enrich_sets_channel_metadata_empty` | `context.channel_metadata == {}` |

### 7.3 Tests de integración — BusinessBrainService

Modificar: `tests/test_business_brain_service.py`

| Test | Cambio |
|---|---|
| `test_business_brain_returns_decision_for_greeting` | Inyectar `ContextInterpreter()` con `InMemoryCustomerProfileProvider`. Verificar que `customer_profile` está presente. |
| `test_business_brain_knowledge_flow` | Inyectar ContextInterpreter. Flujo sigue funcionando. |

### 7.4 Tests de contratos

Modificar: `tests/test_business_contracts.py`

| Test | Cambio |
|---|---|
| `test_business_context_holds_request_and_intent` | Modificar: intent puede omitirse, verificar default `""`. Agregar aserciones para `customer_profile` y `channel_metadata` defaults. |

### 7.5 Tests de regresión

| Archivo | Tests | ¿Cambia? |
|---|---|---|
| `tests/test_vs1_integration.py` | 10 tests | **No** |
| `tests/test_conversation_service.py` | 1 test | **No** (inyecta BusinessBrainService sin ContextInterpreter → provider None → perfil mínimo) |
| `tests/test_business_policy.py` | 4 tests | **No** |
| `tests/test_decision_engine.py` | 2 tests | **No** |
| `tests/test_intent_classifier.py` | 8 tests | **No** |
| Otros | ~116 tests | **No** |
| Total regresión | **~141 tests** | **0 cambios de expectativa** |

---

## 8. Riesgos

### R1 — BusinessContext.intent pasa de requerido a opcional

| Escenario | Impacto | Probabilidad | Mitigación |
|---|---|---|---|
| Código existente crea `BusinessContext(request=request)` sin intent → intent = `""` en vez de error | Puede causar bugs silenciosos si hay código que asume que intent siempre tiene valor | **Baja** | El IntentAnalyzer se ejecuta justo después del ContextInterpreter en el mismo método `process()`. No hay una ventana donde `context.intent == ""` llegue al DecisionEngine. Tests verifican que intent se pobló antes de evaluar. |

### R2 — `model_copy(update=...)` no disponible en versiones antiguas de Pydantic

| Escenario | Impacto | Probabilidad | Mitigación |
|---|---|---|---|
| Pydantic v1 no tiene `model_copy` | Error de runtime | **Nula** | El proyecto usa Pydantic v2 (ver `BaseModel` con `model_config` en todos los contratos). `model_copy(update=...)` es parte de Pydantic v2+. |

### R3 — CustomerProfileProvider sin implementación real (solo in-memory)

| Escenario | Impacto | Probabilidad | Mitigación |
|---|---|---|---|
| En producción, el perfil del cliente es siempre "Cliente" | El BB toma decisiones sin datos reales del cliente | **Alta** (es el diseño de B2) | Documentado como limitación. B2 establece la abstracción y el punto de inyección. Una implementación real (DB, CRM API) se agrega sin cambiar el `ContextInterpreter`. |

---

## Resumen de archivos

| Tipo | Archivos | Líneas |
|---|---|---|
| Crear (2) | `app/core/business/customer_profile_provider.py`, `app/core/business/context_interpreter.py` | ~50 |
| Modificar (4) | `app/domain/business/contracts.py`, `app/core/business/service.py`, `app/api/dependencies.py`, `tests/test_business_contracts.py` | ~30 total |
| Tests nuevos (2) | `tests/test_customer_profile_provider.py`, `tests/test_context_interpreter.py` | ~80 |
| Tests modificar (1) | `tests/test_business_brain_service.py` | ~10 |
| Regresión | ~141 tests | Sin cambios |
