# D-012-06 – Integration Adapter

**Proyecto:** BotWA Starter
**Engine ID:** ENG-005
**Estado:** Aprobado

## Objetivo
Traducir contratos internos al protocolo del proveedor y normalizar las respuestas.

## Responsabilidad Principal
Traducir la comunicación entre BotWA y sistemas externos.

## Entradas
- Provider Context
- Validated Integration Request

## Salidas
- Provider Request
- Canonical Integration Response

## Principios
- Un Adapter por proveedor.
- Sin lógica de negocio.
- Los cambios tecnológicos afectan solo al Adapter.

## CTO Review
Principal mecanismo de aislamiento tecnológico de BotWA.
