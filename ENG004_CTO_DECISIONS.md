# ENG-004 — CTO Decisions

**Proyecto:** BotWA Starter  
**Propósito:** Decisiones arquitectónicas abiertas para ENG-004 antes de iniciar el Master Implementation Plan  
**Fuente:** ENG004_DOMAIN_ANALYSIS.md  
**Documentos relacionados:** D-011 (completo), ADR-004, ADR-005, ADR-006, ADR-008, ADR-009

---

## D01 — Sincronía de ejecución

### Contexto

El Domain Analysis identifica que el pipeline del Business Brain (ENG-001) es actualmente síncrono. El Automation Engine debe ejecutar procesos que pueden implicar reintentos, scheduling, paralelismo y operaciones lentas (integración externa). Si el AE se ejecuta sincrónicamente dentro del pipeline del BB, el usuario espera la respuesta hasta que termine toda la automatización.

El Blueprint D-011 no especifica el modelo de ejecución (síncrono vs asíncrono). El ADR-008 dice "ejecutar procesos" pero no define el mecanismo.

### Alternativas

**A1 — Síncrono (dentro del pipeline del BB)**
El AE se ejecuta inmediatamente después de que el BB genera el `BusinessActionPlan`, dentro del mismo thread y antes de que el Conversation Engine entregue la respuesta al usuario.

**A2 — Asíncrono (cola/task queue)**
El AE recibe el `BusinessActionPlan` y lo encola. La ejecución ocurre en un proceso separado. El CE responde al usuario inmediatamente sin esperar a que termine la automatización.

**A3 — Híbrido (invocación asíncrona desde pipeline síncrono)**
El pipeline del BB sigue siendo síncrono pero, en lugar de ejecutar el AE, lanza un background task (vía `asyncio.create_task`, `threading`, o un task runner ligero) y retorna inmediatamente. La automatización corre en segundo plano.

### Impacto

| Área | A1 (Síncrono) | A2 (Asíncrono con cola) | A3 (Híbrido) |
|---|---|---|---|
| **AE** | Diseño simple, sin infraestructura adicional. | Requiere cola de mensajes o task queue (Redis, SQL, APScheduler). | Diseño simple, pero el background task comparte recursos del proceso principal. |
| **BB** | Sin cambios. El AE se invoca desde `BusinessBrainService.process()`. | Sin cambios. El AE se invoca pero retorna inmediatamente después de encolar. | Sin cambios. Igual que A2 pero sin cola externa. |
| **CE** | El tiempo de respuesta se degrada si la automatización es lenta. | El CE responde al usuario inmediatamente. | El CE responde inmediatamente. |
| **IE** | Solo aplica si la tarea es rápida. | La cola permite retry y scheduling natural. | Background task puede morir si el proceso se reinicia. |

### Riesgos

| Alternativa | Riesgos |
|---|---|
| **A1** | Degradación de UX en tareas lentas. Imposibilidad de ejecutar tareas programadas. Bloqueo del pipeline si una tarea falla con timeout largo. |
| **A2** | Complejidad operativa (cola, consumidor, monitoreo). Dependencia de infraestructura adicional. Mayor superficie de testing. |
| **A3** | Background tasks no sobreviven restart del proceso. Sin garantía de entrega. Dificultad para monitorear tareas en vuelo. |

### Recomendación

**A3 (Híbrido) para Fase 1**, evolucionando a **A2** cuando la carga lo justifique. Fase 1 no necesita cola externa: las automatizaciones previstas (respond, query_knowledge, escalate) son rápidas y pueden ejecutarse en background task. Esto mantiene el diseño simple, desacopla la respuesta al usuario de la ejecución, y pospone la inversión en infraestructura asíncrona hasta que haya casos de uso que la requieran.

---

## D02 — Punto de inyección en el pipeline

### Contexto

El AE debe recibir una `BusinessDecision` + `BusinessActionPlan` para comenzar. Actualmente, el pipeline de BotWA tiene dos puntos candidatos para invocar al AE:

1. Dentro de `BusinessBrainService.process()`, después de generar el plan (línea 134).
2. Dentro de `ConversationService.handle_message()`, después de recibir la `BusinessDecision` del BB y antes o después de componer la respuesta.

