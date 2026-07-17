# D-009-08 – Response Composer

**Proyecto:** BotWA Starter
**Documento:** D-009 – Conversation Engine
**Engine ID:** ENG-002
**Versión:** 1.0
**Estado:** Aprobado

## Objetivo
Transformar una Business Decision en una respuesta clara, natural y alineada con la identidad comunicacional de la empresa.

## Responsabilidad
Responder: ¿Cómo debe expresarse esta decisión al cliente?

## Entradas
- Business Decision
- Conversation Context
- Conversation State
- Perfil del cliente
- Configuración comunicacional de la empresa

## Salida
Business Response

## Principios
- Natural.
- Consistente.
- Personalizable.
- Multilingüe.
- Independiente del canal.

## Regla Arquitectónica
Solo el Response Composer puede transformar una Business Decision en una Business Response.

## CTO Review
Separa completamente la lógica del negocio de la experiencia conversacional.
