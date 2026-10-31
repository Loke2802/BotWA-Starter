#!/bin/sh
# Dump PostgreSQL, encrypt it for an age public key and upload it offsite.
# Only the public key lives here: this job can write backups but never read them.
# Never print the database URL or storage credentials.
set -eu

: "${BACKUP_DATABASE_URL:?missing BACKUP_DATABASE_URL}"
: "${BACKUP_AGE_RECIPIENT:?missing BACKUP_AGE_RECIPIENT}"
: "${BACKUP_REMOTE:?missing BACKUP_REMOTE, e.g. r2:bucket/staging}"

umask 077
stamp=$(date -u +%Y%m%dT%H%M%SZ)
name="luri-${BACKUP_LABEL:-staging}-${stamp}.dump.age"
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

fail() {
    # First error line only, with any URL removed: it may embed credentials.
    detail=""
    [ -s "$work/err" ] && detail=$(head -n 1 "$work/err" \
        | sed -E 's#[a-z0-9+.-]+://[^ "]+#<url>#g; s/["\\]//g' | cut -c 1-200)
    echo "{\"status\":\"backup_failed\",\"step\":\"$1\",\"detail\":\"$detail\"}" >&2
    exit 1
}

pg_dump --format=custom --no-owner --no-privileges \
    --file="$work/db.dump" --dbname="$BACKUP_DATABASE_URL" 2>"$work/err" \
    || fail pg_dump
# A dump that pg_restore cannot list is useless; stop before uploading it.
listing=$(pg_restore --list "$work/db.dump" 2>"$work/err") || fail verify_archive
tables=$(printf '%s\n' "$listing" | grep -c " TABLE DATA " || true)
[ "$tables" -gt 0 ] || fail empty_archive

age --encrypt --recipient "$BACKUP_AGE_RECIPIENT" \
    --output "$work/$name" "$work/db.dump" 2>"$work/err" || fail encrypt
rm -f "$work/db.dump"
bytes=$(wc -c <"$work/$name" | tr -d ' ')

rclone copyto --s3-no-check-bucket "$work/$name" "$BACKUP_REMOTE/$name" \
    2>"$work/err" || fail upload
remote_bytes=$(rclone lsf --format s "$BACKUP_REMOTE/$name" 2>"$work/err") \
    || fail readback
[ "$remote_bytes" = "$bytes" ] || fail size_mismatch

echo "{\"status\":\"backup_uploaded\",\"object\":\"$name\",\"bytes\":$bytes,\"tables_with_data\":$tables}"
