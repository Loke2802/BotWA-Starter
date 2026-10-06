LURI-CTX-001 — Contexto maestro para ampliar Luri a CRM

Fecha: 06/10/2026 · Propietario: Angelo Echegaray · Versión: 1.0
Estado: requisitos funcionales y criterios de arquitectura confirmados en conversación; diseño técnico propuesto, sujeto a contraste con el código actual.

1. Objetivo y jerarquía

Kalivur es la empresa madre. Kalivur Marketing Pro es la unidad de servicios de marketing. Luri es el producto de agentes/asistentes IA y la empleada digital de Kalivur.

Ampliar Luri a un CRM comercial con atención multicanal, múltiples cuentas/números, intervención humana, oportunidades, proceso de venta, seguimiento y recompra. Debe servir a los negocios propios y a empresas clientes, con aislamiento y permisos por empresa.

Kalivur Marketing Pro es el primer piloto comercial propuesto: consulta → diagnóstico → propuesta → seguimiento → venta → renovación/recompra. El producto debe admitir otros negocios mediante configuración, sin reglas exclusivas de una agencia o clínica.

2. Base comprobada y límites de la evidencia

Repositorio identificado: https://github.com/Loke2802/BotWA-Starter. Rama de referencia: master.

En la revisión realizada el 06/10/2026 se consultó el commit 026ca10d3276ed06cb8f644549e807a684921f22, merge del PR #45. Incluye PR #44, integración de IA, y PR #45, capa de respuesta conversacional. La CI de ese SHA figura en success: https://github.com/Loke2802/BotWA-Starter/actions/runs/35693413985.

Base identificada: Python/FastAPI, SQLAlchemy/PostgreSQL, multiempresa, roles/permisos, conversaciones, conocimiento, integración WhatsApp y atención humana. El código revisado incorpora trabajos IA persistentes, adaptador OpenAI y respuesta conversacional con validación/fallback. Consultar el código para determinar el alcance concreto de cada capacidad.

Esto no prueba la versión actualmente desplegada, migración aplicada, flags activos, acceso real al modelo, calidad/latencia/costo ni entrega efectiva por WhatsApp. El estado de despliegue debe verificarse en el entorno autorizado. Tampoco acredita oportunidades, seguimiento y recompra ya implementados.

El documento LURI_DECISION_IA_PARA_GPT.md del 18/09 es anterior a PR #44/#45. Su afirmación de IA pendiente no describe el código posterior. Conservarlo como antecedente, sin usarlo como diagnóstico actual.

3. Requisitos confirmados por Angelo

ID

Requisito

Comportamiento esperado

CRM-01

Panel de conversaciones

Leer, responder y gestionar conversaciones desde una bandeja central.

CRM-02

Múltiples WhatsApp

Gestionar diversos números; identificar empresa y número de origen.

CRM-03

Atención multicanal

Contemplar WhatsApp, Facebook/Messenger, Instagram, TikTok, chat web y futuros canales.

CRM-04

Avance de clientes

Mostrar necesidades, oportunidades, etapa, responsable y próxima acción.

CRM-05

Potencial comercial

Clasificar intención de compra y conservar interesados sin intención actual.

CRM-06

Proceso de venta

Gestionar oportunidades desde consulta hasta cierre ganado/perdido.

CRM-07

Seguimiento

Actividades, recordatorios y pendientes; identificar falta de atención.

CRM-08

Recompra

Registrar compras e identificar próximas oportunidades de compra/renovación.

CRM-09

Criterio arquitectónico

Responsabilidades claras, base de datos consistente y recuperación ante fallos.

CRM-10

Código auditable

Módulos pequeños/cohesivos, cambios revisables y pruebas relevantes.

4. Panel y operación comercial

Bandeja propuesta: selector de empresa/cuenta/número; lista de conversaciones; historial y composición de respuesta; ficha lateral del cliente y su oportunidad. Mostrar claramente el canal/cuenta desde el que se responderá y los estados pendiente, enviado, fallido o incierto según evidencia real del transporte.

Filtros: empresa, canal, cuenta/número, responsable, atención Luri/humano, pendiente de respuesta, potencial de compra y etapa de oportunidad. Los permisos delimitan tanto resultados como contadores, búsquedas y exportaciones.

La vista general de Kalivur requiere permisos administrativos explícitos. No implica acceso universal por defecto a los datos de empresas clientes. Cada cliente ve únicamente los recursos autorizados de su empresa.

Una ficha reúne identidad, datos de contacto, etiquetas, necesidades, conversaciones, actividades, oportunidades y compras registradas. Un contacto puede tener múltiples conversaciones y oportunidades; no reemplazar su historial al iniciar una nueva venta.

5. Clasificaciones independientes

Valores iniciales propuestos, configurables por negocio y sujetos a revisión durante el diseño:

Dimensión

Valores iniciales

Potencial de compra

Sin evaluar; posible comprador; listo para comprar; sin intención actual; no encaja.

Etapa de oportunidad

Consulta nueva; necesidad identificada; oferta presentada; en decisión; ganada; perdida.

Atención

