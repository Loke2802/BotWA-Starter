# Luri CRM: cuatro avances locales — 06/10/2026

Entrega sobre `codex/luri-crm-increment-1`, después de `e18742e`. Conserva el
incremento anterior y los cambios del checkout original. No requiere DigitalOcean.
No hay despliegue, envíos a WhatsApp ni llamadas a modelos externos.

## 1. Esquema y migraciones

La revisión inicial encontró 141 operaciones propuestas al comparar todas las
tablas migradas con todos los módulos ORM. No eran 141 fallos de datos: incluían
pares de eliminación/creación por nombres, índices y tipos distintos.

Se alinearon los modelos con el DDL histórico: JSONB en PostgreSQL con JSON para
SQLite, nombres de constraints ya existentes (incluida truncación PostgreSQL),
índices compuestos/descendentes/parciales, unicidad y FKs de mensajes. Los índices
parciales de identidad y transporte se conservan; ninguna migración los elimina.
`conv()` fija nombres históricos sin volver a aplicar la convención de nombres.

La revisión pasó de 141 a 114, luego a 25 adiciones necesarias y finalmente a
**cero diferencias**. La migración congelada `20261006_0028`, hija de `0027`,
añade 23 índices no únicos declarados en los modelos y dos checks de automatización
ya exigidos por el dominio. No importa modelos runtime, elimina objetos previos,
convierte JSON, corrige filas ni altera datos comerciales.

Antes del DDL verifica que acciones y triggers históricos sean compatibles.
Si no lo son, aborta toda la transacción y exige revisar esos registros; no los
reescribe. Se comprobó este rechazo con una configuración ficticia inválida.

`alembic check` **aprobado** sobre DB vacía migrada y sobre la DB restaurada con
datos. El informe final incluye metadata completa, sin filtros ni exclusiones.
Las revisiones intermedias son evidencia histórica, no instrucciones de DDL.

Herramienta reproducible de solo lectura:

```powershell
python -m scripts.audit_schema_local --url $env:BOTWA_DATABASE_URL --output docs/validacion-local/schema-review-final.json
python -m alembic check
```

El script admite únicamente PostgreSQL local y genera propuestas para revisión;
no ejecuta su SQL. La corrección aplicable es la migración `0028`, no SQL generado
automáticamente. Antes de cualquier despliegue futuro hay que revisar la revisión
real de la DB y sus datos, medir el tiempo de creación de índices y realizar backup.

## 2. Actualización y recuperación con datos

`scripts/rehearse_crm_local.py` crea bases con nombres únicos exclusivamente en
un contenedor desechable `luri-crm-local-*`, publicado en `127.0.0.1`. Nunca borra
bases, conecta a un servidor remoto ni usa datos reales.

Recorrido ejecutado en PostgreSQL 17:

1. Migrar a `20260921_0026`; registrar dos empresas, usuarios, contacto/ficha,
   mensaje cifrado y una automatización válida previa.
2. Crear backup real con `pg_dump -Fc`; restaurarlo con `pg_restore --exit-on-error`.
3. Aplicar `0027` y `0028`; comparar hashes de **todas las filas de todas las tablas
   anteriores**. Permanecen iguales, salvo la revisión Alembic.
4. Crear oportunidades vencida, futura y sin acción; editar con historial y
   completar la acción anterior. Comprobar reintento con la misma clave.
5. Crear/restaurar otro backup; comparar todas las filas, incluidos ciphertext,
   vínculos, actividades, auditoría e historial. Consultar historia y repetir la
   creación sin duplicar tras restaurar.
6. Intentar downgrade destructivo: se rechaza y las filas/revisión quedan iguales.
7. En otra copia, insertar una acción de automatización inválida y comprobar que
   la actualización completa se rechaza por ese motivo, sin cambios de datos.

Los backups y bases quedan en el contenedor local de pruebas. Los JSON incluyen
hashes y IDs ficticios, nunca contenido descifrado, tokens o claves. Esto verifica
recuperación local; no certifica backups operativos de producción ni el arranque
de un binario anterior. El rollback de aplicación recomendado conserva el esquema.

Repetir desde la raíz del worktree, con Docker disponible:

```powershell
docker run --detach --name luri-crm-local-recovery --publish 127.0.0.1:15437:5432 --env POSTGRES_USER=botwa --env POSTGRES_PASSWORD=crm_local_test --env POSTGRES_DB=crm_local_test postgres:17
python -m scripts.rehearse_crm_local --container luri-crm-local-recovery --output docs/validacion-local/recovery.json
```

Si ese contenedor ya existe, usarlo o elegir otro nombre `luri-crm-local-*`.
Las credenciales anteriores son exclusivamente sintéticas para este ensayo.

## 3. Acceso autorizado y recorrido del panel

Prueba normal con login y bearer token, sin reemplazar dependencias de autorización:
owner y operador editan; viewer no edita y recibe título/textos comerciales
restringidos, sin necesidad, motivo o monto; otra empresa no puede consultar la
cola ni IDs ajenos. Las escrituras repetidas con versión antigua devuelven 409.
Solo owner puede configurar etapas entre los roles de este ensayo.

