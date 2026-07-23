# EnvVault Backend

API FastAPI + PostgreSQL (RLS) + envelope encryption.

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- Docker (Postgres + Redis vía `docker-compose` en la raíz del monorepo)
- `psql` en el PATH (solo para provisioning de roles)

## Quick start (local)

```bash
# Desde la raíz del monorepo
docker compose up -d postgres redis

cd backend
cp .env.example .env   # si existe; o exporta las vars de app/core/config.py

# 1) Rol de aplicación (NO es un paso de Alembic — ver sección siguiente)
export APP_DB_PASSWORD='choose-a-strong-password'
./scripts/provision_app_role.sh

# 2) Migraciones (como rol dueño del schema / superuser local)
uv sync --group dev
uv run alembic upgrade head

# 3) Privilegios DML sobre tablas ya creadas
./scripts/provision_app_role.sh --grants

# 4) Tests
uv run pytest
```

La app en runtime **debe** conectarse como `envvault_app`, no como el usuario
de migraciones. Si conectas como superuser (`POSTGRES_USER` de docker-compose),
**RLS no se aplica** aunque exista `FORCE ROW LEVEL SECURITY`.

## Database roles

Hay dos roles con responsabilidades distintas:

| Rol | Quién lo usa | Privilegios esperados |
|-----|--------------|------------------------|
| Rol de migraciones (local: `envvault_user`) | Alembic / ops | Dueño del schema. En docker-compose es **superuser** (conveniencia local). |
| `envvault_app` | FastAPI en runtime + tests de integración | `LOGIN`, **sin** `BYPASSRLS`, sin `SUPERUSER`. Solo DML + `EXECUTE` explícito en funciones de negocio. |

### Por qué `envvault_app` no se crea dentro de Alembic

1. **`CREATE ROLE` exige `CREATEROLE` o superuser.** Un runner de migraciones
   restringido (patrón habitual en staging/prod) **fallaría** en
   `c3f8a91d2e47` si la migración intentara crear el rol.
2. **`LOGIN` + `PASSWORD` son secretos de entorno.** No pertenecen al historial
   de migraciones versionado en git.

Por eso:

- Alembic **asume** que `envvault_app` ya existe y solo hace
  `GRANT EXECUTE … TO envvault_app` (falla con un mensaje claro si falta el rol).
- El script [`scripts/provision_app_role.sh`](scripts/provision_app_role.sh)
  es el único lugar que crea/actualiza el rol **con**
  `LOGIN` + `PASSWORD`.

```bash
# Obligatorio antes de `alembic upgrade` cuando la revisión c3f8a91d2e47
# (o posteriores que GRANT a envvault_app) aún no está aplicada:
export APP_DB_PASSWORD='...'
./scripts/provision_app_role.sh

uv run alembic upgrade head

# Después de que existan las tablas:
./scripts/provision_app_role.sh --grants
```

Equivalente manual (mismo efecto que el script):

```sql
-- Conectar como superuser o rol con CREATEROLE
CREATE ROLE envvault_app
  LOGIN
  PASSWORD '...'
  NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;

-- Si el rol ya existía sin LOGIN (legado):
ALTER ROLE envvault_app WITH LOGIN PASSWORD '...';
```

### Requisitos del rol que ejecuta Alembic

| Operación | ¿Quién puede? |
|-----------|----------------|
| `CREATE TABLE` / policies / functions | Dueño del schema o superuser |
| `CREATE ROLE` (**no lo hace Alembic**) | Superuser o `CREATEROLE` — solo el script de provisioning |
| `GRANT EXECUTE … TO envvault_app` | Dueño de la función (el rol de migraciones, tras crear la función) |

**Estado actual en docker-compose:** `POSTGRES_USER=envvault_user` es el
superuser del cluster Postgres del contenedor. Por eso `provision_app_role.sh`
y `alembic upgrade` funcionan con las mismas credenciales en local. Eso **no**
garantiza el mismo layout en producción: allí conviene un rol de migraciones
con privilegios de schema (sin necesidad de `CREATEROLE`) + un bootstrap
one-shot de `envvault_app` hecho por un operador/superuser.

## Tests

Los tests de integración levantan Postgres con testcontainers, crean
`envvault_app` **antes** de migrar (mismo contrato que el script), migran, y
ejecutan la suite como ese rol para que FORCE RLS sea efectivo.

```bash
uv run pytest
```

## Useful commands

```bash
uv run alembic upgrade head
uv run alembic revision -m "message"
uv run ruff check .
uv run pytest -v
```
