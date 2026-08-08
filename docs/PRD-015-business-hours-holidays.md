# PRD-015 Business Hours & Holidays

**Estado:** CLOSED

**Tipo:** Product / Scheduling Domain

**Fuente de verdad:** este documento

**Dependencias:** PRD-003 Roles and Permissions, PRD-004 Bot Management,
PRD-005 Business Configuration y PRD-013 Integration Management

**No modifica:** PRD-014 Dashboard

## 1. Decisión de producto

PRD-014 conserva su numeración y alcance como Dashboard. Business Hours &
Holidays se asigna oficialmente a PRD-015. Este documento define el contrato del
producto; su creación no inicia la implementación funcional.

PRD-015 introduce un dominio de calendario operativo propio, agnóstico del
proveedor y tenant-scoped. BotWA/Luri será Source of Truth de las reglas que
determinan si una organización o bot está abierto en un instante dado. Un
calendario externo podrá aportar reglas normalizadas mediante un adaptador
futuro, pero nunca será una dependencia del dominio ni recibirá control sobre la
resolución de precedencia.

## 2. Problema

La configuración básica de horarios de PRD-005 solo representa un intervalo
regular por día. No cubre de forma canónica:

- varios intervalos en un mismo día;
- feriados y cierres completos;
- excepciones de apertura o cierre por fecha;
- cierres parciales;
- overrides manuales con vigencia limitada;
- resolución determinista entre reglas superpuestas;
- semántica explícita de zona horaria y DST;
- auditoría, idempotencia y concurrencia administrativa.

PRD-015 debe resolver esas necesidades sin introducir lógica de Google Calendar
en el dominio y sin alterar el alcance de Dashboard.

## 3. Objetivos

- Administrar uno o más calendarios operativos por organización, opcionalmente
  asociados a un bot.
- Representar horarios semanales regulares con múltiples intervalos.
- Representar excepciones por fecha, feriados, aperturas especiales, cierres
  completos y cierres parciales.
- Permitir overrides manuales temporales para abrir o cerrar.
- Resolver de forma pura y determinista el estado `open` o `closed` de un
  instante.
- Aplicar zona horaria IANA y reglas DST sin depender de la zona del servidor.
- Garantizar aislamiento tenant, autorización, auditoría, idempotencia y
  consistencia transaccional.
- Exponer contratos de aplicación estables para Conversation, Automation y
  futuras integraciones sin acoplar esos consumidores a la persistencia.

## 4. Principios y fronteras

### 4.1 Dominio agnóstico

El dominio solo conoce reglas canónicas y puertos. No conoce SDKs, payloads,
identificadores ni errores de Google, Microsoft u otros proveedores. No debe
existir branching por proveedor en entidades, servicios de resolución o DTOs
canónicos.

### 4.2 Source of Truth

Las reglas persistidas por PRD-015 son la única fuente de verdad para la
resolución operativa. La estructura `business_hours` de PRD-005 se considera
configuración legacy hasta que una estrategia de migración explícita la importe
o retire. Durante la implementación no podrán existir dos rutas de escritura
activas que produzcan decisiones contradictorias.

El contrato de compatibilidad es explícito: un calendario PRD-015 activo y
aplicable es el Source of Truth. Se selecciona primero el calendario activo del
bot y, si no existe, el calendario activo general de la organización. Solo puede
existir un calendario activo por cada scope. Si ninguno existe, PRD-012 conserva
temporalmente el cálculo legacy de PRD-005. Calendarios `draft`, `inactive` o
`archived` no deshabilitan ese fallback.

El fallback no combina decisiones ni copia reglas. Un calendario activo que no
pueda resolverse retorna `unknown`; no cae silenciosamente a PRD-005. Su retiro
futuro exige migrar y activar calendarios para los tenants restantes y aprobar
separadamente la deprecación de la lectura legacy.

### 4.3 Aislamiento tenant

Toda entidad persistida incluye `organization_id`. Las consultas y mutaciones
usan como mínimo `organization_id + resource_id`. Una asociación opcional a
`bot_id` debe validar que el bot pertenece a la misma organización. Una
referencia cross-tenant se trata como recurso inexistente y nunca revela datos.

## 5. Modelo conceptual

### 5.1 Business calendar

Definición administrativa con:

- `id`, `organization_id` y `bot_id` opcional;
- nombre y descripción;
- zona horaria IANA;
- estado administrativo `draft`, `active`, `inactive` o `archived`;
- versión para concurrencia optimista;
- timestamps y actor de creación/actualización.

Solo calendarios `active` participan en resolución. `archived` es terminal. No
se permite eliminación física desde la API v1.

### 5.2 Weekly schedule

