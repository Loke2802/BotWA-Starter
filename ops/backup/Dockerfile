# Offsite PostgreSQL backup job for Luri. Separate from the application image:
# the API never needs pg_dump, age or rclone.
FROM postgres:17-alpine@sha256:266d3c257594e195b309ae9d1805e54c788f1d7b375f56bf6c367aac6c917e7b

RUN apk add --no-cache age rclone

COPY --chmod=0555 backup.sh /usr/local/bin/luri-backup
COPY --chmod=0555 restore.sh /usr/local/bin/luri-restore

USER postgres
WORKDIR /tmp
ENTRYPOINT []
CMD ["luri-backup"]
