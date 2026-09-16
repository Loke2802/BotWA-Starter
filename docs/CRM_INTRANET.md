# CRM de la intranet — primera versión

## Alcance y acceso

El CRM vive en el portal de Luri, /portal → Clientes. La web corporativa
solo es el punto de acceso; no recibe credenciales ni datos privados.
Esta entrega se valida y despliega primero en staging.

Permite crear contactos por WhatsApp, abrir fichas, editar nombre y notas,
clasificar prospectos/clientes/inactivos, indicar servicio de interés,
asignar un responsable de la misma empresa y programar el próximo seguimiento.
Incluye resumen, filtros, paginación, búsqueda de nombre en la página actual,
archivo/reactivación y estados de carga, vacío y error.
El seguimiento es un recordatorio visual: no envía mensajes ni agenda
automatizaciones. No se implementan cobros ni se envían mensajes de WhatsApp.

## Datos y permisos

- Reutiliza contact: nombre, teléfono y notas siguen cifrados.
- customer_profile tiene una sola ficha comercial por contacto.
- FK compuesta de contacto y empresa impide cruzar datos de empresas.
- FK compuesta del responsable y empresa impide asignaciones entre empresas.
- Se validan responsables activos en cada escritura.
- contacts.read permite consultar; contacts.update editar datos comerciales;
  contacts.read_sensitive es obligatorio para teléfono/notas y alta manual.
  Archivar/reactivar conserva el permiso contacts.archive existente.
- Los contactos previos se muestran como prospectos sin crear filas en lectura.
- Las notas existentes, incluido el registro inicial de consentimiento web,
  no se borran si un rol sin acceso sensible edita la parte comercial.
- Ediciones usan bloqueo de fila y versión: un cambio obsoleto devuelve 409.
- Alta duplicada devuelve 409 y no sobrescribe la ficha existente.
- La captura pública conserva su comportamiento; sus contactos aparecen aquí.
- Se registra la operación de edición en auditoría sin nombre, teléfono ni notas.
- Al cambiar de empresa o cerrar sesión se descartan respuestas tardías.
- No se mantiene una copia de los clientes en localStorage.

## Esquema y despliegue

Migración Alembic 20260916_0023, posterior a 20260813_0022.
Añade customer_profile y claves únicas auxiliares, sin reescribir contactos.
Aplicar alembic upgrade head antes de activar la nueva API/portal.
No se debe usar downgrade como restauración de datos: elimina perfiles comerciales.
Para revertir la aplicación se puede recuperar la imagen anterior conservando
el esquema aditivo. Verificar copia/restauración antes de datos comerciales reales.

## Verificación

Pruebas API: alta/lectura, cifrado, deduplicación, permisos, aislamiento,
responsable de otra empresa, campos inválidos, contactos previos, clasificación,
seguimiento y conflictos. Prueba PostgreSQL de dos ediciones concurrentes.
CI valida una sola cabeza Alembic y ciclo upgrade/downgrade/upgrade en base de test.

## Siguientes ampliaciones

Historial de actividades y tareas múltiples, búsqueda global por nombre con
estrategia compatible con cifrado, consent_event y lead_submission separados,
integración de conversaciones en ficha, pagos verificados y automatizaciones.
Estas ampliaciones no se presentan como operativas en esta primera versión.
