# I2 — Conversation Context Builder: Technical Plan

**Implementation status:** Implemented / Closed  
**Closure evidence:** `app/core/conversation/context_builder.py`, enriched `ConversationContext`, `tests/test_conversation_context_builder.py`, and full Core quality gates passing.  
**Historical note:** This document is retained as the original implementation plan.

**Blueprint:** D-009-05  
**Incremento:** 2 de 5  
**Dependencias:** I1 — Conversation State Manager  
**Resoluciones aplicables:** AR-001, AR-002, AR-003 (sin cambios en este incremento)

---

## 1. Qué debe cambiar en ConversationContext

### 1.1 ConversationMessage (entrada del pipeline)

Blueprint D-009-04 especifica que `ConversationMessage` debe contener `canal` y `metadata`. Actualmente faltan.

**Cambio:** Agregar dos campos con defaults para no romper constructores existentes:

```python
class ConversationMessage(BaseModel):
    content: str = Field(min_length=1)
    customer_id: str = Field(min_length=1)
    company_id: str = Field(min_length=1)
    conversation_id: UUID = Field(default_factory=uuid4)
    channel: str = Field(default="http")                # NUEVO
    metadata: dict[str, object] = Field(default_factory=dict)  # NUEVO
    received_at: datetime = Field(default_factory=...)
```

- `channel`: identificador del canal de origen ("http", "whatsapp", etc.)
- `metadata`: payload adicional del canal (para WhatsApp: phone_number_id, message_id, timestamp del webhook)

### 1.2 HistoryEntry (nuevo contrato de dominio)

Para representar el historial conversacional sin depender de `ConversationMessage` (cuyos campos `customer_id`/`company_id` no se persisten en `MessageModel`).

```python
class HistoryEntry(BaseModel):
    model_config = ConfigDict(frozen=True)
    role: str                          # "user" | "assistant"
    content: str
    created_at: datetime
```

Propiedad: Conversation Engine (ENG-002), objeto conversacional interno.

### 1.3 ConversationContext (enriquecimiento)

**Actual:** 3 campos (message, context_id, created_at)  
**Después de I2:**

```python
class ConversationContext(BaseModel):
    message: ConversationMessage
    context_id: UUID = Field(default_factory=uuid4)
    created_at: datetime = Field(default_factory=...)
    # NUEVOS: -------------------------------------------------
    state: ConversationState | None = None
    history: list[HistoryEntry] = Field(default_factory=list)
    customer_profile: dict[str, object] = Field(default_factory=dict)
    channel_metadata: dict[str, object] = Field(default_factory=dict)
```

| Campo | Blueprint D-009-05 | Fuente |
|---|---|---|
| `state` | "Estado conversacional" | `ConversationStateManager.get_or_create()` (I1) |
| `history` | "Historial" | `MessageRepository.list(conversation_id=...)` |
| `customer_profile` | "Perfil del cliente" | Derivado de `message.customer_id` + `message.company_id`. Stub para extensión futura (CRM, preferencias) |
| `channel_metadata` | "Metadata del canal" | `message.metadata` |

Se elimina el classmethod `from_message()` — su responsabilidad pasa al `ConversationContextBuilder`.

### 1.4 Ubicación en el código

| Tipo | Archivo |
|---|---|
| `HistoryEntry` | `app/domain/conversation/contracts.py` |
| Campos nuevos en `ConversationMessage` | `app/domain/conversation/contracts.py` |
| Campos nuevos en `ConversationContext` | `app/domain/conversation/contracts.py` |

No se crean archivos nuevos de contratos. Todo permanece en `contracts.py`.

---

## 2. ConversationContextBuilder

### 2.1 Ubicación y constructor

```
Nuevo archivo: app/core/conversation/context_builder.py
```

```python
class ConversationContextBuilder:
    def __init__(
        self,
        state_manager: ConversationStateManager,
        message_repo: MessageRepository | None = None,
    ) -> None: ...
```

Recibe `state_manager` (I1) para obtener el estado conversacional y `message_repo` para cargar historial.

### 2.2 Método principal

```python
def build(
    self,
    message: ConversationMessage,
    state: ConversationState,
) -> ConversationContext:
```

**Responsabilidades:**

