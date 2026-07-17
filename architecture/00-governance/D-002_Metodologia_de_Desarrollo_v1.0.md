# D-002 -- Metodología de Desarrollo

**Proyecto:** BotWA Starter\
**Documento:** Metodología de Desarrollo\
**Código:** D-002\
**Versión:** 1.0\
**Estado:** Aprobado\
**Fase:** 0 -- Product Vision

------------------------------------------------------------------------

# 1. Objetivo

Definir la metodología oficial mediante la cual se diseñará,
documentará, implementará y evolucionará BotWA Starter.

La arquitectura y la documentación preceden a la implementación. El
código es consecuencia del diseño.

# 2. Filosofía

BotWA Starter seguirá una metodología **Documentation First**.

-   Primero la visión.
-   Luego la arquitectura.
-   Después las especificaciones.
-   Finalmente la implementación.

# 3. Organización del Proyecto

## CEO / Product Owner

Responsable de: - Visión del producto. - Priorización. - Validación de
negocio. - Aprobación funcional.

## CTO

Responsable de: - Arquitectura. - Calidad técnica. - Especificaciones. -
Seguridad. - Escalabilidad. - Revisión técnica.

## OpenCode

Responsable de: - Implementar Specifications. - Generar código. - Crear
pruebas. - Refactorizar.

OpenCode implementa. No diseña arquitectura.

# 4. Flujo Oficial

``` text
Phase Planning
        ↓
Desarrollo de Entregables
        ↓
Revisión CTO
        ↓
Revisión CEO
        ↓
Aprobación
        ↓
Gate Review
        ↓
Cierre de Fase
```

# 5. Entregables

Cada fase producirá únicamente los artefactos necesarios.

Ejemplos:

-   ADR
-   Blueprint
-   Specification
-   Diagramas
-   Roadmaps
-   Reviews

# 6. Flujo de Ingeniería

``` text
Visión

↓

Arquitectura

↓

Modelo de Dominio

↓

Blueprint

↓

ADR

↓

Specification

↓

OpenCode

↓

Architecture Review

↓

Release
```

# 7. Definition of Ready (DoR)

Antes de implementar debe existir:

-   Blueprint aprobado.
-   ADR relacionados.
-   Specification aprobada.
-   Interfaces definidas.
-   Casos de uso.
-   Objetivo claro.

# 8. Definition of Done (DoD)

Un entregable está terminado cuando:

-   Cumple su objetivo.
-   Fue revisado por el CTO.
-   Fue aprobado por el CEO.
-   Tiene versión oficial.
-   Está archivado.

# 9. Versionado

Todos los documentos oficiales tendrán versión (v1.0, v1.1, v2.0...).

# 10. Reglas

1.  No avanzamos por tiempo, sino por entregables aprobados.
2.  No programamos ideas; programamos Specifications.
3.  La arquitectura gobierna la implementación.
4.  OpenCode implementa, no diseña.
5.  El Core debe permanecer estable.
6.  La documentación debe ser mínima, suficiente y útil.
7.  Toda decisión importante debe quedar documentada.

# 11. Calidad

Todo entregable será evaluado por:

-   Valor para la MYPE.
-   Calidad arquitectónica.
-   Claridad para OpenCode.
-   Mantenibilidad.

# 12. Cierre

Esta metodología constituye el estándar oficial de desarrollo de BotWA
Starter.

**Versión:** 1.0\
**Estado:** Aprobado
