"""widen memberships SELECT for org peers

Revision ID: a1f2b3c4d5e6
Revises: e7c4d91a5b26
Create Date: 2026-07-23 15:00:00.000000

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1f2b3c4d5e6"
down_revision: Union[str, Sequence[str], None] = "e7c4d91a5b26"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    The original memberships SELECT policy only returned the caller's own rows.
    That blocked org-scoped list/invite workflows and last-owner checks.

    A direct EXISTS subquery against memberships inside the memberships SELECT
    policy causes "infinite recursion detected in policy" when other policies
    (e.g. organizations) also read memberships. Use a SECURITY DEFINER helper
    so the peer check bypasses RLS safely.
    """
    op.execute(
        """
        CREATE OR REPLACE FUNCTION user_is_org_member(p_user_id uuid, p_org_id uuid)
        RETURNS boolean
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = public
        AS $$
            SELECT EXISTS (
                SELECT 1
                FROM memberships m
                WHERE m.user_id = p_user_id
                  AND m.organization_id = p_org_id
            );
        $$;
        """
    )
    op.execute("REVOKE ALL ON FUNCTION user_is_org_member(uuid, uuid) FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION user_is_org_member(uuid, uuid) TO envvault_app")

    op.execute("DROP POLICY IF EXISTS org_memberships_select ON memberships")
    op.execute(
        """
        CREATE POLICY org_memberships_select ON memberships
            FOR SELECT
            USING (
                user_id = app_setting_uuid('app.current_user_id')
                OR (
                    organization_id = app_setting_uuid('app.current_org_id')
                    AND user_is_org_member(
                        app_setting_uuid('app.current_user_id'),
                        app_setting_uuid('app.current_org_id')
                    )
                )
            );
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS org_memberships_select ON memberships")
    op.execute(
        """
        CREATE POLICY org_memberships_select ON memberships
            FOR SELECT
            USING (user_id = app_setting_uuid('app.current_user_id'));
        """
    )
    op.execute("DROP FUNCTION IF EXISTS user_is_org_member(uuid, uuid)")
