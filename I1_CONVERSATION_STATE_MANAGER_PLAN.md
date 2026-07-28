# I1 — Conversation State Manager: Technical Plan

**Implementation status:** Implemented / Closed  
**Closure evidence:** `app/core/conversation/state_manager.py`, `app/domain/conversation/state.py`, `app/infrastructure/models/conversation_state_history.py`, `tests/test_conversation_state.py`, and full Core quality gates passing.  
**Historical note:** This document is retained as the original implementation plan.

**Blueprint:** D-009-07  
**Incremento:** 1 de 5 (CONVERSATION_ENGINE_GAP_ANALYSIS.md)  
**Dependencias satisfechas:** Ninguna. Primer componente en orden arquitectónico.  
**Resoluciones aplicables:** AR-001 (BusinessResponse → CE), AR-002 (Topic → CE, Intent → BB), AR-003 (contrato CE↔BB inalterado en este incremento)

---

## 1. Componentes a Crear

### 1.1 `app/domain/conversation/state.py` — Conversation State Domain Object

```python
class ConversationState:
    """Domain object representing the conversational state per blueprint D-009-07.
    
    States defined in blueprint:
    - new, in_progress, awaiting_info, awaiting_brain,
      awaiting_client, completed, cancelled, escalated
    
    Owned by Conversation Engine per ADR-005 and AR-001.
    """
    
    conversation_id: UUID
    current_state: str
    previous_state: str | None
    created_at: datetime
    updated_at: datetime
```

**Estados del blueprint (D-009-07):**
| Estado | Cuándo se aplica |
|---|---|
| `new` | Conversación creada, primer mensaje recibido |
| `in_progress` | Flujo activo, procesando mensajes |
| `awaiting_info` | El sistema necesita información del cliente |
| `awaiting_brain` | El Business Brain está procesando |
| `awaiting_client` | Esperando respuesta del cliente |
| `completed` | Conversación finalizada |
| `cancelled` | Conversación cancelada |
| `escalated` | Escalada a humano |

**Transiciones válidas (máquina de estados, D-009-MMD-04):**

```
new → in_progress, cancelled
in_progress → awaiting_info, awaiting_brain, completed, cancelled, escalated
awaiting_info → in_progress, cancelled, escalated
awaiting_brain → in_progress, awaiting_client, cancelled, escalated
awaiting_client → in_progress, completed, cancelled, escalated
completed → (terminal)
cancelled → (terminal)
escalated → (terminal)
```

**Nota:** I1 no registra auto-transiciones (ej. `in_progress → in_progress`). Toda llamada a `transition()` representa un cambio real de estado. En el pipeline síncrono actual, un mensaje genera las transiciones `[new →] in_progress → awaiting_brain → in_progress`. Las transiciones `awaiting_info` y `awaiting_client` están definidas pero no se usarán hasta que el pipeline soporte operaciones asíncronas.

### 1.2 `app/core/conversation/state_manager.py` — ConversationStateManager

```python
class ConversationStateManager:
    """Gobierna el ciclo de vida de las conversaciones.
    
    Regla arquitectónica (D-009-07):
    "Solo el Conversation State Manager puede modificar el Conversation State."
    
    Responsabilidad: Administrar el estado de cada conversación
    y de cada hilo conversacional durante todo su ciclo de vida.
    """
    
    def __init__(self, session: Session | None = None): ...
    
    def get_or_create(
        self, conversation_id: UUID, company_id: str, customer_id: str
    ) -> ConversationState:
        """Retorna el estado actual o crea uno nuevo con estado 'new'."""
    
    def transition(
        self, conversation_id: UUID, target_state: str
    ) -> ConversationState:
        """Valida y ejecuta una transición de estado.
        
        Lanza ValueError si la transición no está permitida.
        Actualiza ConversationModel.status y registra en history.
        """
    
    def can_transition(self, current: str, target: str) -> bool:
        """Evalúa si una transición es válida sin ejecutarla."""
    
    def get_state(self, conversation_id: UUID) -> ConversationState | None:
        """Consulta el estado actual sin crearlo."""
```

### 1.3 `app/infrastructure/models/conversation_state_history.py` — History Model

