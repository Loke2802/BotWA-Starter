# D-004-02 – Lenguaje Ubicuo

**Proyecto:** BotWA Starter
**Documento:** Modelo de Dominio
**Capítulo:** 02 – Lenguaje Ubicuo
**Versión:** 1.0
**Estado:** Aprobado

# Objetivo

Definir el lenguaje oficial de BotWA Starter para que negocio, arquitectura, desarrollo y OpenCode utilicen exactamente los mismos conceptos.

## Principios

- Un concepto = un significado.
- Sin sinónimos dentro del dominio.
- El lenguaje es la referencia oficial del proyecto.

## Conceptos

### Empresa
Organización que utiliza BotWA y es propietaria de su configuración, conocimiento y reglas.

### Cliente
Persona que interactúa con la empresa mediante uno o más canales.

### Conversación
Secuencia de interacciones. Es el medio de comunicación, no el objetivo.

### Caso de Negocio
Concepto central del dominio. Representa el objetivo que el cliente desea resolver.

### Business Brain
Servicio de Dominio que analiza el contexto y decide la estrategia.

### Agente IA
Genera lenguaje natural a partir de las decisiones del Business Brain.

### Conocimiento
Información oficial del negocio.

### Acción
Actividad ejecutada para avanzar un Caso de Negocio.

### Resultado
Estado final alcanzado por un Caso de Negocio.

### Canal
Medio de interacción entre cliente y empresa.

## Regla Fundamental

BotWA administra Casos de Negocio utilizando conversaciones como medio de interacción.

## Decisión Arquitectónica

Todo documento y componente deberá utilizar este Lenguaje Ubicuo.

## CTO Review

Antes de crear una nueva entidad o servicio, deberá verificarse si el concepto ya existe en este lenguaje.
