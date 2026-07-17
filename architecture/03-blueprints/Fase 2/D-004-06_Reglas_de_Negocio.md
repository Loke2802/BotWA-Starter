# D-004-06 – Reglas de Negocio

**Proyecto:** BotWA Starter
**Documento:** Modelo de Dominio
**Capítulo:** 06 – Reglas de Negocio
**Versión:** 1.0
**Estado:** Aprobado

# Objetivo
Definir las reglas que gobiernan el comportamiento del dominio.

# Principios
Las reglas pertenecen al negocio, no a la tecnología.

# Reglas Fundamentales

1. Toda Conversación pertenece a una Empresa.
2. Toda Conversación pertenece a un Cliente.
3. Todo Caso pertenece a un Cliente y una Empresa.
4. Todo Caso posee un Objetivo.
5. Solo existe una estrategia activa por Caso.
6. Toda Acción pertenece a un Caso.
7. Toda decisión relevante genera un Evento de Dominio.
8. La IA nunca modifica directamente el dominio.
9. El conocimiento pertenece a la Empresa.
10. Todo Caso finaliza en un estado válido.

# Reglas de Evolución

11. El dominio nunca dependerá de un proveedor externo.
12. Las nuevas industrias reutilizarán el mismo dominio mediante configuración.

# Decisión Arquitectónica

El Business Brain es el único componente autorizado para modificar el estado del dominio.

# CTO Review

Las Reglas de Negocio son el contrato que protege la coherencia de BotWA. Toda modificación futura deberá registrarse mediante un ADR.