```python
class ConversationStateHistoryModel(Base):
    __tablename__ = "conversation_state_history"
    
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    conversation_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("conversation.id"), nullable=False
    )
    from_state: Mapped[str] = mapped_column(String(50), nullable=False)
    to_state: Mapped[str] = mapped_column(String(50), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(UTC)
    )
    
    # Relación con ConversationModel (opcional por ahora)
    # Se agregará cuando sea necesario navegar entre tablas
```

### 1.4 Nueva migración Alembic

`alembic/versions/20260718_0001_add_conversation_state.py`

- Crea tabla `conversation_state_history`
- No modifica `conversation.status` (se reutiliza la columna existente)

**Justificación:** La columna `status` ya existe en `conversation`. Su semántica actual ("active") es un subconjunto del estado conversacional. Se reutiliza almacenando los valores del Conversation State Manager. El `server_default="active"` se preserva para no romper registros existentes (en I1, el valor "active" se mapea al estado "in_progress").

---

## 2. Archivos a Modificar

### 2.1 `app/core/conversation/service.py` — ConversationService

**Cambio:** Inyectar `ConversationStateManager` y llamarlo en `handle_message()`.

Pipeline antes de I1:
```
handle_message:
  1. ConversationContext.from_message(message)
  2. router.route(context)                → BB
  3. mapper.to_channel_response(decision)  → Response
  4. persist(message, text)
```

Pipeline después de I1:
```
handle_message:
  1. ConversationContext.from_message(message)
  2. state = state_manager.get_or_create(conversation_id, company_id, customer_id)
  3. if terminal state → return ChannelResponse(rejected)
  4. if state.current_state == "new":
       state_manager.transition(conversation_id, "in_progress")   # new → in_progress
  5. state_manager.transition(conversation_id, "awaiting_brain")  # in_progress → awaiting_brain
  6. router.route(context)                → BB
  7. state_manager.transition(conversation_id, "in_progress")     # awaiting_brain → in_progress
  8. mapper.to_channel_response(decision)  → Response
  9. persist(message, text)
```

**Detalle del cambio:**

```python
class ConversationService:
    def __init__(
        self,
        router: MessageRouter,
        mapper: ConversationMapper,
        state_manager: ConversationStateManager,  # NUEVO
        session: Session | None = None,
        conversation_repo: ConversationRepository | None = None,
        message_repo: MessageRepository | None = None,
    ) -> None:
        self._router = router
        self._mapper = mapper
        self._state_manager = state_manager  # NUEVO
        self._session = session
        self._conversation_repo = conversation_repo
        self._message_repo = message_repo

    def handle_message(self, message: ConversationMessage) -> ChannelResponse:
        state = self._state_manager.get_or_create(  # NUEVO
            conversation_id=message.conversation_id,
            company_id=message.company_id,
            customer_id=message.customer_id,
        )
        if state.current_state in (
            "completed", "cancelled", "escalated"
        ):
            return ChannelResponse(
                status="rejected",
                message="La conversación se encuentra finalizada.",
            )

        # Transición real: new → in_progress (solo primer mensaje)
        if state.current_state == "new":
            self._state_manager.transition(
                message.conversation_id, "in_progress"
            )

        # Transición real: in_progress → awaiting_brain
        self._state_manager.transition(
            message.conversation_id, "awaiting_brain"
        )

        context = ConversationContext.from_message(message)
        business_response = self._router.route(context)

        # Transición real: awaiting_brain → in_progress
        self._state_manager.transition(
            message.conversation_id, "in_progress"
        )

        response = self._mapper.to_channel_response(business_response)
        self._persist(message, business_response.message)
        return response
```

### 2.2 `app/api/dependencies.py` — Dependencies

**Cambio:** Instanciar `ConversationStateManager` y pasarlo a `ConversationService`.

```python
from app.core.conversation.state_manager import ConversationStateManager

def get_conversation_service() -> ConversationService:
    ...
    state_manager = ConversationStateManager(session=session)
    
    return ConversationService(
        router=router,
        mapper=mapper,
        state_manager=state_manager,  # NUEVO
        session=session,
        conversation_repo=conversation_repo,
        message_repo=message_repo,
    )
```

### 2.3 `app/infrastructure/models/__init__.py`

**Cambio:** Exportar `ConversationStateHistoryModel` para que Alembic lo detecte.

