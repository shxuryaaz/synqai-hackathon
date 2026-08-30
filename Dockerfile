FROM node:22-slim AS ui
WORKDIR /ui
COPY ui/package.json ui/package-lock.json ./
RUN npm ci
COPY ui .
RUN npm run build

FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
COPY . .
COPY --from=ui /ui/dist ui/dist
ENV PORT=10000
CMD ["sh", "-c", "uv run --no-sync python boot.py && uv run --no-sync uvicorn server:app --host 0.0.0.0 --port ${PORT}"]
