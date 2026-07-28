# I5 — Channel Adapter: Technical Plan

**Implementation status:** Implemented / Closed  
**Closure evidence:** `app/core/integration/channel_adapter.py`, `app/core/conversation/channel_adapter.py`, `ConversationService` adapter selection, `tests/test_channel_adapter.py`, and full Core quality gates passing.  
**Historical note:** This document is retained as the original implementation plan.

**Blueprint:** D-009-09  
**Incremento:** 5 de 5  
**Dependencias:** I1 (State Manager) + I2 (Context Builder) + I3 (Topic Detector) + I4 (Response Composer)  
**Estado de brechas (Gap Analysis):**  
  - Brecha 1: **RESUELTA en I4** (ConversationMapper ya recibe BusinessResponse)  
  - Brecha 2: **Pendiente** — no existe interfaz abstracta ChannelAdapter  
  - Brecha 3: **Pendiente** — solo WhatsApp implementado (fuera de alcance de I5)

---

## 1. Responsabilidad del Channel Adapter

### 1.1 Definición (D-009-09)

| Atributo | Valor |
|---|---|
| **Responsabilidad** | Adaptar la Business Response al formato y capacidades del canal de destino |
| **Pregunta** | ¿Cómo debe enviarse esta respuesta por este canal? |
| **Entradas** | Business Response |
| **Salida** | Channel Response |
| **Principios** | Independiente del negocio, multicanal, reutilizable, extensible |
| **Regla** | Todo envío hacia un canal debe realizarse mediante un Channel Adapter |

### 1.2 Qué NO debe hacer

- NO contiene lógica de negocio.
- NO decide qué responder.
- NO clasifica intents ni detecta topics.
- NO gestiona estados de conversación.
- NO persiste mensajes.
- NO envía datos por HTTP (eso es responsabilidad del sender específico).

### 1.3 Contrato exacto

```
BusinessResponse            ← entrada (desde ResponseComposer)
    │
ChannelAdapter.adapt()
    │
ChannelResponse             ← salida (hacia sender o response HTTP)
```

---

## 2. Estado actual

### 2.1 Componentes existentes

| Componente | Ubicación | Rol actual | Problema |
|---|---|---|---|
| `ConversationMapper` | `app/core/conversation/mapper.py` | Recibe `BusinessResponse`, produce `ChannelResponse` | **No formalizado.** Es un mapper genérico sin interfaz. No sabe qué canal es. |
| `to_whatsapp_text_payload()` | `app/channels/whatsapp/mapper.py` | Recibe `ChannelResponse`, produce dict WhatsApp API | Es correcto — transforma `ChannelResponse` a formato del canal. No necesita cambio. |
| `WhatsAppSender` | `app/channels/whatsapp/sender.py` | Toma `ChannelResponse`, envía por HTTP a WhatsApp | Es correcto — es el sender, no el adapter. |
| `WhatsAppAdapter` (inbound) | `app/channels/whatsapp/adapter.py` | Convierte webhook payload a `ConversationMessage` | Es el **Message Receiver** del canal WhatsApp, no el Channel Adapter outbound. Nombre confuso pero funcional. |

### 2.2 Flujo actual

```
ResponseComposer
    ↓ BusinessResponse
ConversationMapper.to_channel_response()   ← acoplado directamente
    ↓ ChannelResponse
WhatsAppSender.send()   o   HTTP Response JSON
```

### 2.3 Gaps identificados

1. **No existe interfaz `ChannelAdapter`** — `ConversationMapper` está acoplado por tipo en `ConversationService`.
2. **`ConversationService` no sabe qué canal es** — usa un mapper único para todos los canales. Hoy funciona porque solo hay HTTP (síncrono) y WhatsApp (asíncrono, pero el mapper es el mismo).
3. **`ConversationMapper` está en `core/conversation/`** — debería estar en `app/channels/` o al menos bajo una abstracción formal.

---

## 3. Diseño

### 3.1 Interfaz ChannelAdapter

```python
class ChannelAdapter(ABC):
    """Adapta una BusinessResponse al formato del canal de destino.
    
    Responsabilidad (D-009-09): ¿Cómo debe enviarse esta respuesta por este canal?
    
    Entrada: BusinessResponse (mensaje + status + tone)
    Salida: ChannelResponse (status + message)
    
    Regla: Todo envío hacia un canal debe realizarse mediante un Channel Adapter.
    Principios: Independiente del negocio, multicanal, reutilizable, extensible.
    """
    
    @abstractmethod
    def adapt(self, response: BusinessResponse) -> ChannelResponse:
        """Transforma BusinessResponse → ChannelResponse."""
```

