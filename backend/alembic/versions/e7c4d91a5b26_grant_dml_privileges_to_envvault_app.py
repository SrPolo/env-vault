"""grant DML privileges to envvault_app

Revision ID: e7c4d91a5b26
Revises: d4a1b72e9c08
Create Date: 2026-07-23 10:40:00.000000

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e7c4d91a5b26"
down_revision: Union[str, Sequence[str], None] = "d4a1b72e9c08"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

APP_DB_USER = "envvault_app"


def upgrade() -> None:
    """
    Give the runtime role DML on schema objects created by migrations.

    CREATE ROLE stays outside Alembic (init-db.sh / provision_app_role.sh).
    This migration only GRANTs and fails fast if the role is missing.
    """
    op.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{APP_DB_USER}') THEN
                RAISE EXCEPTION
                    'Role {APP_DB_USER} does not exist. '
                    'On Docker first boot it is created by backend/init-db.sh. '
                    'Otherwise run backend/scripts/provision_app_role.sh. '
                    'See backend/README.md (Database roles).'
                    USING ERRCODE = '42704';
            END IF;
        END
        $$;
        """
    )
    op.execute(f"GRANT USAGE ON SCHEMA public TO {APP_DB_USER}")
    op.execute(
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES "
        f"IN SCHEMA public TO {APP_DB_USER}"
    )
    op.execute(
        f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {APP_DB_USER}"
    )
    op.execute(
        f"GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO {APP_DB_USER}"
    )
    op.execute(
        f"GRANT USAGE ON TYPE membership_role, audit_action, "
        f"audit_resource_type TO {APP_DB_USER}"
    )
    # Keep SECURITY DEFINER bootstrap non-PUBLIC even if ALL FUNCTIONS was granted.
    op.execute(
        "REVOKE ALL ON FUNCTION create_organization_with_owner(text, text, uuid) "
        "FROM PUBLIC"
    )
    op.execute(
        f"GRANT EXECUTE ON FUNCTION create_organization_with_owner(text, text, uuid) "
        f"TO {APP_DB_USER}"
    )
    op.execute(
        f"""
        ALTER DEFAULT PRIVILEGES IN SCHEMA public
          GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {APP_DB_USER}
        """
    )
    op.execute(
        f"""
        ALTER DEFAULT PRIVILEGES IN SCHEMA public
          GRANT USAGE, SELECT ON SEQUENCES TO {APP_DB_USER}
        """
    )


def downgrade() -> None:
    op.execute(
        f"""
        ALTER DEFAULT PRIVILEGES IN SCHEMA public
          REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLES FROM {APP_DB_USER}
        """
    )
    op.execute(
        f"""
        ALTER DEFAULT PRIVILEGES IN SCHEMA public
          REVOKE USAGE, SELECT ON SEQUENCES FROM {APP_DB_USER}
        """
    )
    op.execute(
        f"REVOKE USAGE ON TYPE membership_role, audit_action, "
        f"audit_resource_type FROM {APP_DB_USER}"
    )
    op.execute(
        f"REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA public FROM {APP_DB_USER}"
    )
    op.execute(
        f"REVOKE ALL ON FUNCTION create_organization_with_owner(text, text, uuid) "
        f"FROM {APP_DB_USER}"
    )
    op.execute(
        f"REVOKE SELECT, INSERT, UPDATE, DELETE ON ALL TABLES "
        f"IN SCHEMA public FROM {APP_DB_USER}"
    )
    op.execute(
        f"REVOKE USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public FROM {APP_DB_USER}"
    )
    op.execute(f"REVOKE USAGE ON SCHEMA public FROM {APP_DB_USER}")
