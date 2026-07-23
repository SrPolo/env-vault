"""add create_organization_with_owner bootstrap fn

Revision ID: c3f8a91d2e47
Revises: 177077e10656
Create Date: 2026-07-21 11:30:00.000000

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3f8a91d2e47"
down_revision: Union[str, Sequence[str], None] = "177077e10656"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Organizations SELECT policy requires a membership, but INSERT ... RETURNING
    also evaluates SELECT policies. That makes ORM/API org creation impossible
    under FORCE RLS without a privileged bootstrap path.

    create_organization_with_owner inserts the org + owner membership atomically
    as SECURITY DEFINER (bypasses RLS), while still requiring the caller to set
    app.current_user_id and pass the same user id.

    EXECUTE is granted only to envvault_app (never PUBLIC).

    Role lifecycle is intentionally outside Alembic:
    - Create + LOGIN/PASSWORD: backend/scripts/provision_app_role.sh
    - This migration only GRANTs and fails fast if the role is missing,
      so the migration role does not need CREATEROLE.
    """
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'envvault_app') THEN
                RAISE EXCEPTION
                    'Role envvault_app does not exist. '
                    'Run backend/scripts/provision_app_role.sh before alembic upgrade. '
                    'See backend/README.md (Database roles).'
                    USING ERRCODE = '42704';
            END IF;
        END
        $$;
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION create_organization_with_owner(
            p_name text,
            p_slug text,
            p_user_id uuid
        )
        RETURNS organizations
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = public
        AS $$
        DECLARE
            new_org organizations;
            actor text := current_setting('app.current_user_id', true);
        BEGIN
            IF NULLIF(actor, '') IS NULL THEN
                RAISE EXCEPTION 'app.current_user_id must be set to create an organization'
                    USING ERRCODE = '42501';
            END IF;

            IF actor::uuid IS DISTINCT FROM p_user_id THEN
                RAISE EXCEPTION 'p_user_id must match app.current_user_id'
                    USING ERRCODE = '42501';
            END IF;

            IF NOT EXISTS (SELECT 1 FROM users WHERE id = p_user_id) THEN
                RAISE EXCEPTION 'user % does not exist', p_user_id
                    USING ERRCODE = '23503';
            END IF;

            INSERT INTO organizations (name, slug)
            VALUES (p_name, p_slug)
            RETURNING * INTO new_org;

            INSERT INTO memberships (user_id, organization_id, role)
            VALUES (p_user_id, new_org.id, 'owner');

            RETURN new_org;
        END;
        $$;
        """
    )
    op.execute(
        "REVOKE ALL ON FUNCTION create_organization_with_owner(text, text, uuid) FROM PUBLIC"
    )
    op.execute(
        "GRANT EXECUTE ON FUNCTION create_organization_with_owner(text, text, uuid) "
        "TO envvault_app"
    )


def downgrade() -> None:
    op.execute(
        "DROP FUNCTION IF EXISTS create_organization_with_owner(text, text, uuid)"
    )