Conjunto de intervalos locales recurrentes por día ISO de la semana. Cada día
puede estar cerrado o contener varios intervalos abiertos no solapados. Los
intervalos se expresan como límites `[start, end)`, con inicio inclusivo y fin
exclusivo.

Los intervalos que cruzan medianoche se normalizan de forma determinista en dos
segmentos asociados a fechas locales consecutivas. La API puede exigir esa forma
normalizada para evitar ambigüedad.

### 5.3 Date exception

Regla para una fecha local concreta que puede:

- cerrar el día completo;
- abrir el día completo;
- añadir intervalos especiales de apertura;
- cerrar intervalos parciales;
- reemplazar explícitamente el horario semanal de esa fecha.

Cada excepción declara su modo y sus intervalos; no se infiere semántica a
partir de campos vacíos.

### 5.4 Holiday

Feriado tenant-scoped para una fecha local, con nombre público no sensible,
alcance completo o intervalos parciales de cierre y procedencia `manual` o
`external_import`. PRD-015 v1 no incluye un catálogo mundial implícito: cada
tenant administra o importa explícitamente sus feriados.

### 5.5 Manual override

Decisión temporal `open` o `closed` para un intervalo de instantes, con motivo,
actor, creación, expiración opcional y estado de revocación. Se usa para cambios
operativos inmediatos. No modifica ni borra la regla semanal o la excepción
subyacente.

## 6. Precedencia determinista

Para resolver un instante UTC:

1. Validar tenant, calendario activo y zona horaria.
2. Convertir el instante UTC a fecha, hora y día semanal locales.
3. Aplicar un override manual vigente, si existe.
4. Aplicar una excepción explícita para la fecha local.
5. Aplicar el feriado correspondiente.
6. Aplicar el horario semanal regular.
7. Si ninguna regla abre el instante, resolver `closed` por defecto.

Reglas de desempate:

- una capa superior reemplaza la decisión de cualquier capa inferior;
- dentro de una misma capa, `closed` prevalece sobre `open` como política
  fail-safe;
- dos reglas incompatibles con igual alcance deben rechazarse al escribir, no
  resolverse de manera implícita;
- si varios overrides válidos fueran posibles por concurrencia, gana la mayor
  versión y luego `created_at` e `id` como desempate estable;
- todos los límites temporales usan intervalos `[start, end)`.

El resultado canónico incluye `state`, `evaluated_at`, `timezone`, `local_date`,
`local_time`, `winning_rule_type`, `winning_rule_id`, `calendar_version` y el
próximo cambio conocido cuando pueda calcularse sin consulta externa.

## 7. Zona horaria y DST

- Solo se aceptan zonas IANA disponibles mediante `zoneinfo`; no se aceptan
  abreviaturas ambiguas ni offsets fijos como sustituto de zona.
- Los horarios regulares representan tiempo civil local y se evalúan contra un
  instante UTC.
- Los instantes de entrada y salida de la API deben incluir offset o usar UTC.
- Una fecha/hora local inexistente durante el salto DST se rechaza con un error
  tipado; no se desplaza silenciosamente.
- Una fecha/hora local ambigua durante el retroceso DST exige `fold` u offset
  explícito cuando se usa para crear un override.
- La resolución desde un instante UTC no es ambigua y debe conservar el `fold`
  resultante.
- La estrategia de pruebas incluye zonas sin DST, transición de primavera,
  transición de otoño y cambios históricos de offset.

## 8. Arquitectura objetivo

### 8.1 Contratos y DTOs

Contratos explícitos y validados para:

- crear, actualizar, activar, desactivar y archivar calendarios;
- reemplazar el horario semanal con versión esperada;
- crear, actualizar y revocar excepciones, feriados y overrides;
- listar recursos con paginación y filtros allowlisted;
- resolver un instante y consultar el próximo cambio.

Los DTOs no exponen modelos ORM, configuración interna del proveedor, payloads
externos ni información de otros tenants.

### 8.2 Puertos

- `BusinessCalendarRepository`: persistencia tenant-scoped y locks/versiones.
- `BusinessHoursResolver`: evaluación pura de reglas canónicas.
- `ExternalCalendarAdapter`: importación opcional de eventos normalizados.
- `AuditSink`: eventos administrativos allowlisted y sin PII innecesaria.
- `Clock`: tiempo inyectable para expiración, DST y pruebas deterministas.

### 8.3 Servicios

Los servicios de aplicación coordinan RBAC, validación tenant, lifecycle,
versionado, idempotencia, repositorios y auditoría. La lógica de precedencia vive
en el resolver de dominio; no se duplica en endpoints, workers o adaptadores.

### 8.4 Errores tipados

Como mínimo:

