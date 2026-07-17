# D-009 – Conversation Engine (Consolidado)

**Proyecto:** BotWA Starter  
**Documento:** D-009 – Conversation Engine  
**Engine ID:** ENG-002  
**Versión:** 1.0  
**Estado:** Aprobado

---

# Propósito

El Conversation Engine es el **Motor de Comunicación Empresarial** de BotWA.

Su responsabilidad es transformar la comunicación humana en información estructurada para el Business Brain y convertir las decisiones del negocio en respuestas naturales para el cliente.

---

# Estructura del Documento

## D-009-01
Introducción

## D-009-02
Filosofía

Principios:

- La conversación pertenece al cliente.
- La empresa mantiene una sola voz.
- Comprender antes de responder.
- Mantener continuidad.
- Separación entre comunicación y decisiones.
- Adaptación al canal.

---

## D-009-03
Communication Pipeline

```
Message
    ↓
Message Receiver
    ↓
Conversation Context Builder
    ↓
Topic Detector
    ↓
Conversation State Manager
    ↓
Business Brain
    ↓
Response Composer
    ↓
Channel Adapter
    ↓
Response
```

---

## D-009-04
Message Receiver

Responsabilidad:

- Recibir mensajes.
- Validarlos.
- Normalizarlos.

Produce:

**Conversation Message**

---

## D-009-05
Conversation Context Builder

Construye:

**Conversation Context**

Mantiene:

- historial
- continuidad
- información conocida
- información pendiente

---

## D-009-06
Topic Detector

Construye:

- Conversation Topics
- Conversation Threads

Permite administrar múltiples temas dentro de una misma conversación.

---

## D-009-07
Conversation State Manager

Administra:

- Estado conversacional.
- Próximo paso.
- Conversaciones pausadas.
- Conversaciones reanudadas.
- Escalamientos.

Produce:

**Conversation State**

---

## D-009-08
Response Composer

Transforma:

Business Decision

↓

Business Response

Manteniendo:

- tono
- personalidad
- idioma
- identidad empresarial

---

## D-009-09
Channel Adapter

Transforma:

Business Response

↓

Channel Response

Adaptándose a:

- WhatsApp
- Telegram
- Instagram
- Web Chat
- Email
- Voz

---

## D-009-10
Conclusiones

El Conversation Engine se adopta oficialmente como el Motor de Comunicación Empresarial de BotWA.

---

# Objetos Conversacionales

- Conversation Message
- Conversation Context
- Conversation Topics
- Conversation Threads
- Conversation State
- Business Decision Request
- Business Response
- Channel Response

---

# Principios Arquitectónicos

- El Conversation Engine comunica.
- El Business Brain decide.
- Cada Engine es dueño de sus propios objetos.
- La comunicación entre Engines se realiza mediante contratos explícitos.
- Toda comunicación sigue el Communication Pipeline.

---

# Relación con el Business Brain

Conversation Engine

↓

Business Decision Request

↓

Business Brain

↓

Business Decision

↓

Business Response

↓

Channel Response

---

# Resultado

El Conversation Engine queda definido como el segundo Engine oficial de BotWA y el responsable exclusivo de toda la comunicación empresarial de la plataforma.

Este documento constituye la referencia oficial para la implementación del ENG-002.
