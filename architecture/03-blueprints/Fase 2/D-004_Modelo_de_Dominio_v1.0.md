# D-004 – Modelo de Dominio

**Proyecto:** BotWA Starter
**Código:** D-004
**Versión:** 1.0
**Estado:** Aprobado

## Objetivo
Definir el modelo de dominio oficial de BotWA Starter y el lenguaje de negocio que guiará la implementación.

## Principios
- Dominio antes que tecnología.
- Lenguaje ubicuo.
- Independencia del sector.
- El negocio es la fuente de verdad.

## Lenguaje Ubicuo
Empresa, Cliente, Conversación, Caso de Negocio, Business Brain, Agente IA, Conocimiento, Acción, Resultado y Canal.

**Principio central:** BotWA administra Casos de Negocio utilizando conversaciones como medio de interacción.

## Entidades
- Empresa
- Cliente
- Conversación
- Caso de Negocio
- Agente IA
- Canal
- Acción
- Automatización

## Agregados
- Empresa
- Cliente
- Caso de Negocio (Aggregate Root principal)
- Automatización

## Value Objects
- Objetivo del Caso
- Estado del Caso
- Resultado del Caso
- Contexto Conversacional
- Identidad Externa
- Periodo de Seguimiento
- Prioridad
- Resultado de Acción

## Eventos de Dominio
Conversación iniciada, Caso creado, Caso actualizado, Estrategia seleccionada, Respuesta generada, Seguimiento programado y Caso resuelto.

## Reglas de Negocio
- Toda conversación pertenece a una Empresa y a un Cliente.
- Todo Caso pertenece a una Empresa y a un Cliente.
- Todo Caso tiene un objetivo.
- Solo existe una estrategia activa por Caso.
- Toda Acción pertenece a un Caso.
- La IA no modifica directamente el dominio.
- Toda decisión importante genera un Evento.

## Relaciones
Empresa
 ├── Clientes
 │     └── Conversaciones
 │              └── Casos de Negocio
 │                      ├── Acciones
 │                      ├── Eventos
 │                      └── Resultado
 ├── Conocimiento
 ├── Agentes IA
 ├── Canales
 └── Automatizaciones

El Business Brain actúa como Servicio de Dominio.

## Conclusiones
Este documento define el lenguaje oficial de BotWA Starter y servirá como referencia para Blueprints, Arquitectura Técnica, Specifications e implementación.

**Estado:** Aprobado
