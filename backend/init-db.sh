#!/bin/bash
# Runs once on first Postgres data directory init (docker-entrypoint-initdb.d).
# Creates the runtime role envvault_app so FastAPI can connect with RLS enforced.
# LOGIN/PASSWORD stay out of Alembic — see scripts/provision_app_role.sh for
# re-runs on existing volumes or non-Docker environments.
set -euo pipefail

APP_DB_USER="${APP_DB_USER:-envvault_app}"
APP_DB_PASSWORD="${APP_DB_PASSWORD:-envvault_app_password}"

if [[ "$APP_DB_PASSWORD" == *"'"* ]]; then
  echo "APP_DB_PASSWORD must not contain single quotes." >&2
  exit 1
fi

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    CREATE EXTENSION IF NOT EXISTS "pgcrypto";

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
        RAISE NOTICE 'Created role %', '${APP_DB_USER}';
      ELSE
        RAISE NOTICE 'Role % already exists', '${APP_DB_USER}';
      END IF;
    END
    \$\$;

    GRANT CONNECT ON DATABASE ${POSTGRES_DB} TO ${APP_DB_USER};
    GRANT USAGE ON SCHEMA public TO ${APP_DB_USER};

    -- Tables/functions created later by the migration role pick these up.
    ALTER DEFAULT PRIVILEGES FOR ROLE ${POSTGRES_USER} IN SCHEMA public
      GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO ${APP_DB_USER};
    ALTER DEFAULT PRIVILEGES FOR ROLE ${POSTGRES_USER} IN SCHEMA public
      GRANT USAGE, SELECT ON SEQUENCES TO ${APP_DB_USER};
    ALTER DEFAULT PRIVILEGES FOR ROLE ${POSTGRES_USER} IN SCHEMA public
      GRANT EXECUTE ON FUNCTIONS TO ${APP_DB_USER};
EOSQL
