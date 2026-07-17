# D-012-04 – Integration Gateway

**Proyecto:** BotWA Starter
**Documento:** D-012 – Integration Engine
**Capítulo:** 04 – Integration Gateway
**Engine ID:** ENG-005
**Versión:** 1.0
**Estado:** Aprobado

## Objetivo
Definir el componente responsable de recibir todas las solicitudes provenientes del Core de BotWA.

## Definición
El Integration Gateway constituye el punto oficial de entrada al Integration Engine.

## Responsabilidad Principal
Validar, normalizar y aceptar solicitudes de integración antes del proceso de resolución del proveedor.

## Entradas
- Integration Request

## Salida
- Validated Integration Request

## Es responsable de
- Validar contratos.
- Verificar integridad.
- Rechazar solicitudes inválidas.
- Registrar el inicio de la integración.
- Preparar la solicitud para el Provider Resolver.

## No es responsable de
- Seleccionar proveedores.
- Ejecutar llamadas externas.
- Transformar protocolos.
- Interpretar reglas de negocio.
- Ejecutar automatizaciones.

## Principios Arquitectónicos
- Toda integración comienza aquí.
- Ninguna solicitud llega directamente al Provider Resolver.
- Todo contrato debe validarse.

## CTO Review
El Integration Gateway protege al Integration Engine de solicitudes inconsistentes y fortalece su gobernanza.