| Dato | Cómo se obtiene |
|---|---|
| `message` | Recibido del Message Receiver (parámetro) |
| `state` | Recibido del State Manager (parámetro, ya calculado en Service) |
| `history` | `message_repo.list(conversation_id=conv_id)` → mapear a `list[HistoryEntry]`. Sin repo: `[]` |
| `customer_profile` | `{"customer_id": ..., "company_id": ...}` (stub extensible) |
| `channel_metadata` | `message.metadata` |
| `context_id` | `uuid4()` |
| `created_at` | `datetime.now(UTC)` |

### 2.3 Comportamiento sin repositorio

Cuando `message_repo is None` (modo sin DB), `history` se retorna como lista vacía. Esto mantiene compatibilidad con todos los tests unitarios existentes.

---

## 3. Archivos a crear y modificar

### Crear (1 archivo)

| Archivo | Líneas | Propósito |
|---|---|---|
| `app/core/conversation/context_builder.py` | ~50 | `ConversationContextBuilder` |

### Modificar (4 archivos)

| Archivo | Cambio |
|---|---|
| `app/domain/conversation/contracts.py` | Agregar `channel`, `metadata` a `ConversationMessage`. Agregar `HistoryEntry`. Agregar `state`, `history`, `customer_profile`, `channel_metadata` a `ConversationContext`. Eliminar `from_message()`. |
| `app/core/conversation/service.py` | Reemplazar `ConversationContext.from_message(message)` por `self._context_builder.build(message, state)`. Inyectar `context_builder` en `__init__`. |
| `app/api/dependencies.py` | Instanciar `ConversationContextBuilder(state_manager, message_repo)`. Pasar a `ConversationService`. |
| `app/channels/whatsapp/adapter.py` | Pasar `channel="whatsapp"` al construir `ConversationMessage`. Opcional: incluir `msg.id`, `msg.timestamp` en `metadata`. |

### No se modifican

| Archivo | Razón |
|---|---|
| `state_manager.py` (I1) | Se reutiliza vía `get_or_create()`. Sin cambios. |
| `router.py` | Sigue consumiendo `context.message.*`. Sin cambios. |
| `mapper.py` | Sigue mapeando `BusinessDecision → ChannelResponse`. Sin cambios. |
| `state.py` (I1) | Contrato `ConversationState` intacto. |

---

## 4. Repositorios/contratos existentes reutilizados

| Componente | Uso en I2 | ¿Ya existe? |
|---|---|---|
| `ConversationStateManager` | `get_or_create()` para obtener `ConversationState` | I1 |
| `MessageRepository` | `list(conversation_id=...)` para cargar historial | WP-001 |
| `BaseRepository.list()` | Filtro por columna `conversation_id` en `MessageModel` | WP-001 |
| `ConversationMessage` | Contrato de entrada, extendido con `channel`/`metadata` | WP-002 |
| `ConversationContext` | Contrato de salida, enriquecido | WP-002 |
| `ChannelResponse` | Sin cambios | WP-002 |

No se crean nuevos repositorios. No se modifican repositorios existentes.

---

## 5. Integración exacta en ConversationService

### Pipeline antes de I2

```python
state = self._state_manager.get_or_create(...)
# ... transitions ...
context = ConversationContext.from_message(message)  # contexto mínimo
business_response = self._router.route(context)
```

### Pipeline después de I2

```python
state = self._state_manager.get_or_create(...)
# ... transitions ... (sin cambios en I1)
context = self._context_builder.build(message, state)  # contexto enriquecido
business_response = self._router.route(context)
```

**Cambios en `__init__`:**

```python
class ConversationService:
    def __init__(
        self,
        router: MessageRouter,
        mapper: ConversationMapper,
        state_manager: ConversationStateManager,
        context_builder: ConversationContextBuilder,          # NUEVO
        session: Session | None = None,
        conversation_repo: ConversationRepository | None = None,
        message_repo: MessageRepository | None = None,
    ) -> None:
```

### Efecto sobre el Router

`MessageRouter.route(context)` actualmente usa:
- `context.message.content` → sin cambios
- `context.message.customer_id` → sin cambios
- `context.message.company_id` → sin cambios
- `context.message.conversation_id` → sin cambios

El contexto enriquecido (`state`, `history`, `customer_profile`, `channel_metadata`) está disponible en `context` pero el Router no lo usa todavía. Estará disponible para I3 (Topic Detector) e I4 (Response Composer) sin cambios adicionales en el contrato.

---

## 6. Tests necesarios

### Tests nuevos

