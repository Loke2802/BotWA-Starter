# Architecture Gap Analysis — Conversation Engine (ENG-002)

**Documento:** CONVERSATION_ENGINE_GAP_ANALYSIS.md  
**Blueprint:** D-009 — Conversation Engine (v1.0, Aprobado)  
**Código base:** Commit `ca9327d` — CTO Update Sprint 0  
**Fecha:** 2026-07-18  

---

## 1. Blueprint Breakdown

### 1.1 Communication Pipeline

El Blueprint D-009 define el siguiente pipeline secuencial:

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
Channel Adapter
    ↓
Response
```

### 1.2 Descomposición por Componente

#### Componente 1: Message Receiver

| Atributo | Valor |
|---|---|
| **Responsabilidad** | Recibir, validar y normalizar mensajes de cualquier canal |
| **Entradas** | Payload crudo del canal (HTTP, webhook, SDK, etc.) |
| **Salidas** | `Conversation Message` |
| **Regla** | Todo mensaje ingresa por el Message Receiver |
| **Principios** | Independiente del canal, normalizado |
| **Ref. blueprint** | D-009-04 |

#### Componente 2: Conversation Context Builder

| Atributo | Valor |
|---|---|
| **Responsabilidad** | Construir el contexto conversacional que representa el estado actual de la interacción |
| **Entradas** | `Conversation Message`, Historial, Estado conversacional, Perfil del cliente, Metadata del canal |
| **Salidas** | `Conversation Context` |
| **Regla** | Solo el Conversation Context Builder puede generar el Conversation Context |
| **Principios** | Continuidad conversacional, independiente del canal y del idioma, sin decisiones de negocio |
| **Ref. blueprint** | D-009-05 |

#### Componente 3: Topic Detector

| Atributo | Valor |
|---|---|
| **Responsabilidad** | Identificar y administrar los temas (topics) e hilos (threads) de una conversación |
| **Entradas** | `Conversation Context`, `Conversation Message`, Historial relevante |
| **Salidas** | `Conversation Topics`, `Conversation Threads` |
| **Capacidades** | Detectar tema principal/secundario, cambios de tema, reanudar temas anteriores, múltiples hilos |
| **Regla** | Solo el Topic Detector administra los temas e hilos |
| **Ref. blueprint** | D-009-06 |

#### Componente 4: Conversation State Manager

| Atributo | Valor |
|---|---|
| **Responsabilidad** | Administrar el estado de cada conversación y de cada hilo conversacional durante todo su ciclo de vida |
| **Entradas** | `Conversation Context`, `Conversation Topics`, Historial, Metadata del canal |
| **Salidas** | `Conversation State` |
| **Estados** | Nueva → En progreso → Esperando información → Esperando Business Brain → Esperando respuesta del cliente → Finalizada / Cancelada / Escalada |
| **Regla** | Solo el Conversation State Manager puede modificar el Conversation State |
| **Principios** | Consistente, determinístico, auditable, reanudable, independiente del canal |
| **Ref. blueprint** | D-009-07 |

#### Componente 5: Business Brain (Engine externo, ENG-001)

| Atributo | Valor |
|---|---|
| **Responsabilidad** | Recibir `Business Decision Request`, aplicar lógica de negocio, devolver `Business Decision` |
| **Entradas** | `Business Decision Request` (desde Conversation State Manager) |
| **Salidas** | `Business Decision` (hacia Response Composer) |
| **Nota** | Componente externo al ENG-002. El contrato entre engines es `BusinessDecisionRequest` / `BusinessDecision` (ADR-006). |

#### Componente 6: Response Composer

| Atributo | Valor |
|---|---|
| **Responsabilidad** | Transformar una `Business Decision` en una respuesta clara, natural y alineada con la identidad comunicacional de la empresa |
| **Entradas** | `Business Decision`, `Conversation Context`, `Conversation State`, Perfil del cliente, Configuración comunicacional de la empresa |
| **Salidas** | `Business Response` |
| **Regla** | Solo el Response Composer puede transformar una Business Decision en una Business Response |
| **Principios** | Natural, consistente, personalizable, multilingüe, independiente del canal |
| **Ref. blueprint** | D-009-08 |

#### Componente 7: Channel Adapter

| Atributo | Valor |
|---|---|
| **Responsabilidad** | Adaptar la `Business Response` al formato y capacidades del canal de destino |
| **Entradas** | `Business Response`, Configuración del canal, Capacidades del canal |
| **Salidas** | `Channel Response` |
| **Regla** | Todo envío hacia un canal debe realizarse mediante un Channel Adapter |
| **Principios** | Independiente del negocio, multicanal, reutilizable, extensible |
| **Cubrimiento** | WhatsApp, Telegram, Instagram, Web Chat, Email, Voz |
| **Ref. blueprint** | D-009-09 |

### 1.3 Objetos Conversacionales (Blueprint)

| Objeto | Blueprint | ¿Existe en código? |
|---|---|---|
| `Conversation Message` | D-009-04 | Sí — `app/domain/conversation/contracts.py:ConversationMessage` |
| `Conversation Context` | D-009-05 | Sí — `app/domain/conversation/contracts.py:ConversationContext` |
| `Conversation Topics` | D-009-06 | No |
| `Conversation Threads` | D-009-06 | No |
| `Conversation State` | D-009-07 | No |
| `Business Decision Request` | D-009-00 | Parcial — `app/domain/business/contracts.py:BusinessRequest` |
| `Business Response` | D-009-08 | No |
| `Channel Response` | D-009-09 | Sí — `app/domain/conversation/contracts.py:ChannelResponse` |

---

## 2. Código Actual

### Componente 1: Message Receiver

**Estado: Implementado**

| Aspecto | Detalle |
|---|---|
| **Código** | `app/api/routes.py:29-38` — endpoint `POST /conversation/message` recibe `ConversationMessage` vía FastAPI |
| **Código** | `app/channels/whatsapp/webhook.py:42-51` — endpoint `POST /webhooks/whatsapp` recibe payload Meta webhook |
| **Código** | `app/channels/whatsapp/adapter.py:13-36` — `WhatsAppAdapter.to_conversation_message()` normaliza payload → `ConversationMessage` |
| **Brecha** | No existe una interfaz o abstract method `MessageReceiver`. Cada canal implementa su propia recepción sin un contrato unificado. El blueprint dice "Todo mensaje ingresa por el Message Receiver" pero no hay un componente único de recepción. |

### Componente 2: Conversation Context Builder

**Estado: Parcial**

| Aspecto | Detalle |
|---|---|
| **Código** | `app/core/conversation/service.py:37` — `ConversationContext.from_message(message)` |
| **Código** | `app/domain/conversation/contracts.py:17-27` — `ConversationContext` contiene solo `message` + `context_id` + `created_at` |
| **Brecha** | El blueprint especifica que el Context Builder debe considerar: **historial**, **estado conversacional**, **perfil del cliente**, y **metadata del canal**. La implementación actual solo envuelve el `ConversationMessage`. No hay trazabilidad de mensajes anteriores, ni perfil de cliente, ni metadata de canal. |

### Componente 3: Topic Detector

**Estado: No implementado**

| Aspecto | Detalle |
|---|---|
| **Código** | No existe clase, módulo ni función relacionada |
| **Brecha** | El pipeline salta directamente de Context Builder a Business Brain. No hay detección de temas, ni hilos (`ConversationThreads`), ni administración de multi-tema. La única noción de "tema" es el `intent` del Business Brain, lo cual es incorrecto arquitectónicamente: el intent pertenece al ENG-001, no al ENG-002. |

### Componente 4: Conversation State Manager

**Estado: No implementado**

| Aspecto | Detalle |
|---|---|
| **Código** | No existe clase, módulo ni función relacionada |
| **Brecha** | No hay estados de conversación. Toda conversación se trata como nueva en cada mensaje. No hay pausa, reanudación, escalamiento, ni ciclo de vida. La persistencia registra `status="active"` en `ConversationModel` (en `service.py:58`) pero es un valor fijo, no un estado gestionado. |

### Componente 5: Business Brain (ENG-001)

**Estado: Implementado** (pero este gap analysis solo documenta el contrato)

| Aspecto | Detalle |
|---|---|
| **Código** | `app/core/business/service.py:26-56` — `BusinessBrainService.process(BusinessRequest) → BusinessDecision` |
| **Código** | `app/domain/business/contracts.py:6-29` — `BusinessRequest` y `BusinessDecision` |
| **Contrato** | El Conversation Engine llama a `BusinessBrainService.process()` con un `BusinessRequest` y recibe un `BusinessDecision`. |

### Componente 6: Response Composer

**Estado: No implementado**

| Aspecto | Detalle |
|---|---|
| **Código** | No existe clase, módulo ni función dedicada |
| **Brecha** | Actualmente no hay transformación alguna entre `BusinessDecision` y la respuesta al cliente. El `ConversationMapper.to_channel_response()` (ver Componente 7) toma directamente `BusinessDecision` y produce `ChannelResponse`. No hay etapa de composición de respuesta que considere tono, personalidad, idioma, o identidad empresarial. |

### Componente 7: Channel Adapter

**Estado: Parcial**

| Aspecto | Detalle |
|---|---|
| **Código** | `app/core/conversation/mapper.py:5-9` — `ConversationMapper.to_channel_response(decision)` toma `BusinessDecision` y devuelve `ChannelResponse` |
| **Código** | `app/channels/whatsapp/mapper.py:4-9` — `to_whatsapp_text_payload(response, to)` toma `ChannelResponse` y devuelve `dict` para API de WhatsApp |
| **Código** | `app/channels/whatsapp/sender.py:17-38` — `WhatsAppSender.send()` envía el payload |
| **Brecha 1** | El `ConversationMapper` actúa como si fuera un Channel Adapter pero opera sobre `BusinessDecision`, no sobre `BusinessResponse`. Esto significa que la etapa de Response Composer está ausente y su responsabilidad se fusionó incorrectamente con el adapter. |
| **Brecha 2** | No existe una interfaz abstracta `ChannelAdapter`. El `ConversationMapper` está acoplado directamente en `ConversationService`. |
| **Brecha 3** | Solo existe adapter para WhatsApp. Los otros 5 canales listados en el blueprint (Telegram, Instagram, Web Chat, Email, Voz) no tienen implementación. |

### 1.4 Resumen General

| Componente Blueprint | Responsabilidad | Estado | Referencia Código |
|---|---|---|---|
| Message Receiver | Recibir, validar, normalizar | **Implementado** | `routes.py`, `webhook.py`, `adapter.py` |
| Conversation Context Builder | Construir contexto con historial y perfil | **Parcial** | `service.py:37`, `contracts.py:17-27` |
| Topic Detector | Detectar temas y administrar hilos | **No implementado** | — |
| Conversation State Manager | Administrar ciclo de vida de la conversación | **No implementado** | — |
| Business Brain (ENG-001) | Recibir request, decidir, devolver decision | **Implementado** | `business/service.py` |
| Response Composer | Transformar decisión en respuesta natural | **No implementado** | — |
| Channel Adapter | Adaptar respuesta al canal destino | **Parcial** | `mapper.py`, `whatsapp/mapper.py` |

---

## 3. Dependency Graph

### 3.1 Grafo de Dependencias Arquitectónicas (Blueprint)

```
Message Receiver
    ↓
