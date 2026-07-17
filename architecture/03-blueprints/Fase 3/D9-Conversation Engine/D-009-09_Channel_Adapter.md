# D-009-09 – Channel Adapter

**Proyecto:** BotWA Starter
**Documento:** D-009 – Conversation Engine
**Engine ID:** ENG-002
**Versión:** 1.0
**Estado:** Aprobado

## Objetivo
Adaptar la Business Response al formato y capacidades del canal de destino.

## Responsabilidad
Responder: ¿Cómo debe enviarse esta respuesta por este canal?

## Entradas
- Business Response
- Configuración del canal
- Capacidades del canal

## Salida
Channel Response

## Principios
- Independiente del negocio.
- Multicanal.
- Reutilizable.
- Extensible.

## Regla Arquitectónica
Todo envío hacia un canal deberá realizarse mediante un Channel Adapter.

## CTO Review
Desacopla completamente la lógica conversacional de los canales externos.
