#!/bin/sh
# Runs once on first Postgres data-dir init (docker-entrypoint-initdb.d).
# Creates extensions + the restricted app role used by FastAPI / tests.
#
# On subsequent starts (existing volume), docker-compose `db-provision`
# re-applies the same role CREATE/ALTER idempotently.
set -eu

APP_DB_USER="${APP_DB_USER:-envvault_app}"
APP_DB_PASSWORD="${APP_DB_PASSWORD:-envvault_app_password}"

case "$APP_DB_PASSWORD" in
  *"'"*)
    echo "APP_DB_PASSWORD must not contain single quotes." >&2
    exit 1
    ;;
esac

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