Sin cambio requerido si se usa `Base.metadata` de SQLAlchemy — la importación del modelo es suficiente para que Alembic lo encuentre. Pero por consistencia con el código existente, se importará en el `__init__.py`.

---

## 3. Contratos Utilizados

### Contratos de dominio (nuevos)

| Contrato | Archivo | Propósito |
|---|---|---|
| `ConversationState` | `app/domain/conversation/state.py` | Objeto de dominio del estado conversacional. Propiedad de ENG-002 (AR-001). |

### Contratos de dominio (existentes, sin cambios)

| Contrato | Archivo | Propósito en I1 |
|---|---|---|
| `ConversationMessage` | `app/domain/conversation/contracts.py` | Entrada. Sin cambios. |
| `ConversationContext` | `app/domain/conversation/contracts.py` | Sin cambios. El estado se gestiona aparte, no se incorpora al context todavía (será en I2). |
| `ChannelResponse` | `app/domain/conversation/contracts.py` | Salida. Sin cambios. Se agrega uso de `status="rejected"` para terminal. |
| `BusinessRequest` | `app/domain/business/contracts.py` | Sin cambios. AR-003 se respeta: el contrato no se modifica. |
| `BusinessDecision` | `app/domain/business/contracts.py` | Sin cambios. |

### Contrato de infrastructura (nuevo)

| Modelo | Archivo | Propósito |
|---|---|---|
| `ConversationStateHistoryModel` | `app/infrastructure/models/conversation_state_history.py` | Auditoría de transiciones de estado. |

---

## 4. Persistencia Necesaria

### Tabla: `conversation_state_history`

| Columna | Tipo | Nullable | Descripción |
|---|---|---|---|
| `id` | UUID (PK) | No | Identificador único |
| `conversation_id` | UUID (FK→conversation.id) | No | Conversación asociada |
| `from_state` | String(50) | No | Estado anterior |
| `to_state` | String(50) | No | Nuevo estado |
| `reason` | String(255) | Sí | Razón de la transición |
| `created_at` | DateTime(tz) | No | Timestamp |

### Columna existente reutilizada: `conversation.status`

Actualmente almacena `"active"` para toda conversación. En I1, `status` almacenará el estado actual del Conversation State Manager (`new`, `in_progress`, `awaiting_info`, `awaiting_brain`, `awaiting_client`, `completed`, `cancelled`, `escalated`).

**Compatibilidad hacia atrás:** La migración no modifica el esquema de `conversation`. No hay conversaciones existentes en producción que migrar (Sprint 0 es local). El `server_default="active"` en la migración existente es irrelevante porque el nuevo código siempre escribirá el estado explícitamente.

### Integración con repositorio existente

`ConversationRepository` ya implementa `update()`. El State Manager usará este método para persistir cambios de estado:

```python
def transition(self, conversation_id: UUID, target_state: str) -> ConversationState:
    if not self.can_transition(current, target):
        raise ValueError(...)
    
    # Actualizar columna status en ConversationModel
    conv = self._conversation_repo.get(conversation_id)
    conv.status = target_state
    self._conversation_repo.update(conv)
    
    # Registrar en history
    history = ConversationStateHistoryModel(...)
    # persistir history (directo con session.add o nuevo HistoryRepository)
    
    if self._session:
        self._session.commit()
```

**Decisión:** En I1, el State Manager tendrá acceso opcional a `BaseRepository[ConversationStateHistoryModel]` para persistencia. Sin sesión, opera en memoria (útil para tests unitarios sin DB).

---

## 5. Integración con el Conversation Engine Actual

### Pipeline actual (antes de I1)

```
POST /messages
  → ConversationService.handle_message(message)
    → ConversationContext.from_message(message)        # (futuro I2)
    → MessageRouter.route(context)                      # CE → BB
      → BusinessBrainService.process(BusinessRequest)   # ENG-001
      → BusinessDecision                                # BB → CE
    → ConversationMapper.to_channel_response(decision)  # (futuro I4+I5)
    → _persist()                                        # DB
    → ChannelResponse
```

### Pipeline después de I1

