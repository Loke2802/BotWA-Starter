# Luri CRM — búsqueda global y duplicados completos

06/10/2026. Rama independiente `codex/luri-crm-increment-1`. Conserva las entregas
anteriores. Implementación y validación local; no despliegue ni DigitalOcean.

## Cambios entregados

1. **Clientes → Buscar en toda la empresa** consulta todos los contactos que
   cumplen los filtros. Nombre admite palabras parciales en cualquier orden,
   sin distinguir acentos o mayúsculas: `perez josé` encuentra `José Pérez tardío`.
   Teléfono completo con código de país y correo completo usan coincidencia exacta
   normalizada. Los resultados y el total vienen del servidor; paginar conserva
   búsqueda, clasificación, estado y seguimientos pendientes.
2. **Calidad de clientes** examina todos los contactos principales activos de la
   empresa. Se elimina el corte de 2000. Informa contactos examinados, total de
   coincidencias y páginas de 20. Un grupo propone cada ficha contra su primer
   miembro; combina razones cuando nombre y correo/teléfono coinciden. No genera
   todas las combinaciones de un grupo ni une clientes automáticamente.

El permiso `contacts.read` permite buscar por nombre. Teléfono/correo requieren
`contacts.read_sensitive`; el panel sólo ofrece esos modos a usuarios autorizados.
El backend aplica el permiso antes de descifrar identidades. La revisión/unión
conserva todos sus permisos anteriores; operator/viewer no pueden unir fichas.

Todas las consultas y redirecciones están limitadas por empresa. Buscar un nombre,
teléfono o correo de una ficha unida devuelve su principal activo una sola vez;
el filtro Archivados permite encontrar el original. Conversaciones, actividades,
oportunidades y sus historiales conservan el comportamiento previo.

## Organización y límites

- `app/application/contacts/search.py`: normalización y comparación transitoria.
- `app/application/contacts/crm.py`: permisos, filtros, total y paginación global.
- `app/infrastructure/repositories/crm_identity.py`: resolución de alias por empresa.
- `app/application/crm/duplicates.py`: escaneo completo y páginas de candidatos.
- `app/portal/crm.js` y `customer-quality.js`: controles y presentación.
- `scripts/crm_search_dataset.py`: contactos ficticios cifrados para pruebas;
  no añade un endpoint público para sembrar datos.
- El ejecutor del recorrido anterior añade búsqueda y volumen, y los repite
  después de reiniciar el servidor contra la misma base PostgreSQL.

Sin migración nueva: esquema `0030`. No se persiste un índice con datos personales
en texto plano. Se leen contactos por lotes de 256 y sólo se construye la página
solicitada. Para obtener totales exactos se vuelve a recorrer la empresa en cada
consulta. El tiempo es lineal en el número de contactos; el mapa de identidades
de duplicados y el de alias crecen con la empresa. Esto elimina el truncamiento,
pero no acredita búsqueda instantánea ni memoria constante para volúmenes enormes.

Los resultados son estables mientras no cambien los datos. Inserciones/uniones
concurrentes pueden cambiar el total o la posición entre solicitudes; se debe
actualizar y revisar la vista previa vigente antes de unir.

## Ejecutar y comprobar

Desde el checkout independiente, con el contenedor PostgreSQL local existente
`luri-crm-local-recovery` en `127.0.0.1:15437` y `8770` libre:

```powershell
Set-Location 'D:\BotWA Starter\.worktrees\luri-crm-increment-1'
& 'D:\BotWA Starter\.venv\Scripts\python.exe' -m scripts.rehearse_crm_journey_local --container luri-crm-local-recovery --output-dir docs/validacion-local/journey
```

Por defecto añade 10 000 contactos cifrados. `--contact-count` admite como mínimo
2100, para superar siempre el corte anterior. Cada ensayo prepara bases propias,
conserva bases y evidencia anteriores, y detiene sólo su servidor temporal.
La conexión de la demo local permite 15 segundos de espera para Docker; las
respuestas erróneas siguen haciendo fallar el ensayo, sin reintentos que las oculten.

Comprueba nombres tardíos después del contacto 2000, teléfono formateado, correo
con mayúsculas, 23 resultados en tres páginas sin repetir IDs, permisos viewer,
aislamiento entre empresas, candidatos tardíos y paginación de duplicados. Verifica
además venta, historial, actividades, métricas, número exacto de contactos y columnas
cifradas en SQL. Repite estas comprobaciones después de reiniciar e iniciar sesión.

