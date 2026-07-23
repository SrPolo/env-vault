#!/usr/bin/env bash
# =============================================================================
# Provision the migration / schema-owner DB role `envvault_migrate`.
#
# Staging / production only. Local docker-compose keeps using POSTGRES_USER
# (envvault_user) as a superuser for convenience — do NOT force this role
# into the local Docker path (init-db.sh / compose stay unchanged).
#
# WHY A DEDICATED MIGRATE ROLE
#   - Alembic needs to own the schema (CREATE TABLE, policies, functions,
#     GRANT to envvault_app). That does not require SUPERUSER / BYPASSRLS /
#     CREATEROLE.
#   - CREATE ROLE stays outside Alembic (needs CREATEROLE or superuser).
#   - LOGIN + PASSWORD are environment secrets and must not live in git or
#     migration history.
#
# REQUIREMENTS
#   - Connect as a PostgreSQL superuser (or a role that can CREATE ROLE and
#     ALTER SCHEMA OWNER). One-shot operator bootstrap.
#
# USAGE
#   export MIGRATION_DB_PASSWORD='choose-a-strong-password'
#   # optional overrides:
#   # export MIGRATION_DB_USER=envvault_migrate
#   # export DATABASE_URL=postgresql://ops_superuser:secret@db-host:5432/envvault
#   ./scripts/provision_migration_role.sh
#
#   # If objects already exist under another role (e.g. after a lift from a
#   # superuser-owned bootstrap), reassign them in the current database:
#   ./scripts/provision_migration_role.sh --transfer-from=old_owner_role
#
# Typical staging/prod bootstrap order (superuser one-shot, then CI):
#   1) ./scripts/provision_migration_role.sh   # envvault_migrate + schema owner
#   2) ./scripts/provision_app_role.sh         # envvault_app (LOGIN/PASSWORD)
#   3) Alembic as envvault_migrate:
#        MIGRATION_POSTGRES_USER=envvault_migrate \
#        MIGRATION_POSTGRES_PASSWORD="$MIGRATION_DB_PASSWORD" \
#        uv run alembic upgrade head
#   4) Runtime / FastAPI connects as envvault_app (POSTGRES_*)
#
# Map script env → app config:
#   MIGRATION_DB_USER     → MIGRATION_POSTGRES_USER
#   MIGRATION_DB_PASSWORD → MIGRATION_POSTGRES_PASSWORD
# =============================================================================
set -euo pipefail

SCRIPT_PATH="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"
ROOT="$(cd "$(dirname "$SCRIPT_PATH")/.." && pwd)"
cd "$ROOT"

TRANSFER_FROM=""
for arg in "$@"; do
  case "$arg" in
    --transfer-from=*)
      TRANSFER_FROM="${arg#--transfer-from=}"
      ;;
    -h|--help)
      sed -n '2,48p' "$SCRIPT_PATH"
      exit 0
      ;;
    *)
      echo "Unknown argument: $arg" >&2
      exit 1
      ;;
  esac
done

MIGRATION_DB_USER="${MIGRATION_DB_USER:-envvault_migrate}"
MIGRATION_DB_PASSWORD="${MIGRATION_DB_PASSWORD:?Set MIGRATION_DB_PASSWORD before provisioning envvault_migrate}"

POSTGRES_SERVER="${POSTGRES_SERVER:-localhost}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
POSTGRES_USER="${POSTGRES_USER:-envvault_user}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-envvault_secure_password}"
POSTGRES_DB="${POSTGRES_DB:-envvault_dev}"

DATABASE_URL="${DATABASE_URL:-postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@${POSTGRES_SERVER}:${POSTGRES_PORT}/${POSTGRES_DB}}"

# Password is interpolated by the shell into a dollar-quoted DO body so we do
# not rely on psql :variables inside CREATE ROLE (awkward with special chars).
# Callers must supply a password without single quotes.
if [[ "$MIGRATION_DB_PASSWORD" == *"'"* ]]; then
  echo "MIGRATION_DB_PASSWORD must not contain single quotes." >&2
  exit 1
fi

if [[ ! "$MIGRATION_DB_USER" =~ ^[a-zA-Z_][a-zA-Z0-9_]*$ ]]; then
  echo "MIGRATION_DB_USER must be a simple PostgreSQL role identifier." >&2
  exit 1
fi

if [[ -n "$TRANSFER_FROM" ]]; then
  if [[ ! "$TRANSFER_FROM" =~ ^[a-zA-Z_][a-zA-Z0-9_]*$ ]]; then
    echo "--transfer-from must be a simple PostgreSQL role identifier." >&2
    exit 1
  fi
  if [[ "$TRANSFER_FROM" == "$MIGRATION_DB_USER" ]]; then
    echo "--transfer-from cannot be the same as MIGRATION_DB_USER." >&2
    exit 1
  fi
fi

if ! command -v psql >/dev/null 2>&1; then
  echo "psql is required to provision database roles." >&2
  exit 1
fi

echo "Provisioning role '${MIGRATION_DB_USER}' via ${DATABASE_URL%%@*}@*** ..."

psql "$DATABASE_URL" -v ON_ERROR_STOP=1 <<EOSQL
-- Extensions used by migrations; create while connected as operator/superuser
-- so envvault_migrate never needs SUPERUSER for CREATE EXTENSION.
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS citext;

DO \$\$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '${MIGRATION_DB_USER}') THEN
    CREATE ROLE ${MIGRATION_DB_USER}
      LOGIN
      PASSWORD '${MIGRATION_DB_PASSWORD}'
      NOSUPERUSER
      NOCREATEDB
      NOCREATEROLE
      NOINHERIT
      NOBYPASSRLS;
    RAISE NOTICE 'Created role % with LOGIN', '${MIGRATION_DB_USER}';
  ELSE
    ALTER ROLE ${MIGRATION_DB_USER}
      WITH LOGIN
      PASSWORD '${MIGRATION_DB_PASSWORD}'
      NOSUPERUSER
      NOCREATEDB
      NOCREATEROLE
      NOINHERIT
      NOBYPASSRLS;
    RAISE NOTICE 'Updated role % (LOGIN/PASSWORD/flags)', '${MIGRATION_DB_USER}';
  END IF;
END
\$\$;

GRANT CONNECT ON DATABASE ${POSTGRES_DB} TO ${MIGRATION_DB_USER};

-- Schema ownership: migrate role can CREATE objects and GRANT to envvault_app.
ALTER SCHEMA public OWNER TO ${MIGRATION_DB_USER};
EOSQL

if [[ -n "$TRANSFER_FROM" ]]; then
  echo "Reassigning objects owned by '${TRANSFER_FROM}' to '${MIGRATION_DB_USER}' ..."
  psql "$DATABASE_URL" -v ON_ERROR_STOP=1 <<EOSQL
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '${TRANSFER_FROM}') THEN
    RAISE EXCEPTION 'Role % does not exist ( --transfer-from )', '${TRANSFER_FROM}';
  END IF;
END
\$\$;
REASSIGN OWNED BY ${TRANSFER_FROM} TO ${MIGRATION_DB_USER};
EOSQL
fi

echo "Done. Point Alembic at this role via MIGRATION_POSTGRES_USER=${MIGRATION_DB_USER}"
echo "and MIGRATION_POSTGRES_PASSWORD=(same as MIGRATION_DB_PASSWORD)."
echo "Next: ./scripts/provision_app_role.sh  then  alembic upgrade head as ${MIGRATION_DB_USER}."