El Blueprint D-011-03 dice "Business Decision → Automation Request Builder", lo que sugiere que el punto de entrada es la `BusinessDecision`. Pero la decisión sola no contiene el plan de acción — el `BusinessActionPlan` también es necesario.

### Alternativas

**A1 — Inyección en BusinessBrainService**
El AE se invoca al final de `BusinessBrainService.process()`, después de generar el `BusinessActionPlan` y publicar eventos. El service crea un `AutomationRequest` y lo envía al AE.

**A2 — Inyección en ConversationService**
El `ConversationService` recibe la `BusinessDecision` del BB y decide si debe invocar al AE. El service del CE crea el `AutomationRequest`.

### Impacto

| Área | A1 (en BB) | A2 (en CE) |
|---|---|---|
| **BB** | El BB conoce la existencia del AE. Nueva dependencia en `BusinessBrainService`. | El BB no cambia. No sabe que existe el AE. |
| **CE** | El CE no cambia. Solo recibe `BusinessDecision`. | El CE debe conocer al AE y construir `AutomationRequest`. Mezcla responsabilidad conversacional con ejecución. |
| **AE** | Recibe `BusinessDecision` + `BusinessActionPlan` directamente del BB. | Recibe datos a través del CE, que no es dueño del `BusinessActionPlan`. |
| **Desacople** | El BB ya conoce al KE. Conocer al AE es consistente. | El CE no debería conocer detalles de ejecución (ADR-006, D-009). |

### Riesgos

| Alternativa | Riesgos |
|---|---|
| **A1** | El BB acumula dependencias de otros Engines (KE, AE). Mayor acoplamiento. |
| **A2** | El CE viola su responsabilidad (comunicar, no ejecutar). El `BusinessActionPlan` es propiedad del BB (ADR-005). |

### Recomendación

**A1 (inyección en BusinessBrainService).** El BB ya es el punto de coordinación de lógica de negocio. Conoce al KE y publica eventos. Conocer al AE es consistente con su rol. El CE debe mantenerse limpio de responsabilidades operativas.

---

## D03 — Dependencia del Integration Engine

### Contexto

El Blueprint D-011-01 dice: "El Automation Engine no accede directamente a sistemas externos sin pasar por el Integration Engine." El ADR-009 define al Integration Engine (ENG-005) como responsable de integraciones externas.

El Integration Engine está planificado para Fase 4 pero aún no existe. El AE necesitará ejecutar tareas que requieren integración externa (enviar email, actualizar CRM, notificar a Slack). Si el AE no puede ejecutarlas sin el IE, su utilidad inicial es muy limitada.

### Alternativas

**A1 — Esperar al Integration Engine**
El AE solo ejecuta tareas que no requieren integración externa hasta que ENG-005 exista. Tareas con `target` externo quedan como "no implementadas" o se marcan como error.

**A2 — Adaptador HTTP directo temporal**
El AE incluye un adaptador HTTP mínimo para integrarse con APIs externas mientras el IE no existe. El adaptador es interno al AE y se depreca cuando ENG-005 esté operativo.

**A3 — Stub/skip de tareas externas**
El AE detecta tareas externas y las salta (o las marca como "pendientes") registrando un evento. No las ejecuta.

### Impacto

| Área | A1 (Esperar IE) | A2 (HTTP directo) | A3 (Skip) |
|---|---|---|---|
| **AE** | Sin cambios futuros. Alcance limitado. | Código temporal que debe deprecarse. Riesgo de que se vuelva permanente. | Fácil de implementar. Baja utilidad. |
| **BB** | El `ActionPlanner` solo genera tareas internas. | Puede generar tareas externas desde Fase 1. | El `ActionPlanner` limitado a tareas internas. |
| **IE** | Sin deuda técnica. El IE se construye limpio. | El IE debe ser compatible con el adaptador temporal o reemplazarlo. | Sin impacto. |
| **Caso de uso** | No se pueden automatizar procesos reales (ej: notificar a un sistema externo tras una compra). | Se pueden construir casos de uso reales desde el inicio. | Frustrante para el negocio. El AE "no hace nada" con tareas externas. |

### Riesgos

