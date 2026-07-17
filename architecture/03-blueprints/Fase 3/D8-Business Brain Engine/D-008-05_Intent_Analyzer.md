# D-008-05 – Intent Analyzer

Proyecto: BotWA Starter
Documento: D-008 – Business Brain Engine
Engine ID: ENG-001
Versión: 1.0
Estado: Aprobado

## Objetivo
Transformar el Business Context en un Business Intent normalizado.

## Responsabilidad
Responder: ¿Qué quiere lograr realmente el cliente?

## Entradas
- Business Context

## Salida
- Business Intent

## Business Intent
Representa el objetivo de negocio identificado (reservar, reprogramar, cancelar, comprar, reclamar, etc.).

## Principios
- No interpreta lenguaje directamente.
- No aplica reglas.
- No toma decisiones.
- Puede apoyarse en IA para resolver ambigüedades.

## Regla Arquitectónica
Solo el Intent Analyzer puede generar un Business Intent.

## CTO Review
Separar el contexto de la intención desacopla el lenguaje humano del dominio del negocio.
