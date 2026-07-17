# ADR-008 – Automation Engine

**Estado:** Aprobado

## Contexto

BotWA necesitaba un componente responsable de ejecutar procesos derivados de las decisiones del Business Brain sin mezclar lógica de negocio con ejecución.

## Decisión

Se adopta un Engine independiente denominado **Automation Engine**.

## Responsabilidades

- Orquestar workflows.
- Ejecutar procesos.
- Supervisar la ejecución.
- Publicar Business Events.

## Consecuencias

- Separación entre decisión y ejecución.
- Mayor trazabilidad.
- Mayor escalabilidad.
- Desacoplamiento del Core respecto a la tecnología de automatización.
