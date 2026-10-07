# Luri CRM — autorización y aislamiento local

07/10/2026. Rama `codex/luri-crm-security-review`, basada en `9f3c333`.
Continúa el ensayo de rendimiento sin despliegue ni servicios externos.

## Cambio implementado

La presentación de oportunidades comprobaba el permiso comercial, pero descifraba
los campos y después los sustituía en la respuesta de viewer. No se encontró una
fuga en esas respuestas evaluadas. Ahora evita descifrar título, necesidad,
descripción de acción y motivos de cierre/ausencia de acción cuando falta
`crm.opportunities.read_content`. Importe y moneda siguen siendo nulos.
Conserva los mismos metadatos y textos de restricción de la API.

El cambio está concentrado en `app/application/crm/presentation.py`, compartido
por detalle, listados, tablero, ficha y seguimiento. No añade permisos, columnas,
caché de autorización ni cambios al historial. Los snapshots históricos se guardan
como un documento cifrado completo: el backend sigue descifrándolo para validar
su estructura y redactar la respuesta. No se afirma que viewer nunca produzca
descifrado en todo el CRM; el nombre del contacto también es información permitida.

## Comprobaciones con autenticación real

`tests/test_crm_authorization.py` crea una base SQLite independiente con claves
foráneas activas y datos cifrados ficticios. Los JWT se emiten en la fixture;
las peticiones pasan por la autenticación JWT y consulta de usuario/empresa
normales, sin reemplazar `require_authenticated_user` ni los servicios CRM.
No prueba el formulario de login. El ensayo sostenido PostgreSQL del incremento
anterior sí usó login normal y volvió a iniciar sesión tras reiniciar.

Las seis pruebas verifican:

- Viewer recibe registros actuales redactados sin descifrar contenido comercial
  en detalle, listado y seguimiento. Ficha, actividades, acciones y snapshots
  históricos tampoco exponen las cadenas privadas de la fixture. Admin recibe
  el registro completo y sin cambios.
- Otra empresa recibe `403` al pedir la ruta de la empresa ajena y `404` al usar
  sus propios prefijos con UUID ajenos. Cubre ficha, workspace, actividades,
  acciones, oportunidad, historial, contexto de conversación, sugerencia IA y
  filtros por contacto/conversación. Esos rechazos preceden al descifrado.
- No se puede crear una oportunidad con contacto/conversación ajenos, asignar un
  responsable ajeno, vincular una conversación ajena, registrar una actividad con
  oportunidad ajena ni revisar/confirmar una unión con contacto de otra empresa.
  Se mantienen filas de oportunidades, acciones, historial y auditoría y el
  registro original; las operaciones rechazadas no quedan parcialmente aplicadas.
- Cambiar el rol persistido a viewer aplica inmediatamente al token existente,
  incluso al reintentar una creación con clave válida ya usada. Usuario inactivo
  o empresa inactiva produce `403`; aumentar `auth_version` invalida el token con
  `401`. No se usa el rol anterior del cliente ni una sesión global de base de datos.
- Claims adicionales de rol/empresa en un JWT firmado para la fixture no sustituyen
  la pertenencia persistida. Firma incorrecta, algoritmo sin firma, expiración,
  falta de versión, usuario inexistente y ausencia de token reciben `401` sin
  descifrar contactos. No se guardan tokens en evidencia.
- Operador mantiene edición comercial y generación de versiones, pero no obtiene
  teléfono/correo, duplicados ni configuración de etapas. Viewer no puede editar
  ni consultar sugerencias de contenido. Las denegaciones no añaden auditoría de
  operaciones exitosas ni alteran historial/acciones.

## Validación

Las pruebas nuevas están aprobadas. Ruff y Black aprobados para los archivos
cambiados; mypy aprobado en `app tests` (576 archivos). La regresión de CRM y
autenticación pasó **43 pruebas**, además de las **6 pruebas nuevas**.
Hay una advertencia existente por la deprecación Starlette/httpx.
La suite general del incremento de rendimiento pasó 1121 casos y omitió 68;
ese número es el punto de partida, no incluye estas seis pruebas nuevas.

```powershell
Set-Location 'D:\BotWA Starter\.worktrees\luri-crm-increment-1'
$env:BOTWA_DATABASE_URL='sqlite:///:memory:'
& 'D:\BotWA Starter\.venv\Scripts\python.exe' -m pytest tests/test_crm_authorization.py tests/test_crm_request_session.py -q -p no:cacheprovider
```

La base de la fixture sólo vive en el directorio temporal de pytest. No modifica
la copia PostgreSQL del ensayo, los cambios previos ni datos de clientes reales.

## Límites y próximos pasos

Esta matriz es una regresión automatizada local, no una auditoría externa de
seguridad ni un pentest de producción. Quedan piloto con usuarios reales,
configuración y custodia de claves, políticas operativas y validación del entorno
definitivo. No se ha desplegado. La paginación estable del historial en el panel
continúa como el siguiente incremento autorizado.