Conversation Context Builder ──→ requiere historial (repo/db)
    ↓
Topic Detector ──→ depende de Conversation Context
    ↓
Conversation State Manager ──→ depende de Conversation Context, Topics
    ↓
Business Brain ──→ (ENG-001, externo)
    ↓
Response Composer ──→ depende de Business Decision, Conversation Context, Conversation State
    ↓
Channel Adapter ──→ depende de Business Response
    ↓
Response
```

### 3.2 Dependencias de Implementación

```
WhatsAppAdapter ──→ produce ──→ ConversationMessage
    ↓
ConversationService.handle_message():
    1. ConversationContext.from_message() ──→ produce ConversationContext (sin historial)
    2. MessageRouter.route(context) ──→ consume ConversationContext, produce BusinessRequest ──→ llama a BusinessBrainService
    3. BusinessBrainService.process(request) ──→ produce BusinessDecision
    4. ConversationMapper.to_channel_response(decision) ──→ produce ChannelResponse
    5. _persist() ──→ guarda en DB
```

### 3.3 ¿Qué debe implementarse primero?

**Orden por dependencias arquitectónicas ascendentes:**

1. **Conversation State Manager** — Dependencia más basal. Sin estado, no hay contexto histórico, no hay pausa/reanudación, no hay ciclo de vida. El Topic Detector necesita estado para saber a qué hilo pertenece un mensaje. El Context Builder necesita estado para construir contexto histórico.

2. **Conversation Context Builder (completar)** — Depende del State Manager (necesita historial y estado). Sin contexto completo, el Topic Detector no tiene suficiente información.

3. **Topic Detector** — Depende de Context Builder y State Manager. Necesita contexto enriquecido y estado para detectar cambios de tema y administrar hilos.

4. **Response Composer** — Depende de Business Decision (ya implementada en ENG-001) y de Conversation Context + State. Puede implementarse después de Context Builder y State Manager, en paralelo con Topic Detector.

5. **Channel Adapter (formalizar)** — Depende de Business Response. Puede implementarse en paralelo con Response Composer, pero requiere que el Response Composer exista primero para producir Business Response en lugar de mapear directamente desde BusinessDecision.

### 3.4 ¿Qué puede implementarse en paralelo?

| Grupo | Componentes | Pre-requisito común |
|---|---|---|
| **Paralelo A** | Response Composer + Channel Adapter (formalización) | State Manager (parcial) + Context Builder (completado) |
| **Paralelo B** | Topic Detector | State Manager + Context Builder |

---

## 4. Incrementos

### Incremento 1 — Conversation State Manager

**Dependencias satisfechas:** Ninguna (es el primer componente en el orden arquitectónico).

**Qué implementar:**
- `ConversationState` object en `app/domain/conversation/contracts.py`
- `ConversationStateManager` en `app/core/conversation/state_manager.py`
- Máquina de estados: Nueva → En Progreso → Esperando Información → Esperando Business Brain → Esperando Respuesta Cliente → Finalizada / Cancelada / Escalada
- Persistencia del estado (extender `ConversationModel` o crear tabla separada)
- Integración en `ConversationService.handle_message()` para consultar/actualizar estado

**Justificación:** Todos los componentes río abajo (Context Builder, Topic Detector, Response Composer) necesitan estado conversacional. Sin estado no hay continuidad.

---

### Incremento 2 — Conversation Context Builder (completar)

**Dependencias satisfechas:** Conversation State Manager (Incremento 1).

**Qué implementar:**
- Enriquecer `ConversationContext` con:
  - `history: list[ConversationMessage]` — mensajes anteriores de la conversación
  - `state: ConversationState` — estado actual
  - `customer_profile: dict` — perfil del cliente (desde repositorio)
  - `channel_metadata: dict` — metadata del canal de origen
- Mecanismo de carga de historial desde repositorio
- `ConversationContextBuilder` class en `app/core/conversation/context_builder.py`

**Justificación:** El Context Builder actual es un wrapper mínimo. El blueprint exige historial, perfil y metadata. El Topic Detector y Response Composer dependen de un contexto completo.

---

### Incremento 3 — Topic Detector

**Dependencias satisfechas:** State Manager (I1) + Context Builder completo (I2).

**Qué implementar:**
- `ConversationTopics` y `ConversationThreads` objects en `app/domain/conversation/contracts.py`
- `TopicDetector` en `app/core/conversation/topic_detector.py`
- Detección de tema principal, temas secundarios, cambios de tema
- Administración de múltiples hilos por conversación
- Integración en pipeline entre Context Builder y State Manager (o como insumo del State Manager)

**Justificación:** El Topic Detector necesita contexto completo y estado para identificar a qué hilo pertenece un mensaje y si hubo cambio de tema.

---

### Incremento 4 — Response Composer

**Dependencias satisfechas:** State Manager (I1) + Context Builder completo (I2). No depende de Topic Detector (I3).

**Qué implementar:**
- `BusinessResponse` object en `app/domain/conversation/contracts.py` (o en `app/domain/business/contracts.py` — ver riesgo R3)
- `ResponseComposer` en `app/core/conversation/response_composer.py`
- Transformación: `BusinessDecision` + `ConversationContext` + `ConversationState` → `BusinessResponse`
- Gestión de tono, personalidad, idioma, identidad empresarial
- Eliminar el mapeo directo `ConversationMapper.to_channel_response(BusinessDecision)` → reemplazar con `ResponseComposer.compose()`

**Justificación:** Actualmente el `ConversationMapper` salta la composición de respuesta. El Response Composer debe existir antes que el Channel Adapter formal.

---

### Incremento 5 — Channel Adapter (formalizar)

**Dependencias satisfechas:** Response Composer (I4).

**Qué implementar:**
- `ChannelAdapter` abstract class en `app/core/conversation/channel_adapter.py`
- Método: `adapt(response: BusinessResponse, channel_config: dict) → ChannelResponse`
- Refactor: `ConversationMapper` pasa a ser un ChannelAdapter HTTP
- Los adapters específicos (`WhatsAppAdapter` de envío) implementan la interfaz
- Registro de adapters por canal

**Justificación:** El blueprint requiere que todo envío pase por un Channel Adapter. Actualmente el `ConversationMapper` mezcla responsabilidades de adapter con lógica de conversación.

---

### Resumen de Incrementos

```
I1: State Manager ────────────────── sin dependencias previas
I2: Context Builder (completo) ───── depende de I1
I3: Topic Detector ───────────────── depende de I1, I2
I4: Response Composer ────────────── depende de I1, I2 (paralelo a I3)
I5: Channel Adapter (formal) ─────── depende de I4
```

**Ejecutable como:**
- I1 → I2 → (I3 ∥ I4) → I5

Donde (I3 ∥ I4) indica que Topic Detector y Response Composer pueden implementarse en paralelo.

---

## 5. Riesgos

### R1 — Desviación: Message Receiver sin componente unificado

| Fuente | Detalle |
|---|---|
| **Blueprint** | "Todo mensaje ingresa por el Message Receiver" |
| **Código** | Cada canal implementa su propia recepción: `routes.py` para HTTP directo, `webhook.py` + `WhatsAppAdapter` para WhatsApp. No hay un componente `MessageReceiver` con interfaz explícita. |
| **Impacto** | Nuevos canales requerirían duplicar lógica de validación y normalización. El principio "Independiente del canal" se debilita. |
| **Nota** | No constituye bloqueo — la recepción funciona. Es una desviación del principio arquitectónico. |

### R2 — Desviación: Context Builder sin historial ni perfil

| Fuente | Detalle |
|---|---|
| **Blueprint** | Entradas del Context Builder: "Conversation Message, Historial, Estado conversacional, Perfil del cliente, Metadata del canal" |
| **Código** | `ConversationContext.from_message(message)` solo recibe el mensaje. No hay historial, estado, perfil ni metadata. |
| **Impacto** | El Business Brain recibe un contexto pobre. No puede distinguir un saludo inicial de un mensaje en medio de una conversación. No conoce al cliente. |

### R3 — Conflicto: Propiedad del objeto `Business Response`

| Fuente | Detalle |
|---|---|
| **Blueprint D-009-08** | "Response Composer" produce `Business Response` → "Channel Adapter" recibe `Business Response` |
| **Blueprint D-009-00** | `Business Response` listado como "Objeto Conversacional" |
| **ADR-005** | "Cada Engine es propietario exclusivo de sus objetos de dominio" — los objetos conversacionales pertenecen al ENG-002 |
| **Código** | No existe `BusinessResponse`. El `ChannelResponse` se construye directamente desde `BusinessDecision`. |
| **Conflicto** | ¿`Business Response` pertenece al Conversation Engine (ENG-002) o al Business Brain (ENG-001)? El blueprint D-009 lo lista como objeto conversacional, pero su nombre "Business Response" sugiere que describe una decisión del negocio. Esto debe resolverse antes de implementar el Response Composer. |

### R4 — Desviación: Pipeline lineal vs. implementación actual

| Fuente | Detalle |
|---|---|
| **Blueprint** | Pipeline: Message Receiver → Context Builder → Topic Detector → State Manager → Business Brain → Response Composer → Channel Adapter |
| **Código** | Pipeline actual: Message Receiver → Context Builder (mínimo) → Business Brain → Mapper (fusión Response Composer + Channel Adapter) |
| **Diferencia** | Faltan 3 etapas completas (Topic Detector, State Manager, Response Composer). El orden difiere: el State Manager está ANTES del Business Brain en el blueprint, pero no existe en código. La fusión Response Composer + Channel Adapter en `ConversationMapper` es incorrecta. |

### R5 — Desviación: Channel Adapter sin interfaz y con responsabilidad mezclada

| Fuente | Detalle |
|---|---|
| **Blueprint** | "Channel Adapter" transforma `Business Response` → `Channel Response`. Todo envío debe realizarse mediante un Channel Adapter. |
| **Código** | `ConversationMapper.to_channel_response()` toma `BusinessDecision` directamente, saltándose el `BusinessResponse`. No existe interfaz `ChannelAdapter`. El adapter de WhatsApp (`to_whatsapp_text_payload`) es una función suelta, no implementa un contrato. |
| **Impacto** | No hay polimorfismo de canales. Agregar Telegram o Email requeriría cambiar `ConversationService` directamente. |

### R6 — Riesgo: Estado actual hardcodeado en persistencia

| Fuente | Detalle |
|---|---|
| **Blueprint** | Conversation State Manager con máquina de estados: Nueva, En Progreso, Esperando Información, Esperando Business Brain, Esperando Respuesta Cliente, Finalizada, Cancelada, Escalada |
| **Código** | `service.py:58`: `status="active"` — valor fijo, sin gestión de estados, sin transiciones. |
| **Impacto** | No hay conversaciones pausadas, no hay escalamiento a humano, no hay espera por información. Toda conversación es "activa" permanente. |

### R7 — Riesgo: Dependencia del Business Brain para detección de intención conversacional

| Fuente | Detalle |
|---|---|
| **Blueprint** | "El Conversation Engine comunica. El Business Brain decide." (D-009-00). El Topic Detector (ENG-002) administra temas. El Intent Classifier (ENG-001) administra intenciones de negocio. |
| **Código** | `router.py:10-17` — `MessageRouter.route()` envía directamente al Business Brain, que ejecuta `IntentClassifier.classify()`. No hay etapa de Topic Detector antes del Business Brain. |
| **Conflicto** | El `intent` que retorna el `IntentClassifier` mezcla temas conversacionales (greeting, farewell) con intenciones de negocio (price_inquiry). Según el blueprint, el Topic Detector debería identificar temas conversacionales antes de que el Business Brain evalúe intenciones de negocio. |

### R8 — Brecha: No existe objeto `Conversation Thread`

| Fuente | Detalle |
|---|---|
| **Blueprint** | El Topic Detector administra `Conversation Threads`. El diagrama D-009-MMD-05 muestra múltiples threads por conversación (Citas, Precios, Facturación). |
| **Código** | No existe representación de threads. Todos los mensajes pertenecen a una sola conversación sin subdivisión temática. |
| **Impacto** | Un cliente que pregunta sobre precios y luego sobre facturación en la misma conversación no tendrá separación de contextos. |

---

## 6. Conclusión

El Conversation Engine implementado cubre **2 de 7 componentes** del blueprint (Message Receiver, Business Brain contract) con **2 componentes parciales** (Context Builder, Channel Adapter) y **3 componentes ausentes** (Topic Detector, State Manager, Response Composer).

El orden de implementación correcto, gobernado por dependencias arquitectónicas y no por preferencia, es:

1. **State Manager** — fundamento de toda continuidad conversacional
2. **Context Builder (completo)** — necesita estado para enriquecer contexto
3. **Topic Detector ∥ Response Composer** — paralelizable; ambos dependen de I1+I2
4. **Channel Adapter formal** — necesita Response Composer

La desviación más crítica no es la cantidad de componentes faltantes, sino que el `ConversationMapper` actual fusiona incorrectamente las responsabilidades de **Response Composer** y **Channel Adapter**, saltándose la etapa de composición de respuesta. Esto debe corregirse en el Incremento 4 antes de formalizar el Channel Adapter en el Incremento 5.
