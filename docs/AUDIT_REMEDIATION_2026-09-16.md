# Correcciones de la auditoría de Luri — 16 de septiembre de 2026

## Alcance y ubicación

Trabajo local en `codex/audit-fixes-20260916`, partiendo del master de GitHub
`4f763909e3bd150d8d8ae13fbce3eab867a37b31` (incluye registro web y CRM).
La copia está en `D:\BotWA Starter\.worktrees\audit-fixes-20260916`.
La carpeta original conserva los cambios previos del usuario. No se modificaron
sus secretos ni respaldos. Estos cambios todavía no están publicados ni desplegados.

## Cambios por hallazgo

| Hallazgo | Corrección |
|---|---|
| A01: destinos de WhatsApp | La autorización de destinatarios se comprueba también al enviar respuestas humanas y reintentos; el emisor común aplica la lista de Meta. |
| A02: mensajes fallidos sin recuperación | Se conserva temporalmente el mensaje cifrado; el trabajo de negocio y la cola de respuesta se confirman en una transacción. Un proceso independiente recupera fallos sin repetir el trabajo ya confirmado. |
| A03: reintentos simultáneos | Cada envío se reclama con una actualización atómica y un identificador de propietario antes de contactar al proveedor. PostgreSQL protege también el procesamiento de entradas. |
| A04: notificaciones entre organizaciones | Los destinos se configuran por organización y bot. La lista global anterior no autoriza envíos. Los reintentos vuelven a comprobar la política vigente. |
| A05: recuperación global en cada solicitud | La composición del servicio deja de ejecutar recuperación global. El canal administrado no dispara los trabajos heredados del Core fuera de su transacción. |
| A06: historial descartado | Se carga y descifra solo el historial de la conversación y organización actuales, con límites de tamaño, y se entrega a la solicitud del motor de negocio. |
| A07: consentimiento sobrescrito | El registro web guarda evidencia cifrada separada de las notas. Al editar notas antiguas se conserva primero su evidencia de registro. También se admite borrar notas sin intentar cifrar una cadena vacía. |
| A08: conocimiento limitado a cien entradas | La búsqueda filtra en la base de datos antes de limitar resultados, conservando el alcance por organización, bot y estado publicado. |
| A09: contraseñas inconsistentes | Las entradas y el servicio usan el mismo límite configurado. Se reutiliza el servicio de contraseñas por configuración para evitar repetir su preparación costosa. |
| A10: archivos locales sensibles | Se excluyen variantes de `.env`, respaldos y copias de trabajo; `.env.example` sigue versionado. |
| A11: versiones y documentación | La base incorpora el CRM actual; el SHA grabado en la imagen tiene prioridad sobre una variable de entorno antigua. Se actualiza el contexto del proyecto y el procedimiento operativo. |

La migración aditiva `20260916_0024` incorpora los campos de recuperación,
propiedad de envío y evidencia de registro. Los consentimientos antiguos se
preservan al editar sus notas; esta migración no descifra ni reescribe masivamente
los datos existentes.

## Validación

- Suite general: **967 aprobadas, 41 omitidas** por requisitos de entorno.
- Regresiones específicas adicionales: **20 aprobadas**, incluyendo recuperación,
  consentimiento, historial, límites de contraseñas, notificaciones entre
  organizaciones y búsqueda después de cien entradas.
- PostgreSQL temporal: **2 pruebas simultáneas aprobadas**; una sola ejecución del
  mensaje entrante y un solo envío saliente ante dos procesos competidores.
- Migración desde base vacía y ciclo `0024 → 0023 → 0024`: aprobados únicamente
  en la base temporal, sin información real.
- Ruff y Black: aprobados en el alcance de CI (`app tests scripts`).
- Control de tipos: aprobado, 512 archivos. Contratos de despliegue: 16 aprobados.
- Configuración de Compose: validada con el archivo de ejemplo, sin cargar
  secretos del entorno original.
- PostgreSQL ampliado: **40 aprobadas, ninguna omitida**. Incluye concurrencia,
  conservación de mensajes antiguos durante la migración y las integraciones
  deterministas de CRM, automatizaciones, auditoría, planes y facturación.
- Revisión de diferencias: sin errores de espacios ni conflictos.

## Requisitos de puesta en servicio

1. Revisar e integrar esta rama y construir una imagen con el SHA completo de esa
   revisión como `BOTWA_BUILD_SHA`. El archivo incluido en la imagen evita que una
   variable antigua falsee `/version`.
2. Ejecutar una sola migración a `20260916_0024` antes de arrancar la API y el
   recuperador nuevos. No se ha ejecutado esta migración en staging ni producción.
3. Configurar `BOTWA_LEAD_NOTIFICATION_SCOPES` como JSON con claves
   `UUID-organización:UUID-bot` y listas de números internacionales sin `+`.
   `{}` desactiva estas notificaciones. Migrar deliberadamente los destinatarios
   de la configuración global anterior; no asumir una organización por defecto.
4. Arrancar `python -m app.operations.whatsapp_worker` con la misma imagen,
   base, claves, modo de proveedor, lista de destinatarios y política de
   notificaciones que la API. Compose incluye este servicio. Reiniciar ambos
   procesos al cambiar la política de entorno.
5. Comprobar con datos sintéticos el recorrido web → CRM y WhatsApp → historial,
   además de `/version`, antes de promover el despliegue.

## Límites y recuperación operativa

El motor sigue siendo determinista. Disponer del historial no equivale a tener
integrado un modelo generativo ni demuestra comprensión de todas las preguntas
de seguimiento. Esa integración requiere su propio alcance y evaluación.

Un envío interrumpido puede haber llegado a Meta sin devolver confirmación.
Los resultados inciertos y las reclamaciones vencidas se marcan
`DELIVERY_UNKNOWN` y no se reenvían automáticamente. Es necesario comprobar el
proveedor antes de un reenvío manual; no se promete entrega exactamente una vez.

Los mensajes fallidos anteriores a esta migración que carecen del contenido
cifrado requieren revisión individual: podrían tener efectos de negocio ya
guardados. No se reproducen automáticamente. Las entradas agotadas, los envíos
fallidos y los resultados inciertos requieren seguimiento operativo.

La migración conserva el contenido de los envíos antiguos pendientes y los marca
`LEGACY_DELIVERY_REVIEW`: no tenían propiedad durable ni una marca fiable de
notificación. Revisarlos individualmente antes de reenvío evita duplicados y
avisos a destinos globales heredados. Detener la API anterior y sus procesos de
envío antes de migrar; no mezclar versiones antiguas y nuevas durante el cambio.

En producción, preferir revertir a una imagen compatible conservando las columnas
aditivas. El descenso de esquema elimina los nuevos campos y su contenido; el
ciclo de descenso se probó solo con datos temporales, no autoriza eliminar
evidencia de consentimiento ni mensajes pendientes reales.

Procedimiento del recuperador: [workers-and-jobs.md](runbooks/workers-and-jobs.md).
