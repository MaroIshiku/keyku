FROM python:3.12-alpine

ARG APP_VERSION=0.2.1
ARG APP_BUILD_DATE=local
ARG GITHUB_SHA=local

ENV PYTHONUNBUFFERED=1 \
    PORT=3000 \
    PUBLIC_DIR=/app/public \
    ISHIKU_DATA_DIR=/data \
    APP_VERSION=$APP_VERSION \
    APP_BUILD_DATE=$APP_BUILD_DATE \
    GITHUB_SHA=$GITHUB_SHA

WORKDIR /app

COPY python/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY python/app.py /app/app.py
COPY public /app/public

EXPOSE 3000
VOLUME ["/data"]

CMD ["gunicorn", "--bind", "0.0.0.0:3000", "--workers", "1", "--threads", "8", "--access-logfile", "-", "--error-logfile", "-", "app:app"]
