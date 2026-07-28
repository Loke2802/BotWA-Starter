# Architecture Resolution Report

**Solicitado por:** CTO  
**Base:** Hallazgos de CONVERSATION_ENGINE_GAP_ANALYSIS.md  
**Source of Truth:** D-008, D-009, ADR-005, ADR-006, código actual  
**Fecha:** 2026-07-18  

---

## AR-001 — BusinessResponse Ownership

### 1.1 Evidencia Documental

| Documento | Afirmación |
|---|---|
| **D-009-08** (Response Composer) | **Salida:** `Business Response`. Regla: "Solo el Response Composer puede transformar una Business Decision en una Business Response." |
| **D-009-09** (Channel Adapter) | **Entradas:** `Business Response`, Configuración del canal, Capacidades del canal. |
| **D-009-00** (Objetos Conversacionales) | `Business Response` listado explícitamente como objeto conversacional dentro de ENG-002. |
| **D-009-00** (Relación con BB) | `Business Decision → Business Response → Channel Response`. La secuencia completa está dentro del Communication Pipeline del CE. |
| **D-009-00** (Principios) | "Cada Engine es dueño de sus propios objetos." |
| **D-008-07** (Decision Maker) | **Salida:** `Business Decision`. No menciona `Business Response`. |
| **D-008-08** (Action Planner) | **Entrada:** `Business Decision`. **Salida:** `Business Action Plan`. No menciona `Business Response`. |
| **D-008-10** (Modelo Cognitivo) | `Business Context → Business Intent → Business Constraints → Business Options → Business Decision → Business Action Plan → Business Event`. No incluye `Business Response`. |
| **ADR-005** | "Cada Engine es propietario exclusivo de sus objetos de dominio." |
| **ADR-006** | "Los Engines colaboran únicamente mediante contratos explícitos." Lista `Business Response` como ejemplo de contrato. |

### 1.2 Análisis

`Business Response` aparece en **dos contextos documentales distintos**:

**A. D-009 (Blueprint del Conversation Engine):**
El Response Composer (ENG-002, etapa 6 del pipeline) transforma `Business Decision` en `Business Response`. Este objeto viaja dentro del CE hacia el Channel Adapter (etapa 7). D-009-00 lo clasifica como "Objeto Conversacional". El CTO Review de D-009-08 dice: "Separa completamente la lógica del negocio de la experiencia conversacional" — es decir, la frontera entre BB y CE es `Business Decision`, no `Business Response`.

**B. ADR-006 (Engine Contracts):**
Lista `Business Response` junto con `Business Decision Request`, `Business Decision`, y `Knowledge Response` como ejemplos de contratos entre Engines.

### 1.3 Tensión Identificada

ADR-006 incluye `Business Response` como "contrato entre Engines", pero:
- Según D-009, `Business Response` nunca cruza la frontera del Conversation Engine. Sale del Response Composer y entra al Channel Adapter — ambas etapas dentro de ENG-002.
- D-008 (Business Brain) no define ni produce `Business Response`. El último objeto que produce el BB es `Business Decision` (D-008-07), que luego opcionalmente pasa al Action Planner para producir `Business Action Plan` (D-008-08).
- ADR-005 establece ownership exclusivo por Engine. Los objetos conversacionales pertenecen al CE.

### 1.4 Resolución

**Engine propietario:** Conversation Engine (ENG-002).

**Justificación documental:**

1. **D-009-08** (fuente primaria) define `Business Response` como salida del Response Composer, componente de ENG-002.
2. **D-008** (fuente primaria del BB) no lo menciona en ninguna etapa de su pipeline.
3. **ADR-005** asigna objetos conversacionales al CE.
4. **D-009-00** lo lista explícitamente como objeto conversacional.

**Sobre ADR-006:** Es una **imprecisión de nomenclatura**, no un conflicto real. ADR-006 pretendía ejemplificar contratos explícitos, pero `Business Response` es un **objeto intra-engine**, no un contrato inter-engine. Los contratos inter-engine reales entre CE y BB son:
- `Business Decision Request` (CE → BB)
- `Business Decision` (BB → CE)

**No requiere modificación de documentos.** Basta con interpretar ADR-006 restrictivamente: sus ejemplos incluyen objetos que no cruzan fronteras de Engine (Business Response permanece en CE; Knowledge Response puede ser intra-engine KE o inter-engine KE→BB). El ADR no define ownership — solo establece el principio de contratos explícitos.

---