- `BusinessCalendarNotFound`;
- `BusinessCalendarForbidden`;
- `BusinessCalendarConflict`;
- `BusinessCalendarInactive`;
- `ScheduleValidationError`;
- `ScheduleVersionConflict`;
- `TimezoneInvalid`;
- `LocalTimeNonexistent`;
- `LocalTimeAmbiguous`;
- `IdempotencyConflict`;
- `ExternalCalendarUnavailable`.

La API mapea estos errores a códigos seguros y estables. No retorna excepciones
raw, SQL, payloads externos ni stack traces.

## 9. API administrativa propuesta

El diseño final debe conservar rutas tenant-scoped equivalentes a:

- `POST /organizations/{organization_id}/business-calendars`;
- `GET /organizations/{organization_id}/business-calendars`;
- `GET/PATCH /organizations/{organization_id}/business-calendars/{calendar_id}`;
- `POST .../{calendar_id}/activate|deactivate|archive`;
- `PUT .../{calendar_id}/weekly-schedule`;
- `POST/GET/PATCH .../{calendar_id}/date-exceptions`;
- `POST/GET/PATCH .../{calendar_id}/holidays`;
- `POST/GET .../{calendar_id}/overrides`;
- `POST .../{calendar_id}/overrides/{override_id}/revoke`;
- `GET .../{calendar_id}/resolve?at={instant}`.

No se define `DELETE` físico. Las rutas definitivas y sus schemas se congelan en
la revisión de implementación antes de crear la migración.

## 10. RBAC propuesto

- `business_calendar.read`;
- `business_calendar.create`;
- `business_calendar.update`;
- `business_calendar.activate`;
- `business_calendar.deactivate`;
- `business_calendar.archive`;
- `business_calendar.schedule.manage`;
- `business_calendar.exception.manage`;
- `business_calendar.holiday.manage`;
- `business_calendar.override.manage`;
- `business_calendar.resolve`.

Owner y organization admin reciben administración completa. Por mínimo
privilegio, Operator solo puede leer y resolver; no puede administrar overrides,
horarios, excepciones, feriados ni lifecycle. Cualquier ampliación futura requiere
un contrato de producto explícito. Viewer no recibe permisos por defecto.
Platform admin siempre opera con organización explícita.

## 10.1 Compatibilidad con PRD-012

`conversation.inbound_received` obtiene `business_hours_state` mediante el
contrato de compatibilidad anterior. Una resolución PRD-015 `open` se traduce a
`inside` y `closed` a `outside`; sin calendario activo se usa PRD-005, y sin una
configuración legacy válida se usa `unknown`. El snapshot durable de PRD-012
conserva ese estado sin duplicar reglas ni cambiar su trigger o acción.

## 11. Auditoría, observabilidad y seguridad

- Toda mutación registra actor, tenant, recurso, operación, versión anterior y
  nueva, timestamp y correlation ID.
- La auditoría guarda diffs allowlisted; no guarda tokens, headers, payloads raw,
  PII innecesaria ni cuerpos de proveedores.
- Métricas mínimas: resoluciones por estado, latencia, conflictos de versión,
  errores de validación, overrides activos e importaciones externas.
- Logs estructurados incluyen IDs técnicos y safe error codes, nunca secretos.
- Entradas tienen límites de longitud, cantidad de reglas, rango temporal y
  paginación.
- Todas las escrituras requieren permiso y scope tenant verificados antes de
  revelar existencia del recurso.

## 12. Idempotencia y consistencia transaccional

- Las creaciones y comandos externos aceptan `Idempotency-Key` tenant-scoped.
- La misma clave con el mismo hash de request retorna el resultado durable
  anterior; con payload distinto retorna `IdempotencyConflict`.
- El receipt se persiste en la misma transacción que la mutación y la auditoría.
- La versión esperada evita lost updates en horarios y excepciones.
- Los reemplazos de horario semanal son atómicos: nunca queda un conjunto
  parcialmente actualizado.
- Crear/revocar un override y registrar auditoría ocurre en una transacción.
- Un fallo de adaptador externo no deja reglas parciales ni marca como exitosa la
  idempotencia.
- Las operaciones reintentables usan constraints únicos y locks explícitos; no
  dependen solo de comprobaciones en memoria.

## 13. Integración opcional con calendarios externos

Una integración futura puede implementar `ExternalCalendarAdapter` para importar
feriados o cierres. Debe convertir datos externos a comandos canónicos, conservar
provenance e identificador externo hasheado o no sensible, y aplicar idempotencia.

Google Calendar es únicamente un adaptador futuro. PRD-015 no autoriza OAuth,
Calendar List, event sync ni nuevas llamadas Google. PRD-013 continúa siendo la
frontera de conexiones y credenciales externas.

## 14. Criterios de aceptación