Pendiente; atiende Luri; atiende humano; esperando cliente; resuelta.

No fusionar estas dimensiones. “Sin intención actual” permite conservar una relación para más adelante; no debe cerrar automáticamente una oportunidad. Conversación resuelta no significa venta ganada. Venta ganada no significa pago recibido.

La IA puede sugerir potencial/etapa/resumen/próxima acción con razones y referencias al historial. Distinguir sugerencia de dato confirmado; la primera versión propone confirmación/corrección humana para cambios comerciales. No inventar porcentajes de probabilidad ni considerar una afirmación de pago del cliente como verificación.

6. Datos y fuentes de verdad

Modelo conceptual propuesto. Contrastar primero con entidades/migraciones existentes y reutilizarlas cuando corresponda; esta tabla no autoriza duplicar tablas.

Entidad

Responsabilidad y relación

Empresa

Ámbito de propiedad, configuración y permisos.

Cuenta de canal

Identidad externa/cuenta/número de una empresa y estado de conexión.

Contacto

Identidad comercial dentro de una empresa.

Identidad de contacto

Identificador verificado de un contacto en un canal/cuenta; conservar procedencia.

Conversación / mensaje

Canal/cuenta de origen, participantes, atención, historial y estados de transporte.

Oportunidad

Contacto, pipeline/etapa, productos/servicios, importe/moneda, responsable y cierre.

Actividad / tarea

Próxima acción, fecha, responsable, estado y vínculos con contacto/oportunidad.

Compra registrada

Evidencia, fecha, productos/servicios e importe; independiente de cobro.

Regla / tarea de recompra

Frecuencia o fecha sugerida, origen de regla, revisión humana y oportunidad vinculada.

Auditoría

Actor, cambio, recurso, fecha y correlación, sin secretos ni contenido privado innecesario.

PostgreSQL será la fuente de verdad propuesta para los datos propios del CRM. Definir claves foráneas, unicidad tenant-scoped, restricciones de estados y concurrencia. Usar importes decimales con moneda; fechas persistidas con zona y presentación en zona de la empresa.

Mantener el conocimiento publicado separado de las reglas del CRM y de los hechos de inventario/pago. Si se conecta un CRM/ERP externo, decidir la fuente de verdad por recurso, dirección de sincronización y conflictos en un ADR antes de implementar; evitar dos sistemas escribiendo el mismo dato sin autoridad definida.

Vincular identidades de diferentes canales solo con evidencia o confirmación autorizada. Nombre parecido no acredita identidad. No unir contactos de distintas empresas. Una unión dentro de empresa debe ser revisable, auditada y preservar historial.

7. Seguimiento, ventas y recompra

Cada oportunidad abierta debe mostrar responsable, próxima acción y fecha o motivo explícito para no tenerla. Registrar cambios de etapa, propuesta, objeciones, actividades y razón de cierre. Permitir varias oportunidades simultáneas sin sobrescribir el avance anterior.

Primera recompra propuesta: compra registrada → fecha/regla del negocio → tarea de revisión → contacto aprobado → nueva oportunidad. No asumir que todo negocio tiene la misma frecuencia ni que una compra autoriza mensajes promocionales.

Empezar con tareas y recordatorios visibles. Para automatizar mensajes, comprobar preferencias/consentimiento, reglas del canal, autorización, frecuencia y mecanismos de exclusión. Identificar mensajes administrativos y comerciales según su propósito real.

Informes propuestos: oportunidades por etapa/responsable/origen, tareas vencidas, tiempo de atención, ventas registradas y recompra. Definir denominadores, período y fuente; no confundir importes propuestos, vendidos y cobrados. No prometer atribución causal a campañas.

8. Arquitectura y extensibilidad

Conservar la arquitectura modular existente y ampliar sus límites con coherencia. Núcleo CRM independiente de canales y del modelo IA; adaptadores por proveedor; persistencia y clientes externos fuera de reglas de negocio.

Flujo propuesto: entrada del canal → validación de empresa/identidad/deduplicación → persistencia de conversación → atención humana o trabajo IA → resultado validado/sugerencia CRM → outbox → envío con estado comprobado. La autoridad sobre empresa, contacto, permisos y acciones pertenece al backend.

El panel usa contratos/API existentes o nuevos explícitos; no copia lógica comercial ni usa acceso directo a tablas. Implementar búsqueda, paginación y filtros tenant-scoped. Definir concurrencia de asignaciones/cambios de etapa para no perder actualizaciones.

Cada adaptador declara sus capacidades y restricciones: recibir, responder, iniciar contacto, adjuntos y estados de entrega. Mensajes directos y comentarios son capacidades distintas. Verificar documentación oficial, acceso de cuenta y permisos antes de comprometer cada integración, especialmente TikTok. No afirmar que un canal está implementado por existir un nombre en configuración.

WhatsApp es el primer recorrido completo propuesto; el diseño contempla los otros canales desde el inicio. No fijar aquí fechas de lanzamiento, APIs o capacidades no verificadas.

9. Fallos, diagnóstico y recuperación

