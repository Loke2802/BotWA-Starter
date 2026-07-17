# MS-001 - Master Implementation Specification v1.0

**Proyecto:** BotWA Starter  
**Documento:** Master Implementation Specification  
**Codigo:** MS-001  
**Version:** 1.0  
**Estado:** APPROVED FOR IMPLEMENTATION  
**Fase:** 6 - Core Implementation  
**Ubicacion:** architecture/01-specs/Implementation/  

---

# 1. Objetivo

Definir la guia maestra oficial para iniciar la implementacion de BotWA Starter, utilizando exclusivamente la arquitectura aprobada, congelada y certificada durante las Fases 0 a 5.

Este documento no reemplaza ADRs, Blueprints, SPECs, Governance, Core Consolidation ni Architecture Handoff. Su funcion es ordenar las referencias oficiales y establecer el marco de trabajo diario para el equipo de desarrollo durante la Fase 6.

---

# 2. Alcance del MVP

El MVP de BotWA Starter se construira sobre el Core certificado y los cinco Engines oficiales:

- ENG-001 Business Brain.
- ENG-002 Conversation Engine.
- ENG-003 Knowledge Engine.
- ENG-004 Automation Engine.
- ENG-005 Integration Engine.

El alcance inicial de implementacion comenzara con el Vertical Slice 1 definido en `SPEC-VS001-First-Vertical-Slice-v1.0.md`.

El MVP debera preservar:

- Business Brain como responsable de decisiones.
- Conversation Engine como responsable de comunicacion.
- Knowledge Engine como responsable del conocimiento.
- Automation Engine como responsable de ejecucion de procesos.
- Integration Engine como frontera tecnologica con sistemas externos.
- Contratos publicos del Core definidos en `CCS-001`.
- Modelos canonicos definidos en `CCS-001`.
- Event Governance definido en `CCS-001`.
- Dependency Matrix definida en `CCS-001`.

---

# 3. Arquitectura oficial

La arquitectura oficial para implementacion es la arquitectura certificada por Fase 5.

Referencias obligatorias:

- `architecture/00-governance/CAB-001_Core_Architecture_Baseline_v1.0.md`
- `architecture/00-governance/AGR-001_Architecture_Governance_Rules_v1.0.md`
- `architecture/00-governance/CTO-RES-001_Architecture_Freeze_Authorization.md`
- `architecture/05-core/standards/CCS-001_Core_Consolidation_Standard_v1.0.md`
- `architecture/09-architecture rewiev/AHP-001_Architecture_Handoff_Package_v1.0.md`
- `architecture/09-architecture rewiev/CERT-001_Core_Certification_v1.0.md`
- `architecture/09-architecture rewiev/GATE-001_Implementation_Gate_Review_v1.0.md`

Reglas centrales:

- No modificar responsabilidades de Engines sin gobernanza.
- No introducir nuevos Engines sin Architecture Review.
- No cambiar contratos publicos sin actualizar el Contracts Catalog.
- No cambiar modelos sin actualizar Canonical Models.
- No cambiar Pipelines sin actualizar Blueprint, SPEC y Diagramas.
- Toda integracion pasa por Integration Engine.
- Business Brain decide.
- La IA no gobierna el negocio.
- El Core nunca conoce proveedores.

---

# 4. Referencias a SPEC por Engine

## ENG-001 Business Brain

Documentos oficiales:

- `architecture/01-specs/SPEC_Fase_3_v1.0_Nucleo_Cognitivo_BotWA.md`
- `architecture/03-blueprints/Fase 3/D8-Business Brain Engine/D-008-01_Introduccion_Business_Brain_Engine.md`
- `architecture/03-blueprints/Fase 3/D8-Business Brain Engine/D-008-03_Decision_Pipeline.md`
- `architecture/03-blueprints/Fase 3/D8-Business Brain Engine/D-008-10_Conclusiones.md`

Estado para implementacion: usable directamente durante Fase 6, complementado por `CCS-001` para contratos, modelos, eventos y dependencias.

## ENG-002 Conversation Engine

Documentos oficiales:

- `architecture/01-specs/SPEC_Fase_3_v1.0_Nucleo_Cognitivo_BotWA.md`
- `architecture/03-blueprints/Fase 3/D9-Conversation Engine/D-009_Conversation_Engine_Consolidado_v1.0.md`

Estado para implementacion: usable directamente durante Fase 6, complementado por `CCS-001`.

## ENG-003 Knowledge Engine

Documentos oficiales:

- `architecture/01-specs/SPEC_Fase_3_v1.0_Nucleo_Cognitivo_BotWA.md`
- `architecture/03-blueprints/Fase 3/D10-Knowledge Engine/D-010_Knowledge_Engine_Consolidado_v1.0.md`

