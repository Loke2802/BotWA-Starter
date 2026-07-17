# D-007-04 – Responsabilidades de un Engine

Proyecto: BotWA Starter
Documento: D-007 – Estándar de Blueprints
Capítulo: 04
Versión: 1.0
Estado: Aprobado

## Objetivo
Definir las responsabilidades permitidas y los límites de cada Engine.

## Principios
- Una responsabilidad principal por Engine.
- Alta cohesión.
- Bajo acoplamiento.

## Puede
- Aplicar reglas del negocio.
- Orquestar procesos.
- Consumir y publicar Eventos de Dominio.
- Colaborar mediante interfaces definidas.

## No puede
- Invadir otros Engines.
- Depender de proveedores.
- Saltarse el Modelo de Dominio.
- Acceder directamente a infraestructura cuando exista un Integration Engine.

## Quality Checklist
- Responsabilidad única.
- Límites claros.
- Independencia.
- Alineación con el Dominio.
- Evolución independiente.

## CTO Review
Los Engines se dividen por responsabilidad del negocio, nunca por tecnología.
