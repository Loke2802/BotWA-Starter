# D-009-05 – Conversation Context Builder

**Proyecto:** BotWA Starter
**Documento:** D-009 – Conversation Engine
**Engine ID:** ENG-002
**Versión:** 1.0
**Estado:** Aprobado

## Objetivo
Construir el contexto conversacional que representa el estado actual de la interacción entre el cliente y la empresa.

## Responsabilidad
Responder: ¿Cuál es el contexto actual de esta conversación?

## Entradas
- Conversation Message
- Historial
- Estado conversacional
- Perfil del cliente
- Metadata del canal

## Salida
Conversation Context

## Principios
- Continuidad conversacional.
- Independiente del canal.
- Independiente del idioma.
- Sin decisiones de negocio.

## Regla Arquitectónica
Solo el Conversation Context Builder puede generar el Conversation Context.

## CTO Review
Separa el contexto conversacional del contexto de negocio para entregar información de calidad al Business Brain.