Estado para implementacion: usable directamente durante Fase 6, complementado por `CCS-001`.

## ENG-004 Automation Engine

Documentos oficiales:

- `architecture/02-adrs/ADR-008_Automation_Engine.md`
- `architecture/03-blueprints/Fase 4/D11-Automation Engine/D-011_Automation_Engine_Consolidado.md`
- `architecture/03-blueprints/Fase 4/README_ENG-004_Automation_Engine.md`

Estado para implementacion: usable durante Fase 6 con `CCS-001` como consolidacion oficial de contratos, modelos, eventos y dependencias.

## ENG-005 Integration Engine

Documentos oficiales:

- `architecture/01-specs/SPEC_Fase_4_ENG-005_Integration_Engine_v1.0.md`
- `architecture/03-blueprints/Fase 4/D12-Integration Engine/D-012_Integration_Engine_Consolidado.md`
- `architecture/03-blueprints/Fase 4/README_ENG-005_Integration_Engine.md`

Estado para implementacion: usable directamente durante Fase 6, complementado por `CCS-001`.

---

# 5. Stack tecnologico aprobado

El stack tecnologico oficial esta definido por `architecture/08-technology/ADR-T001-Technology-Stack-v1.0.md`.

Stack aprobado:

- Python 3.13+.
- FastAPI.
- Uvicorn.
- Pydantic v2.
- PostgreSQL 17.
- SQLAlchemy 2.x.
- Alembic.
- Pydantic Settings.
- Pytest.
- Black.
- Ruff.
- mypy.
- OpenAPI.
- Swagger UI.
- Docker.
- Docker Compose.
- Structlog.
- Python Logging.
- Arquitectura de IA provider-agnostic con proveedor inicial OpenAI-compatible.
- n8n como integracion externa para automatizacion cuando corresponda.

Restriccion: la tecnologia nunca reemplaza ni modifica la arquitectura.

---

# 6. Orden recomendado de implementacion

El orden recomendado para Fase 6 es:

1. Preparacion del proyecto base usando el stack aprobado.
2. Configuracion de calidad, pruebas, logging y settings.
3. Implementacion de contratos publicos iniciales definidos por `CCS-001` y requeridos por `SPEC-VS001`.
4. Implementacion del Vertical Slice 1.
5. Validacion de limites entre ENG-001, ENG-002 y ENG-003.
6. Registro de eventos requeridos por `SPEC-VS001` y `CCS-001`.
7. Persistencia minima requerida por `SPEC-VS001`.
8. Extension controlada hacia ENG-004 Automation Engine cuando exista una Business Decision que requiera ejecucion.
9. Extension controlada hacia ENG-005 Integration Engine cuando exista necesidad de comunicacion externa.
10. Validacion de Definition of Done.

Este orden no modifica el Roadmap. Solo operacionaliza la Fase 6 de acuerdo con la arquitectura certificada.

---

# 7. Vertical Slice 1

El primer Vertical Slice oficial esta definido por:

- `architecture/01-specs/Implementation/SPEC-VS001-First-Vertical-Slice-v1.0.md`

Objetivo del VS1:

- Validar el flujo minimo del Nucleo Cognitivo.
- Procesar un mensaje textual mediante canal HTTP simulado.
- Utilizar Conversation Engine, Business Brain y Knowledge Engine.
- Responder con conocimiento oficial.
- Registrar eventos minimos.
- Evitar dependencia inicial de WhatsApp, Automation Engine e Integration Engine.

VS1 no reemplaza la implementacion completa del Core. Es el primer mecanismo de validacion incremental.

---

# 8. Convenciones generales de desarrollo

Las convenciones de desarrollo deben respetar la AKB y el stack aprobado.

Convenciones obligatorias:

- El codigo debe respetar los limites de Engines.
- La API no debe contener logica de negocio.
- La infraestructura no debe gobernar el dominio.
- Los Engines colaboran mediante contratos publicos.
- Ningun Engine modifica objetos internos de otro Engine.
- Ningun Engine accede directamente a sistemas externos salvo Integration Engine.
- Business Brain es el unico responsable de decisiones de negocio.
- Automation Engine ejecuta, no decide.
- Conversation Engine comunica, no decide.
- Knowledge Engine conoce, no decide.
- Integration Engine conecta, no decide negocio.
- La IA no modifica directamente el dominio.
- La configuracion debe usar variables de entorno y Pydantic Settings.
- Las pruebas deben validar comportamiento y limites arquitectonicos.

---

# 9. Definition of Done

