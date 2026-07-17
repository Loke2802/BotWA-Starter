# BotWA Master SPEC v0.2

**Proyecto:** BotWA Starter  
**Documento:** Master Specification  
**Versión:** 0.2  
**Estado:** Aprobado (Arquitectura Fases 1 y 2)

---

# 0. Control del Documento

**Propósito:** Ser la única Source of Truth para la implementación.

Jerarquía documental:

ADR
↑
D-XXX
↑
Master SPEC
↑
Código

---

# 1. Proyecto

- Producto: BotWA Starter
- Tipo: SaaS
- Arquitectura: Domain Driven Design (DDD)
- Canal inicial: WhatsApp
- Público objetivo: MYPES

Objetivo principal: Gestionar Casos de Negocio utilizando conversaciones como medio de interacción.

---

# 2. Misión y Visión

**Misión:** Democratizar el acceso a asistentes inteligentes para MYPES.

**Visión:** Evolucionar BotWA desde Starter hasta Business y Enterprise manteniendo un mismo Core.

---

# 3. Objetivos

- Automatizar atención.
- Gestionar Casos de Negocio.
- Reducir tiempos de respuesta.
- Mejorar la experiencia del cliente.
- Mantener independencia tecnológica.

---

# 4. Alcance

Incluye:

- WhatsApp
- IA Conversacional
- Business Brain
- Automatizaciones
- Gestión de Casos

No incluye:

- ERP
- CRM completo
- BI avanzado

---

# 5. Principios Arquitectónicos

- Dominio antes que tecnología.
- Lenguaje Ubicuo.
- Source of Truth.
- Arquitectura desacoplada.
- Evolución mediante configuración.

---

# 6. Arquitectura General

Componentes principales:

- Business Brain
- Agente IA
- Knowledge
- Automatizaciones
- Integraciones
- Adaptadores

---

# 7. Modelo de Dominio

Aggregate Root:
- Caso de Negocio

Domain Service:
- Business Brain

Entidades:
- Empresa
- Cliente
- Conversación
- Caso de Negocio
- Acción
- Automatización
- Agente IA
- Canal

---

# 8. Reglas de Negocio

- Toda Conversación pertenece a una Empresa.
- Toda Conversación pertenece a un Cliente.
- Todo Caso pertenece a una Empresa y un Cliente.
- La IA no modifica el dominio.
- El Business Brain aplica las reglas.

---

# 9. Eventos de Dominio

- Conversación iniciada
- Caso creado
- Objetivo identificado
- Estrategia seleccionada
- Respuesta generada
- Caso actualizado
- Seguimiento programado
- Caso resuelto

---

# 10. Value Objects

- Objetivo
- Estado
- Resultado
- Prioridad
- Contexto Conversacional
- Periodo de Seguimiento
- Identidad Externa
- Resultado de Acción

---

# 11. Agregados

- Empresa
- Cliente
- Caso de Negocio
- Automatización

---

# 12. Relaciones

Empresa
→ Cliente
→ Conversación
→ Caso de Negocio
→ Acción
→ Evento
→ Resultado

---

# 13. Decisiones Arquitectónicas

Referencias:

- ADR-001
- ADR-002

---

# 14. Diagramas

Arquitectura:
- DG-001 a DG-008

Dominio:
- DGD-001 a DGD-008

---

# 15. Convenciones

- Markdown
- Mermaid
- ADR
- DDD
- CamelCase para entidades
- snake_case cuando corresponda en implementación

---

# 16. Roadmap

- Fase 3 – Blueprints
- Fase 4 – Arquitectura Técnica
- Fase 5 – Implementación

---

# 17. Pendientes

- Definir Blueprints.
- Diseñar APIs.
- Definir Adaptadores.
- Validar con casos reales.

---

# 18. Criterios de Evolución

Toda modificación deberá:

- Respetar el Modelo de Dominio.
- Respetar los ADR.
- Mantener compatibilidad cuando sea posible.
- Actualizar este documento antes del código.

---

**Este documento constituye la especificación oficial de implementación de BotWA Starter v0.2.**
