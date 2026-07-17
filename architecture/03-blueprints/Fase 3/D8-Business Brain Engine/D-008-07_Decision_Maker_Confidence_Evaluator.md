# D-008-07 – Decision Maker & Confidence Evaluator

**Proyecto:** BotWA Starter
**Documento:** D-008 – Business Brain Engine
**Capítulo:** 07 – Decision Maker
**Engine ID:** ENG-001
**Versión:** 1.0
**Estado:** Aprobado

## Objetivo
Seleccionar la mejor decisión posible utilizando el Business Context, el Business Intent y las restricciones del negocio.

## Entradas
- Business Context
- Business Intent
- Business Constraints

## Business Options
Antes de decidir, el Engine construye un conjunto de alternativas válidas (Business Options).

## Decision Criteria
Las alternativas se comparan utilizando criterios del negocio:
- Cumplimiento de reglas.
- Satisfacción de la intención del cliente.
- Optimización de recursos.
- Reducción de riesgos.
- Generación de valor.

## Salida
Produce un objeto denominado **Business Decision**.

## Confidence Evaluator
Después de decidir, evalúa el nivel de confianza.

- Alta → Continuar.
- Media → Solicitar más información.
- Baja → Escalar a un humano.

## Principios
- Consistente.
- Explicable.
- Auditable.
- Configurable.
- Independiente de IA.

## Regla Arquitectónica
Solo el Decision Maker puede generar un Business Decision.

## CTO Review
El Decision Maker representa el criterio empresarial de BotWA y el Confidence Evaluator evita automatizaciones inseguras.
