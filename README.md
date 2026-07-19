# CP Hub Backend

Backend API for an online IELTS learning platform management system.

## Stack

- FastAPI
- PostgreSQL
- SQLAlchemy 2.x async ORM
- Alembic migrations
- Pydantic v2
- uv
- pytest
- ruff

## Project Shape

```txt
app/
  main.py
  api/
    router.py
    deps.py
  core/
    config.py
    exceptions.py
    pagination.py
  db/
    base.py
    session.py
  modules/
    users/
    students/
    teachers/
    schedules/
    classes/
    bookings/
    leads/
  shared/
    enums.py
    types.py
    utils.py
alembic/
tests/
```

## Local Setup

```bash
uv sync
cp .env.example .env
docker compose up -d postgres
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

Postgres runs locally through Docker Compose:

```txt
host: localhost
port: 5432
database: cp_hub
user: postgres
password: postgres
```

Useful database commands:

```bash
docker compose up -d postgres
docker compose ps
docker compose down
```

To delete the local database data completely:

```bash
docker compose down -v
```

Health check:

```txt
GET /health
```

API root:

```txt
/api/v1
```
