# Engineering Standards

## Primary Architecture
This repository follows Feature First Architecture.
Never organize code by technical layers such as:
* controllers/
* services/
* repositories/
at the application root.
Always organize by business domain or feature.

## Root Structure
```
frontend/
backend/
shared/
infrastructure/
docs/
scripts/
tests/
.github/
```

## Frontend Rules
All frontend code belongs inside:
```
frontend/src/features/
```

Example:
```
features/
  users/
  auth/
  dashboard/
  reports/
```

Every feature must contain:
```
api/
components/
hooks/
pages/
store/
types/
constants/
utils/
tests/
```

No standalone files directly inside feature folders.

Shared, cross-feature UI (buttons, layout shells, design system primitives) belongs in `frontend/src/shared/`, never duplicated inside a feature.

## Backend Rules
All backend code belongs inside:
```
backend/app/modules/
```

Example:
```
modules/
  users/
  auth/
  reports/
  notifications/
```

Every module must contain:
```
router.py
service.py
repository.py
schemas.py
models.py
dependencies.py
constants.py
exceptions.py
tests/
```

Business logic belongs only in `service.py`.
Database logic belongs only in `repository.py`.
API logic belongs only in `router.py`.
Validation/serialization belongs only in `schemas.py`.
ORM models belong only in `models.py`.
Module-specific exceptions belong only in `exceptions.py`, and must subclass a shared base exception from `shared/`.

### Backend Root-Level Files
```
backend/
  app/
    modules/
    core/          # settings, security, startup/shutdown, middleware
    db/             # session/engine setup, base model, migrations entrypoint
    main.py         # app instantiation only — no business logic
  migrations/       # Alembic or equivalent
  tests/
```

## Shared Code
Reusable code belongs in:
```
shared/types
shared/constants
shared/utils
```
Do not duplicate logic. If two modules/features need the same logic, it moves to `shared/` — it is never copy-pasted.

## Naming Conventions
Folders: `kebab-case`
React Components: `PascalCase`
Hooks: `useXxx.ts`
Python Classes: `PascalCase`
Python Functions: `snake_case`
Python Files/Modules: `snake_case`
Constants (both languages): `UPPER_SNAKE_CASE`
Database tables: `snake_case`, plural (`users`, `report_entries`)
Environment variables: `UPPER_SNAKE_CASE`, prefixed by domain where relevant (`AUTH_JWT_SECRET`)

## Import Rules
Use absolute imports only. Never use deep relative imports.

Bad:
```
../../../components/Button
```
Good:
```
@/features/users
```
or
```python
from app.modules.users.service import UserService
```

## API Conventions
All routes are versioned: `/api/v1/...`.
Route definitions live only in `router.py`; routers are registered centrally in `app/main.py` or a dedicated `app/core/api.py`, never scattered.
Request/response shapes are always defined via `schemas.py` — never return raw ORM models or untyped dicts from an endpoint.
Errors return a consistent shape (e.g. `{ "error": { "code": ..., "message": ... } }`) defined once in `shared/` and reused across modules.

## Error Handling & Logging
Raise domain-specific exceptions from `exceptions.py`; do not raise generic `Exception` or bare HTTP errors from inside `service.py`.
Exceptions are translated to HTTP responses at the router/middleware layer only, never inside `service.py` or `repository.py`.
Use structured logging (key-value, not string concatenation). Never log secrets, tokens, or PII.

## Configuration & Environments
All config is loaded through `app/core/config.py` (backend) or a single typed config module (frontend) — no scattered `os.getenv()` / `process.env` calls in business logic.
`.env.example` must be kept in sync with any new environment variable; never commit `.env`.

## File Creation Rules
Before creating a file:
1. Search existing implementation.
2. Reuse existing code.
3. Follow feature/module architecture.
4. Avoid duplicate utilities.
5. Avoid duplicate services.

## Testing
New business logic requires tests.
Tests must be colocated with the feature or module (in its `tests/` subfolder), not centralized in a single top-level `tests/` dump — the root `tests/` folder is reserved for integration/e2e tests that span multiple modules or features.

## Database Rules
All schema changes must be migration based.
Never modify schema manually.
One migration per logical change; never bundle unrelated schema changes into a single migration.

## Git Rules
Feature branches only:
```
feature/<name>
bugfix/<name>
hotfix/<name>
```
Never commit directly to `main`.
Commit messages follow Conventional Commits (`feat:`, `fix:`, `refactor:`, `chore:`).

## AI Agent Rules
When generating code:
1. Follow existing patterns.
2. Do not introduce new architectural patterns.
3. Prefer modifying existing files over creating new files.
4. Minimize file creation.
5. Maintain consistency over creativity.
6. Never place business logic in `router.py`, in React components, or in database/repository code — keep it isolated in `service.py` or feature hooks/store.
7. When uncertain which module/feature a piece of logic belongs to, ask before creating a new top-level folder.

Architecture consistency is the highest priority.

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

When the user types `/graphify`, invoke the `skill` tool with `skill: "graphify"` before doing anything else.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- Dirty graphify-out/ files are expected after hooks or incremental updates; dirty graph files are not a reason to skip graphify. Only skip graphify if the task is about stale or incorrect graph output, or the user explicitly says not to use it.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).
