# D-004-03 – Entidades y Agregados

**Proyecto:** BotWA Starter
**Documento:** Modelo de Dominio
**Capítulo:** 03 – Entidades y Agregados
**Versión:** 1.0
**Estado:** Aprobado

---

# Objetivo

Identificar las entidades principales del dominio de BotWA Starter y definir los primeros agregados que garantizan la consistencia del negocio.

Este capítulo no modela tablas de base de datos ni clases de programación. Modela conceptos del negocio con identidad propia.

---

# ¿Qué es una Entidad?

Una Entidad es un objeto del dominio que posee identidad propia y puede evolucionar a lo largo del tiempo.

Aunque cambien sus atributos, sigue siendo el mismo objeto del negocio.

Una Entidad normalmente:

- Tiene un identificador único.
- Cambia de estado.
- Participa en reglas del negocio.
- Puede ser referenciada por otras entidades.

---

# Entidades del Core

## Empresa
Representa al negocio que utiliza BotWA.

Es responsable de:

- Configuración.
- Conocimiento.
- Automatizaciones.
- Agentes IA.
- Canales.
- Reglas propias del negocio.

## Cliente

Representa a la persona que interactúa con la Empresa.

Puede iniciar múltiples conversaciones y múltiples Casos de Negocio a lo largo del tiempo.

## Conversación

Representa una sesión de interacción entre un Cliente y una Empresa.

La conversación contiene el historial de mensajes y proporciona el contexto de comunicación.

Una conversación puede contener uno o varios Casos de Negocio.

## Caso de Negocio

Es la entidad central del dominio.

Representa el objetivo que el Cliente desea resolver.

Ejemplos:

- Solicitar información.
- Comprar un producto.
- Agendar una cita.
- Solicitar soporte.
- Gestionar una devolución.

Todo el comportamiento de BotWA gira alrededor de esta entidad.

## Agente IA

Representa una instancia especializada en comunicación.

Puede existir un único agente o varios agentes especializados según la evolución del producto.

## Canal

Representa el medio por el cual ocurre la interacción.

BotWA Starter comienza con WhatsApp, pero el dominio admite múltiples canales.

## Acción

Representa una actividad ejecutada por BotWA para avanzar un Caso de Negocio.

Toda Acción debe tener un propósito claramente asociado al objetivo del Cliente.

## Automatización

Representa procesos automáticos configurados por la Empresa.

Puede activarse por eventos, condiciones o programación.

---

# ¿Qué es un Agregado?

Un Agregado es un conjunto de entidades que deben mantenerse consistentes entre sí.

Cada agregado tiene una única puerta de entrada denominada **Aggregate Root**.

El Aggregate Root protege las reglas del negocio y evita modificaciones inconsistentes.

---

# Agregados Propuestos

## Agregado Empresa
**Aggregate Root:** Empresa

Organiza el ecosistema completo de una Empresa.

## Agregado Cliente
**Aggregate Root:** Cliente

Representa la relación histórica entre una Empresa y una persona.

## Agregado Caso de Negocio
**Aggregate Root:** Caso de Negocio

Es el agregado principal del dominio y administra objetivo, estado, acciones, eventos y resultado.

## Agregado Automatización
**Aggregate Root:** Automatización

Gestiona disparadores, condiciones y acciones automáticas.

---

# Reglas de Consistencia

- Todo Caso de Negocio pertenece exactamente a una Empresa.
- Todo Caso de Negocio pertenece exactamente a un Cliente.
- Toda Acción pertenece exactamente a un Caso de Negocio.
- Ninguna Conversación puede existir fuera del contexto de una Empresa.

---

# Decisión Arquitectónica

El **Caso de Negocio** se define como el **Aggregate Root principal** del dominio.

La Conversación es únicamente el medio por el cual el Caso evoluciona.

---

# CTO Review

BotWA no gestiona chats.

BotWA gestiona objetivos del negocio.

Gracias a esta decisión, la plataforma podrá evolucionar sin modificar su núcleo conceptual.
