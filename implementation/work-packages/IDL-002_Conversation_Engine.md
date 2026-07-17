# IDL-002 - Conversation Engine Implementation Decision Log

**Proyecto:** BotWA Starter  
**Work Package:** WP-002 - Conversation Engine  
**Estado:** RECORDED  

---

# 1. Decisiones

## IDL-002-01 - Contratos Pydantic v2

Se implementaron `ConversationMessage`, `ConversationContext` y `ChannelResponse` como contratos publicos con Pydantic v2.

Justificacion: WP-002 solicita estos contratos publicos y ADR-T001 define Pydantic v2 como tecnologia oficial de validacion.

## IDL-002-02 - Conversation Engine en `app/core/conversation`

Se ubico `ConversationService`, `MessageRouter` y `ConversationMapper` dentro de `app/core/conversation`.

Justificacion: WP-002 requiere estructura definitiva `app/core`, y el Conversation Engine pertenece al Core certificado.

## IDL-002-03 - Contratos conversacionales en `app/domain/conversation`

Se ubicaron los contratos conversacionales en `app/domain/conversation`.

Justificacion: los contratos representan objetos publicos del dominio conversacional y deben estar separados de API e infraestructura.

## IDL-002-04 - Business Brain Stub en `app/shared/stubs`

Se creo un stub temporal del Business Brain en `app/shared/stubs`.

Justificacion: WP-002 prohibe implementar Business Brain, pero requiere validar el flujo Conversation Engine -> Business Brain.

## IDL-002-05 - API sin logica de negocio

El endpoint `POST /conversation/message` delega en `ConversationService`.

Justificacion: MS-001 establece que la API no debe contener logica de negocio.

---

# 2. Restricciones Respetadas

- No se implemento IA.
- No se implemento Business Brain real.
- No se implemento Knowledge Engine.
- No se implemento Automation Engine.
- No se implemento Integration Engine.
- No se agregaron proveedores externos.
- No se agrego WhatsApp ni integraciones reales.
- No se modifico arquitectura ni gobernanza.
