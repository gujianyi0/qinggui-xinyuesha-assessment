FROM python:3.13-slim
WORKDIR /app
COPY --from=ghcr.io/astral-sh/uv:0.9.8 /uv /usr/local/bin/uv
COPY pyproject.toml uv.lock ./
COPY backend ./backend
COPY integrations ./integrations
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --extra embeddings --link-mode=copy
COPY migrations ./migrations
COPY alembic.ini ./
COPY data ./data
COPY rulings ./rulings
COPY scripts ./scripts
COPY evaluations ./evaluations
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
