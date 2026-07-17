# D-002 – Arquitectura General

**Proyecto:** BotWA Starter  
**Documento:** Arquitectura General  
**Código:** D-002  
**Versión:** 1.0  
**Estado:** Aprobado  
**Fase:** 1 – Arquitectura Funcional

---

# Objetivo

Describir la arquitectura general de BotWA Starter desde una perspectiva funcional, mostrando cómo se organiza la plataforma y cómo colaboran sus principales capacidades.

Este documento complementa al D-001 y sirve como puente entre la Arquitectura Funcional y las siguientes fases de diseño.

---

# Alcance

Este documento describe:

- La organización general de BotWA Starter.
- Las capacidades estratégicas.
- Las relaciones entre capacidades.
- Los flujos principales.
- Los principios arquitectónicos.
- Las bases para la evolución del sistema.

No describe aspectos técnicos de implementación.

---

# Vista General

BotWA Starter es una plataforma orientada a ayudar a las MYPES a mejorar la comunicación con sus clientes mediante inteligencia artificial, automatización y una arquitectura basada en capacidades.

La plataforma está organizada alrededor de un núcleo de decisiones (Business Brain), el cual coordina el resto de capacidades funcionales.

---

# Arquitectura General

La plataforma está compuesta por siete capacidades estratégicas:

1. Gestión Conversacional.
2. Gestión de Decisiones (Business Brain).
3. Gestión del Conocimiento.
4. Gestión Comercial.
5. Gestión de Automatizaciones.
6. Gestión Analítica.
7. Administración de la Plataforma.

Cada capacidad posee una única responsabilidad y colabora con las demás mediante interfaces funcionales claramente definidas.

---

# Organización Funcional

## Gestión Conversacional
Responsable de comprender y comunicar.

## Gestión de Decisiones (Business Brain)
Responsable de analizar y decidir.

## Gestión del Conocimiento
Responsable de proporcionar información confiable.

## Gestión Comercial
Responsable de convertir conversaciones en oportunidades.

## Gestión de Automatizaciones
Responsable de ejecutar acciones automáticas.

## Gestión Analítica
Responsable de transformar datos en conocimiento para el negocio.

## Administración de la Plataforma
Responsable de la configuración, seguridad y operación del sistema.

---

# Flujo Principal

Cliente

↓

Gestión Conversacional

↓

Business Brain

↓

Consulta de Conocimiento

↓

Selección de Estrategia

↓

Ejecución

↓

Respuesta

↓

Análisis

↓

Aprendizaje

---

# Relaciones entre Capacidades

- El Business Brain orquesta.
- Gestión Conversacional comunica.
- Gestión del Conocimiento informa.
- Gestión Comercial ejecuta estrategias comerciales.
- Automatizaciones ejecutan procesos.
- Gestión Analítica mide resultados.
- Administración gobierna la plataforma.

Cada capacidad permanece desacoplada del resto.

---

# Dependencias

- Ninguna capacidad depende directamente de otra implementación.
- Los proveedores externos se consumen mediante adaptadores.
- El Core permanece independiente de tecnologías específicas.

---

# Principios Arquitectónicos

- Arquitectura basada en capacidades.
- Source of Truth.
- Responsabilidad única.
- Colaboración desacoplada.
- Configuración sobre programación.
- Core estable.
- Adaptadores reemplazables.
- IA como potenciador del negocio.
- Objetivos antes que respuestas.

---

# Evolución

La arquitectura ha sido diseñada para evolucionar sin modificar el Core.

Esta versión corresponde exclusivamente a **BotWA Starter**.

---

# Relación con otros documentos

Depende de:

- D-001 – Arquitectura Funcional.

Servirá de base para:

- Modelo de Dominio.
- Blueprints.
- Arquitectura Técnica.
- Specifications.
- Implementación en OpenCode.

---

# Conclusión

La Arquitectura General de BotWA Starter consolida la visión funcional del producto y establece una referencia de alto nivel para comprender la organización de la plataforma.

---

**Código:** D-002  
**Versión:** 1.0  
**Estado:** Aprobado
