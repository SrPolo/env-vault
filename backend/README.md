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

### Local vs staging/prod

| Entorno | Rol de migraciones (Alembic) | Rol de runtime (FastAPI) | Notas |
|---------|------------------------------|--------------------------|--------|
| **Local** (docker-compose) | `envvault_user` | `envvault_app` | `envvault_user` es **superuser** por conveniencia. `init-db.sh` crea `envvault_app` en el primer boot. |
| **Staging / prod** | `envvault_migrate` | `envvault_app` | Ambos **sin** `SUPERUSER` / `BYPASSRLS` / `CREATEROLE`. Bootstrap one-shot por un operador/superuser; no reutilizar el modelo local. |

| Rol | Quién lo usa | Privilegios esperados |
|-----|--------------|------------------------|
| `envvault_user` (solo local) | Alembic / ops en docker-compose | Dueño del schema. Superuser de conveniencia — **no** usar este patrón en staging/prod. |
| `envvault_migrate` (staging/prod) | Alembic vía `MIGRATION_POSTGRES_*` | Dueño del schema `public`. `LOGIN`, **sin** `SUPERUSER` / `BYPASSRLS` / `CREATEROLE`. Puede crear tablas, policies, functions y `GRANT` a `envvault_app`. |
| `envvault_app` | FastAPI en runtime + tests de integración | `LOGIN`, **sin** `BYPASSRLS`, sin `SUPERUSER`. Solo DML + `EXECUTE` explícito en funciones de negocio. |

Defaults en `app/core/config.py`:

- Runtime: `POSTGRES_USER=envvault_app` / `POSTGRES_PASSWORD=envvault_app_password`
- Migraciones (local): `MIGRATION_POSTGRES_USER=envvault_user` / `MIGRATION_POSTGRES_PASSWORD=…`
- Migraciones (staging/prod): `MIGRATION_POSTGRES_USER=envvault_migrate` / `MIGRATION_POSTGRES_PASSWORD=…`
  (Alembic lee `SQLALCHEMY_MIGRATION_URI`; override con `ENVVAULT_DATABASE_URL`)

Si conectas FastAPI como superuser, **RLS no se aplica** aunque exista
`FORCE ROW LEVEL SECURITY`.

### Bootstrap staging / prod (one-shot)

Ejecutar como operador/superuser (secret store / CI secrets — **nunca** passwords en git):

```bash
# 1) Rol de migraciones + ownership del schema public (+ extensiones pgcrypto/citext)
export MIGRATION_DB_PASSWORD='…'   # → luego MIGRATION_POSTGRES_PASSWORD
export DATABASE_URL='postgresql://ops_superuser:…@db-host:5432/envvault'
./scripts/provision_migration_role.sh

# 2) Rol de runtime
export APP_DB_PASSWORD='…'         # → luego POSTGRES_PASSWORD
./scripts/provision_app_role.sh

# 3) Migraciones como envvault_migrate (no como superuser)
export MIGRATION_POSTGRES_USER=envvault_migrate
export MIGRATION_POSTGRES_PASSWORD="$MIGRATION_DB_PASSWORD"
export POSTGRES_USER=envvault_app
export POSTGRES_PASSWORD="$APP_DB_PASSWORD"
uv run alembic upgrade head

# 4) Runtime: FastAPI con POSTGRES_* = envvault_app
```

Si el schema ya tenía objetos bajo otro rol (p. ej. bootstrap previo como
superuser), reasigna ownership en el paso 1:

```bash
./scripts/provision_migration_role.sh --transfer-from=old_owner_role
```

Orden mental: **crear migrate → crear app → Alembic como migrate → runtime como app**.

### Por qué los roles no se crean dentro de Alembic

1. **`CREATE ROLE` exige `CREATEROLE` o superuser.** Un runner de migraciones
   restringido (patrón habitual en staging/prod) **fallaría** si la migración
   intentara crear el rol.
2. **`LOGIN` + `PASSWORD` son secretos de entorno.** No pertenecen al historial
   de migraciones versionado en git.

Por eso:

- **Docker local (primer boot):** [`init-db.sh`](init-db.sh) crea `envvault_app`.
- **Volumen ya existente / repair local:** [`scripts/provision_app_role.sh`](scripts/provision_app_role.sh).
- **Staging / prod:** [`scripts/provision_migration_role.sh`](scripts/provision_migration_role.sh)
  + [`scripts/provision_app_role.sh`](scripts/provision_app_role.sh).
- Alembic **asume** que `envvault_app` ya existe y hace `GRANT … TO envvault_app`
  (falla con un mensaje claro si falta el rol).

### Requisitos del rol que ejecuta Alembic

| Operación | ¿Quién puede? |
|-----------|----------------|
| `CREATE TABLE` / policies / functions | Dueño del schema (`envvault_migrate` en staging/prod; `envvault_user` en local) |
| `CREATE ROLE` (**no lo hace Alembic**) | Superuser o `CREATEROLE` — scripts de provisioning / `init-db.sh` |
| `GRANT … TO envvault_app` | Dueño del schema (rol de migraciones) |
| `CREATE EXTENSION` | Superuser en bootstrap (`provision_migration_role.sh` / `init-db.sh`); Alembic asume que ya existen |

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
