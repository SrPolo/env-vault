FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

ENV UV_PROJECT_ENVIRONMENT=/opt/venv
ENV PATH="/opt/venv/bin:${PATH}"

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY . .