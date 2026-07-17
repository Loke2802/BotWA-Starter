# SPEC-VS001 - First Vertical Slice v1.0

**Proyecto:** BotWA Starter  
**Documento:** Implementation Specification  
**Codigo:** SPEC-VS001  
**Version:** 1.0  
**Estado:** Draft  
**Ubicacion:** architecture/01-specs/Implementation/  

---

# 1. Objetivo del Vertical Slice

Definir la primera Specification implementable de BotWA Starter para validar el flujo minimo del Nucleo Cognitivo aprobado en Fase 3.

El Vertical Slice debe demostrar que BotWA puede recibir un mensaje, transformarlo en informacion estructurada, tomar una decision de negocio, consultar conocimiento oficial y devolver una respuesta empresarial respetando los limites arquitectonicos definidos en la AKB.

El objetivo principal es validar:

- El Business Brain como unico responsable de decisiones de negocio.
- El Conversation Engine como unico responsable de comunicacion.
- El Knowledge Engine como fuente gobernada de conocimiento empresarial.
- La colaboracion entre Engines mediante contratos explicitos.
- El uso de modelos canonicos para desacoplar el Core de tecnologias externas.
- La ejecucion inicial sin depender de WhatsApp ni integraciones externas.

---

# 2. Alcance

Este Vertical Slice incluye un flujo funcional minimo del Nucleo Cognitivo:

```text
Message
-> Conversation Engine
-> Business Brain
-> Knowledge Engine
-> Business Brain
-> Conversation Engine
-> Response
```

El alcance incluye:

- Recepcion de un mensaje textual mediante un endpoint HTTP inicial.
- Normalizacion minima del mensaje como objeto conversacional.
- Construccion de contexto conversacional minimo.
- Creacion de una solicitud de decision para el Business Brain.
- Identificacion de una intencion de negocio simple.
- Evaluacion basica de reglas del negocio.
- Consulta de conocimiento empresarial oficial mediante el Knowledge Engine.
- Generacion de una decision de negocio.
- Composicion de una respuesta empresarial.
- Adaptacion de la respuesta al canal HTTP simulado.
- Registro de eventos de negocio requeridos por el flujo.
- Persistencia minima necesaria para validar trazabilidad.

---

# 3. Exclusiones (Out of Scope)

Queda fuera de este Vertical Slice:

- Integracion con WhatsApp.
- Redis.
- RabbitMQ.
- Kafka.
- Memoria conversacional avanzada.
- Integraciones externas.
- Workflows de automatizacion.
- Automation Engine.
- Integration Engine.
- Gestion analitica avanzada.
- Administracion SaaS completa.
- Multiempresa avanzada.
- Autenticacion y autorizacion avanzada.
- Ingesta automatica de conocimiento.
- Resolucion avanzada de conflictos de conocimiento.
- Knowledge Health Score avanzado.
- Multiples canales reales.
- Multiples proveedores de IA en ejecucion.
- Modelado completo de base de datos.
- Implementacion de modelos Pydantic en esta Specification.
- Implementacion de API en esta Specification.

---

# 4. Caso de uso inicial

El caso de uso inicial validara una consulta simple de informacion del negocio.

Ejemplo funcional:

```text
Cliente: ¿Cual es el horario de atencion?
BotWA: Responde utilizando conocimiento oficial del negocio.
```

Este caso de uso fue seleccionado porque permite validar los tres Engines cognitivos aprobados sin introducir dependencias de canales reales, automatizaciones o integraciones externas.

---

# 5. Flujo funcional

El flujo funcional del Vertical Slice sera:

```text
Cliente
-> Endpoint HTTP inicial
-> Conversation Engine
-> Message Receiver
-> Conversation Context Builder
-> Topic Detector
-> Conversation State Manager
-> Business Decision Request
-> Business Brain
-> Intent Analyzer
-> Rule Evaluator
-> Decision Maker
-> Confidence Evaluator
-> Knowledge Engine
-> Knowledge Query
-> Knowledge Catalog
-> Knowledge Response
-> Business Brain
-> Action Planner
-> Event Publisher
-> Business Decision
-> Conversation Engine
-> Response Composer
-> Channel Adapter
-> Channel Response
-> Cliente
```

Reglas del flujo:

- Toda comunicacion debe seguir el Communication Pipeline.
- Toda decision debe seguir el Decision Pipeline.
- Toda consulta de conocimiento debe pasar por el Knowledge Engine.
- El Conversation Engine no decide.
- El Knowledge Engine no interpreta intenciones ni toma decisiones.
- El Business Brain no formatea respuestas especificas de canal.
- Todo evento relevante debe registrarse para trazabilidad.

---

# 6. Engines involucrados

## ENG-001 Business Brain

Responsabilidad en este Vertical Slice:

- Transformar contexto de negocio en una decision consistente.
- Ejecutar el Decision Pipeline minimo.
- Coordinar la consulta al Knowledge Engine cuando la decision requiera conocimiento oficial.
- Generar Business Decision.
- Generar Business Action Plan cuando corresponda.
- Publicar Business Events.

## ENG-002 Conversation Engine

Responsabilidad en este Vertical Slice:

- Recibir y normalizar el mensaje inicial.
- Construir contexto conversacional minimo.
- Crear Business Decision Request.
- Recibir la decision del Business Brain.
- Componer una Business Response.
- Adaptar la respuesta al canal HTTP simulado.

## ENG-003 Knowledge Engine

Responsabilidad en este Vertical Slice:

- Recibir Knowledge Query desde el Business Brain.
- Consultar conocimiento empresarial oficial disponible en el Knowledge Catalog minimo.
- Retornar Knowledge Response.
- Mantener la separacion entre informacion, conocimiento y decision.

---

# 7. Contratos minimos requeridos

Los contratos minimos requeridos derivan de los Blueprints D-008, D-009 y D-010, y de ADR-006 Engine Contracts.

## Conversation Engine

- Conversation Message
- Conversation Context
- Conversation Topics
- Conversation State
- Business Decision Request
- Business Response
- Channel Response

## Business Brain

- Business Context
- Business Intent
- Business Constraints
- Business Options
- Business Decision
- Business Action Plan
- Business Event

## Knowledge Engine

- Knowledge Source
- Knowledge Query
- Knowledge Item
- Normalized Knowledge Item
- Resolved Knowledge Item
- Validated Knowledge Item
- Knowledge Response
- Knowledge Catalog

Para este Vertical Slice, los contratos deben definirse en su forma minima necesaria para ejecutar el caso de uso inicial. Esta Specification no define modelos Pydantic ni estructuras de tablas completas.

---

# 8. Endpoint HTTP inicial

El canal inicial sera un canal HTTP simulado, en reemplazo temporal de WhatsApp.

Endpoint inicial propuesto:

```text
POST /messages
```

Responsabilidad del endpoint:

- Recibir un mensaje textual de entrada.
- Entregar el mensaje al Conversation Engine.
- Retornar la respuesta producida por el Channel Adapter del Conversation Engine.

Restricciones:

- El endpoint no debe contener logica de negocio.
- El endpoint no debe consultar conocimiento directamente.
- El endpoint no debe tomar decisiones.
- El endpoint no representa una integracion real con WhatsApp.

---

# 9. Persistencia minima necesaria

La persistencia minima debe existir solo para validar trazabilidad, relaciones basicas del dominio y ejecucion del flujo.

Elementos minimos a persistir:

- Empresa.
- Cliente.
- Conversacion.
- Caso de Negocio.
- Business Events.
- Knowledge Items aprobados para el Knowledge Catalog minimo.

Restricciones:

- No se deben disenar tablas completas en esta Specification.
- No se debe implementar un modelo SaaS completo.
- No se debe introducir persistencia para Engines fuera del Vertical Slice.
- La persistencia debe respetar que el Caso de Negocio es el Aggregate Root principal del dominio.
- La IA no debe modificar directamente el dominio.

---

# 10. Estructura inicial del proyecto

La estructura inicial del proyecto debe reflejar los limites de Engines, contratos e infraestructura aprobados en la AKB.

Estructura conceptual inicial:

```text
app/
  api/
  contracts/
  domain/
  engines/
    business_brain/
    conversation/
    knowledge/
  infrastructure/
    database/
    logging/
    settings/
  tests/
```

Reglas de organizacion:

- Los Engines deben permanecer separados.
- Los contratos compartidos deben ser explicitos.
- La infraestructura no debe gobernar el dominio.
- La API no debe contener reglas de negocio.
- La configuracion debe realizarse mediante variables de entorno y Pydantic Settings.
- La validacion de datos debe realizarse con Pydantic v2 durante la implementacion.
- La persistencia debe utilizar PostgreSQL 17, SQLAlchemy 2.x y Alembic cuando corresponda.

---

# 11. Estrategia de IA para este Vertical Slice

La arquitectura aprobada establece que la IA comunica y colabora, pero no gobierna el negocio.

Para este Vertical Slice, la estrategia sera provider-agnostic y minimamente dependiente de IA.

Reglas:

