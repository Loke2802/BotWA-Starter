# Backup diario de PostgreSQL fuera de DigitalOcean

En octubre de 2026 staging se perdió por completo, junto con sus backups, al
suspenderse la cuenta de DigitalOcean: los backups vivían en la misma cuenta.
Este job guarda una copia **cifrada** cada día en Cloudflare R2, fuera de
DigitalOcean.

## Cómo funciona

1. Un trabajo programado de App Platform (`kind: SCHEDULED`) arranca a las
   03:00 de Lima con esta imagen (`ops/backup/Dockerfile`, separada de la de Luri).
2. `luri-backup` ejecuta `pg_dump` en formato custom y comprueba que el archivo
   sea legible y tenga tablas con datos.
3. Lo cifra con [age](https://age-encryption.org) usando **solo la clave
   pública**. El job puede escribir backups, pero no leerlos.
4. Lo sube a R2 y verifica que el tamaño remoto coincida.
5. R2 borra las copias de más de 30 días con una regla de ciclo de vida del bucket.
   El job no tiene que borrar nada.

Si algo falla, el job termina con error y una línea JSON con el paso fallido.
Nunca imprime la URL de la base ni credenciales.

**Costo estimado:** el job corre 1–2 minutos al día y App Platform
[solo cobra mientras corre](https://docs.digitalocean.com/products/app-platform/details/pricing/),
así que serán céntimos al mes. R2 incluye
[10 GB al mes gratis y no cobra descargas](https://developers.cloudflare.com/r2/pricing/);
hoy la base cifrada ocupa menos de 1 MB por copia.

## Lo que el propietario configura (una sola vez)

### 1. Par de claves de cifrado (en tu PC)

```bash
docker run --rm alpine:3.20 sh -c "apk add -q age && age-keygen"
```

- La línea `# public key: age1…` es la **clave pública**: va a DigitalOcean.
- La línea `AGE-SECRET-KEY-…` es la **clave privada**: guárdala en tu gestor de
  contraseñas y en una copia fuera de línea. **Nunca** va a DigitalOcean ni a
  GitHub. Si se pierde, los backups no se pueden abrir.

### 2. Bucket en Cloudflare R2

1. Cloudflare → R2 → *Create bucket* → nombre `luri-backups`.
2. En el bucket → *Settings* → *Object lifecycle rules* → regla que borre
   objetos con más de 30 días.
3. R2 → *Manage API tokens* → *Create API token*:
   - Permisos: **Object Read & Write**.
   - Alcance: **solo** el bucket `luri-backups`.
   - Anota *Access Key ID*, *Secret Access Key* y el endpoint
     `https://<ACCOUNT_ID>.r2.cloudflarestorage.com`.

### 3. Job en DigitalOcean

App `luri-staging` → *Settings* → *App Spec* → añadir bajo `jobs:` (junto al job
de migración existente):

```yaml
  - name: luri-db-backup
    kind: SCHEDULED
    schedule:
      cron: "0 3 * * *"
      time_zone: America/Lima
    git:
      repo_clone_url: https://github.com/Loke2802/BotWA-Starter.git
      branch: master
    source_dir: ops/backup
    dockerfile_path: ops/backup/Dockerfile
    instance_count: 1
    instance_size_slug: apps-s-1vcpu-0.5gb
    envs:
      - key: BACKUP_DATABASE_URL
        # Mismo host privado que BOTWA_DATABASE_URL de la API, sin "+psycopg".
        value: postgresql://${luri-staging-db.USERNAME}:${luri-staging-db.PASSWORD}@<HOST_PRIVADO_DE_LA_BASE>:25060/defaultdb?sslmode=require
        type: SECRET
        scope: RUN_TIME
      - key: BACKUP_AGE_RECIPIENT
        value: <CLAVE_PUBLICA_age1...>
        scope: RUN_TIME
      - key: BACKUP_REMOTE
        value: r2:luri-backups/staging
        scope: RUN_TIME
      - key: RCLONE_CONFIG_R2_TYPE
        value: s3
        scope: RUN_TIME
      - key: RCLONE_CONFIG_R2_PROVIDER
        value: Cloudflare
        scope: RUN_TIME
      - key: RCLONE_CONFIG_R2_ENDPOINT
        value: https://<ACCOUNT_ID>.r2.cloudflarestorage.com
        scope: RUN_TIME
      - key: RCLONE_CONFIG_R2_ACCESS_KEY_ID
        value: <REEMPLAZAR_EN_LA_CONSOLA>
        type: SECRET
        scope: RUN_TIME
      - key: RCLONE_CONFIG_R2_SECRET_ACCESS_KEY
        value: <REEMPLAZAR_EN_LA_CONSOLA>
        type: SECRET
        scope: RUN_TIME
```

- Mientras este cambio no esté en `master`, usa `branch: ops/offsite-db-backup`.
- Escribe los dos valores de R2 directamente en la consola de DigitalOcean como
  variables cifradas. No los pegues en chats ni en archivos.
- La base solo acepta conexiones de la app `luri-staging`, y este job forma
  parte de esa app. Comprueba en *Databases → Trusted sources* que la app sigue
  listada.

### 4. Primera ejecución

Ejecuta el job una vez a mano desde la consola, o espera a las 03:00. El log
debe terminar en:

```json
{"status":"backup_uploaded","object":"luri-staging-<fecha>.dump.age","bytes":...,"tables_with_data":...}
```

y el objeto debe aparecer en el bucket.

## Restauración y simulacro mensual

En tu PC, con Docker, contra una base **vacía** (el script se niega a escribir
sobre una base con tablas):

```bash
docker build -t luri-backup ops/backup
```

```bash
docker run --rm \
  -v "/ruta/a/tu/clave-privada.txt:/run/secrets/age-identity:ro" \
  -e RESTORE_DATABASE_URL="postgresql://usuario:clave@host:5432/base_vacia" \
  -e BACKUP_REMOTE="r2:luri-backups/staging" \
  -e RCLONE_CONFIG_R2_TYPE=s3 -e RCLONE_CONFIG_R2_PROVIDER=Cloudflare \
  -e RCLONE_CONFIG_R2_ENDPOINT="https://<ACCOUNT_ID>.r2.cloudflarestorage.com" \
  -e RCLONE_CONFIG_R2_ACCESS_KEY_ID -e RCLONE_CONFIG_R2_SECRET_ACCESS_KEY \
  luri-backup luri-restore
```

Sin argumento restaura la copia más reciente; con un nombre de objeto, esa
copia. Al final muestra la versión de Alembic restaurada.

**Importante:** contactos, mensajes y credenciales de canales están cifrados con
las claves de la aplicación (`BOTWA_*_KEY`). Un backup sin esas claves no sirve
para leer esos datos. Guarda los valores `SECRET` de la app en tu gestor de
contraseñas, aparte de la clave privada de age.

## Verificación realizada antes del PR

PostgreSQL 17 local con el esquema completo (`20260921_0026`) y datos
sintéticos, sin red externa (backend `local` de rclone en lugar de R2):

- Backup subido y cifrado (cabecera `age-encryption.org/v1`), 53 tablas con datos.
- Restauración en una base vacía: mismas tablas, filas y versión de Alembic. El
  volcado de datos es idéntico salvo los tokens aleatorios `\restrict` que
  `pg_dump` 17 genera en cada ejecución.
- Restaurar sobre una base con datos se rechaza (`target_not_empty`).
- Con una contraseña errónea, el error no contiene la contraseña.
- `shellcheck` sin advertencias en ambos scripts.

Falta comprobarlo contra R2 real y desde DigitalOcean: depende de la
configuración anterior.
