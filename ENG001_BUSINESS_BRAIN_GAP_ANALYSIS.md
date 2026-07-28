# ENG-001 — Business Brain Gap Analysis

**Documento:** ENG001_BUSINESS_BRAIN_GAP_ANALYSIS.md  
**Blueprint:** D-008 — Business Brain Engine (v1.0, Aprobado)  
**Código base:** I5 completado (Conversation Engine cerrado)  
**Fecha:** 2026-07-22  

---

## 1. Blueprint Breakdown

### 1.1 Decision Pipeline (D-008-03)

El Blueprint D-008 define el siguiente pipeline secuencial:

```
Evento (inbound)
    ↓
Context Interpreter
    ↓
Intent Analyzer
    ↓
Rule Evaluator
    ↓
Decision Maker
    ↓
Confidence Evaluator
    ↓
Action Planner
    ↓
Event Publisher
    ↓
Business Event (outbound)
```

**Regla:** Todas las decisiones deben recorrer el Decision Pipeline.

### 1.2 Descomposición por Componente

#### Componente 1: Context Interpreter

| Atributo | Valor |
|---|---|
| **Nro. blueprint** | D-008-04 |
| **Responsabilidad** | Transformar el evento/request entrante en un Business Context normalizado |
| **Entradas** | Evento entrante (Business Request) |
| **Salidas** | `Business Context` |
| **Principios** | Normaliza, enriquece, no decide |
| **Regla** | — (documento D-008-04 no existe en el blueprint) |
| **Nota** | El blueprint no tiene un documento D-008-04. El pipeline (D-008-03) menciona "Context Interpreter" como primera etapa, pero no hay especificación publicada. |

#### Componente 2: Intent Analyzer

| Atributo | Valor |
|---|---|
| **Blueprint** | D-008-05 |
| **Responsabilidad** | Responder: ¿Qué quiere lograr realmente el cliente? |
| **Entradas** | `Business Context` |
| **Salidas** | `Business Intent` |
| **Principios** | No interpreta lenguaje directamente. No aplica reglas. No toma decisiones. Puede apoyarse en IA para resolver ambigüedades. |
| **Regla** | Solo el Intent Analyzer puede generar un Business Intent. |

#### Componente 3: Rule Evaluator

| Atributo | Valor |
|---|---|
| **Blueprint** | D-008-06 |
| **Responsabilidad** | Responder: ¿Qué está permitido hacer? |
| **Entradas** | `Business Context`, `Business Intent`, Reglas del Dominio (BR-XXX), Configuración de la empresa |
| **Salidas** | `Business Constraints` |
| **Principios** | Determinístico, auditable, independiente de IA, independiente del canal |
| **Regla** | Todas las reglas del negocio deben evaluarse exclusivamente dentro del Rule Evaluator. |

#### Componente 4: Decision Maker

| Atributo | Valor |
|---|---|
| **Blueprint** | D-008-07 |
| **Responsabilidad** | Seleccionar la mejor decisión posible usando Contexto, Intención y Restricciones |
| **Entradas** | `Business Context`, `Business Intent`, `Business Constraints` |
| **Paso intermedio** | Construye `Business Options` (alternativas válidas) antes de decidir |
| **Criterios** | Cumplimiento de reglas, Satisfacción de intención, Optimización de recursos, Reducción de riesgos, Generación de valor |
| **Salida** | `Business Decision` |
| **Regla** | Solo el Decision Maker puede generar un Business Decision. |

#### Componente 5: Confidence Evaluator

| Atributo | Valor |
|---|---|
| **Blueprint** | D-008-07 (comparte documento con Decision Maker) |
| **Responsabilidad** | Evaluar nivel de confianza de la decisión |
| **Salida** | Nivel: Alta → Continuar. Media → Solicitar más información. Baja → Escalar a humano. |
| **Principios** | Consistente, explicable, auditable, configurable, independiente de IA |

#### Componente 6: Action Planner

