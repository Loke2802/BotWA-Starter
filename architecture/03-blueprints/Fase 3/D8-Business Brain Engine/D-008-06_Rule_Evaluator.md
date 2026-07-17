# D-008-06 – Rule Evaluator

Proyecto: BotWA Starter
Documento: D-008 – Business Brain Engine
Engine ID: ENG-001
Versión: 1.0
Estado: Aprobado

## Objetivo
Aplicar las reglas del negocio sobre el Business Context y el Business Intent.

## Responsabilidad
Responder: ¿Qué está permitido hacer?

## Entradas
- Business Context
- Business Intent
- Reglas del Dominio (BR-XXX)
- Configuración de la empresa

## Salida
- Business Constraints

## Business Constraints
Conjunto de restricciones y condiciones válidas para el caso de negocio.

## Principios
- Determinístico
- Auditable
- Independiente de IA
- Independiente del canal

## Regla Arquitectónica
Todas las reglas del negocio deberán evaluarse exclusivamente dentro del Rule Evaluator.

## CTO Review
Las reglas evolucionan; el Decision Pipeline permanece estable.