## AR-002 — Topic vs Intent

### 2.1 Evidencia Documental

| Documento | Afirmación |
|---|---|
| **D-009-06** (Topic Detector) | Responsabilidad: "¿De qué está hablando realmente el cliente?" Salidas: `Conversation Topics`, `Conversation Threads`. Capacidades: tema principal, secundario, cambios de tema, reanudar, múltiples hilos. |
| **D-008-05** (Intent Analyzer) | Responsabilidad: "¿Qué quiere lograr realmente el cliente?" Salida: `Business Intent`. Definición: "Representa el objetivo de negocio identificado (reservar, reprogramar, cancelar, comprar, reclamar, etc.)." |
| **D-009-00** (Principios) | "El Conversation Engine comunica. El Business Brain decide." |
| **D-009-01** (Límites del CE) | "No toma decisiones de negocio, no aplica reglas, no ejecuta automatizaciones ni consulta sistemas externos." |
| **D-009-02** (Filosofía) | "Separación entre comunicación y decisiones." |

### 2.2 Análisis de cada caso

#### greeting ("hola", "buenos días")

| Atributo | ¿Topic? | ¿Intent? |
|---|---|---|
| Pregunta del dominio | ¿De qué habla? → Inicio de conversación | ¿Qué quiere lograr? → No hay objetivo de negocio |
| Naturaleza | Marcador conversacional de apertura | Sin intención de negocio |
| Según blueprint | Topic Detector identifica "inicio de conversación" | Intent Analyzer no tendría entrada — no hay Business Intent |
| **Resolución** | **TOPIC** (pertenece a ENG-002) |

#### farewell ("adiós", "hasta luego")

| Atributo | ¿Topic? | ¿Intent? |
|---|---|---|
| Pregunta del dominio | ¿De qué habla? → Cierre de conversación | ¿Qué quiere lograr? → Finalizar interacción |
| Naturaleza | Marcador conversacional de cierre | No es un objetivo de negocio (reservar, comprar, etc.) |
| Según blueprint | Topic Detector identifica "cierre de conversación" | No es un Business Intent según ejemplos de D-008-05 |
| **Resolución** | **TOPIC** (pertenece a ENG-002) |

#### price_inquiry ("cuánto cuesta")

| Atributo | ¿Topic? | ¿Intent? |
|---|---|---|
| Pregunta del dominio | ¿De qué habla? → Productos/precios | ¿Qué quiere lograr? → Conocer precio para decidir compra |
| Naturaleza | Tema: información de producto | Intención de negocio: consulta de precio como paso pre-compra |
| Según blueprint | Topic Detector identifica "producto" como tema | Intent Analyzer identifica "consultar precio" como Business Intent |
| **Resolución** | **AMBOS.** Topic (ENG-002): "producto/consulta". Intent (ENG-001): "price_inquiry" |

#### support ("ayuda", "no funciona")

| Atributo | ¿Topic? | ¿Intent? |
|---|---|---|
| Pregunta del dominio | ¿De qué habla? → Problema técnico | ¿Qué quiere lograr? → Resolver incidencia |
| Naturaleza | Tema: soporte técnico | Intención de negocio: solicitar asistencia |
| Según blueprint | Topic Detector identifica "soporte" | Intent Analyzer identifica "support_request" como Business Intent |
| **Resolución** | **AMBOS.** Topic (ENG-002): "soporte". Intent (ENG-001): "support" |

#### question ("¿cuándo abren?")

| Atributo | ¿Topic? | ¿Intent? |
|---|---|---|
| Pregunta del dominio | ¿De qué habla? → Información general | ¿Qué quiere lograr? → Obtener datos específicos |
| Naturaleza | Tema: consulta genérica | Intención de negocio: solicitar información |
| Según blueprint | Topic Detector identifica "información general" | Intent Analyzer identifica "information_request" |
| **Resolución** | **AMBOS.** Topic (ENG-002): "información general". Intent (ENG-001): "question" (o "information_request") |

### 2.3 Frontera Exacta

```
Topic (ENG-002 — Conversation Engine)
    Pregunta: "¿De qué está hablando realmente el cliente?"
    Responde: greeting, farewell, producto, soporte, información general
    Output: Conversation Topics, Conversation Threads
    Regla: No evalúa objetivo de negocio. No decide.
    
Intent (ENG-001 — Business Brain)
    Pregunta: "¿Qué quiere lograr realmente el cliente?"
    Responde: price_inquiry, support, question, purchase, cancel, etc.
    Output: Business Intent
    Regla: No interpreta lenguaje directamente. No aplica reglas. No decide.
```

