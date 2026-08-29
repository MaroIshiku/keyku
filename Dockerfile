# syntax=docker/dockerfile:1.7

FROM python:3.14-alpine@sha256:05b2b8b732ecd268fee8727a369f936f022d1321b59befd13c30ede22769dcdc

ARG APP_VERSION=0.3.1
ARG APP_BUILD_DATE=local
ARG GITHUB_SHA=local

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=3000 \
    PUBLIC_DIR=/app/public \
    ISHIKU_DATA_DIR=/data \
    APP_VERSION=$APP_VERSION \
    APP_BUILD_DATE=$APP_BUILD_DATE \
    GITHUB_SHA=$GITHUB_SHA

WORKDIR /app

COPY python/requirements.txt /app/requirements.txt
RUN apk add --no-cache --upgrade \
        libcrypto3=3.5.8-r0 \
        libssl3=3.5.8-r0 \
    && python -m pip install --no-cache-dir -r /app/requirements.txt \
    && python -m pip uninstall --yes pip \
    && python -c "import ensurepip, pathlib, shutil; shutil.rmtree(pathlib.Path(ensurepip.__file__).parent)" \
    && addgroup -S -g 10001 keyku \
    && adduser -S -D -H -u 10001 -G keyku keyku \
    && install -d -o keyku -g keyku -m 0750 /data

COPY --chown=10001:10001 python/app.py /app/app.py
COPY --chown=10001:10001 public /app/public

USER 10001:10001
EXPOSE 3000
VOLUME ["/data"]
STOPSIGNAL SIGTERM
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:3000/readyz', timeout=3).read()"

CMD ["gunicorn", "--bind", "0.0.0.0:3000", "--workers", "1", "--threads", "8", "--worker-tmp-dir", "/tmp", "--no-control-socket", "--access-logfile", "-", "--error-logfile", "-", "app:app"]