Los JSON de evidencia no guardan tokens ni contraseñas; sólo datos ficticios.
`browser_automation: false` identifica correctamente que el comando prueba HTTP/SQL.
Los controles del navegador se verifican aparte, con fixtures y con el panel real.

## Pruebas ejecutadas y evidencia

- Suite completa: **1092 aprobadas, 68 omitidas**, una advertencia de deprecación
  Starlette/httpx ya existente. Tiempo: 711.27 segundos. Los casos omitidos requieren
  integraciones externas o configuraciones explícitas; no se consideran aprobados.
- Pruebas focalizadas de búsqueda, CRM y crecimiento: **19 aprobadas**. Incluyen
  páginas disjuntas después del contacto 2000, permisos antes de descifrar,
  filtros combinados y una cadena de uniones con original archivado conservado.
- PostgreSQL explícito: **7 aprobadas**; concurrencia de fichas, oportunidades,
  etapas, actividades y unión, más restricciones entre empresas.
- Navegador con API simulada: **27 aprobadas** (búsqueda 5, calidad/métricas 6,
  ficha comercial 11 y recorrido original 5). El caso nuevo pulsa el botón de
  envío explícito del formulario de búsqueda.
- Recorrido HTTP/SQL autenticado y reinicio: **aprobado**, con **10 003 contactos
  persistidos**, **10 002 principales activos examinados** y **24 candidatos**.
  Ninguna clave/token se exporta. IA externa apagada.
- Ruff, Black, mypy (408 archivos), sintaxis de los módulos JS y `git diff --check`:
  aprobados.

Muestras locales registradas: búsquedas entre **1.54 y 2.82 segundos** por petición;
dos páginas de duplicados entre **5.62 y 8.43 segundos** en conjunto. Son observaciones
de esta máquina y dataset ficticio, no una prueba de carga ni una garantía en producción.

El primer intento se conservó como fallido por timeout de conexión durante login.
La ejecución posterior pasó completa, sin ignorar respuestas HTTP erróneas, antes
y después del reinicio. Evidencia estable:
[informe HTTP/SQL y tiempos](validacion-local/search-authorized-http.json),
[manifiesto de restauración](validacion-local/search-recovery.json),
[búsqueda por nombre](validacion-local/search-name.png),
[segunda página global](validacion-local/search-page-2.png) y
[segunda página de duplicados](validacion-local/search-duplicates-page-2.png).

## Recorrido en el panel

Panel de la base comprobada: `http://127.0.0.1:8772/portal`. Login normal ficticio:
`organization_owner@local-crm.example.test`, clave de demo `SyntheticCRM2026!`.

1. **Clientes** → **Buscar por: Nombre**, introducir `perez josé` y pulsar
   **Aplicar filtros**: aparecen los dos contactos tardíos.
2. **Teléfono completo** → `+1 (203) 000-2001`: un resultado.
   **Correo completo** → `TARDIO@example.test`: dos resultados.
3. **Nombre** → `grupo marta`: 23 resultados. **Siguiente** conserva el término
   y muestra los tres restantes, `21–23 de 23`.
4. **Calidad de clientes**: 10 002 examinados y 24 coincidencias. **Siguiente**
   abre la segunda página. **Revisar unión** conserva la vista previa y confirmación
   manual existentes; este ensayo de búsqueda no ejecuta uniones adicionales.
5. Con viewer, la búsqueda sólo ofrece Nombre. Las peticiones de teléfono/correo
   y duplicados se rechazan en el servidor, como comprueba el ejecutor autenticado.

Para abrir esta base si el servidor de demo no sigue activo:

```powershell
& 'D:\BotWA Starter\.venv\Scripts\python.exe' -m scripts.serve_crm_local --manifest docs/validacion-local/search-recovery.json --port 8772
```

Las bases de esta máquina no se incluyen en Git. Un clon debe ejecutar el ensayo
para crear su propia base y usar el nuevo manifiesto generado.

## Pendientes

Despliegue/staging, datos reales y piloto con usuarios; carga concurrente y tiempos
en el servidor definitivo. Para empresas mucho mayores habrá que evaluar índices
de búsqueda cifrada o procesos de detección persistidos con permisos e invalidación.
No se habilitaron IA externa ni WhatsApp real. La prueba local no acredita ninguno
de esos pasos.