| Atributo | Valor |
|---|---|
| **Blueprint** | D-008-08 |
| **Responsabilidad** | Responder: ¿Cómo debe ejecutarse esta decisión? |
| **Entradas** | `Business Decision`, `Business Context`, `Business Constraints` |
| **Salida** | `Business Action Plan` |
| **Principios** | No ejecuta acciones. Organiza tareas. Asigna responsables. Independencia tecnológica. |
| **Regla** | Solo el Action Planner puede generar un Business Action Plan. |

#### Componente 7: Event Publisher

| Atributo | Valor |
|---|---|
| **Blueprint** | D-008-09 |
| **Responsabilidad** | Responder: ¿Qué necesita saber el resto del sistema? |
| **Entradas** | `Business Decision`, `Business Action Plan`, `Business Context` |
| **Salida** | `Business Event` |
| **Principios** | Inmutable, auditable, trazable, independiente de infraestructura |
| **Regla** | Todo Decision Pipeline finaliza publicando uno o más Business Events. |

### 1.3 Modelo Cognitivo (D-008-10)

```
Business Context → Business Intent → Business Constraints
→ Business Options → Business Decision → Business Action Plan → Business Event
```

### 1.4 Objetos del Blueprint

| Objeto | Blueprint | ¿Existe en código? |
|---|---|---|
| `Business Context` | D-008-05 | Sí — `app/domain/business/contracts.py:BusinessContext` |
| `Business Intent` | D-008-05 | No — no existe contrato explícito. El intent es un `str` dentro de `BusinessContext`. |
| `Business Constraints` | D-008-06 | No |
| `Business Options` | D-008-07 | No |
| `Business Decision` | D-008-07 | Sí — `app/domain/business/contracts.py:BusinessDecision` |
| `Business Action Plan` | D-008-08 | No |
| `Business Event` | D-008-09 | No — existe `BusinessEventModel` ORM pero no contrato de dominio `BusinessEvent` |

---

## 2. Estado actual del código

### 2.1 Mapa de componentes

| Componente Blueprint | Responsabilidad | Estado | Código |
|---|---|---|---|
| Context Interpreter | Normalizar request → Business Context | **No implementado** | — |
| Intent Analyzer | Clasificar intención de negocio | **Parcial / Desviado** | `app/core/business/intent_classifier.py` |
| Rule Evaluator | Aplicar reglas → Business Constraints | **No implementado** | — |
| Decision Maker | Seleccionar mejor decisión → Business Decision | **Parcial / Fusionado** | `app/core/business/decision_engine.py` |
| Confidence Evaluator | Evaluar confianza de la decisión | **Parcial / Fusionado** | (dentro de `decision_engine.py` + `policy.py`) |
| Action Planner | Planificar ejecución → Business Action Plan | **No implementado** | — |
| Event Publisher | Publicar eventos de negocio | **Parcial** | `app/core/business/event_publisher.py` |

### 2.2 Componente por componente

#### Context Interpreter — No implementado

| Aspecto | Detalle |
|---|---|
| **Código** | No existe clase, módulo ni función dedicada. |
| **Brecha** | El `BusinessBrainService.process()` recibe `BusinessRequest` y construye `BusinessContext(request=request, intent=intent)` directamente en la línea 28. No hay etapa de interpretación o enriquecimiento. |
| **Impacto** | El `BusinessContext` solo tiene `request` + `intent`. No hay perfil de cliente, historial, estado conversacional ni metadata de canal. El Intent Analyzer recibe un contexto pobre. |

#### Intent Analyzer — Parcial / Desviado

