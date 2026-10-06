# Luri CRM: conversación, ficha, oportunidad y próxima acción

**Actualización:** la [continuación local](LURI_CRM_CONTINUACION_LOCAL_2026-10-06.md) añade Seguimiento y resuelve el drift histórico con `0028`. Los resultados de este documento corresponden a la entrega inicial.

Fecha: 06/10/2026. Rama: `codex/luri-crm-increment-1`.
Base: `026ca10d3276ed06cb8f644549e807a684921f22` (PR #45), referencia remota
guardada localmente. El checkout principal y sus cambios previos se conservan.

Requisitos: [contexto maestro](LURI-CTX-001_CONTEXTO_MAESTRO_CRM_2026-10-06.md)
y [auditoría/diseño inicial](LURI_CRM_AUDITORIA_Y_DISENO_2026-10-06.md).
Este documento describe el incremento implementado; la auditoría sigue siendo
la evidencia histórica previa a la implementación.

## Resultado

Desde Conversaciones se abre la ficha existente de CRM, se crea una oportunidad
vinculada o se vincula otra oportunidad del mismo contacto. Cada oportunidad
tiene responsable activo de la empresa, etapa, necesidad y próxima acción con
fecha. Edición por versión, historial comercial cifrado, auditoría en la misma
transacción y creación idempotente. Un contacto puede tener varias oportunidades.
No se reemplazan mensajes, perfil comercial, clasificación, seguimiento previo,
atención ni asignación de handoff.

El panel muestra la cuenta real cuando existe, y declara cuando no está vinculada.
Una conversación sin contacto verificado no permite crear/vincular oportunidades:
corresponde revisar la identidad/backfill existente, no duplicar ni inferir contactos.
Fechas almacenadas en UTC con zona; visualización en zona de la empresa. El
formulario identifica expresamente que la entrada de fecha usa la zona del dispositivo.

Se conserva la IA de PR #44/#45 y su worker, sin activar llamadas, flags o
sugerencias comerciales nuevas. No se envían mensajes desde acciones CRM.
Ganada/perdida requiere razón humana y cancela/completa la acción pendiente;
no verifica pagos ni cambia la clasificación del contacto o estado de atención.

## Componentes y contratos

- `domain/crm/contracts.py`: solicitudes/respuestas e invariantes de entrada.
- `application/crm/service.py`: autorización y casos de uso transaccionales.
- `application/crm/presentation.py`: respuesta y redacción según permisos.
- `infrastructure/repositories/crm_opportunity_repository.py`: SQL scoped y locks.
- `infrastructure/models/crm_opportunity.py`: etapa, oportunidad, vínculo,
  actividad e historial; las relaciones críticas incluyen empresa y contacto.
- `api/crm_opportunity_routes.py`: HTTP, validación y errores sin contenido privado.
- `portal/opportunities.js`: composición del recorrido sobre API autenticada;
  `crm.js` conserva su ficha, y `conversations.js` integra el módulo comercial.

Prefijo `/organizations/{organization_id}`:

| Operación | Ruta |
|---|---|
| Contexto de conversación | `GET /conversations/{id}/commercial-context` |
| Etapas | `GET /crm/stages`, `PUT /crm/stages` |
| Listar/crear | `GET /crm/opportunities`, `POST /crm/opportunities` |
| Consultar/editar | `GET /crm/opportunities/{id}`, `PATCH /crm/opportunities/{id}` |
| Vincular | `PUT /crm/opportunities/{id}/conversations/{conversation_id}` |
| Historial paginado | `GET /crm/opportunities/{id}/history` |

Listados filtran por contacto, conversación, responsable y etapa; paginación
acotada. `POST` requiere `Idempotency-Key`, `PATCH` requiere `version` y el
estado editable completo. En API, una oportunidad abierta puede tener motivo
explícito de ausencia de acción; el formulario propone acción y fecha obligatorias.
Importe decimal y moneda opcionales disponibles en API, sin prueba de cobro.

Permisos nuevos: `crm.opportunities.read`, `crm.opportunities.read_content`,
`crm.opportunities.write`, `crm.stages.manage`. Viewer ve metadatos con contenido
comercial restringido; operator puede trabajar oportunidades; owner/admin
administran etapas. Se conservan permisos independientes de teléfono/notas y
de conversaciones. Acceso entre empresas solo mediante Platform Admin explícito
existente, nunca por pertenencia a Kalivur.

## Decisiones del incremento

Un pipeline por empresa, con etapas configurables mediante API y códigos
estables. Inicialización perezosa transaccional con los seis valores del contexto;
lectura de etapas no escribe. No se permite eliminar códigos o cambiar su tipo
para proteger oportunidades e historia. Varios pipelines y editor visual de
etapas quedan para el incremento de bandeja/pipeline.

La próxima acción es una actividad asociada a la versión vigente de la
oportunidad. Al editar se conserva la anterior como completada (confirmación
explícita) o cancelada/sustituida y se crea la nueva. La unicidad oportunidad/versión
evita duplicados; no existe una segunda fecha de acción dentro de oportunidad.
El historial cifrado conserva cada versión confirmada, incluso tras cierre/reapertura.

Las escrituras usan lock de empresa seguido de lock de oportunidad/contacto:
serializa también claves de creación entre contactos y la configuración de etapas.
Es una decisión conservadora del primer incremento; medir contención por empresa
antes de sustituirla por locks más finos. No añadir infraestructura para resolverla.

La clave de creación es única por empresa y actor; el digest HMAC del payload
detecta reutilización con datos distintos (409). Reintento idéntico devuelve el
recurso actual autorizado, sin duplicar oportunidad, acción, vínculo o Audit.
El panel conserva hash/clave en sessionStorage hasta éxito; nunca guarda el
contenido comercial en almacenamiento del navegador. El vínculo usa PUT y su
clave compuesta; el historial de vínculo conserva actor/fecha y Audit separado.

## Migración y recuperación

`20261006_0027`, hija de `20260921_0026`, añade cinco tablas CRM, índices y
unicidad compuesta en conversación. DDL congelado, sin importar modelos runtime.
Datos existentes y migraciones IA se conservan. Las etapas se inicializan cuando
una empresa crea su primera oportunidad o configura etapas.

Antes de desplegar: revalidar master/head de DB, probar backup/restauración,
aplicar en staging con el mismo artefacto de API y verificar recorrido autenticado.
Si hubo migraciones posteriores, rebasar y ajustar el padre; no crear dos heads.
Un fallo de DB/Audit revierte toda la mutación. Ante resultado incierto de POST,
consultar/reintentar con la misma clave; PATCH obsoleto devuelve 409.

Rollback de aplicación conserva esquema y datos. El downgrade destructivo queda
bloqueado si hay oportunidades o configuración de etapas; no usarlo para retirar
una versión que ya recibió datos comerciales.

## Cómo comprobarlo en el panel

1. Con la rama y DB de prueba migrada, iniciar API normalmente y abrir `/portal`.
   Ingresar como owner/admin/operator de una empresa de prueba.
2. Abrir Conversaciones y seleccionar una con contacto enlazado. Comprobar cuenta,
   canal y zona; pulsar **Abrir ficha del cliente** y cerrar la ficha.
3. Pulsar **Crear oportunidad**; indicar título, necesidad, etapa abierta,
   responsable y próxima acción con fecha. Guardar y comprobar el aviso de éxito.
4. Recargar completamente, reabrir conversación y verificar los mismos datos.
5. Editar oportunidad: cambiar etapa/acción, marcar completada la anterior si
   corresponde; abrir **Ver historial**. Dos pestañas con la misma versión deben
   producir un conflicto en la segunda escritura, sin sobrescribir la primera.
6. Para una oportunidad del mismo contacto sin vínculo, pulsar **Vincular a esta
   conversación**. Repetir la operación no debe crear ventas ni vínculos nuevos.
7. Repetir con Viewer: sin creación/edición ni texto comercial/teléfono/notas.
   Verificar que otra empresa no puede consultar IDs, listar, contar o asignar
   responsables de la primera empresa.
8. Los casos de doble clic/respuesta perdida, FK cruzadas y edición simultánea
   tienen pruebas automatizadas; usar datos ficticios, nunca activar envíos para
   comprobar el CRM.

Pruebas de navegador autocontenidas: servir raíz con `python -m http.server 8765
--bind 127.0.0.1` y abrir `/tests/portal_crm_opportunities.html` (API simulada) y
`/tests/portal_conversations.html` (regresión de atención). No equivalen a staging.

## Límites y pendientes

No desplegado ni validado contra WhatsApp/Meta o un modelo externo. Pendientes:
master remoto actual, staging con roles reales, backup/restauración y smoke
WhatsApp/handoff con cuentas autorizadas. La validación local del panel con
PostgreSQL y datos ficticios se registra separadamente de los casos simulados.

Potencial comercial independiente, varias identidades por contacto, varias
pipelines, catálogo de servicios por negocio, tareas generales/recordatorios,
recompra, nuevos canales y sugerencias IA comerciales siguen en incrementos
posteriores. La incertidumbre de transporte conserva el contrato previo; este
incremento no redefine estados de entrega ni resuelve carreras externas de envío.


## Validación ejecutada (06/10/2026)

- Suite general con DB de prueba SQLite explícita: **1.057 passed, 65 skipped**,
  una advertencia de deprecación de TestClient/httpx; los casos externos requieren
  sus variables de entorno. No se interpretan los skipped como validación externa.
- PostgreSQL 17 local desechable: **4 passed** (tres casos nuevos CRM y la
  regresión de concurrencia del CRM previo). Comprueba creación simultánea
  idempotente, edición optimista y claves foráneas entre empresas.
- Migraciones desde DB vacía hasta `20261006_0027`: aplicadas correctamente.
  Comparación Alembic de las cinco tablas CRM contra los modelos: **sin diferencias**;
  verificada unicidad conversación/empresa/contacto.
- `alembic check` global: **falló** por diferencias de tablas anteriores
  (nombres de constraints, índices y tipos de otras áreas). Revisar ese drift
  antes del despliegue; esta entrega no modifica esas tablas para corregirlo.
- Ruff, Black, mypy, sintaxis Node de los tres módulos del panel y
  `git diff --check`: aprobados.
- Navegador con API simulada: **5/5 CRM**, **7/7 conversaciones**; incluyen
  respuesta perdida/reintento, doble clic, escape de HTML y permisos.
- Panel normal autenticado → API → PostgreSQL local, con datos ficticios:
  abrir ficha existente, crear con responsable/etapa/acción fechada, recargar y
  comprobar persistencia, editar y completar acción anterior, revisar versiones
  del historial y vincular una oportunidad existente. Se mantuvieron dos
  oportunidades; vincular no creó una tercera.

Evidencia visual: `luri-crm-incremento-1-panel-local.jpg`.
Las pruebas locales no equivalen a despliegue, prueba de staging o validación
con empresas reales. No hubo envíos a WhatsApp ni llamadas a modelos externos.
El CRM y la IA existentes se conservan; este incremento reutiliza ficha, actor,
cifrado, permisos y auditoría, sin introducir otro motor de IA.