**Decisiones de diseño:**

- **Abstract method único.** No se necesitan más métodos en I5. `adapt()` es la operación fundamental.
- **Sin configuración de canal en el método.** La config (límites de caracteres, tipos de contenido soportados) se pasa en el constructor de cada adapter concreto cuando sea necesario.
- **`ChannelResponse` no se modifica.** Sigue siendo `{status, message}`. Cuando un canal necesite metadatos adicionales (ej: botones, imágenes), se extenderá `ChannelResponse` en un futuro incremento.
- **`tone` está disponible** en `BusinessResponse` pero ningún adapter lo consume aún. Queda como extensión futura.

### 3.2 HttpChannelAdapter (concreto)

Reemplaza a `ConversationMapper`. Es el adapter por defecto.

```python
class HttpChannelAdapter(ChannelAdapter):
    def adapt(self, response: BusinessResponse) -> ChannelResponse:
        return ChannelResponse(
            status=response.status,
            message=response.message,
        )
```

- Sin dependencias externas.
- Comportamiento idéntico a `ConversationMapper.to_channel_response()`.
- Se usa para canales HTTP directos (endpoints `/messages`, `/conversation/message`).

### 3.3 Relación con WhatsApp

**No se crea `WhatsAppChannelAdapter` en I5.** Razones:

1. El `WhatsAppSender` ya hace la transformación correcta: `ChannelResponse → WhatsApp API payload → HTTP send`. No hay nada que adaptar entre `BusinessResponse` y `ChannelResponse` que sea específico de WhatsApp.
2. El `tone` de `BusinessResponse` no se usa todavía en ningún adapter (extensión futura).
3. "No rediseñar WhatsApp" — el flujo actual funciona y cumple el blueprint: el adapter produce `ChannelResponse`, el sender lo envía.

**Futuro:** Cuando se necesite formateo específico de WhatsApp (ej: emojis por tone, límite de 1024 chars, soporte de botones), se crea `WhatsAppChannelAdapter(ChannelAdapter)` y se registra. Sin cambios en el `ConversationService` ni en `HttpChannelAdapter`.

### 3.4 Mecanismo de selección

`ConversationService` recibe un diccionario `{channel_name: ChannelAdapter}` y selecciona según `message.channel`:

```python
class ConversationService:
    def __init__(
        self,
        ...,
        adapters: dict[str, ChannelAdapter],      # NUEVO
    ) -> None:
        self._adapters = adapters
    
    def handle_message(self, message: ConversationMessage) -> ChannelResponse:
        ...
        adapter = self._get_adapter(message.channel)
        response = adapter.adapt(business_response)
        ...
    
    def _get_adapter(self, channel: str) -> ChannelAdapter:
        return self._adapters.get(channel, self._adapters.get("http"))
```

- Si `message.channel == "http"` (default) → `HttpChannelAdapter`
- Si `message.channel == "whatsapp"` → fallback a `"http"` (hasta que exista un adapter específico)
- Toda channel no registrada → fallback a `"http"`

### 3.5 Ubicación arquitectónica

```
app/
  channels/                    ← canales (inbound + outbound)
    whatsapp/
      adapter.py               ← Message Receiver (inbound) — no se toca
      mapper.py                ← ChannelResponse → WhatsApp API — no se toca
      sender.py                ← envío HTTP — no se toca
      ...
  core/
    conversation/
      channel_adapter.py       ← NUEVO: ChannelAdapter (ABC) + HttpChannelAdapter
      mapper.py                ← ELIMINAR: reemplazado por HttpChannelAdapter
      service.py               ← MODIFICAR: usar adapters en vez de mapper
      ...
```

**Principio:** `ChannelAdapter` vive en `core/conversation/` porque es parte del pipeline del Conversation Engine. Los adapters concretos pueden vivir en `core/conversation/` (si son genéricos como HTTP) o en `channels/<nombre>/` (si son específicos de canal).

---

## 4. Cambios necesarios

### 4.1 Archivos nuevos (1)

| Archivo | Contenido | Líneas |
|---|---|---|
| `app/core/conversation/channel_adapter.py` | `ChannelAdapter` (ABC) + `HttpChannelAdapter` (concreto) | ~25 |

### 4.2 Archivos eliminados (1)

| Archivo | Razón |
|---|---|
| `app/core/conversation/mapper.py` | Reemplazado por `HttpChannelAdapter`. Cero líneas de lógica duplicada. |

### 4.3 Archivos modificados (3)

