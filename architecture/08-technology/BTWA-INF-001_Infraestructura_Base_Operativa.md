# BTWA-INF-001

# Infraestructura Base Operativa de BotWA

**Proyecto:** BotWA\
**Fecha:** 17/07/2026\
**Estado:** COMPLETADO\
**Chat responsable:** DevOps e Infraestructura

------------------------------------------------------------------------

# Objetivo

Dejar completamente operativo el entorno de desarrollo e integración
necesario para comenzar la implementación de BotWA.

Este documento **NO** describe lógica de negocio ni implementación.
Únicamente registra el estado de la infraestructura.

------------------------------------------------------------------------

# Componentes instalados

## Control de versiones

-   Git
-   GitHub

**Estado:** ✅ Operativo

## Desarrollo

-   Python 3.13
-   OpenCode

**Estado:** ✅ Operativo

## Virtualización

-   WSL2
-   Docker Desktop
-   Docker Compose

**Estado:** ✅ Operativo

## Base de datos

-   PostgreSQL 17

**Estado:** ✅ Operativo

## Backend

-   FastAPI

**Estado:** ✅ Operativo

Validaciones realizadas: - Swagger - Docker - API inicial

## Migraciones

-   Alembic

**Estado:** ✅ Operativo

## Configuración

-   Pydantic Settings
-   Archivo `.env`

**Estado:** ✅ Operativo

## Logging

-   Structlog

**Estado:** ✅ Operativo

------------------------------------------------------------------------

# Variables de entorno

La aplicación utiliza un archivo `.env`.

Variables principales:

-   BOTWA_APP_NAME
-   BOTWA_ENVIRONMENT
-   BOTWA_LOG_LEVEL
-   BOTWA_API_VERSION
-   BOTWA_DATABASE_URL
-   BOTWA_WHATSAPP_ACCESS_TOKEN
-   BOTWA_WHATSAPP_PHONE_NUMBER_ID
-   BOTWA_WHATSAPP_WEBHOOK_VERIFY_TOKEN
-   BOTWA_WHATSAPP_API_VERSION

**Estado:** ✅ Docker recibe correctamente todas las variables.

------------------------------------------------------------------------

# WhatsApp Cloud API

Configurado:

-   Meta Developers
-   WhatsApp Cloud API
-   Número de prueba
-   Phone Number ID
-   Access Token

**Estado:** ✅ Operativo

------------------------------------------------------------------------

# Cloudflare Tunnel

Software: `cloudflared`

Modo utilizado: **Quick Tunnel**

**Estado:** ✅ Operativo

------------------------------------------------------------------------

# Webhook

Endpoints:

``` text
GET /webhooks/whatsapp
POST /webhooks/whatsapp
```

**Estado:** ✅ Verificado correctamente por Meta.

Validación:

-   HTTP 200 OK

------------------------------------------------------------------------

# Suscripciones Meta

Campo:

-   `messages`

**Estado:** ✅ Suscrito

------------------------------------------------------------------------

# Arquitectura de infraestructura

``` text
WhatsApp Cloud API
        │
        ▼
Meta Developers
        │
        ▼
Cloudflare Tunnel
        │
        ▼
FastAPI
        │
        ▼
BotWA
        │
        ▼
PostgreSQL
```

------------------------------------------------------------------------

# Alcance

Este documento certifica únicamente la infraestructura.

No implica que BotWA esté implementado.

La implementación funcional (casos de uso, servicios, adaptadores,
agentes, persistencia y lógica de negocio) continuará en el chat de
desarrollo.

------------------------------------------------------------------------

# Estado Final

## ✅ Infraestructura Base BotWA OPERATIVA

A partir de este punto puede iniciarse la implementación del producto.

------------------------------------------------------------------------

# Contexto para el chat de implementación

La infraestructura del proyecto ya fue instalada, configurada y
validada.

No es necesario volver a configurar:

-   Docker
-   PostgreSQL
-   FastAPI
-   Cloudflare Tunnel
-   Meta Developers
-   WhatsApp Cloud API

Todo lo relacionado con infraestructura debe considerarse operativo.

El trabajo del chat de implementación debe centrarse exclusivamente en
desarrollar BotWA utilizando esta base ya preparada.
