FROM node:26-slim AS web

WORKDIR /web
# Manifests first, so the npm ci layer is reused until dependencies change.
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOST=0.0.0.0 \
    PORT=9685

WORKDIR /app

COPY pyproject.toml ./
COPY app ./app
RUN pip install --no-cache-dir .

COPY --from=web /web/dist ./web-dist
ENV BOOPBOX_WEB_DIR=/app/web-dist

EXPOSE 9685

# Startup (schema check, migrations) finishes before the server listens, so a
# passing check also means the database is ready.
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD ["python", "-c", "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.environ.get('PORT', '9685') + '/health', timeout=4)"]

CMD ["sh", "-c", "uvicorn app.main:create_app --factory --host \"$HOST\" --port \"$PORT\""]
