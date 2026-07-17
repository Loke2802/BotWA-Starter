# D-001 – Arquitectura Funcional

**Proyecto:** BotWA Starter  
**Documento:** Arquitectura Funcional  
**Código:** D-001  
**Versión:** 1.0  
**Estado:** Aprobado  
**Fase:** 1 – Arquitectura Funcional

---

## 1. Objetivo

Definir la arquitectura funcional de BotWA Starter, estableciendo las capacidades estratégicas, sus responsabilidades, límites y reglas de colaboración.

---

## 2. Principios de la Arquitectura Funcional

- Orientación a objetivos de negocio.
- Capacidades antes que módulos.
- Responsabilidad única.
- Colaboración entre capacidades.
- Independencia tecnológica.
- Source of Truth.
- La IA potencia las capacidades, no gobierna el negocio.

---

## 3. Capability Map

1. Gestión Conversacional
2. Gestión de Decisiones (Business Brain)
3. Gestión del Conocimiento
4. Gestión Comercial
5. Gestión de Automatizaciones
6. Gestión Analítica
7. Administración de la Plataforma

---

## 4. Resumen de Capacidades

### Gestión Conversacional
Comprende la intención, mantiene el contexto, utiliza memoria conversacional y comunica las respuestas.

### Gestión de Decisiones (Business Brain)
Analiza el contexto, selecciona estrategias y orquesta el resto de capacidades.

### Gestión del Conocimiento
Entrega información oficial del negocio desde una Source of Truth.

### Gestión Comercial
Convierte conversaciones en oportunidades de negocio y busca no perder ventas.

### Gestión de Automatizaciones
Ejecuta seguimientos, recordatorios y procesos automáticos derivados de decisiones.

### Gestión Analítica
Convierte datos en métricas, insights y recomendaciones para el negocio.

### Administración de la Plataforma
Gestiona empresas, usuarios, canales, agentes IA, servicios externos, configuración y seguridad.

---

## 5. Flujo Funcional General

Cliente

↓

Gestión Conversacional

↓

Business Brain

↓

Gestión del Conocimiento

↓

Business Brain

↓

Gestión Comercial / Automatizaciones

↓

Gestión Conversacional

↓

Cliente

↓

Gestión Analítica

---

## 6. Ciclo de Vida de una Conversación

Estados:

- Nueva
- Comprendiendo
- Analizando
- Ejecutando
- Esperando
- Seguimiento
- Escalada
- Finalizada
- Pausada
- Reabierta
- Cancelada

---

## 7. Reglas de Colaboración

- El Business Brain siempre orquesta.
- Gestión Conversacional nunca decide.
- Gestión del Conocimiento nunca interpreta.
- Gestión Comercial nunca conversa directamente.
- Automatizaciones ejecutan decisiones.
- Analítica mide, no modifica procesos.
- Administración configura, no redefine la lógica.
- La memoria conversacional pertenece a BotWA.

---

## 8. Principios Inmutables

1. El Business Brain siempre orquesta.
2. La IA comunica, no gobierna el negocio.
3. El conocimiento pertenece al negocio.
4. El Core permanece estable.
5. BotWA piensa en objetivos.
6. La memoria conversacional es un activo estratégico.
7. La configuración prevalece sobre la programación.

---

## 9. Conclusión

Este documento constituye la referencia oficial de la Arquitectura Funcional de BotWA Starter y servirá como base para el Modelo de Dominio, los Blueprints, las Specifications y la implementación.

**Versión:** 1.0  
**Estado:** Aprobado
