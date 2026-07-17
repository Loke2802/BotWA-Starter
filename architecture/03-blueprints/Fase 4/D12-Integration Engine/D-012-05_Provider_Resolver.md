# D-012-05 – Provider Resolver

**Proyecto:** BotWA Starter
**Engine ID:** ENG-005
**Estado:** Aprobado

## Objetivo
Seleccionar el proveedor externo adecuado según la configuración del tenant.

## Responsabilidad Principal
Resolver el proveedor que ejecutará la integración.

## Entradas
- Validated Integration Request

## Salida
- Provider Context

## Es responsable de
- Identificar la capacidad solicitada.
- Consultar la configuración del tenant.
- Seleccionar el proveedor.
- Aplicar políticas de fallback.
- Preparar el contexto para el Integration Adapter.

## No es responsable de
- Ejecutar llamadas externas.
- Traducir protocolos.
- Tomar decisiones de negocio.

## CTO Review
Materializa el principio provider-agnostic de BotWA.
