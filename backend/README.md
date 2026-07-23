# EnvVault Backend

API FastAPI + PostgreSQL (RLS) + envelope encryption.

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- Docker (Postgres + Redis vía `docker-compose` en la raíz del monorepo)

## Quick start (local)

```bash
# Desde la raíz del monorepo
docker compose up -d postgres redis

cd backend
uv sync --group dev

# Migraciones como rol de ops (envvault_user). FastAPI usa envvault_app.
uv run alembic upgrade head

# Arrancar API (conecta como envvault_app → RLS efectivo)
uv run fastapi dev app/main.py
```

En el **primer** `docker compose up` de un volumen vacío, `init-db.sh` crea
`envvault_app` automáticamente. Si el volumen de Postgres ya existía sin ese
rol, o estás fuera de Docker:

```bash
export APP_DB_PASSWORD='envvault_app_password'
./scripts/provision_app_role.sh
uv run alembic upgrade head
```

## Database roles

Hay dos roles con responsabilidades distintas:

| Rol | Quién lo usa | Privilegios esperados |
|-----|--------------|------------------------|
| Rol de migraciones (local: `envvault_user`) | Alembic / ops | Dueño del schema. En docker-compose es **superuser** (conveniencia local). |
| `envvault_app` | FastAPI en runtime + tests de integración | `LOGIN`, **sin** `BYPASSRLS`, sin `SUPERUSER`. Solo DML + `EXECUTE` explícito en funciones de negocio. |

Defaults en `app/core/config.py`:

- Runtime: `POSTGRES_USER=envvault_app` / `POSTGRES_PASSWORD=envvault_app_password`
- Migraciones: `MIGRATION_POSTGRES_USER=envvault_user` / `MIGRATION_POSTGRES_PASSWORD=…`
  (Alembic lee `SQLALCHEMY_MIGRATION_URI`; override con `ENVVAULT_DATABASE_URL`)

Si conectas FastAPI como superuser, **RLS no se aplica** aunque exista
`FORCE ROW LEVEL SECURITY`.

### Por qué `envvault_app` no se crea dentro de Alembic

1. **`CREATE ROLE` exige `CREATEROLE` o superuser.** Un runner de migraciones
   restringido (patrón habitual en staging/prod) **fallaría** si la migración
   intentara crear el rol.
2. **`LOGIN` + `PASSWORD` son secretos de entorno.** No pertenecen al historial
   de migraciones versionado en git.

Por eso:

- **Docker (primer boot):** [`init-db.sh`](init-db.sh) crea el rol.
- **Volumen ya existente / staging / prod:** [`scripts/provision_app_role.sh`](scripts/provision_app_role.sh).
- Alembic **asume** que `envvault_app` ya existe y hace `GRANT … TO envvault_app`
  (falla con un mensaje claro si falta el rol).

### Requisitos del rol que ejecuta Alembic

| Operación | ¿Quién puede? |
|-----------|----------------|
| `CREATE TABLE` / policies / functions | Dueño del schema o superuser |
| `CREATE ROLE` (**no lo hace Alembic**) | Superuser o `CREATEROLE` — `init-db.sh` / script de provisioning |
| `GRANT … TO envvault_app` | Dueño del schema (rol de migraciones) |

En staging/prod conviene: bootstrap one-shot de `envvault_app` por un
operador/superuser + rol de migraciones con privilegios de schema (sin
necesidad de `CREATEROLE`).

## Tests

Los tests de integración levantan Postgres con testcontainers, crean
`envvault_app` **antes** de migrar (mismo contrato que init-db), migran, y
ejecutan la suite como ese rol para que FORCE RLS sea efectivo.

```bash
uv run pytest
```

## Useful commands

```bash
uv run alembic upgrade head
uv run alembic revision -m "message"
uv run ruff check .
uv run pytest
```
