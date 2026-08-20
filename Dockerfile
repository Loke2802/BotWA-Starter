# syntax=docker/dockerfile:1
# Python 3.13.15 slim multi-arch index, updated by Dependabot.
ARG PYTHON_IMAGE=python:3.13.15-slim@sha256:ffb752e139c0a19692a43af8d8523b274222dd68eebad5d583b45c2201c6e30a

FROM ${PYTHON_IMAGE} AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN python -m venv /opt/venv
COPY requirements/runtime.lock /tmp/runtime.lock
RUN /opt/venv/bin/python -m pip install --require-hashes -r /tmp/runtime.lock

FROM ${PYTHON_IMAGE} AS runtime

ARG BOTWA_BUILD_SHA
ENV BOTWA_BUILD_SHA=${BOTWA_BUILD_SHA} \
    PATH=/opt/venv/bin:${PATH} \
    PYTHONPATH=/app \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

LABEL org.opencontainers.image.source="https://github.com/Loke2802/BotWA-Starter" \
      org.opencontainers.image.revision=${BOTWA_BUILD_SHA}

RUN apt-get update \
    && apt-get install --yes --no-install-recommends --only-upgrade \
        bsdutils \
        libblkid1 \
        liblastlog2-2 \
        libmount1 \
        libsmartcols1 \
        libuuid1 \
        login \
        mount \
        util-linux \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --uid 10001 --user-group botwa

WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
RUN rm -rf \
    /opt/venv/lib/python3.13/site-packages/pip \
    /opt/venv/lib/python3.13/site-packages/pip-*.dist-info \
    /usr/local/lib/python3.13/site-packages/pip \
    /usr/local/lib/python3.13/site-packages/pip-*.dist-info
COPY --chown=10001:10001 app/ ./app/
COPY --chown=10001:10001 alembic/ ./alembic/
COPY --chown=10001:10001 alembic.ini ./alembic.ini

USER 10001:10001
EXPOSE 8000
STOPSIGNAL SIGTERM
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/live', timeout=2).read()"]

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