Un incremento de implementacion se considera terminado cuando:

- Cumple el documento SPEC aplicable.
- Respeta `CAB-001`, `AGR-001`, `CCS-001` y `ADR-T001`.
- Mantiene los limites de Engines.
- Usa contratos publicos del Core.
- No introduce nuevos conceptos arquitectonicos sin gobernanza.
- No acopla el Core a proveedores externos.
- Incluye pruebas automatizadas suficientes para el comportamiento implementado.
- Incluye validaciones de limites arquitectonicos cuando corresponda.
- Registra eventos requeridos por la SPEC aplicable.
- Mantiene calidad mediante Black, Ruff y mypy.
- Puede ejecutarse mediante el entorno aprobado para desarrollo.
- No rompe Vertical Slices previamente aceptados.

---

# 10. Validacion de Engine SPEC

Resultado de validacion para Fase 6:

| Engine | Fuente oficial principal | Estado |
|--------|--------------------------|--------|
| ENG-001 Business Brain | SPEC Fase 3 + Blueprint D-008 + CCS-001 | Usable directamente |
| ENG-002 Conversation Engine | SPEC Fase 3 + Blueprint D-009 + CCS-001 | Usable directamente |
| ENG-003 Knowledge Engine | SPEC Fase 3 + Blueprint D-010 + CCS-001 | Usable directamente |
| ENG-004 Automation Engine | ADR-008 + Blueprint D-011 + CCS-001 | Usable durante Fase 6 |
| ENG-005 Integration Engine | SPEC Fase 4 + Blueprint D-012 + CCS-001 | Usable directamente |

Nota operativa: para ENG-004, la fuente implementable diaria debe combinar D-011, ADR-008 y CCS-001, dado que no existe un archivo independiente en `01-specs` equivalente al de ENG-005. Fase 5 certifica el Core completo y autoriza su implementacion.

---

# 11. Riesgos de implementacion conocidos

Riesgos que permanecen durante Fase 6:

- Interpretar los contratos de forma distinta entre Engines.
- Convertir Business Brain en wrapper de IA.
- Permitir que Conversation Engine o Knowledge Engine tomen decisiones.
- Saltar Integration Engine para acceder a proveedores externos.
- Confundir Automation Engine con Integration Engine.
- Acoplar temprano el Core a WhatsApp u otro proveedor.
- Tratar eventos tecnicos como eventos de dominio.
- Implementar mas alcance que el definido por el Vertical Slice activo.

Estos riesgos deben gestionarse mediante revisiones de implementacion, pruebas y cumplimiento de `AGR-001`.

---

# 12. Referencias documentales

## Governance

- `architecture/00-governance/D-000_Constitucion_Arquitectonica_BotWA.md`
- `architecture/00-governance/D-001_Constitucion_de_BotWA_v1.0.md`
- `architecture/00-governance/D-002_Metodologia_de_Desarrollo_v1.0.md`
- `architecture/00-governance/CAB-001_Core_Architecture_Baseline_v1.0.md`
- `architecture/00-governance/AGR-001_Architecture_Governance_Rules_v1.0.md`
- `architecture/00-governance/CTO-RES-001_Architecture_Freeze_Authorization.md`

## Roadmap

- `architecture/Roadmap_v2.0.md`

## Core Consolidation

- `architecture/05-core/standards/CCS-001_Core_Consolidation_Standard_v1.0.md`

## Architecture Review and Handoff

- `architecture/09-architecture rewiev/DCS-001_Documentation_Consolidation_Standard_v1.0.md`
- `architecture/09-architecture rewiev/AHP-001_Architecture_Handoff_Package_v1.0.md`
- `architecture/09-architecture rewiev/GATE-001_Implementation_Gate_Review_v1.0.md`
- `architecture/09-architecture rewiev/CERT-001_Core_Certification_v1.0.md`

## SPECs

- `architecture/01-specs/BotWA_Master_SPEC_v0.2.md`
- `architecture/01-specs/SPEC_Fase_3_v1.0_Nucleo_Cognitivo_BotWA.md`
- `architecture/01-specs/SPEC_Fase_4_ENG-005_Integration_Engine_v1.0.md`
- `architecture/01-specs/Implementation/SPEC-VS001-First-Vertical-Slice-v1.0.md`

## Technology

- `architecture/08-technology/ADR-T001-Technology-Stack-v1.0.md`

---

# 13. Resultado

BotWA Starter queda preparado para iniciar la Fase 6 - Core Implementation utilizando este documento como guia maestra de implementacion y la AKB como Source of Truth.

**Estado final:** READY FOR IMPLEMENTATION
