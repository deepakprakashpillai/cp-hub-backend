FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN pip install --no-cache-dir uv==0.11.25
COPY pyproject.toml uv.lock README.md ./
COPY app ./app
RUN uv sync --locked --no-dev
COPY alembic.ini ./
COPY alembic ./alembic
EXPOSE 8000
CMD ["uv", "run", "--locked", "--no-dev", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