Se comprobaron también las cuatro sesiones en el navegador: controles de edición
para owner/operador, solo lectura para viewer y cola vacía para la otra empresa.
Dos pestañas cargaron la misma versión de una oportunidad: la primera guardó y
la segunda mostró el conflicto, sin sobrescribir. El editor explica que hay que
actualizar y revisar historial antes de editar otra vez.

Reproducción HTTP contra la API local normal:

```powershell
python -m scripts.verify_crm_local_http --base-url http://127.0.0.1:8766 --manifest docs/validacion-local/recovery.json --output docs/validacion-local/authorized-http.json
```

Para abrir la demo restaurada:

```powershell
python -m scripts.serve_crm_local --manifest docs/validacion-local/recovery.json
```

Abrir `http://127.0.0.1:8766/portal`. Cuentas ficticias:
`organization_owner@local-crm.example.test`, `operator@local-crm.example.test`,
`viewer@local-crm.example.test`, `other-company@local-crm.example.test`.
Contraseña de prueba para todas: `SyntheticCRM2026!`.

El servidor debe apuntar a la base `databases.after` de ese manifiesto. `serve_crm_local` establece las claves sintéticas de cifrado y HMAC de
`tests/crm_opportunity_support.py` y limita el servidor a localhost. El script modifica únicamente las oportunidades
ficticias del ensayo, para comprobar escritura y conflictos.

## 4. Vista de seguimiento

Nueva sección **Seguimiento** en `/portal`; endpoint scoped
`GET /organizations/{org}/crm/follow-up`. Módulo de consulta separado del servicio
de mutaciones y módulo de panel separado de conversaciones/clientes. Reutiliza
ficha, editor, historial, cifrado y permisos existentes; no incorpora otra IA.

- Solo oportunidades en etapas abiertas; las ganadas/perdidas salen de la cola.
- Contadores y filtros: abiertas, acciones vencidas, próximas acciones y sin acción.
- Filtros por responsable y etapa, con paginación y orden por fecha ascendente.
- Una acción cuenta únicamente si pertenece a la versión actual y está pendiente;
  las anteriores completadas/canceladas nunca aumentan los vencimientos.
- Vencida significa `due_at < as_of`; la igualdad pertenece a próximas acciones.
  La referencia la calcula el servidor una vez; se muestra en la zona de la empresa.
- Los contadores respetan etapa/responsable; el filtro temporal selecciona una
  categoría sin cambiar el resto de contadores. **Actualizar** recalcula la cola.
- Se puede abrir ficha, editar y consultar historial desde cada fila.
- El editor admite “Sin acción programada por ahora” con motivo obligatorio,
  sin exigir una fecha ficticia; al cerrar exige motivo de cierre.
- Lecturas no toman locks de escritura. Se conservan los locks de empresa/contacto
  de las mutaciones para proteger idempotencia y configuración concurrente.

## Resultados y evidencia

| Comprobación | Resultado |
| --- | --- |
| Suite general | 1.063 passed, 65 skipped, una advertencia TestClient/httpx |
| Suite focal CRM/follow-up/migración/panel | 24 passed |
| PostgreSQL: concurrencia, claves cruzadas y CRM previo | 4 passed |
| Navegador: oportunidades / seguimiento / conversaciones | 5 / 8 / 7 aprobadas |
| HTTP autenticado normal, cuatro roles/empresas | Aprobado |
| Dos backups/restauraciones y actualización con datos | Aprobado |
| Configuración inválida y downgrade destructivo | Rechazados sin cambios, como se esperaba |
| Alembic check y comparación completa en PostgreSQL | Cero operaciones nuevas |
| Ruff, Black, mypy y sintaxis Node | Aprobados |

Los skipped corresponden a requisitos externos o PostgreSQL explícito de otras
suites; no se presentan como pruebas aprobadas. Los cuatro casos PostgreSQL
anteriores se ejecutaron por separado con URL de prueba explícita.

Evidencias en `validacion-local/`: revisiones de esquema, hashes de recuperación,
resultados HTTP y capturas owner/viewer/operador/otra empresa. El recorrido completo
verificado fue panel → API autenticada → PostgreSQL restaurado → panel.

Para comprobar manualmente: ingresar con un rol de prueba → **Seguimiento** →
**Ver acciones vencidas** → abrir ficha → editar oportunidad → recargar → consultar
historial. Repetir como viewer y otra empresa. Probar dos pestañas antes de guardar.

## Pendientes externos

Sin despliegue y sin validación de WhatsApp/Meta, IA externa o empresas reales.
No hay DigitalOcean configurado ni necesario para esta entrega. Cuando exista
un entorno de despliegue, revisar master remoto y revisión real de DB, respaldar,
aplicar migraciones y repetir permisos/recorrido con cuentas autorizadas.