```
POST /messages
  → ConversationService.handle_message(message)
    → ConversationContext.from_message(message)
    → **StateManager.get_or_create()**                   # NUEVO
    → **if new: StateManager.transition("in_progress")**  # NUEVO (new → in_progress)
    → **StateManager.transition("awaiting_brain")**       # NUEVO (in_progress → awaiting_brain)
    → MessageRouter.route(context)
      → BusinessBrainService.process(BusinessRequest)
      → BusinessDecision
    → **StateManager.transition("in_progress")**          # NUEVO (awaiting_brain → in_progress)
    → ConversationMapper.to_channel_response(decision)
    → _persist()
    → ChannelResponse
```

**No se modifican:**
- El contrato `BusinessRequest` → `BusinessDecision` (AR-003)
- El `MessageRouter`
- El `ConversationMapper`
- Las firmas de los endpoints HTTP

**Se preserva:** El Vertical Slice existente (VS1) no cambia su comportamiento observable. Los tests existentes siguen pasando porque:
- El State Manager no rechaza conversaciones nuevas (crea estado `new` → transiciona a `in_progress`)
- No hay conversaciones en estado terminal en los tests
- El ChannelResponse retornado es el mismo (solo se agrega `status="rejected"` en caso terminal, que ningún test existente ejercita)

---

## 6. Tests Requeridos

### 6.1 Tests Unitarios — Conversation State Manager

| Test | Descripción | Archivo |
|---|---|---|
| `test_initial_state_is_new` | Al crear estado, `current_state == "new"` | `tests/test_conversation_state.py` |
| `test_transition_new_to_in_progress` | Transición válida: new → in_progress | `tests/test_conversation_state.py` |
| `test_transition_completed_to_in_progress_raises` | Transición inválida desde terminal lanza ValueError | `tests/test_conversation_state.py` |
| `test_can_transition_returns_false_for_invalid` | can_transition() retorna False sin lanzar | `tests/test_conversation_state.py` |
| `test_get_or_create_returns_same_for_existing` | Segunda llamada retorna mismo estado | `tests/test_conversation_state.py` |
| `test_get_or_create_persists_to_db` | Cuando hay sesión, persiste el estado inicial | `tests/test_conversation_state.py` |
| `test_transition_persists_history` | Transición registra entrada en history | `tests/test_conversation_state.py` |
| `test_all_transitions_are_defined` | Cada estado tiene transiciones válidas | `tests/test_conversation_state.py` |
| `test_terminal_states_block_processing` | Terminal → ChannelResponse(rejected) | `tests/test_conversation_state.py` |

### 6.2 Tests de Integración — Conversation Service

| Test | Descripción | Archivo |
|---|---|---|
| `test_service_with_state_manager_tracks_state` | Tras llamada, estado es "in_progress" | `tests/test_conversation_service.py` |
| `test_service_rejects_terminal_conversation` | Mensaje en conversación finalizada es rechazado | `tests/test_conversation_service.py` |

### 6.3 Tests de Regresión (deben seguir pasando sin cambios)

| Test | Archivo |
|---|---|
| `test_conversation_service_returns_channel_response` | `tests/test_conversation_service.py` |
| `test_conversation_message_endpoint` | `tests/test_conversation_endpoint.py` |
| `test_conversation_message_endpoint_rejects_empty_content` | `tests/test_conversation_endpoint.py` |
| `test_vs1_greeting_flow` | `tests/test_vs1_integration.py` |
| `test_vs1_farewell_flow` | `tests/test_vs1_integration.py` |
| `test_vs1_knowledge_horario_flow` | `tests/test_vs1_integration.py` |
| `test_vs1_price_inquiry_knowledge_flow` | `tests/test_vs1_integration.py` |
| Total 10 tests VS1 + 2 endpoints + 1 service = **13 tests de regresión** |

### 6.4 Tests de Infraestructura

| Test | Archivo |
|---|---|
| `test_conversation_state_history_repository` (nuevo) | `tests/test_infrastructure/test_repositories.py` |

---

## 7. Riesgos de Romper el Vertical Slice Existente

### 7.1 Riesgo: El State Manager rechaza conversaciones existentes

| Escenario | ¿Ocurre? | Mitigación |
|---|---|---|
| Una conversación sin estado previo | Sí — el State Manager crea estado `new` y transiciona a `in_progress` | **Sin riesgo.** Flujo normal. |
| Una conversación en estado terminal recibe un mensaje | Solo si el test específicamente lo provoca | **Sin riesgo para VS1.** Los tests existentes siempre usan conversaciones nuevas. |
| El State Manager falla al no tener sesión de BD | Los tests unitarios existentes no usan sesión | **Mitigado.** `state_manager` acepta `session=None` y opera en memoria. El servicio actual sin sesión no debe romperse. |