| Aspecto | Detalle |
|---|---|
| **Código** | `app/core/business/intent_classifier.py` — `IntentClassifier.classify(content: str) → str` |
| **Implementado** | Clasifica 6 intents: greeting, farewell, price_inquiry, thanks, support, question + unknown |
| **Brecha 1 — Entrada incorrecta** | El blueprint especifica que recibe `Business Context`. El código recibe un `str` (texto crudo). **Violación del principio "No interpreta lenguaje directamente".** |
| **Brecha 2 — Salida incorrecta** | El blueprint especifica que produce `Business Intent` como objeto de dominio. El código retorna un `str`. No existe contrato `BusinessIntent`. |
| **Brecha 3 — Contaminación de topics** | Clasifica `greeting` y `farewell` como intents. **AR-002 resuelve que son topics del CE, no intents del BB.** El `TopicDetector` (I3) ya los detecta, pero el `IntentClassifier` sigue clasificándolos. |
| **Brecha 4 — Keyword matching directo** | El algoritmo usa `if kw in text` directamente sobre el texto crudo. El blueprint dice "No interpreta lenguaje directamente" — la interpretación debería hacerse sobre Business Context enriquecido. |

#### Rule Evaluator — No implementado

| Aspecto | Detalle |
|---|---|
| **Código** | No existe. El `BusinessPolicy` es una simplificación extrema. |
| **Brecha** | El blueprint especifica un componente que recibe `Business Context + Business Intent + Reglas de Dominio` y produce `Business Constraints`. El código actual tiene `BusinessPolicy.get_response(intent)` que retorna `{status, confidence, needs_knowledge}`. No hay `BusinessConstraints`, no hay reglas de dominio (BR-XXX), no hay configuración de empresa. |
| **Impacto** | La lógica de políticas está fusionada con el Decision Maker. No hay separación entre "qué está permitido" y "qué se decide". |

#### Decision Maker — Parcial / Fusionado

| Aspecto | Detalle |
|---|---|
| **Código** | `app/core/business/decision_engine.py` — `DecisionEngine.evaluate(context) → BusinessDecision` |
| **Implementado** | Construye `BusinessDecision` con status, intent, confidence, needs_knowledge |
| **Brecha 1 — Sin Business Options** | El blueprint dice que el Decision Maker construye `Business Options` (alternativas) antes de decidir. No existe. |
| **Brecha 2 — Sin Business Constraints** | El Decision Maker debería recibir `Business Constraints` del Rule Evaluator. No existen. |
| **Brecha 3 — Fusionado con Rule Evaluator** | `DecisionEngine` llama a `BusinessPolicy` directamente. La evaluación de reglas no está separada. |
| **Brecha 4 — Fusionado con Confidence Evaluator** | La confianza viene del policy como atributo fijo, no de una evaluación separada. |

#### Confidence Evaluator — Parcial / Fusionado

| Aspecto | Detalle |
|---|---|
| **Código** | No existe clase separada. La confianza es un valor fijo en `BusinessPolicy`. |
| **Brecha** | El blueprint especifica: Alta → continuar, Media → solicitar más información, Baja → escalar. El código asigna confianza por intent sin lógica de continuación. No hay acciones asociadas al nivel de confianza. |
| **Impacto** | No hay diferenciación de comportamiento según el nivel de confianza. Toda decisión con status "accepted" se trata igual. |

#### Action Planner — No implementado

| Aspecto | Detalle |
|---|---|
| **Código** | No existe. |
| **Brecha** | El blueprint especifica que transforma `Business Decision + Business Context + Business Constraints` en `Business Action Plan`. El código retorna `BusinessDecision` directamente desde `BusinessBrainService.process()`. El CE no recibe un plan de acción. |
| **Impacto** | El contrato CE↔BB está incompleto. El CE debería recibir un `Business Action Plan` que describa qué acciones ejecutar (responder, consultar API, esperar, escalar). Actualmente el CE solo recibe una decisión plana. |

#### Event Publisher — Parcial

| Aspecto | Detalle |
|---|---|
| **Código** | `app/core/business/event_publisher.py` — `BusinessEventPublisher.publish(event_type, **kwargs)` |
| **Implementado** | Publica eventos durante el pipeline: `objetivo_identificado`, `consulta_conocimiento`, `conocimiento_encontrado`, `conocimiento_no_encontrado`, `respuesta_generada`. Persiste en DB si hay repositorio. |
| **Brecha 1 — Pipeline no termina con evento** | El blueprint dice "Todo Decision Pipeline finaliza publicando uno o más Business Events". El código actual retorna `BusinessDecision` — el evento es un side-effect durante el pipeline, no el final. |
| **Brecha 2 — Sin Business Event de dominio** | No existe contrato `BusinessEvent`. Los eventos son strings con kwargs. No hay objeto de dominio que represente un evento de negocio. |
| **Brecha 3 — Action Plan ausente** | El Event Publisher debería recibir `Business Action Plan` como entrada. No existe. |