| Alternativa | Riesgos |
|---|---|
| **A1** | El AE no puede demostrar valor real hasta que exista el IE. Los stakeholders pueden percibirlo como un Engine vacío. |
| **A2** | Deuda técnica. El adaptador temporal puede convertirse en permanente si no se gestiona su deprecación. Posible duplicación de lógica cuando llegue el IE. |
| **A3** | El AE ignora tareas. El usuario cree que la automatización falló silenciosamente. Pérdida de confianza en el sistema. |

### Recomendación

**A2 (adaptador HTTP directo temporal),** con las siguientes reglas:
- El adaptador es un componente interno del AE, no expuesto a otros Engines.
- Cada integración se implementa como un `TaskHandler` con interfaz estándar.
- Cuando exista el IE, los `TaskHandler` se migran al IE y el adaptador se elimina.
- Documentar explícitamente qué handlers son temporales.

---

## D04 — Definiciones de Workflow

### Contexto

El `WorkflowPlanner` debe transformar un `AutomationRequest` en un `ExecutionPlan`. El `BusinessActionPlan` actual del BB expresa solo `steps: list[ActionStep]` con orden lineal. No contiene:
- Políticas de reintento por paso.
- Timeouts por paso.
- Dependencias no lineales.
- Condiciones de ejecución ("si falla, entonces...").
- Metadatos de scheduling.

El AE necesita enriquecer estas definiciones para ejecutar procesos complejos.

### Alternativas

**A1 — Workflow Planner 100% programático**
El `WorkflowPlanner` contiene la lógica para generar `ExecutionPlan` en código. No hay configuración externa. Las reglas de planificación están hardcodeadas.

**A2 — Workflow definitions externas (YAML/JSON)**
El `WorkflowPlanner` consulta definiciones de workflow desde archivos de configuración o DB. Cada tipo de automatización tiene una definición que especifica tareas, dependencias, retry policy, timeout.

**A3 — Híbrido: lógica base en código + definiciones para casos complejos**
El `WorkflowPlanner` tiene reglas por defecto en código pero puede enriquecerse con definiciones externas cuando el caso lo requiere.

### Impacto

| Área | A1 (Programático) | A2 (Externo) | A3 (Híbrido) |
|---|---|---|---|
| **AE** | Simple. Sin parser de configuraciones. | Requiere schema, parser, validación de definiciones. Más complejo. | Flexible. Mayor carga cognitiva (dos fuentes de verdad). |
| **BB** | `BusinessActionPlan` puede mantenerse simple. | `BusinessActionPlan` debe incluir un `workflow_type` para lookup. | `BusinessActionPlan` puede mantenerse simple. |
| **Operaciones** | Cambiar comportamiento requiere deploy. | Cambiar workflow no requiere deploy (solo actualizar archivo). | Cambios simples sin deploy; cambios complejos requieren deploy. |
| **Testing** | Un solo camino de planificación. | Múltiples definiciones → múltiples casos de prueba. | Combinaciones de comportamientos. |

### Riesgos

| Alternativa | Riesgos |
|---|---|
| **A1** | Cada nuevo tipo de automatización requiere modificar código del AE. El Engine se vuelve rígido. |
| **A2** | Complejidad temprana innecesaria si los workflows iniciales son simples (respond, query_knowledge, escalate). Riesgo de over-engineering. |
| **A3** | Dos fuentes de verdad. Puede ser confuso determinar cuándo usar código vs definiciones. |

### Recomendación

**A1 para Fase 1** (Workflow Planner 100% programático). Los tipos de automatización que genera el `ActionPlanner` actual son solo 3 (respond, query_knowledge, escalate). No hay necesidad de definiciones externas. Si en fases futuras aparecen workflows complejos, se introduce A3 en ese momento.

---

## D05 — Alcance de Fase 1

### Contexto

El `ActionPlanner` actual del BB genera `ActionStep` con `action` en: `respond`, `query_knowledge`, `escalate`. Adicionalmente, existen acciones planificadas en el blueprint como: `schedule`, `notify`, `integrate`, `delay`, `retry`.

El AE no puede implementar todo desde el inicio. Se necesita definir qué acciones debe soportar la primera versión.

### Alternativas

**A1 — Solo las acciones del ActionPlanner actual**
Fase 1 soporta: `respond`, `query_knowledge`, `escalate`. El AE básicamente ejecuta los steps que el BB ya planifica.