| Archivo | Cambio |
|---|---|
| `app/core/conversation/service.py` | Import `ChannelAdapter` en vez de `ConversationMapper`. Constructor recibe `adapters: dict[str, ChannelAdapter]`. `handle_message()` usa `_get_adapter(message.channel).adapt()`. |
| `app/api/dependencies.py` | Import `HttpChannelAdapter`. Crear `adapters = {"http": HttpChannelAdapter()}`. Pasar a `ConversationService`. |
| `tests/test_conversation_service.py` | Import `HttpChannelAdapter`. Pasar `adapters={"http": HttpChannelAdapter()}` al constructor. |

### 4.4 Archivos no modificados

| Archivo | Razón |
|---|---|
| `app/channels/whatsapp/adapter.py` | Inbound adapter. No tocar. |
| `app/channels/whatsapp/mapper.py` | `ChannelResponse → WhatsApp payload`. Correcto. No tocar. |
| `app/channels/whatsapp/sender.py` | Sender. No tocar. |
| `app/channels/whatsapp/webhook.py` | Routing. No tocar. |
| `app/channels/whatsapp/client.py` | HTTP client. No tocar. |
| `app/core/conversation/state_manager.py` | I1 intacto. |
| `app/core/conversation/context_builder.py` | I2 intacto. |
| `app/core/conversation/topic_detector.py` | I3 intacto. |
| `app/core/conversation/response_composer.py` | I4 intacto. |
| `app/core/business/*` | ENG-001 intacto. |
| `app/domain/*` | Contratos intactos. |

### 4.5 Contratos afectados

| Contrato | Cambio |
|---|---|
| `ChannelResponse` | Sin cambios. Sigue siendo `{status, message}`. |
| `BusinessResponse` | Sin cambios. El `tone` sigue disponible pero no consumido. |
| `ConversationService.__init__` | **NUEVO parámetro:** `adapters: dict[str, ChannelAdapter]`. Reemplaza `mapper: ConversationMapper`. |

### 4.6 Dependencias

| Clase | Depende de | Existe desde |
|---|---|---|
| `ChannelAdapter` | `BusinessResponse`, `ChannelResponse` | I5 |
| `HttpChannelAdapter` | `ChannelAdapter` (hereda) | I5 |
| `ConversationService` | `dict[str, ChannelAdapter]` (reemplaza `ConversationMapper`) | I1 (modificado en I5) |

---

## 5. Pipeline final esperado

### 5.1 Pipeline oficial (D-009-03)

```
Message
    ↓
Message Receiver
    ↓
Conversation Context Builder
    ↓
Topic Detector
    ↓
Conversation State Manager
    ↓
Business Brain
    ↓
Response Composer
    ↓
Channel Adapter          ← I5: formalizado
    ↓
Channel Response
```

### 5.2 Pipeline implementado (I1+I2+I3+I4+I5)

```
StateManager.get_or_create()
    ↓
ContextBuilder.build(message, state)
    ↓
TopicDetector.detect(context)
    ↓
StateManager.transition("awaiting_brain")
    ↓
Router.route(context) → BusinessDecision
    ↓
StateManager.transition("in_progress")
    ↓
ResponseComposer.compose(decision, context) → BusinessResponse
    ↓
ChannelAdapter.adapt(response)        ← I5: seleccionado por message.channel
    ↓
ChannelResponse
    ↓
Persist(message, response_message)
    ↓
Retorno al caller (HTTP response o WhatsAppSender)
```

### 5.3 Flujo HTTP (síncrono)

```
POST /messages
  → ConversationService.handle_message()
    → ... → ChannelAdapter.adapt() → ChannelResponse
  → FastAPI serializa ChannelResponse a JSON
  → HTTP 200
```

### 5.4 Flujo WhatsApp (asíncrono)

```
POST /webhooks/whatsapp
  → WhatsAppAdapter.to_conversation_message() → ConversationMessage(channel="whatsapp")
  → ConversationService.handle_message()
    → ... → _get_adapter("whatsapp") → fallback a "http" → HttpChannelAdapter.adapt()
    → ChannelResponse
  → WhatsAppSender.send(ChannelResponse, to)
    → to_whatsapp_text_payload() → WhatsApp API payload
    → HTTP POST a WhatsApp API
  → HTTP 200 (OK al webhook)
```

**Nota:** El adapter usado es `HttpChannelAdapter` (fallback). El `WhatsAppSender` sigue haciendo la transformación a formato WhatsApp API. Esto es correcto porque la adaptación BusinessResponse → ChannelResponse no necesita lógica específica de WhatsApp en I5.

---

## 6. Tests

### 6.1 Tests unitarios — ChannelAdapter (nuevo archivo)

Nuevo: `tests/test_channel_adapter.py`