### 7.2 Riesgo: Cambio en el constructor de ConversationService

| Escenario | ¿Ocurre? | Mitigación |
|---|---|---|
| `test_conversation_service_returns_channel_response` construye `ConversationService` sin `state_manager` | Sí — el test no pasa `state_manager` | **Riesgo alto.** El test crea el servicio directamente. Requiere actualizar el test para pasar un `ConversationStateManager()`, o hacer el parámetro opcional con un default. |

**Decisión:** El parámetro `state_manager` será **requerido** en el constructor. El test existente se actualiza para pasar `state_manager=ConversationStateManager()`. Esto es explícito y evita defaults ocultos.

### 7.3 Riesgo: El endpoint HTTP retorna status diferente

| Escenario | ¿Ocurre? | Mitigación |
|---|---|---|
| `ChannelResponse.status` cambia de "accepted" a otra cosa | No — los tests verifican `data["status"] == "accepted"` | **Sin riesgo.** El `ConversationMapper` sigue mapeando `decision.status` directamente. El State Manager no altera `ChannelResponse.status`. Solo lo retorna con `"rejected"` si la conversación está terminal, pero ningún test actual ejercita ese camino. |

### 7.4 Riesgo: La migración Alembic nueva falla sobre datos existentes

| Escenario | ¿Ocurre? | Mitigación |
|---|---|---|
| Migración ejecutada sobre BD vacía (dev local) | Sí — es el entorno actual | **Sin riesgo.** No hay datos de producción. |
| `upgrade()` lanza error por tabla existente | No — la tabla `conversation_state_history` es nueva | **Sin riesgo.** No hay conflictos de nombres. |
| La columna `status` en `conversation` cambia de tipo o constraint | No — no se modifica | **Sin riesgo.** La columna no se toca. |

### 7.5 Riesgo: Acoplamiento State Manager → Repository

| Escenario | ¿Ocurre? | Mitigación |
|---|---|---|
| StateManager depende de `ConversationRepository` para leer/escribir estado | Sí — necesita `get()` y `update()` | **Riesgo controlado.** El StateManager recibe el repo por inyección (como `ConversationService` recibe `message_repo`). Tests unitarios pueden pasar un repo mock. |

---

## 8. Resumen de Archivos

### Crear (4 archivos)

| Archivo | Tipo | Líneas estimadas |
|---|---|---|
| `app/domain/conversation/state.py` | Domain contract | ~30 |
| `app/core/conversation/state_manager.py` | Core logic | ~80 |
| `app/infrastructure/models/conversation_state_history.py` | ORM model | ~40 |
| `alembic/versions/20260718_0001_add_conversation_state.py` | Migration | ~30 |

### Modificar (3 archivos)

| Archivo | Cambio |
|---|---|
| `app/core/conversation/service.py` | Inyectar StateManager, agregar 2 transiciones en pipeline |
| `app/api/dependencies.py` | Instanciar StateManager, pasar a ConversationService |
| `app/infrastructure/models/__init__.py` | Importar ConversationStateHistoryModel |

### Agregar/Actualizar tests

| Archivo | Cambio |
|---|---|
| `tests/test_conversation_state.py` | Nuevo. ~9 tests unitarios + 1 integración |
| `tests/test_conversation_service.py` | Modificar test existente para pasar `state_manager` |
| `tests/test_infrastructure/test_repositories.py` | Agregar test para history repository |

---

## 9. Criterio de Éxito

- 82 tests existentes + 10 nuevos = **92 tests pasando**
- El pipeline VS1 completo funciona sin cambios visibles desde el exterior
- Toda conversación nueva comienza en `new`
- Toda conversación activa está en `in_progress`
- Transiciones inválidas lanzan error
- Conversaciones en estado terminal devuelven `ChannelResponse(status="rejected")`
- Sin cambios en contratos públicos (BusinessRequest, BusinessDecision, API endpoints)
- Sin cambios en blueprints, ADRs, o resoluciones AR-001/002/003
