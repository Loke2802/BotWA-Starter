# D-009-07 – Conversation State Manager

**Proyecto:** BotWA Starter
**Documento:** D-009 – Conversation Engine
**Engine ID:** ENG-002
**Versión:** 1.0
**Estado:** Aprobado

## Objetivo
Administrar el estado de cada conversación y de cada hilo conversacional durante todo su ciclo de vida.

## Responsabilidad
Responder: ¿Cuál es el estado actual de esta conversación?

## Entradas
- Conversation Context
- Conversation Topics
- Historial
- Metadata del canal

## Salida
Conversation State

## Estados
- Nueva
- En progreso
- Esperando información
- Esperando decisión del Business Brain
- Esperando respuesta del cliente
- Finalizada
- Cancelada
- Escalada a humano

## Principios
- Consistente
- Determinístico
- Auditable
- Reanudable
- Independiente del canal

## Regla Arquitectónica
Solo el Conversation State Manager puede modificar el Conversation State.

## CTO Review
Permite pausar, reanudar y continuar conversaciones sin perder continuidad.