---

## 3. Contratos

### 3.1 Contratos existentes

```python
# app/domain/business/contracts.py

class BusinessRequest(BaseModel):        # ← Debería llamarse BusinessDecisionRequest (AR-003)
    content: str                         # solo texto, sin contexto enriquecido
    customer_id: str
    company_id: str
    conversation_id: UUID

class BusinessContext(BaseModel):
    request: BusinessRequest             # referencia al request original
    intent: str                          # ← string, no BusinessIntent

class BusinessDecision(BaseModel):
    status: str
    intent: str                          # ← string, no BusinessIntent
    confidence: str
    needs_knowledge: bool = False
    knowledge_content: str | None = None  # ← agregado en I4
```

### 3.2 Contratos faltantes (blueprint)

| Contrato | Blueprint | Estado |
|---|---|---|
| `Business Intent` | D-008-05 | **Faltante.** El intent es un `str`, no un objeto de dominio. |
| `Business Constraints` | D-008-06 | **Faltante.** No existe representación de restricciones. |
| `Business Options` | D-008-07 | **Faltante.** No existe representación de alternativas. |
| `Business Action Plan` | D-008-08 | **Faltante.** No existe plan de acción. |
| `Business Event` | D-008-09 | **Faltante.** Solo existe `BusinessEventModel` (ORM), no contrato de dominio. |

### 3.3 Contratos con desviaciones documentadas

| Contrato | Desviación | Referencia |
|---|---|---|
| `BusinessRequest` | Nombre incorrecto (debería ser `BusinessDecisionRequest`). Contenido pobre (sin contexto enriquecido). | AR-003 (C4) |
| `BusinessContext` | Solo tiene `request` + `intent`. Blueprint espera mucho más (perfil, historial, metadata). | AR-003 (C4) |
| `BusinessDecision` | Sin `Business Action Plan` asociado. Sin referencia a `BusinessConstraints` evaluadas. | D-008-08 |

---

## 4. Dependency Graph

### 4.1 Grafo Arquitectónico (Blueprint)

```
Business Request (inbound)
    ↓
Context Interpreter ─────────────────── sin dependencias previas (recibe request crudo)
    ↓
Intent Analyzer ─────────────────────── depende de Business Context
    ↓
Rule Evaluator ──────────────────────── depende de Business Context + Business Intent
    ↓
Decision Maker ──────────────────────── depende de Business Context + Intent + Constraints
    ↓  (construye Business Options internamente)
Confidence Evaluator ────────────────── depende de Business Decision
    ↓
Action Planner ──────────────────────── depende de Business Decision + Context + Constraints
    ↓
Event Publisher ─────────────────────── depende de Business Decision + Action Plan
    ↓
Business Event (outbound)
```

### 4.2 Grafo de Implementación Actual

```
BusinessBrainService.process(request)
    1. IntentClassifier.classify(content)          ← salta Context Interpreter
    2. BusinessContext(request=request, intent=str)
    3. DecisionEngine.evaluate(context)            ← fusiona Rule Evaluator + Decision Maker + Confidence
    4. (KnowledgeService opcional)                 ← salto lateral, fuera del pipeline formal
    5. Return BusinessDecision                     ← salta Action Planner
    6. EventPublisher.publish()                    ← side-effect, no es salida final
```

### 4.3 Diferencia Estructural