**La frontera es: Topic describe el dominio conversacional; Intent describe el objetivo de negocio.**

Un mensaje tiene exactamente **un topic** (o un thread en conversaciones multi-tema) y **un intent**.

### 2.4 Desviación del Código

El `IntentClassifier` en `app/core/business/intent_classifier.py` clasifica **los 5 casos** (greeting, farewell, price_inquiry, thanks, support, question) como si fueran todos Business Intents. Adicionalmente, la clasificación se hace por **keywords en el texto plano**, sin pasar por un Business Context enriquecido (D-008-05 dice: "No interpreta lenguaje directamente").

Esto constituye una **mezcla confirmada de responsabilidades**:

| Código actual | Blueprint |
|---|---|
| `IntentClassifier` clasifica `greeting` como intent | `Topic Detector` debería detectar greeting como topic conversacional |
| `IntentClassifier` clasifica `farewell` como intent | `Topic Detector` debería detectar farewell como topic de cierre |
| `IntentClassifier` clasifica `price_inquiry` como intent **(correcto)** | `Intent Analyzer` identifica price_inquiry como Business Intent |
| `IntentClassifier` clasifica `support` como intent **(correcto)** | `Intent Analyzer` identifica support como Business Intent |
| `IntentClassifier` clasifica `question` como intent | Topic: información general. Intent: information_request |
| `IntentClassifier` usa keywords directamente en texto | Intent Analyzer recibe `Business Context`, no texto crudo |

### 2.5 Conclusión

**Existe contradicción entre el blueprint y el código.** El código implementa un clasificador plano en ENG-001 que mezcla topics conversacionales (greeting, farewell) con intents de negocio (price_inquiry, support). El blueprint exige dos etapas separadas: Topic Detector (ENG-002) antes de enviar al Business Brain, e Intent Analyzer (ENG-001) como primera etapa del Decision Pipeline.

No hay contradicción entre blueprints — D-008 y D-009 son consistentes. La contradicción es entre el blueprint (ambos) y la implementación actual.

---

## AR-003 — CE ↔ BB Contract

### 3.1 Evidencia Documental

| Documento | Contrato CE → BB | Contrato BB → CE |
|---|---|---|
| **D-009-00** (Relación con BB) | `Business Decision Request` | `Business Decision` |
| **D-008-03** (Decision Pipeline) | — | `Business Decision` (salida del Decision Maker) |
| **ADR-006** | `Business Decision Request` | `Business Decision` |
| **Código** (`router.py`, `business/contracts.py`, `business/service.py`) | `BusinessRequest` (content, customer_id, company_id, conversation_id) | `BusinessDecision` (status, intent, message, confidence, needs_knowledge) |

### 3.2 Confirmación

El contrato oficial entre Conversation Engine y Business Brain es:

```
Business Decision Request  ──→ Business Brain ──→ Business Decision
```

### 3.3 Desviaciones del Código

#### Desviación 1 — Nombre del contrato de entrada

| Documento | Código |
|---|---|
| `Business Decision Request` | `BusinessRequest` |

**Severidad:** Baja. Es la misma estructura con distinto nombre. No afecta el comportamiento ni la integridad del contrato.

#### Desviación 2 — Contenido del Business Decision Request

| Documento | Código |
|---|---|
| Debe incluir: `Conversation Context` enriquecido con historial, estado conversacional, perfil del cliente, metadata del canal (D-009-05) | `BusinessRequest` solo incluye: `content`, `customer_id`, `company_id`, `conversation_id` |

**Severidad:** Estructural. El Business Brain recibe menos contexto del que el blueprint prescribe. Esto corresponde a la brecha del Conversation Context Builder (gap del Gap Analysis), no a una violación del contrato per se, sino a una entrada empobrecida.

#### Desviación 3 — `BusinessDecision.message` como texto de respuesta

| Documento | Código |
|---|---|
| El Business Brain produce `Business Decision` (decisión estructurada). Luego el Response Composer la transforma en `Business Response` (texto). D-009 dice que el BB "decide", no que "escribe respuestas". | `BusinessDecision.message` contiene el texto de respuesta listo para enviar al cliente. El `ConversationMapper` simplemente copia `decision.message` a `ChannelResponse.message`. |

