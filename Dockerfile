FROM node:24-slim AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --silent
COPY frontend/ ./
RUN npx vite build --logLevel warn

FROM python:3.13-slim
RUN pip install --no-cache-dir uv==0.9.18 && useradd --system --create-home app
WORKDIR /srv
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY app ./app
COPY alembic.ini ./
COPY scripts/docker-entry.sh /entry.sh
COPY --from=frontend /build/dist ./frontend/dist
RUN mkdir /data && chmod +x /entry.sh
ENV TALLY_DB_PATH=/data/tally.db TALLY_SECURE_COOKIES=1 PYTHONDONTWRITEBYTECODE=1
EXPOSE 8080
ENTRYPOINT ["/entry.sh"]
CMD ["/srv/.venv/bin/uvicorn", "--factory", "app.main:get_app", "--host", "0.0.0.0", "--port", "8080", "--proxy-headers", "--no-access-log"]
