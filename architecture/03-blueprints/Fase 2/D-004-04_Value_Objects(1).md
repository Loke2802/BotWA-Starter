# D-004-04 – Value Objects

**Proyecto:** BotWA Starter
**Documento:** Modelo de Dominio
**Capítulo:** 04 – Value Objects
**Versión:** 1.0
**Estado:** Aprobado

# Objetivo

Definir los Value Objects del dominio de BotWA Starter y explicar su propósito.

## ¿Qué es un Value Object?

Un Value Object representa un concepto del negocio cuyo valor es más importante que su identidad.

Características:

- No posee identidad propia.
- Se compara por su valor.
- Es reutilizable.
- Expresa reglas del negocio.
- Mantiene el dominio limpio.

## Value Objects

### Objetivo del Caso
Describe el propósito que el Cliente desea alcanzar.

### Estado del Caso
Estados propuestos:
- NUEVO
- EN_ANALISIS
- EN_PROGRESO
- ESPERANDO_CLIENTE
- ESPERANDO_NEGOCIO
- EN_SEGUIMIENTO
- ESCALADO
- RESUELTO
- CANCELADO

### Resultado del Caso
Describe cómo terminó un Caso de Negocio.

### Contexto Conversacional
Información relevante para comprender el estado actual de la conversación.

### Identidad Externa
Canal + Identificador Externo.

### Periodo de Seguimiento
Define cuándo debe realizarse una acción de seguimiento.

### Prioridad
BAJA, NORMAL, ALTA y CRÍTICA.

### Resultado de Acción
Éxito, Pendiente, Requiere intervención humana o Error controlado.

## Principios

Un Value Object existe para representar un concepto del negocio o proteger una regla del dominio.

## Decisión Arquitectónica

Los Value Objects encapsulan información del dominio sin convertirse en entidades.

## CTO Review

Si un concepto no necesita identidad propia, probablemente deba modelarse como un Value Object y no como una Entidad.
