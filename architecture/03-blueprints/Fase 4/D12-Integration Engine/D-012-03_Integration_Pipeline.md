# D-012-03 – Integration Pipeline

**Estado:** Aprobado

Integration Request
→ Integration Gateway
→ Provider Resolver
→ Integration Adapter
→ External System
→ Response Normalizer
→ Integration Response

## Principios
- Todo acceso externo pasa por el Integration Engine.
- El Provider Resolver selecciona el proveedor según la configuración del negocio.
- Todo proveedor utiliza un Integration Adapter.
- Toda respuesta se normaliza antes de volver al Core.

## CTO Review
El Integration Pipeline desacopla el Core de cualquier proveedor tecnológico.
