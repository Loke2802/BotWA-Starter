# D-011-06 – Task Orchestrator

**Proyecto:** BotWA Starter
**Documento:** D-011 – Automation Engine
**Capítulo:** 06 – Task Orchestrator
**Engine ID:** ENG-004
**Versión:** 1.0
**Estado:** Aprobado

## Objetivo
Definir el componente responsable de coordinar la ejecución del Execution Plan.

## Definición
El Task Orchestrator dirige la ejecución del workflow definido por el Workflow Planner sin alterar el plan original.

## Responsabilidad Principal
Ejecutar el Execution Plan de forma ordenada y controlada.

## Entradas
- Execution Plan

## Salida
- Execution Status

## Es responsable de
- Iniciar tareas.
- Coordinar la secuencia de ejecución.
- Gestionar dependencias.
- Ejecutar procesos paralelos.
- Detectar bloqueos.
- Informar el estado de ejecución.

## No es responsable de
- Diseñar workflows.
- Modificar el Execution Plan.
- Tomar decisiones de negocio.
- Consultar conocimiento.
- Comunicarse directamente con sistemas externos.

## Principios Arquitectónicos
- Toda ejecución sigue un Execution Plan.
- Ninguna tarea se ejecuta fuera del plan.
- Coordina; no decide.
- Mantiene el estado de ejecución actualizado.

## CTO Review
El Task Orchestrator es el corazón operativo del Automation Engine, garantizando una ejecución consistente y trazable.
