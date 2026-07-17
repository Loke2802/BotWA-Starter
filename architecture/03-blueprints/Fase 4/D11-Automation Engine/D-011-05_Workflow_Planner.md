# D-011-05 – Workflow Planner

**Proyecto:** BotWA Starter  
**Documento:** D-011 – Automation Engine  
**Capítulo:** 05 – Workflow Planner  
**Engine ID:** ENG-004  
**Versión:** 1.0  
**Estado:** Aprobado

## Objetivo
Definir el componente responsable de transformar un Automation Request en un Execution Plan.

## Definición
El Workflow Planner construye el plan de ejecución del Automation Engine.

## Responsabilidad Principal
Diseñar el plan de ejecución sin ejecutar ninguna tarea.

## Entradas
- Automation Request

## Salida
- Execution Plan

## El Execution Plan define
- Tareas
- Orden de ejecución
- Dependencias
- Ejecución secuencial o paralela
- Políticas de reintento
- Condiciones de finalización

## No es responsable de
- Ejecutar tareas
- Tomar decisiones
- Consultar conocimiento
- Comunicarse con sistemas externos
- Registrar resultados

## Principios Arquitectónicos
- Todo workflow nace de un Automation Request.
- El plan es declarativo.
- El Workflow Planner prepara la ejecución, pero no la ejecuta.

## CTO Review
El Workflow Planner separa la planificación de la ejecución para mantener procesos consistentes y auditables.