- La IA no debe tomar decisiones de negocio.
- La IA no debe modificar directamente el dominio.
- La IA no debe definir la verdad del conocimiento.
- El Rule Evaluator debe ser independiente de IA.
- El Decision Maker debe ser independiente de IA.
- El Knowledge Engine debe responder desde conocimiento oficial disponible.

Uso permitido en este Vertical Slice:

- Apoyo opcional para resolver ambiguedades de lenguaje dentro de limites definidos por el Engine correspondiente.
- Composicion asistida de lenguaje natural si respeta la Business Decision y el conocimiento oficial.

Implementacion inicial recomendada:

- Mantener el flujo deterministico para el caso de uso inicial.
- Preparar la arquitectura para un proveedor OpenAI-compatible sin acoplar los Engines al proveedor.

---

# 12. Eventos que deberan registrarse

Los eventos derivan del Modelo de Dominio y del Decision Pipeline.

Eventos minimos para este Vertical Slice:

- Conversacion iniciada.
- Caso creado.
- Objetivo identificado.
- Estrategia seleccionada.
- Respuesta generada.
- Caso actualizado.

Reglas:

- Todo evento relevante debe ser trazable.
- Los Business Events deben ser publicados por el Event Publisher del Business Brain.
- Los eventos no deben acoplarse a infraestructura especifica.
- Los eventos deben permitir auditar el flujo del caso de uso inicial.

---

# 13. Criterios de aceptacion

El Vertical Slice sera aceptado cuando cumpla los siguientes criterios:

- Un mensaje textual puede ingresar por `POST /messages`.
- El mensaje es procesado por el Conversation Engine.
- El Conversation Engine genera una Business Decision Request.
- El Business Brain recibe la solicitud y ejecuta el Decision Pipeline minimo.
- El Business Brain identifica una intencion de negocio simple relacionada con consulta de informacion.
- El Business Brain consulta al Knowledge Engine cuando requiere conocimiento oficial.
- El Knowledge Engine responde utilizando el Knowledge Catalog minimo.
- El Business Brain genera una Business Decision.
- El Conversation Engine transforma la decision en una Business Response.
- El Channel Adapter retorna una Channel Response mediante el canal HTTP simulado.
- La respuesta final no depende de WhatsApp.
- La respuesta final no es generada saltando el Business Brain.
- La respuesta final no usa conocimiento fuera del Knowledge Engine.
- Se registran los eventos minimos requeridos.
- La implementacion respeta los limites entre Engines.
- La API no contiene logica de negocio.
- El Knowledge Engine no toma decisiones.
- El Conversation Engine no toma decisiones.
- El Business Brain no formatea respuestas especificas del canal.
- La IA, si se utiliza, no gobierna el negocio ni modifica el dominio.

---

# 14. Riesgos conocidos

- Acoplar prematuramente el Core a WhatsApp o a un proveedor externo.
- Convertir el Business Brain en un wrapper de IA.
- Permitir que el Conversation Engine tome decisiones.
- Permitir que el Knowledge Engine interprete intenciones.
- Saltar contratos explicitos entre Engines.
- Disenar persistencia completa antes de validar el flujo minimo.
- Introducir conceptos de dominio no definidos en la AKB.
- Implementar Automation Engine o Integration Engine antes de validar el Nucleo Cognitivo.
- Omitir eventos y perder auditabilidad.
- Tratar el Vertical Slice como chatbot en lugar de gestion de Casos de Negocio.

---

# 15. Proximos pasos

1. Revisar y aprobar esta Specification.
2. Definir los contratos minimos implementables derivados de esta Specification.
3. Definir la estructura inicial del repositorio Python.
4. Configurar el proyecto base con FastAPI, Pydantic v2, SQLAlchemy 2.x, Alembic, Pytest, Black, Ruff, mypy y Structlog.
5. Implementar el endpoint HTTP simulado sin logica de negocio.
6. Implementar el Knowledge Catalog minimo.
7. Implementar el Decision Pipeline minimo del Business Brain.
8. Implementar el Communication Pipeline minimo del Conversation Engine.
9. Registrar eventos minimos.
10. Validar criterios de aceptacion mediante pruebas.

---

# Open Decisions

- Definir el contenido inicial aprobado del Knowledge Catalog minimo para el caso de uso de horario de atencion.
- Definir si la primera ejecucion usara IA real OpenAI-compatible o comportamiento deterministico sin proveedor externo.
- Definir los campos minimos exactos de cada contrato antes de crear modelos implementables.
- Definir los campos minimos exactos de persistencia antes de crear migraciones.
- Definir el estado oficial del documento: Draft, Approved o Superseded.