Cada recorrido necesita un identificador de correlación y vínculos entre recepción, conversación, job, cambio CRM y salida. Logs estructurados con códigos de error, duraciones y estados; no registrar secretos ni conversaciones completas por defecto.

Fallo

Comportamiento requerido

IA falla/rechaza salida

Mantener entrada y evidencia; fallback seguro o atención humana; no inventar acciones.

Canal falla

Persistir estado y reintentar solo si es seguro; distinguir entrega incierta.

Evento repetido

Deduplicar por identidad externa/ámbito; evitar duplicar mensajes, oportunidades o tareas.

Reinicio de proceso

Recuperar trabajos persistidos y revalidar su vigencia antes de actuar.

Handoff activo

Suspender respuestas automáticas y evitar carreras con mensajes en vuelo.

Base de datos no disponible

No confirmar una escritura que no pudo persistirse; preservar reintento seguro según contrato.

Datos/fuentes cambian

Invalidar resultados obsoletos y reconstruir con las fuentes vigentes.

Actualización incompatible

Versionado, migración probada y rollback compatible; preservar datos.

Pérdida de datos

Respaldos y restauración probada, con RPO/RTO definidos según costo aceptado.

Reutilizar worker/cola/outbox actuales cuando sus garantías sean suficientes. No introducir servicios adicionales ni cambios de hosting sin necesidad, evidencia y costo. El límite daily_jobs del código revisado corresponde a 2 × slots; un turno conversacional puede usar cuatro llamadas. No equivale a conversaciones ni presupuesto monetario.

10. Código legible y auditable

Un módulo debe tener responsabilidad clara; separar HTTP, reglas de negocio, persistencia, IA y transporte.

Funciones pequeñas, nombres descriptivos, contratos explícitos y manejo de errores consistente.

Evitar dependencias circulares, lógica duplicada y módulos genéricos que acumulen responsabilidades.

Revisar archivos de 300–400 líneas y funciones de 40–60 líneas como señal orientativa, no límite rígido. Evitar fragmentación artificial.

Cambios pequeños/cohesivos con propósito, pruebas, migraciones y riesgos descritos. No fijar tamaño máximo de PR por líneas sin considerar el cambio.

Probar reglas, aislamiento, concurrencia, duplicados y recuperación. No añadir pruebas que solo repitan implementación.

Refactorizar lo necesario para cada incremento preservando comportamiento; no mezclar limpieza extensa con una nueva función.

11. Documentación y ejecución por incrementos

Preparar y mantener: arquitectura/componentes; modelo de datos; ADRs con alternativas/consecuencias; runbooks de diagnóstico, recuperación, migración y rollback. Este documento fija el contexto; no sustituye esos diseños detallados ni los gates locales del repo.

Incremento propuesto

Resultado revisable

0 — Auditoría

Matriz completo/parcial/ausente/desconocido con evidencia de código, panel, DB y entorno.

1 — Atención y venta

Abrir conversación, ver ficha y crear/vincular oportunidad con responsable y próxima acción.

2 — Bandeja y pipeline

Multi-WhatsApp práctico, filtros, asignaciones, cambios de etapa y clasificación comercial.

3 — Seguimiento

Tareas, vencimientos, recordatorios y auditoría del avance.

4 — Recompra e informes

Compra registrada, tareas de recompra, nuevas oportunidades e indicadores.

5 — Canales adicionales

Adaptadores incorporados con capacidades/permisos verificados y pruebas por canal.

Orden sujeto a dependencias encontradas. No estimar esfuerzo ni declarar porcentaje restante antes de la auditoría. Cada incremento necesita criterios de aceptación y pruebas de recorrido/fallo.

12. Encargo listo para Codex

Lee este documento y las instrucciones locales del repositorio. Revalida master y el estado desplegado; el SHA aquí es la referencia consultada, no una orden para retroceder. Conserva PR #44/#45 y las funciones existentes.

Primero audita el CRM, la bandeja, contactos, canales, permisos, modelos, migraciones, IA y worker. Entrega una matriz por CRM-01…CRM-10 con estado, evidencia y pendiente. Distingue código existente, prueba simulada, entorno desplegado y validación externa. Si no puedes acceder al panel/staging, indícalo y continúa la revisión del código.

Diseña el primer incremento de conversación + ficha + oportunidad + próxima acción sobre las entidades existentes. Presenta contratos, modelo/migraciones propuestos, responsabilidades de módulos, pruebas y recuperación. Resuelve las decisiones rutinarias con los requisitos confirmados; identifica decisiones pendientes solo cuando cambien alcance, costo, datos o comportamiento comercial.

Mantén cambios aislados y revisables. No autoriza force-push, merge, eliminación de datos, cambios de hosting, activación comercial ni consumo pagado nuevo. Las acciones de implementación/despliegue se rigen por la autorización de la sesión de trabajo y las reglas aplicables del entorno. No sustituir fallos de acceso por secretos solicitados en chat.

Este paquete complementa Avance_Luri_KMP_2026-10-06.zip: contiene 40 casos sintéticos de IA y un evaluador, todavía sin ejecución real. Añadir pruebas de CRM y multicanal según el incremento; no marcar esa plantilla como resultados del sistema.