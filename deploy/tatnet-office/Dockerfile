# Сервер ручной валидации: проектный офис без Claude, Telegram, терминала и файлов проектов.
# Сборка из корня клона: docker build -f deploy/tatnet-office/Dockerfile -t fakt-runs:<версия> .
FROM node:22-slim AS web
WORKDIR /w/web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1
RUN useradd --system --uid 1001 --no-create-home --shell /usr/sbin/nologin office \
    && mkdir -p /app /data && chown office:office /data
WORKDIR /app
COPY requirements.txt requirements.lock ./
RUN pip install --require-hashes -r requirements.lock
COPY src ./src
COPY config ./config
COPY scripts/run_office.py ./scripts/run_office.py
COPY docs/USER-GUIDE.md ./docs/USER-GUIDE.md
COPY --from=web /w/web/dist ./web/dist
USER office
ENV SESSION_DATABASE_PATH=/data/sessions.db
VOLUME ["/data"]
EXPOSE 8765
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8765/api/health', timeout=4).status == 200 else 1)"]
CMD ["python", "scripts/run_office.py", "--host", "0.0.0.0", "--port", "8765"]
