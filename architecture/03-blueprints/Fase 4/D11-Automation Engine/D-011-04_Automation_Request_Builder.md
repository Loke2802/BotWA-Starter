# D-011-04 – Automation Request Builder

**Proyecto:** BotWA Starter  
**Documento:** D-011 – Automation Engine  
**Capítulo:** 04 – Automation Request Builder  
**Engine ID:** ENG-004  
**Versión:** 1.0  
**Estado:** Aprobado

# Objetivo

Definir el componente responsable de transformar una Business Decision en una solicitud de automatización estandarizada.

# Definición

El Automation Request Builder constituye el punto de entrada del Automation Engine y construye el objeto **Automation Request**.

# Responsabilidad Principal

Convertir decisiones del negocio en solicitudes de automatización consistentes e independientes de la tecnología.

# Entradas

- Business Decision
- Business Context
- Business Action Plan

# Salida

- Automation Request

# Validaciones

- Business Decision válida.
- Business Action Plan disponible.
- Información mínima completa.
- Consistencia del contrato.

# Principios Arquitectónicos

- No modifica Business Decision.
- No interpreta reglas de negocio.
- No consulta conocimiento.
- No ejecuta procesos.

# Resultado

Garantiza que todas las automatizaciones comiencen con un contrato uniforme.

# CTO Review

El Automation Request Builder desacopla al Business Brain del Automation Engine mediante contratos explícitos.
