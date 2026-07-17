# WP-001 – Foundation

**Versión:** 1.0
**Estado:** READY

## Objetivo
Construir la infraestructura base de BotWA.

## Incluye
- Repositorio
- FastAPI
- Docker / Docker Compose
- PostgreSQL
- SQLAlchemy
- Alembic
- Configuración
- Logging
- Endpoints `/health` y `/version`
- Testing base

## No incluye
- Engines
- Lógica de negocio
- IA

## Dependencias
- MS-001
- CAB-001
- AGR-001
- CCS-001
- ADR-T001

## Definition of Done
- Docker Compose levanta el proyecto.
- FastAPI operativo.
- PostgreSQL operativo.
- Migración inicial.
- Logging activo.
- Proyecto listo para WP-002.
