# D-009-06 – Topic Detector

**Proyecto:** BotWA Starter
**Documento:** D-009 – Conversation Engine
**Engine ID:** ENG-002
**Versión:** 1.0
**Estado:** Aprobado

## Objetivo
Identificar y administrar los temas presentes en una conversación para mantener una comunicación organizada y coherente.

## Responsabilidad
Responder: ¿De qué está hablando realmente el cliente?

## Entradas
- Conversation Context
- Conversation Message
- Historial relevante

## Salida
Conversation Topics

## Capacidades
- Detectar tema principal.
- Detectar temas secundarios.
- Detectar cambios de tema.
- Reanudar temas anteriores.
- Administrar múltiples hilos (Conversation Threads).

## Principios
- Independiente del canal.
- Independiente del idioma.
- Multitema.
- Consistente.

## Regla Arquitectónica
Solo el Topic Detector administra los temas e hilos de conversación.

## CTO Review
El uso de Conversation Threads permite mantener conversaciones complejas sin perder contexto.