| Etapa pipeline | Blueprint | Código | Diferencia |
|---|---|---|---|
| 1 | Context Interpreter | No existe | **Ausente** |
| 2 | Intent Analyzer | IntentClassifier | **Desviado** (entrada incorrecta, salida incorrecta, contaminado con topics) |
| 3 | Rule Evaluator | No existe | **Ausente** (lógica fusionada en DecisionEngine + BusinessPolicy) |
| 4 | Decision Maker | DecisionEngine | **Parcial** (sin Business Options, sin Constraints) |
| 5 | Confidence Evaluator | (dentro de policy) | **Parcial** (confianza es un valor fijo, no una evaluación) |
| 6 | Action Planner | No existe | **Ausente** |
| 7 | Event Publisher | BusinessEventPublisher | **Parcial** (no es el final del pipeline, no hay BusinessEvent de dominio) |

### 4.4 Orden Correcto de Implementación

Basado en dependencias arquitectónicas ascendentes:

```
1. Domain Contracts         ──── sin dependencias (solo blueprint)
2. Context Interpreter      ──── depende de contracts
3. Intent Analyzer          ──── depende de Context Interpreter + contracts
4. Rule Evaluator           ──── depende de Intent Analyzer
5. Decision Maker           ──── depende de Rule Evaluator
6. Action Planner           ──── depende de Decision Maker
7. Event Publisher          ──── depende de Action Planner
```

---

## 5. Desviaciones Conocidas

### 5.1 C2 — IntentClassifier clasifica topics como intents (AR-002)

| Fuente | Detalle |
|---|---|
| **Blueprint** | Intent Analyzer clasifica Business Intents (price_inquiry, support, question). Topic Detector (CE) clasifica topics (greeting, farewell). |
| **Código** | `IntentClassifier` clasifica 7 intents incluyendo greeting y farewell. |
| **Impacto** | Duplicación con `TopicDetector` (I3). El BB recibe intents conversacionales que no debería procesar. |
| **Resolución futura** | Mover greeting/farewell del `IntentClassifier` al `TopicDetector`. El `IntentClassifier` solo clasifica business intents. |

### 5.2 C3 — BusinessDecision sin message (resuelto en I4)

| Fuente | Detalle |
|---|---|
| **Blueprint** | D-009-08 (Response Composer produce texto). D-008 (BB produce decisión estructurada). |
| **Código** | I4 eliminó `message` de `BusinessDecision` y agregó `knowledge_content`. |
| **Estado** | **Resuelto.** El texto se genera en el ResponseComposer del CE. |

### 5.3 C4 — BusinessRequest sin contexto enriquecido

| Fuente | Detalle |
|---|---|
| **Blueprint** | Context Interpreter debería enriquecer el contexto antes de pasarlo al Intent Analyzer. |
| **Código** | `BusinessRequest` tiene 4 campos. `BusinessContext` solo agrega `intent`. |
| **Impacto** | El BB toma decisiones sin conocer historial, estado conversacional, perfil del cliente ni metadata del canal. |
| **Nota** | El CE ya tiene esa información en `ConversationContext` (I2), pero no la pasa al BB. |

### 5.5 D-008-04 — Documento faltante del Context Interpreter

| Fuente | Detalle |
|---|---|
| **Blueprint** | D-008-03 menciona "Context Interpreter" como primera etapa del pipeline. |
| **Realidad** | No existe archivo D-008-04 en el blueprint. No hay especificación del componente. |
| **Impacto** | El Context Interpreter no tiene definición formal ni en el blueprint ni en el código. |

### 5.6 Action Planner ausente

| Fuente | Detalle |
|---|---|
| **Blueprint** | D-008-08 define Action Planner como etapa obligatoria. |
| **Código** | No existe. `BusinessBrainService.process()` retorna `BusinessDecision` directamente. |
| **Impacto** | El CE no recibe un plan de acción. No sabe si debe responder, esperar, consultar un API externo o escalar. |

### 5.7 Confidence sin acción asociada

| Fuente | Detalle |
|---|---|
| **Blueprint** | Alta → continuar. Media → solicitar más información. Baja → escalar. |
| **Código** | La confianza es un string que viaja en `BusinessDecision` pero nunca se evalúa para cambiar el flujo. |
| **Impacto** | Toda decisión con status "accepted" se ejecuta igual, independientemente de la confianza. |

### 5.8 Knowledge Engine integrado como salto lateral

| Fuente | Detalle |
|---|---|
| **Blueprint** | El Knowledge Engine es un Engine separado (ENG-003). Su integración formal con el BB no está especificada en D-008. |
| **Código** | `BusinessBrainService.process()` consulta `KnowledgeService` directamente si `needs_knowledge=True`, luego reconstruye `BusinessDecision`. |
| **Impacto** | La consulta al KE ocurre fuera del pipeline formal. No pasa por Action Planner, no genera Business Event. Si hay error de KE, toda la decisión se reconstruye. |

---

## 6. Propuesta de Incrementos

Ordenados por dependencias arquitectónicas ascendentes.

### Incremento B1 — Business Domain Contracts

**Dependencias satisfechas:** Ninguna (es el primer componente en el orden arquitectónico).

**Qué implementar:**
- `BusinessIntent` — objeto de dominio con `name: str`, `confidence: str`, `category: str`
- `BusinessConstraints` — objeto de dominio que representa restricciones evaluadas
- `BusinessOptions` — objeto de dominio que representa alternativas de decisión
- `BusinessActionPlan` — objeto de dominio con lista de acciones planificadas
- `BusinessEvent` — objeto de dominio para eventos del pipeline
- Renombrar `BusinessRequest` → `BusinessDecisionRequest` (AR-003)
- Agregar `action_plan: BusinessActionPlan | None` a `BusinessDecision`

**Justificación:** Todos los componentes del pipeline dependen de estos contratos. Sin objetos de dominio no hay pipeline.

---

### Incremento B2 — Context Interpreter

**Dependencias satisfechas:** B1 (Contracts).

**Qué implementar:**
- `ContextInterpreter` class en `app/core/business/context_interpreter.py`
- Transforma `BusinessDecisionRequest` → `BusinessContext` enriquecido
- El contexto debe incluir: request, perfil del cliente (desde repositorio), metadata del canal
- (El historial y estado conversacional pueden venir del CE en un paso posterior)

**Justificación:** Primera etapa del pipeline. Sin contexto enriquecido, el Intent Analyzer no puede operar correctamente.

---

### Incremento B3 — Intent Analyzer (Refactor)

**Dependencias satisfechas:** B1 (Contracts) + B2 (Context Interpreter).

**Qué implementar:**
- Refactor `IntentClassifier` para que reciba `BusinessContext` en lugar de `str`
- Clasificar solo business intents: `price_inquiry`, `support`, `question`
- Mover `greeting`/`farewell`/`thanks` al `TopicDetector` (CE) — completar AR-002
- Producir `BusinessIntent` como objeto de dominio en lugar de `str`
- Mantener compatibilidad: el `str` en `BusinessContext.intent` puede coexistir temporalmente

**Justificación:** El Intent Analyzer actual viola su propio blueprint. Recibe la entrada incorrecta, produce la salida incorrecta, y clasifica lo que no debe.

---

### Incremento B4 — Rule Evaluator

**Dependencias satisfechas:** B1 (Contracts) + B3 (Intent Analyzer).

**Qué implementar:**
- `RuleEvaluator` class en `app/core/business/rule_evaluator.py`
- Recibe `BusinessContext` + `BusinessIntent`
- Aplica reglas de dominio (actualmente en `BusinessPolicy`)
- Produce `BusinessConstraints`
- `BusinessPolicy` se refactoriza o se elimina (su lógica se distribuye entre RuleEvaluator y DecisionMaker)

**Justificación:** Las reglas de negocio deben evaluarse antes de decidir. Actualmente están fusionadas con la decisión.

---

### Incremento B5 — Decision Maker + Confidence Evaluator (Refactor)

**Dependencias satisfechas:** B1 (Contracts) + B3 (Intent Analyzer) + B4 (Rule Evaluator).

**Qué implementar:**
- Refactor `DecisionEngine` para recibir `BusinessContext` + `BusinessIntent` + `BusinessConstraints`
- Construir `BusinessOptions` (alternativas) antes de decidir
- Seleccionar la mejor opción y producir `BusinessDecision`
- `ConfidenceEvaluator` como paso posterior: evaluar confianza y asignar acción
- Mantener compatibilidad: `DecisionEngine.evaluate()` puede coexistir temporalmente

