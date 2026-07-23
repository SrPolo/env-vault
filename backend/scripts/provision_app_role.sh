#!/usr/bin/env bash
# =============================================================================
# Provision the application DB role `envvault_app`.
#
# WHY THIS IS NOT IN ALEMBIC
#   - CREATE ROLE requires CREATEROLE (or superuser). Migration runners in
#     locked-down environments often lack that privilege.
#   - LOGIN + PASSWORD are environment secrets and must not live in migration
#     history.
#
# REQUIREMENTS
#   - Connect as a PostgreSQL superuser OR a role with CREATEROLE.
#   - In local docker-compose, POSTGRES_USER (envvault_user) is a superuser, so
#     it satisfies this. That is a convenience for local only — do not assume
#     the same in staging/production.
#
# USAGE
#   export APP_DB_PASSWORD='choose-a-strong-password'
#   # optional overrides:
#   # export APP_DB_USER=envvault_app
#   # export DATABASE_URL=postgresql://envvault_user:envvault_secure_password@localhost:5432/envvault_dev
#   ./scripts/provision_app_role.sh
#
# Typical order for a fresh environment:
#   1) ./scripts/provision_app_role.sh          # create role + LOGIN/PASSWORD
#   2) uv run alembic upgrade head             # schema + GRANT EXECUTE
#   3) ./scripts/provision_app_role.sh --grants  # DML privileges on tables
#
# Steps 1 and 3 can be combined after migrations by running with --grants on a
# role that already exists; on first boot run without --grants first.
# =============================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

APP_DB_USER="${APP_DB_USER:-envvault_app}"
APP_DB_PASSWORD="${APP_DB_PASSWORD:?Set APP_DB_PASSWORD before provisioning envvault_app}"

POSTGRES_SERVER="${POSTGRES_SERVER:-localhost}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
POSTGRES_USER="${POSTGRES_USER:-envvault_user}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-envvault_secure_password}"
POSTGRES_DB="${POSTGRES_DB:-envvault_dev}"

DATABASE_URL="${DATABASE_URL:-postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@${POSTGRES_SERVER}:${POSTGRES_PORT}/${POSTGRES_DB}}"

DO_GRANTS=0
for arg in "$@"; do
  case "$arg" in
    --grants) DO_GRANTS=1 ;;
    -h|--help)
      sed -n '2,35p' "$0"
      exit 0
      ;;
    *)
      echo "Unknown argument: $arg" >&2
      exit 1
      ;;
  esac
done

if ! command -v psql >/dev/null 2>&1; then
  echo "psql is required to provision database roles." >&2
  exit 1
fi

echo "Provisioning role '${APP_DB_USER}' via ${DATABASE_URL%%@*}@*** ..."

# Password is interpolated by the shell into a dollar-quoted DO body so we do
# not rely on psql :variables inside CREATE ROLE (awkward with special chars).
# Callers must supply a password without single quotes.
if [[ "$APP_DB_PASSWORD" == *"'"* ]]; then
  echo "APP_DB_PASSWORD must not contain single quotes." >&2
  exit 1
fi

psql "$DATABASE_URL" -v ON_ERROR_STOP=1 <<EOSQL
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '${APP_DB_USER}') THEN
    CREATE ROLE ${APP_DB_USER}
      LOGIN
      PASSWORD '${APP_DB_PASSWORD}'
      NOSUPERUSER
      NOCREATEDB
      NOCREATEROLE
      NOINHERIT
      NOBYPASSRLS;
    RAISE NOTICE 'Created role % with LOGIN', '${APP_DB_USER}';
  ELSE
    ALTER ROLE ${APP_DB_USER}
      WITH LOGIN
      PASSWORD '${APP_DB_PASSWORD}'
      NOSUPERUSER
      NOCREATEDB
      NOCREATEROLE
      NOINHERIT
      NOBYPASSRLS;
    RAISE NOTICE 'Updated role % (LOGIN/PASSWORD/flags)', '${APP_DB_USER}';
  END IF;
END
\$\$;

GRANT CONNECT ON DATABASE ${POSTGRES_DB} TO ${APP_DB_USER};
EOSQL

if [[ "$DO_GRANTS" -eq 1 ]]; then
  echo "Granting schema/table privileges to '${APP_DB_USER}' ..."
  psql "$DATABASE_URL" -v ON_ERROR_STOP=1 <<EOSQL
GRANT USAGE ON SCHEMA public TO ${APP_DB_USER};
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO ${APP_DB_USER};
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO ${APP_DB_USER};
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO ${APP_DB_USER};
GRANT USAGE ON TYPE membership_role, audit_action, audit_resource_type TO ${APP_DB_USER};

-- Keep SECURITY DEFINER bootstrap non-PUBLIC even if ALL FUNCTIONS was granted.
REVOKE ALL ON FUNCTION create_organization_with_owner(text, text, uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION create_organization_with_owner(text, text, uuid) TO ${APP_DB_USER};

ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO ${APP_DB_USER};
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO ${APP_DB_USER};
EOSQL
fi

echo "Done. Application runtime must connect as '${APP_DB_USER}' (not the migration superuser)."
