# D-010-04 – Knowledge Sources

**Proyecto:** BotWA Starter
**Documento:** D-010 – Knowledge Engine
**Engine ID:** ENG-003
**Versión:** 1.0
**Estado:** Aprobado

## Objetivo
Definir las fuentes oficiales de conocimiento administradas por el Knowledge Engine.

## Tipos de fuentes
- Documentales (PDF, Word, Excel)
- Sistemas empresariales (CRM, ERP, POS)
- Bases de datos
- APIs
- Plataformas de conocimiento (Notion, SharePoint, Google Drive)
- Sitios web
- Conocimiento humano

## Metadatos mínimos
- Source ID
- Nombre
- Tipo
- Responsable
- Fecha de actualización
- Nivel de confianza
- Estado
- Política de retención

## Ciclo de vida
Activa → En revisión → En cuarentena → Archivada → Eliminada

## Principios
- Identificable
- Auditada
- Versionable
- Trazable
- Gobernable

## Regla Arquitectónica
Todo acceso al conocimiento deberá realizarse exclusivamente mediante el Knowledge Engine.

## CTO Review
BotWA administra un ecosistema de fuentes de conocimiento, no únicamente documentos.
