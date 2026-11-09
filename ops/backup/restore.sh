#!/bin/sh
# Restore one offsite backup into an EMPTY database. Run it on the owner's
# machine with the private age identity mounted read-only; it never runs in
# DigitalOcean. Usage: luri-restore [object-name]  (default: newest object)
set -eu

: "${RESTORE_DATABASE_URL:?missing RESTORE_DATABASE_URL}"
: "${BACKUP_REMOTE:?missing BACKUP_REMOTE}"
identity="${RESTORE_AGE_IDENTITY:-/run/secrets/age-identity}"
[ -r "$identity" ] || { echo '{"status":"restore_failed","step":"identity"}' >&2; exit 1; }

umask 077
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

fail() {
    # First error line only, with any URL removed: it may embed credentials.
    detail=""
    [ -s "$work/err" ] && detail=$(head -n 1 "$work/err" \
        | sed -E 's#[a-z0-9+.-]+://[^ "]+#<url>#g; s/["\\]//g' | cut -c 1-200)
    echo "{\"status\":\"restore_failed\",\"step\":\"$1\",\"detail\":\"$detail\"}" >&2
    exit 1
}

# Refuse to write over existing data: restoring into a live database is never
# what a recovery drill or a rebuild wants.
existing=$(psql --dbname="$RESTORE_DATABASE_URL" --tuples-only --no-align \
    --command="SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public'" \
    2>"$work/err") || fail connect
[ "$existing" = "0" ] || fail target_not_empty

object="${1:-$(rclone lsf --files-only "$BACKUP_REMOTE" | grep '\.dump\.age$' | sort | tail -n 1)}"
[ -n "$object" ] || fail no_backup_found

rclone copyto "$BACKUP_REMOTE/$object" "$work/backup.age" 2>"$work/err" \
    || fail download
age --decrypt --identity "$identity" --output "$work/db.dump" "$work/backup.age" \
    2>"$work/err" || fail decrypt
pg_restore --no-owner --no-privileges --exit-on-error \
    --dbname="$RESTORE_DATABASE_URL" "$work/db.dump" 2>"$work/err" \
    || fail pg_restore

version=$(psql --dbname="$RESTORE_DATABASE_URL" --tuples-only --no-align \
    --command="SELECT version_num FROM alembic_version" 2>/dev/null || true)
echo "{\"status\":\"restored\",\"object\":\"$object\",\"alembic_version\":\"$version\"}"