1. PRD-014 sigue siendo Dashboard y no cambia por esta iniciativa.
2. Dos tenants pueden usar los mismos nombres e identificadores externos sin
   leer, mutar ni resolver reglas del otro.
3. Un horario semanal con múltiples intervalos resuelve correctamente límites
   inclusivos/exclusivos y segmentos normalizados de medianoche.
4. Una excepción de fecha prevalece sobre un feriado y el horario semanal.
5. Un override manual vigente prevalece sobre todas las demás reglas y, al
   expirar o revocarse, reaparece la decisión subyacente.
6. Los cierres parciales solo afectan su intervalo y no el resto del día.
7. Sin regla de apertura aplicable, el resultado es `closed`.
8. La misma entrada y versión de calendario producen el mismo resultado y
   provenance de regla.
9. Las transiciones DST se resuelven según IANA; tiempos inexistentes o ambiguos
   no se aceptan silenciosamente.
10. Un reintento con la misma clave idempotente no duplica calendario, excepción,
    feriado, override ni auditoría.
11. Un fallo transaccional no deja horario parcial, receipt huérfano ni auditoría
    inconsistente.
12. La API y los logs no exponen ORM, payloads externos, secretos ni datos
    cross-tenant.
13. El dominio y los tests de resolución funcionan sin Google Calendar ni red.
14. Alembic conserva un único head y soporta upgrade/downgrade/re-upgrade.
15. pytest, mypy, Ruff, Black y `git diff --check` pasan antes de publicar.

## 15. Estrategia de pruebas

- Tests unitarios del resolver con tabla de precedencia y límites `[start, end)`.
- Property-based tests para intervalos no solapados, determinismo y monotonicidad
  del próximo cambio.
- Tests de zona horaria con UTC, America/Lima y zonas DST representativas.
- Tests de contrato y DTOs para extras, límites y allowlists.
- Tests de servicio para RBAC, lifecycle, version conflict e idempotencia.
- Tests API para status codes seguros, paginación y ausencia de datos sensibles.
- Tests de repositorio PostgreSQL para tenant isolation, constraints, locks y
  rollback atómico.
- Tests Alembic de upgrade/downgrade/re-upgrade y single head.
- Contract tests de adaptadores con fakes; cualquier smoke externo será opcional
  y condicionado a credenciales de desarrollo explícitas.
- Suite de regresión para PRD-005, PRD-012 y PRD-013.

## 16. Exclusiones

- Implementación de PRD-014 Dashboard.
- Eliminación física de calendarios o historial desde la API v1.
- Google Calendar u otro adaptador real.
- OAuth, almacenamiento de credenciales o cambios en PRD-013.
- Sincronización bidireccional, webhooks, polling o workers externos.
- Creación, edición o eliminación de eventos de calendario.
- Reserva de citas, asignación de recursos, capacidad o workforce scheduling.
- Catálogo global automático de feriados o interpretación legal por país.
- Reglas de recurrencia arbitrarias tipo RRULE en v1.
- Eliminar físicamente historial o reglas auditadas.
- Cambios al Core Automation Engine.

## 17. Entregables de implementación

- contratos y resolver de dominio;
- modelos, repositorios y migración Alembic;
- servicios, permisos y endpoints;
- receipt de idempotencia y auditoría transaccional;
- puerto de adaptador externo sin proveedor real obligatorio;
- pruebas focalizadas, PostgreSQL y gates completos;
- documentación de migración desde el horario básico de PRD-005.

La implementación autorizada está disponible en la rama
`feat/prd-015-business-hours-holidays`, con migración `20260808_0016`. Incluye
dominio y resolver agnósticos de proveedor, gestión administrativa tenant-scoped,
RBAC, auditoría e idempotencia transaccionales, API, observabilidad y pruebas
unitarias, API y PostgreSQL. Google Calendar permanece exclusivamente como
adaptador futuro y PRD-014 Dashboard permanece `NOT STARTED`.

## 18. Cierre

PRD-015 fue aprobado y fusionado mediante PR #18 en `master` con el merge commit
`025c3058388d51219e05fff1ae253a296238be89`. El head final de la rama feature fue
`8831de5a3b284e8ba28d7d86ff983254b643c9b5`.

Validación final aprobada:

- pytest: 702 passed, 12 skipped, 2 warnings;
- PostgreSQL PRD-015: 3 passed;
- mypy: PASS — 374 source files;
- Ruff: PASS;
- Black: PASS — 374 files;
- `git diff --check`: PASS;
- Alembic head: `20260808_0016`.

PRD-015 queda `CLOSED`. PRD-014 Dashboard permanece `NOT STARTED` y PRD-016 en
adelante conserva el estado definido en el roadmap, sin iniciar trabajo nuevo.
