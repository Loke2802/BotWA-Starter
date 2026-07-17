# ADR-T001 - Technology Stack v1.0

## BotWA Starter

**Status:** APPROVED

## Purpose

This document defines the official technology stack approved for BotWA
Starter.

## Backend

-   Language: Python 3.13+
-   Framework: FastAPI
-   ASGI Server: Uvicorn

## Data Validation

-   Pydantic v2

## Database

-   PostgreSQL 17

## ORM

-   SQLAlchemy 2.x

## Database Migrations

-   Alembic

## Configuration

-   Pydantic Settings
-   Environment variables only

## Testing

-   Pytest

## Code Quality

-   Formatter: Black
-   Linter: Ruff
-   Static Type Checking: mypy

## API Documentation

-   OpenAPI
-   Swagger UI

## Version Control

-   Git
-   GitHub

## Containers

-   Docker
-   Docker Compose

## Artificial Intelligence

-   Provider-agnostic architecture
-   Initial provider: OpenAI-compatible

## Automation

-   n8n (external integration)

## Logging

-   Structlog
-   Python Logging

## Architecture Rules

Technology never overrides architecture.

Respect: - Constitution - Master SPEC - ADRs - Blueprints - Canonical
Models - Engine Contracts

## Initial Scope

Out of scope for the first Vertical Slice:

-   WhatsApp integration
-   Redis
-   RabbitMQ
-   Kafka
-   Advanced conversation memory
-   External integrations
-   Automation workflows

## Approval Summary

-   Language: APPROVED
-   Backend Framework: APPROVED
-   Database: APPROVED
-   ORM: APPROVED
-   Migration Tool: APPROVED
-   Configuration: APPROVED
-   Testing: APPROVED
-   Containers: APPROVED
-   Automation: APPROVED