**A2 — Acciones del ActionPlanner + scheduling simple**
Fase 1 soporta las acciones actuales más `delay` y `schedule` (ejecutar una acción en X segundos/minutos).

**A3 — Acciones del ActionPlanner + scheduling + notificaciones externas**
Fase 1 soporta todo lo anterior + `notify` (enviar notificación a sistema externo vía adaptador HTTP temporal).

### Impacto

| Área | A1 (Solo actual) | A2 (+ scheduling) | A3 (+ externas) |
|---|---|---|---|
| **AE** | Alcance mínimo. Bajo esfuerzo. | Requiere timer/scheduler interno. | Requiere adaptador HTTP + scheduler. |
| **BB** | `ActionPlanner` no necesita cambios. | `ActionPlanner` puede generar `delay` steps. | `ActionPlanner` puede generar `notify` steps. |
| **IE** | Sin impacto (no se usa). | Sin impacto. | El adaptador temporal debe deprecarse después. |
| **Valor de negocio** | Bajo. Solo orquesta acciones que el BB ya ejecuta conceptualmente. | Medio. Permite "responder ahora, ejecutar después". | Alto. Casos de uso reales (ej: notificar a CRM tras una compra). |

### Riesgos

| Alternativa | Riesgos |
|---|---|
| **A1** | El AE agrega poco valor sobre el BB. Puede percibirse como sobreingeniería. |
| **A2** | Introducir scheduling agrega complejidad de timing (¿qué pasa si el proceso se cae entre el schedule y la ejecución?). |
| **A3** | Dependencia del adaptador temporal (D03). Mayor alcance → mayor esfuerzo de implementación y testing. |

### Recomendación

**A2 (acciones actuales + scheduling simple).** El scheduling es una capacidad diferenciadora clave del AE respecto al BB. Incluso un schedule basado en tiempo simplificado (delay en segundos, sin persistencia) demuestra el valor del Engine. Las notificaciones externas (A3) se posponen hasta que el IE esté definido o hasta Fase 2 del AE.

---

## D06 — Persistencia de ejecuciones

### Contexto

El Execution Monitor debe registrar el ciclo de vida de cada automatización. El Blueprint D-011-07 dice: "Todo cambio de estado debe quedar registrado." No especifica si el registro es en DB, en log, o en eventos.

Actualmente BotWA usa PostgreSQL para datos persistentes (conversaciones, eventos de negocio, catálogo de conocimiento). Los eventos de negocio se persisten vía `BusinessEventModel`.

### Alternativas

**A1 — Persistencia completa en DB**
Cada ejecución (`ExecutionPlan`) y cada tarea (`Task`) se persisten en tablas dedicadas. El `ExecutionMonitor` escribe en DB en cada cambio de estado.

**A2 — Solo eventos (log-based)**
La ejecución solo se registra mediante `BusinessEvent` publications. No hay tablas de ejecución. La trazabilidad se reconstruye a partir de los eventos.

**A3 — Eventos + estado actual en DB**
Los eventos se publican (y persisten como `BusinessEvent`). Adicionalmente, el estado actual de la ejecución se mantiene en una tabla de `automation_execution` para consultas rápidas. El histórico detallado se reconstruye desde eventos.

### Impacto

| Área | A1 (DB completa) | A2 (Solo eventos) | A3 (Eventos + estado) |
|---|---|---|---|
| **AE** | Más tablas, más escrituras. Consultas eficientes. | Sin tablas nuevas. Trazabilidad vía eventos. | Balance entre consultas y escrituras. |
| **BB** | Sin impacto. | Sin impacto. | Sin impacto. |
| **Infraestructura** | Mayor volumen en DB. | Mayor volumen en event store/log. | Medio. |
| **Operaciones** | Fácil consultar "¿qué pasó con esta ejecución?" | Difícil reconstruir estado actual sin procesar todos los eventos. | Estado actual accesible; histórico vía eventos. |

### Riesgos

| Alternativa | Riesgos |
|---|---|
| **A1** | DB puede convertirse en cuello de botella si hay muchas ejecuciones. Cada paso de cada tarea es un write. |
| **A2** | Reconstruir el estado de una ejecución en curso requiere leer y procesar N eventos. Ineficiente para monitoreo en vivo. |
| **A3** | Dos fuentes de verdad (eventos + tabla de estado) deben mantenerse sincronizadas. Mayor complejidad de escritura. |

