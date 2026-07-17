# D-008-09 – Event Publisher

Proyecto: BotWA Starter
Documento: D-008 – Business Brain Engine
Engine ID: ENG-001
Versión: 1.0
Estado: Aprobado

## Objetivo
Publicar los Business Events generados por el Decision Pipeline.

## Responsabilidad
Responder: ¿Qué necesita saber el resto del sistema?

## Entradas
- Business Decision
- Business Action Plan
- Business Context

## Salida
Business Event

## Principios
- Inmutable.
- Auditable.
- Trazable.
- Independiente de infraestructura.

## Regla Arquitectónica
Todo Decision Pipeline finaliza publicando uno o más Business Events.

## CTO Review
El Event Publisher desacopla el Business Brain del resto de los Engines mediante eventos.