| Archivo | Tests | Propósito |
|---|---|---|
| `tests/test_conversation_context_builder.py` | ~8 tests | Unitarios del `ConversationContextBuilder` |

**Casos:**

| Test | Descripción |
|---|---|
| `test_build_returns_context_with_message` | Context contiene el mensaje original |
| `test_build_includes_state` | Context.state coincide con el state recibido |
| `test_build_without_repo_returns_empty_history` | Sin message_repo, history es `[]` |
| `test_build_includes_customer_profile` | profile contiene customer_id y company_id |
| `test_build_includes_channel_metadata` | channel_metadata = message.metadata |
| `test_build_with_repo_loads_history` | Con message_repo SQLite, history contiene mensajes previos |
| `test_build_history_ordered_by_created_at` | Historial en orden cronológico |
| `test_context_message_channel_preserved` | channel del mensaje se preserva en context |

### Tests modificados

| Archivo | Cambio |
|---|---|
| `tests/test_conversation_service.py` | Agregar `context_builder=ConversationContextBuilder(state_manager=...)` al constructor del service |
| `tests/test_vs1_integration.py` | Ninguno (el endpoint no expone el context, solo el ChannelResponse final) |

### Tests de regresión (13 deben pasar sin cambios)

Todos los tests de VS1, endpoints y service existentes.

---

## 7. Riesgos reales de regresión del Vertical Slice

### R1 — Eliminación de `ConversationContext.from_message()`

| Impacto | Mitigación |
|---|---|
| El classmethod `from_message()` es usado en `service.py:56`. Se reemplaza por `context_builder.build()`. Ningún otro código lo usa. | **Sin riesgo.** El reemplazo es directo. Tests pasan porque el builder retorna un `ConversationContext` compatible. |

### R2 — Nuevos campos en `ConversationMessage`

| Impacto | Mitigación |
|---|---|
| Todos los constructores de `ConversationMessage` existentes usan solo 3-4 kwargs. Los nuevos campos tienen defaults. | **Sin riesgo.** `channel="http"` y `metadata={}` son compatibles hacia atrás. |
| La serialización JSON del endpoint podría incluir los nuevos campos si el cliente los envía. FastAPI ignora campos extra por defecto. | **Sin riesgo.** Los tests existentes envían solo content/customer_id/company_id. |

### R3 — Nuevos campos en `ConversationContext`

| Impacto | Mitigación |
|---|---|
| El `router.py` usa `context.message.*`. No accede a los nuevos campos. | **Sin riesgo.** Los nuevos campos son aditivos. |
| `ConversationContext` se usa como `response_model` en `routes.py:31`. Los nuevos campos con defaults podrían aparecer en la respuesta JSON. | **Riesgo controlado.** Si `ConversationContext` se serializa a JSON, los campos nuevos aparecerían. Pero en el código actual, `routes.py` usa `ChannelResponse` como `response_model`, no `ConversationContext`. Confirmar que ningún endpoint expone `ConversationContext`. |

### R4 — WhatsApp adapter pasa `channel` nuevo

| Impacto | Mitigación |
|---|---|
| `WhatsAppAdapter._map_message()` construye `ConversationMessage` con 4 kwargs. Los nuevos campos tienen defaults. Agregar `channel="whatsapp"` es aditivo. | **Sin riesgo.** Los tests de WhatsApp no verifican el channel explícitamente. |

### R5 — History carga mensajes de la conversación actual

| Impacto | Mitigación |
|---|---|
| En el pipeline síncrono, `_persist()` se llama *después* de `context_builder.build()`. El historial no incluirá el mensaje actual ni la respuesta — solo mensajes previos. | **Comportamiento correcto.** El historial representa mensajes anteriores, no el mensaje en proceso. |

---

## Resumen

| Tipo | Archivos | Líneas estimadas |
|---|---|---|
| Crear | 1 (`context_builder.py`) | ~50 |
| Modificar | 4 (`contracts.py`, `service.py`, `dependencies.py`, `adapter.py`) | ~30 total |
| Tests nuevos | 1 archivo, ~8 tests | ~100 |
| Tests modificar | 1 (`test_conversation_service.py`) | +1 línea |
| Regresión | 13 tests VS1 | Sin cambios |

**No se crean:** repositorios, modelos ORM, migraciones, endpoints, ADRs, blueprints.
**No se modifican:** state_manager.py, router.py, mapper.py, state.py, ningún ADR/blueprint.