### Recomendación

**A3 (eventos + estado actual en DB).** Los eventos se publican para el resto de la plataforma (CE, futuros consumidores). La tabla de estado permite al Execution Monitor consultar rápidamente el progreso. El histórico detallado se reconstruye desde eventos si es necesario. Este patrón es el estándar en sistemas de orquestación (event sourcing + snapshot).

---

## D07 — Esquema de nombramiento de eventos

### Contexto

El `BusinessBrainService` ya publica eventos de negocio vía `BusinessEventPublisher` con nombres como `objetivo_identificado`, `reglas_evaluadas`, `plan_generado`, `respuesta_generada`. El AE publicará sus propios eventos de ejecución (`automation.started`, `automation.completed`, etc.).

Actualmente no hay un esquema de nombres definido para eventos entre Engines. El campo `source` existe en `BusinessEvent` pero no se usa consistentemente.

### Alternativas

**A1 — Namespace prefijo por Engine**
Cada Engine usa un prefijo en `event_type`. Ej: `bb.objetivo_identificado`, `ae.automation.started`, `ae.task.completed`.

**A2 — `source` field como discriminador**
Todos los eventos usan el mismo espacio de nombres (`objetivo_identificado`, `automation.started`). El campo `source` indica el Engine emisor (`business_brain`, `automation_engine`).

**A3 — Híbrido: prefijo + source**
Prefijo en `event_type` para legibilidad humana + `source` para filtrado programático.

### Impacto

| Área | A1 (Prefijo) | A2 (Source) | A3 (Híbrido) |
|---|---|---|---|
| **AE** | `event_type = "ae.automation.started"` | `event_type = "automation.started"`, `source = "automation_engine"` | Ambos. |
| **BB** | Requiere migrar eventos existentes a `bb.*`. Cambio en `BusinessEventPublisher`. | Sin cambios en BB. Ya usa `source` no consistentemente. | El BB debe agregar prefijo `bb.` a sus eventos. |
| **Consumidores** | Fácil filtrar por Engine con `startswith`. | Fácil filtrar por `source`. | Máxima flexibilidad. |

### Riesgos

| Alternativa | Riesgos |
|---|---|
| **A1** | Cambiar eventos del BB existentes puede romper consumidores (hoy no hay, pero es un riesgo). |
| **A2** | Colisión de nombres si dos engines usan el mismo `event_type`. `source` no previene colisiones en consumidores que filtran por tipo. |
| **A3** | Redundancia. Dos campos diciendo lo mismo. |

### Recomendación

**A1 (namespace prefijo por Engine).** Es el estándar en sistemas multi-engine. Los eventos actuales del BB (`objetivo_identificado`, etc.) se mantienen sin prefijo por compatibilidad, pero los nuevos eventos del AE usan `ae.*`. En una futura limpieza, los eventos del BB pueden migrarse a `bb.*`. El campo `source` se completa obligatoriamente en ambos casos.

---

## Resumen de decisiones requeridas

| ID | Decisión | Alternativa recomendada | ¿Bloqueante para empezar? |
|---|---|---|---|
| D01 | Sincronía de ejecución | A3 — Híbrido (background task) | Sí |
| D02 | Punto de inyección | A1 — En BusinessBrainService | Sí |
| D03 | Dependencia Integration Engine | A2 — Adaptador HTTP directo temporal | Sí (define alcance de tareas) |
| D04 | Definiciones de Workflow | A1 — Programático Fase 1 | No (puede decidirse durante implementación) |
| D05 | Alcance Fase 1 | A2 — Acciones actuales + scheduling simple | Sí |
| D06 | Persistencia de ejecuciones | A3 — Eventos + estado actual en DB | Sí |
| D07 | Esquema de eventos | A1 — Namespace prefijo por Engine | No (puede definirse al implementar Execution Monitor) |

**Bloqueantes:** D01, D02, D03, D05, D06.

**No bloqueantes pero recomendable cerrar antes del plan:** D04, D07.

---

*Este documento extrae las preguntas abiertas identificadas en ENG004_DOMAIN_ANALYSIS.md y las presenta para decisión del CTO. No incluye respuestas vinculantes ni definiciones de Macro Blocks.*