**Justificación:** El Decision Maker actual es una simplificación que salta la evaluación de alternativas y la evaluación de confianza.

---

### Incremento B6 — Action Planner

**Dependencias satisfechas:** B1 (Contracts) + B5 (Decision Maker + Confidence).

**Qué implementar:**
- `ActionPlanner` class en `app/core/business/action_planner.py`
- Recibe `BusinessDecision` + `BusinessContext` + `BusinessConstraints`
- Produce `BusinessActionPlan` con lista de acciones: [responder, escalar, esperar, consultar API]
- Modificar `BusinessBrainService.process()` para ejecutar Action Planner

**Justificación:** Sin Action Planner, el CE no recibe un plan de ejecución. Es un componente ausente crítico.

---

### Incremento B7 — Event Publisher (Formalizar)

**Dependencias satisfechas:** B1 (Contracts) + B6 (Action Planner).

**Qué implementar:**
- Formalizar `BusinessEvent` como objeto de dominio
- El pipeline termina publicando `BusinessEvent` (uno o más)
- Refactor `BusinessEventPublisher` para usar `BusinessEvent` de dominio
- Los eventos actuales (`objetivo_identificado`, etc.) se mantienen como eventos intermedios

**Justificación:** El blueprint dice "Todo Decision Pipeline finaliza publicando uno o más Business Events". Actualmente el pipeline retorna `BusinessDecision`.

---

### Resumen de Incrementos

```
B1: Domain Contracts ────────────────── sin dependencias previas
B2: Context Interpreter ─────────────── depende de B1
B3: Intent Analyzer (refactor) ──────── depende de B1, B2
B4: Rule Evaluator ──────────────────── depende de B1, B3
B5: Decision Maker + Confidence ─────── depende de B1, B3, B4
B6: Action Planner ──────────────────── depende de B1, B5
B7: Event Publisher (formalizar) ────── depende de B1, B6
```

**Ejecutable como:** B1 → B2 → B3 → B4 → B5 → B6 → B7

No hay paralelismo posible en los primeros 5 incrementos. B6 y B7 podrían implementarse juntos.

---

## 7. Resumen

### Componentes del Blueprint

| Componente | Estado | Prioridad |
|---|---|---|
| Context Interpreter | **No implementado** | Alta |
| Intent Analyzer | **Parcial / Desviado** | Alta (AR-002) |
| Rule Evaluator | **No implementado** | Alta |
| Decision Maker | **Parcial / Fusionado** | Media |
| Confidence Evaluator | **Parcial / Fusionado** | Media |
| Action Planner | **No implementado** | Alta |
| Event Publisher | **Parcial** | Baja |

### Contratos

| Contrato | Estado |
|---|---|
| `Business Decision Request` | Existe como `BusinessRequest` (nombre incorrecto, contenido pobre) |
| `Business Context` | Existe (mínimo: request + intent str) |
| `Business Intent` | **Faltante** (es un str) |
| `Business Constraints` | **Faltante** |
| `Business Options` | **Faltante** |
| `Business Decision` | Existe (sin Action Plan asociado) |
| `Business Action Plan` | **Faltante** |
| `Business Event` | **Faltante** (solo ORM) |

### Conclusión

El Business Brain tiene **3 componentes ausentes** (Context Interpreter, Rule Evaluator, Action Planner), **2 componentes parciales/fusionados** (Decision Maker + Confidence Evaluator), **1 componente desviado** (Intent Analyzer) y **1 componente parcial** (Event Publisher). De los 8 contratos de dominio del blueprint, **5 no existen en código** y los 3 existentes tienen desviaciones documentadas.

El estado actual es menos maduro que el que tenía el Conversation Engine antes de I1. La implementación actual funciona para el Vertical Slice (intentos simples → respuesta directa) pero no implementa el pipeline de decisión del blueprint.
