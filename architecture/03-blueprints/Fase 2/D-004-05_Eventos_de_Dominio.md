# D-004-05 – Eventos de Dominio

**Proyecto:** BotWA Starter
**Documento:** Modelo de Dominio
**Capítulo:** 05 – Eventos de Dominio
**Versión:** 1.0
**Estado:** Aprobado

# Objetivo

Definir los Eventos de Dominio que representan los hechos relevantes del negocio y que impulsan el comportamiento interno de BotWA.

# ¿Qué es un Evento de Dominio?

Un Evento de Dominio representa un hecho que ya ocurrió.

No expresa una intención ni una acción pendiente.

Ejemplos:

- Conversación iniciada.
- Caso creado.
- Caso resuelto.

# Principios

- Representa un hecho del negocio.
- Se escribe en pasado.
- Es auditable.
- Puede desencadenar otros procesos.
- Es independiente de la tecnología.

# Eventos del Dominio

## Conversación
- Conversación iniciada.
- Conversación reanudada.
- Conversación pausada.
- Conversación finalizada.

## Cliente
- Cliente identificado.
- Cliente registrado.
- Cliente actualizado.

## Caso de Negocio
- Caso creado.
- Caso clasificado.
- Caso actualizado.
- Caso escalado.
- Caso resuelto.
- Caso cancelado.

## Business Brain
- Objetivo identificado.
- Estrategia seleccionada.
- Decisión tomada.

## Agente IA
- Respuesta generada.
- Respuesta validada.

## Automatización
- Automatización ejecutada.
- Seguimiento programado.
- Recordatorio enviado.

## Conocimiento
- Conocimiento consultado.
- Información encontrada.
- Información no encontrada.

# Eventos excluidos

No pertenecen al dominio:

- Webhook recibido.
- HTTP 200.
- OpenAI respondió.
- WhatsApp entregó mensaje.
- Error de red.

# Decisión Arquitectónica

El Business Brain reacciona únicamente a Eventos de Dominio.

# CTO Review

Esta decisión desacopla el negocio de la infraestructura y facilita la evolución de la plataforma.
