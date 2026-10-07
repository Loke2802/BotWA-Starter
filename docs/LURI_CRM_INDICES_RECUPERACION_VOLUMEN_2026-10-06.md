# Luri CRM — índices protegidos y recuperación con volumen

06/10/2026, rama `codex/luri-crm-increment-1`. Implementación y comprobación local
con PostgreSQL 17 y datos ficticios. Cambios y evidencia anteriores conservados.
Sin DigitalOcean, despliegue, llamadas a IA externa ni WhatsApp real.

## Búsqueda exacta protegida

La migración aditiva `20261006_0031` crea `contact_search_state` y
`contact_search_token`, sin modificar contactos ni historial. Los tokens son HMAC
SHA-256 separados por empresa, tipo de identidad y propósito. Teléfono y correo
siguen cifrados; el índice no almacena sus valores en claro. Permite varios correos
del mismo contacto y conserva las identidades de originales unidos para encontrar
la ficha principal. Un token compartido entre dos contactos no los une ni elimina.

`ContactSearchIndex` gestiona validación, consulta, sincronización y reconstrucción.
`CrmService` conserva permisos, filtros, paginación y resolución de alias. Las altas
del CRM, del registro público y de los canales entrantes sincronizan el índice
dentro de la transacción existente. Un rollback también revierte sus filas.

Cada estado guarda una copia de la identidad y del registro ya cifrados, además
del identificador de la clave. La consulta comprueba que coinciden con el contacto
actual. Solo los contactos sin estado válido usan el recorrido y descifrado de
respaldo. Esto evita falsos resultados o contactos ocultos por cambios SQL fuera
del servicio, datos antiguos o cambio de clave de búsqueda. Una consulta GET no
escribe ni reconstruye datos. El índice conserva patrones de igualdad dentro de
una empresa; HMAC no convierte esos patrones en información pública.

Las búsquedas sensibles requieren `contacts.read_sensitive` antes de consultar
o descifrar. La reconstrucción exige además `contacts.update`, ambos en la empresa
del actor. Las claves foráneas compuestas impiden asociar el índice de un contacto
a otra empresa; se comprobó su rechazo directamente en PostgreSQL.

Para datos existentes, `CrmService.rebuild_search_index(org, actor)` reconstruye en
lotes de 256 y confirma una transacción. El ejecutor local lo demuestra con el
owner autenticado. No se añadió una ruta pública de mantenimiento. Mantiene
bloqueos de filas hasta terminar: una reconstrucción en producción requiere
planificar su ejecución y medir la concurrencia. Aplicar la migración antes de
arrancar esta versión. Si no se reconstruye, el respaldo conserva resultados,
pero aún descifra los contactos pendientes.

Los tokens reutilizan la clave HMAC existente con separación de propósito.
Detectar un cambio mantiene la búsqueda mediante respaldo; rotar la clave de
identidad principal necesita también el procedimiento correspondiente para sus
hashes existentes. Este incremento no implementa esa rotación completa.

## Recuperación ejecutada y tiempos medidos

Se añadieron 10 000 contactos cifrados al recorrido existente: 10 003 contactos,
10 002 principales activos y 24 pares candidatos a duplicados. El ensayo comprobó
búsqueda, paginación, permisos, idempotencia, concurrencia de versiones, venta
ganada de 195.75 PEN, sus tres snapshots, actividades y acciones. Repitió las
comprobaciones después del reinicio y contra una base nueva restaurada del volumen
completo, con login normal.

| Búsqueda HTTP | Antes de reconstruir | Indexada | Tras reinicio | Restaurada con estadísticas |
| --- | ---: | ---: | ---: | ---: |
| Teléfono completo | 2.851 s | 0.364 s | 0.191 s | 0.312 s |
| Correo completo | 2.213 s | 0.188 s | 0.189 s | 0.403 s |

Son mediciones individuales en esta máquina, no garantías de producción ni un
ensayo de carga concurrente. `EXPLAIN ANALYZE` confirmó `ix_contact_search_exact`.
La comprobación de estados aún compara metadatos cifrados en SQL; no se afirma
coste constante. Nombre y detección de duplicados siguen recorriendo datos por
lotes. En la última comprobación las dos páginas de duplicados tardaron 9.242 s.

El primer restore conservó los datos, pero teléfono/correo tardaron 20.459/18.538 s.
El dump no incluye estadísticas del optimizador. Se añadió `vacuumdb --analyze-only`
tras `pg_restore` y se restauró de nuevo en otra base: los tiempos finales de la
tabla corresponden a esta segunda recuperación. El informe conserva las cinco
mediciones, incluida la primera restauración lenta.

