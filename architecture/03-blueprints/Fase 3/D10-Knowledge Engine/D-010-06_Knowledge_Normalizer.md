# D-010-06 – Knowledge Normalizer

**Proyecto:** BotWA Starter
**Documento:** D-010 – Knowledge Engine
**Engine ID:** ENG-003
**Versión:** 1.0
**Estado:** Aprobado

## Objetivo
Transformar información recuperada desde distintas fuentes en un modelo canónico de conocimiento.

## Responsabilidad
Responder: ¿Cómo representamos este conocimiento de forma uniforme?

## Entradas
- Knowledge Items

## Salida
- Normalized Knowledge Item

## Responsabilidades
- Convertir formatos heterogéneos.
- Estandarizar nombres de campos.
- Unificar fechas, monedas y unidades.
- Eliminar ruido técnico.
- Mantener la trazabilidad de la fuente.

## Principios
- Determinístico.
- Reutilizable.
- Independiente del formato.
- Auditable.

## Regla Arquitectónica
Todo conocimiento deberá ajustarse al Canonical Knowledge Model antes de ser consumido por otros Engines.

## CTO Review
El Knowledge Normalizer desacopla completamente a BotWA de los formatos originales de las fuentes.
