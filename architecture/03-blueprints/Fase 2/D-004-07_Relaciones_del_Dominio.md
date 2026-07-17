# D-004-07 – Relaciones del Dominio

**Proyecto:** BotWA Starter
**Documento:** Modelo de Dominio
**Capítulo:** 07 – Relaciones del Dominio
**Versión:** 1.0
**Estado:** Aprobado

# Objetivo

Definir cómo se relacionan los conceptos principales del dominio de BotWA Starter.

## Relaciones Principales

### Empresa → Cliente
Una Empresa mantiene relación con múltiples Clientes.

### Cliente → Conversación
Un Cliente puede iniciar múltiples Conversaciones.

### Conversación → Caso de Negocio
Una Conversación puede contener uno o varios Casos de Negocio.

### Caso de Negocio → Acción
Todo Caso genera una o más Acciones.

### Caso de Negocio → Evento
Todo cambio importante genera Eventos de Dominio.

### Caso de Negocio → Resultado
Todo Caso concluye con un único Resultado.

### Empresa → Conocimiento
La Empresa es propietaria del conocimiento.

### Empresa → Agentes IA
Una Empresa puede tener uno o varios Agentes IA.

### Empresa → Canales
Una Empresa puede operar mediante múltiples Canales.

### Empresa → Automatizaciones
Cada Empresa define sus Automatizaciones.

# Business Brain

El Business Brain es un Servicio de Dominio.

No es una Entidad.

Su responsabilidad es coordinar entidades y aplicar las reglas del negocio.

# Regla Arquitectónica

Las Entidades se relacionan entre sí.

Los Servicios de Dominio coordinan el comportamiento entre ellas.

# CTO Review

El Modelo de Dominio deja de ser una colección de conceptos y pasa a convertirse en una red coherente de relaciones de negocio.