`crm_volume_recovery.py` solo admite manifiestos ficticios, un contenedor
`luri-crm-local-*` y enlaces explícitos a localhost en el puerto indicado. Crea
una base nueva, ejecuta `pg_dump -Fc` y `pg_restore --exit-on-error`, refresca
estadísticas y compara SHA-256 de todas las filas de las 62 tablas. Comprueba que
la base original permanece igual. No usa `--clean`, no elimina bases y conserva
la evidencia de cada ejecución. `crm_recovery_fingerprint.py` comparte esta
comprobación con el ensayo anterior sin exportar el contenido de las filas.

Resultado: todas las huellas coinciden, 10 003 estados y 10 005 tokens restaurados,
cero estados pendientes/obsoletos, dos escrituras entre empresas rechazadas por
claves foráneas. Reconstruir el índice dejó intactas todas las tablas históricas.
El backup ficticio queda dentro del contenedor, en la ruta registrada en el
manifiesto; no constituye una copia externa de producción.

Evidencia estable:

- [Recorrido HTTP/SQL, tiempos y restricciones](validacion-local/index-volume-authorized-http.json).
- [Manifiesto restaurado y huellas de las 62 tablas](validacion-local/index-volume-recovery.json).
- [Búsqueda en el panel restaurado](validacion-local/index-volume-search.png).

Pruebas ejecutadas: suite general **1096 passed, 68 skipped, 1 warning**; **7 pruebas
PostgreSQL** aprobadas; **16 pruebas** de protección del ejecutor/recuperación
aprobadas, incluidas cinco nuevas. Las cuatro pruebas nuevas del índice cubren
descifrado limitado a resultados, reconstrucción sin cambios históricos ni tokens
repetidos, cambios SQL/clave, permisos/empresa y rollback. Las omisiones de la suite
general no equivalen a validación de esos casos. La advertencia Starlette/httpx
es la deprecación existente. Ruff, Black, mypy y revisión de espacios aprobados.

## Repetir y comprobar en el panel

Desde el checkout independiente, con el contenedor local existente activo y el
puerto 8770 libre:

```powershell
Set-Location 'D:\BotWA Starter\.worktrees\luri-crm-increment-1'
& 'D:\BotWA Starter\.venv\Scripts\python.exe' -m scripts.rehearse_crm_journey_local --container luri-crm-local-recovery --output-dir docs/validacion-local/journey --contact-count 10000
```

Genera bases y una carpeta nueva. El resultado final debe indicar `passed`,
`database_restored: true` y `optimizer_statistics_refreshed: true` dentro de
`volume_restore`. El ejecutor detiene únicamente su servidor temporal al terminar.

Panel comprobado: <http://127.0.0.1:8773/portal>. Cuenta ficticia
`organization_owner@local-crm.example.test`, contraseña de demo `SyntheticCRM2026!`.

1. **Clientes** → **Teléfono completo**, buscar `+1 (203) 000-2001` y pulsar
   **Aplicar filtros**: un resultado. **Correo completo**, buscar
   `TARDIO@example.test`: dos resultados.
2. **Calidad de clientes**: 10 002 examinados, 24 coincidencias; **Siguiente**
   muestra la segunda página. La unión continúa requiriendo revisión manual.
3. **Conversaciones** → abrir la conversación → **Abrir ficha del cliente**:
   conserva la oportunidad `Recorrido integral local 4cf2c2d9`, etapa Ganada,
   importe 195.75 PEN, responsable y tres versiones del historial.
4. Con `viewer@local-crm.example.test` y la misma clave ficticia, solo aparece
   búsqueda por nombre. Las solicitudes sensibles se rechazan en el servidor.

Si se detiene esta demo, volver a abrirla desde este checkout:

```powershell
& 'D:\BotWA Starter\.venv\Scripts\python.exe' -m scripts.serve_crm_local --manifest docs/validacion-local/index-volume-recovery.json --port 8773
```

Las bases de esta máquina no se incluyen en Git. En otro equipo, ejecutar el ensayo
y usar su manifiesto generado. La automatización prueba HTTP/SQL; los clics del
panel se verificaron aparte, con datos reales de la base ficticia restaurada.

## Pendientes

Aplicar `0031`, reconstruir índices y validar tiempos en el entorno definitivo;
staging/piloto con usuarios y datos reales; carga concurrente; copias externas y
recuperación con custodia de las claves; optimizar nombre y detección de duplicados
si el volumen lo requiere. La implementación está entregada en la rama local.
La recuperación y los permisos están comprobados en PostgreSQL local; despliegue
y validación real siguen pendientes.
