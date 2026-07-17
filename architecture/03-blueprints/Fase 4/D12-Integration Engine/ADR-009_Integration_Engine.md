# ADR-009 – Integration Engine

**Estado:** Aprobado

## Contexto
BotWA debe comunicarse con múltiples proveedores sin acoplar el Core.

## Decisión
Crear un Integration Engine independiente.

## Responsabilidades
- Resolver proveedores.
- Adaptar protocolos.
- Ejecutar integraciones.
- Normalizar respuestas.
- Publicar eventos.

## Consecuencias
### Positivas
- Desacoplamiento tecnológico.
- Proveedores reemplazables.
- Escalabilidad.

### Negativas
- Mayor cantidad de adaptadores.
- Mayor complejidad operativa.
