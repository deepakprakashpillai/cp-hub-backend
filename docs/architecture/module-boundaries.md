# Module Boundaries

CP Hub remains a modular monolith. All features share one FastAPI application, one PostgreSQL
database, and one SQLAlchemy `AsyncSession` per request or command.

## Module Roles

- **Adapters** translate HTTP or command input into application calls. Admin and portal modules are
  adapters; they do not own domain behavior.
- **Query services** build read models and projections. Cross-feature presentation joins live in
  `app/modules/read_models/` rather than in leaf feature services.
- **Feature services** own one feature's mutations or queries. Bookings, batch schedule days, and
  batch groups expose separate use-case services instead of one all-purpose service.
- **Workflows** coordinate mutations across features. Student program switching, teacher
  deactivation, lead conversion, and account onboarding are explicitly named workflows.
- **Composition roots** assemble routers and model metadata. `app/api/router.py` and
  `app/db/models.py` are intentional dependency hubs.

## Dependency Rules

- `app/core` and `app/shared` cannot import feature modules.
- Models and schemas cannot import routes, role adapters, or services.
- Feature services cannot import admin, portal, or route modules.
- Cross-feature service composition belongs only in workflow modules, adapters, commands, or
  composition roots.
- Notification publishing is infrastructure invoked by a mutation in the same transaction; it is
  the documented leaf-service exception.
- Admin and portal adapters cannot depend on each other.
- File-level Python import cycles are forbidden.

`tests/architecture/test_module_boundaries.py` enforces these rules with AST analysis.

## Transaction Ownership

An outer workflow creates or receives one `AsyncSession`. Leaf operations participating in that
workflow flush without committing. The outer workflow commits exactly once. Standalone leaf
operations retain their existing commit behavior. This keeps row locks, notification outbox
records, and related entity changes atomic.

## Compatibility

The refactor changes internal Python organization only. HTTP paths, methods, security, defaults,
operation IDs, Pydantic component names, status codes, SQLAlchemy metadata, Alembic history,
commands, and notification payloads remain unchanged. Contract snapshot tests guard OpenAPI and
database metadata.
