# syntax=docker/dockerfile:1.7

FROM python:3.12-alpine@sha256:6d43704baacd1bfbe7c295d7f13079d5d8104ed33568873133f8fc69980419df

ARG APP_VERSION=0.2.1
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
RUN pip install --no-cache-dir -r /app/requirements.txt \
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

CMD ["gunicorn", "--bind", "0.0.0.0:3000", "--workers", "1", "--threads", "8", "--access-logfile", "-", "--error-logfile", "-", "app:app"]