**Severidad:** Alta. Esto constituye una **fusión de responsabilidades**: el Business Brain está escribiendo la respuesta conversacional en lugar de solo producir una decisión estructurada. La etapa de Response Composer (D-009-08) queda eliminada porque el texto ya viene desde el BB.

**Evidencia concreta:**
```python
# router.py — el CE envía al BB y recibe un decision con .message
# service.py — el CE mapea directamente BusinessDecision → ChannelResponse
response = self._mapper.to_channel_response(business_response)
# mapper.py:
return ChannelResponse(status=decision.status, message=decision.message)
# business/policy.py — las políticas devuelven mensajes de texto
# business/decision_engine.py — el Decision Engine produce .message
```

#### Desviación 4 — Ausencia de Business Action Plan

| Documento | Código |
|---|---|
| D-008-08: Action Planner transforma `Business Decision` en `Business Action Plan` antes de que el resultado salga del BB | El BB retorna directamente `BusinessDecision` sin pasar por Action Planner |

**Severidad:** Media. El Action Planner no existe en código. El CE recibe una decisión sin plan de ejecución. Esto no es una desviación del **contrato** CE↔BB (el Action Planner podría ser interno al BB), pero sí del modelo cognitivo de D-008-10.

### 3.4 Conclusión

El contrato `Business Decision Request → Business Decision` se respeta en su **forma** (entrada sale del CE, entra al BB; salida sale del BB, vuelve al CE), pero con dos desviaciones:

1. **Contracción del Request:** `BusinessRequest` omite contexto que el blueprint exige (historial, estado, perfil).
2. **Fuga de responsabilidad en la Response:** `BusinessDecision.message` precarga texto conversacional que según D-009-08 debería producir el Response Composer, no el BB.

---

## 4. Resumen de Conflictos Reales

| ID | Documentos | Naturaleza | ¿Requiere cambio? |
|---|---|---|---|
| C1 | ADR-006 enumera `BusinessResponse` como contrato inter-engine, pero D-009 lo define como objeto intra-engine del CE | Ambigüedad de nomenclatura. No es contradicción — ADR-006 establece el principio de contratos; el ejemplo es incorrecto pero no vinculante. | **No.** Basta con interpretación restrictiva. |
| C2 | Código: `IntentClassifier` en ENG-001 clasifica topics (greeting, farewell) como intents. Blueprints: D-009-06 (Topic Detector) y D-008-05 (Intent Analyzer) son etapas separadas en engines distintos. | Contradicción real entre implementación y arquitectura. | **Sí.** Requiere separar Topic Detector (ENG-002) de Intent Analyzer (ENG-001). |
| C3 | Código: `BusinessDecision.message` contiene texto de respuesta. Blueprint: D-009-08 asigna la producción de texto al Response Composer. | Fuga de responsabilidad del BB hacia el CE. El BB decide; el CE compone la respuesta. | **Sí.** Requiere que el BB produzca una decisión sin texto conversacional, y que el Response Composer genere el texto. |
| C4 | Código: `BusinessRequest` tiene 4 campos. Blueprint D-009-05 exige historial, estado, perfil, metadata. | Contrato empobrecido, no violado. El CE envía menos contexto del posible. | **No como cambio de contrato.** Se resuelve implementando el Context Builder completo del Gap Analysis. |
| C5 | ADR-005 vs D-009 sobre ownership de `BusinessResponse` | No hay conflicto. D-009 es específico del Engine; ADR-005 es genérico. Ambos convergen: CE es propietario. | **No.** |

## 5. Cambios Mínimos Estrictamente Necesarios

| Orden | Cambio | Engine | Documentos Afectados | Resuelve |
|---|---|---|---|---|
| 1 | Separar `IntentClassifier`: mover greeting/farewell a Topic Detector (ENG-002); dejar price_inquiry/support/question como Business Intent (ENG-001) | ENG-001 + ENG-002 | Código: `intent_classifier.py`. No requiere cambio de blueprint. | C2 |
| 2 | Eliminar `message` de `BusinessDecision`. El BB retorna solo status, intent, confidence, needs_knowledge, action_plan. El Response Composer genera el texto. | ENG-001 + ENG-002 | Código: `business/contracts.py`, `business/service.py`, `conversation/mapper.py`. Blueprint D-008 no requiere cambio (no define message); D-009 ya asigna texto al Response Composer. | C3 |

Estos dos cambios habilitan la implementación secuencial por incrementos definida en el Gap Analysis sin modificar la arquitectura ni los documentos aprobados.