| Test | Descripción |
|---|---|
| `test_channel_adapter_is_abstract` | `ChannelAdapter` no puede instanciarse directamente |
| `test_http_adapter_adapt_returns_channel_response` | `HttpChannelAdapter().adapt()` → `ChannelResponse` |
| `test_http_adapter_copies_status_and_message` | `status` y `message` de `BusinessResponse` se copian a `ChannelResponse` |
| `test_http_adapter_ignores_tone` | `tone` presente pero no afecta output |
| `test_http_adapter_with_different_statuses` | status="rejected" se propaga correctamente |

### 6.2 Tests de integración — ConversationService

| Archivo | Cambio |
|---|---|
| `tests/test_conversation_service.py` | Importar `HttpChannelAdapter`. Pasar `adapters={"http": HttpChannelAdapter()}`. Remover `mapper=ConversationMapper()`. |

### 6.3 Tests de regresión

| Archivo | Tests | ¿Cambia? |
|---|---|---|
| `tests/test_vs1_integration.py` | 10 tests | **No** |
| `tests/test_conversation_endpoint.py` | 2 tests | **No** |
| `tests/test_conversation_service.py` | 1 test | **Modificado** (adapters injection) |
| `tests/test_conversation_contracts.py` | 3 tests | **No** |
| `tests/test_conversation_state.py` | 12 tests | **No** |
| `tests/test_conversation_state_manager.py` | 4 tests | **No** |
| `tests/test_conversation_context_builder.py` | 8 tests | **No** |
| `tests/test_topic_detector.py` | 11 tests | **No** |
| `tests/test_response_composer.py` | 7 tests | **No** |
| `tests/test_business_*` | 15 tests | **No** |
| `tests/test_whatsapp_outbound.py` | 8 tests | **No** |
| Total regresión | **~81 tests** | **0 cambios de expectativa** |

### 6.4 Resumen de cambios de tests

| Tipo | Archivos | Tests |
|---|---|---|
| Nuevo | `tests/test_channel_adapter.py` | ~5 tests |
| Modificar | `tests/test_conversation_service.py` | 1 test (adapters injection) |
| Sin cambios | ~20 archivos de test | ~81 tests |

---

## 7. Riesgos

### R1 — `ConversationMapper` es usado en referencias externas

| Escenario | Impacto | Probabilidad | Mitigación |
|---|---|---|---|
| Algún archivo importa `ConversationMapper` que no se haya identificado | Error de importación en runtime | **Baja** (solo 4 referencias, todas identificadas) | Se elimina `mapper.py` y se actualizan todas las referencias en el mismo commit. |

### R2 — Fallback de adapter para WhatsApp cambia comportamiento

| Escenario | Impacto | Probabilidad | Mitigación |
|---|---|---|---|
| Al usar `_get_adapter("whatsapp")` → fallback a `"http"`, el comportamiento es diferente al actual | Hoy WhatsApp ya usa `ConversationMapper` (que produce el mismo `ChannelResponse`). El fallback produce exactamente lo mismo. | **Nula** | `HttpChannelAdapter.adapt()` produce el mismo `ChannelResponse` que `ConversationMapper.to_channel_response()`. Cero diff. |

### R3 — Nuevos canales requieren cambios en `ConversationService`

| Escenario | Impacto | Probabilidad | Mitigación |
|---|---|---|---|
| Agregar un canal requiere modificar `ConversationService` | **Bajo** — el `adapters` dict ya soporta registro dinámico | **Baja** | El diseño con `dict[str, ChannelAdapter]` permite agregar canales desde `dependencies.py` sin tocar `service.py`. |

### R4 — `tone` no se usa y podría eliminarse

| Escenario | Impacto | Probabilidad | Mitigación |
|---|---|---|---|
| Un desarrollador futuro elimina `tone` de `BusinessResponse` pensando que es código muerto | Rompe la extensibilidad planeada | **Media** | Documentado en plan. El `tone` es preparación para adapters específicos de canal (WhatsApp, Telegram). No es código muerto — es capacidad diferida. |

---

## Resumen de archivos

| Tipo | Archivos | Líneas |
|---|---|---|
| Crear (1) | `app/core/conversation/channel_adapter.py` | ~25 |
| Eliminar (1) | `app/core/conversation/mapper.py` | −10 |
| Modificar (3) | `service.py`, `dependencies.py`, `test_conversation_service.py` | ~15 total |
| Tests nuevos (1) | `tests/test_channel_adapter.py` | ~50 |
| Tests modificar (1) | `tests/test_conversation_service.py` | ~5 líneas |
| Regresión | ~81 tests | Sin cambios |
