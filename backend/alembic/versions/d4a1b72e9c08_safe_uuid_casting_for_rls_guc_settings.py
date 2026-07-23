"""safe uuid casting for RLS GUC settings

Revision ID: d4a1b72e9c08
Revises: c3f8a91d2e47
Create Date: 2026-07-21 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op

revision: str = "d4a1b72e9c08"
down_revision: Union[str, Sequence[str], None] = "c3f8a91d2e47"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    current_setting(..., true) may return '' instead of NULL for unset custom
    GUCs depending on connection state. Casting ''::uuid raises and breaks RLS
    evaluation. Route all GUC→uuid reads through app_setting_uuid().

    Policies are dropped and recreated explicitly (final text auditable here).
    """
    op.execute(
        """
        CREATE OR REPLACE FUNCTION app_setting_uuid(p_name text)
        RETURNS uuid
        LANGUAGE sql
        STABLE
        AS $$
            SELECT NULLIF(current_setting(p_name, true), '')::uuid;
        $$;
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION current_user_belongs_to_current_org()
        RETURNS boolean
        LANGUAGE sql
        STABLE
        AS $$
            SELECT EXISTS (
                SELECT 1
                FROM memberships m
                WHERE m.organization_id = app_setting_uuid('app.current_org_id')
                  AND m.user_id = app_setting_uuid('app.current_user_id')
            );
        $$;
        """
    )

    # -- memberships ---------------------------------------------------------
    op.execute("DROP POLICY IF EXISTS org_memberships_select ON memberships")
    op.execute(
        """
        CREATE POLICY org_memberships_select ON memberships
            FOR SELECT
            USING (user_id = app_setting_uuid('app.current_user_id'));
        """
    )

    op.execute("DROP POLICY IF EXISTS org_memberships_insert ON memberships")
    op.execute(
        """
        CREATE POLICY org_memberships_insert ON memberships
            FOR INSERT
            WITH CHECK (
                (
                    EXISTS (
                        SELECT 1
                        FROM memberships actor
                        WHERE actor.organization_id = memberships.organization_id
                          AND actor.user_id = app_setting_uuid('app.current_user_id')
                          AND actor.role IN ('owner', 'admin')
                    )
                    AND memberships.role IN ('admin', 'member', 'viewer')
                )
                OR (
                    memberships.user_id = app_setting_uuid('app.current_user_id')
                    AND memberships.role = 'owner'
                    AND NOT EXISTS (
                        SELECT 1
                        FROM memberships existing
                        WHERE existing.organization_id = memberships.organization_id
                    )
                )
            );
        """
    )

    op.execute("DROP POLICY IF EXISTS org_memberships_update ON memberships")
    op.execute(
        """
        CREATE POLICY org_memberships_update ON memberships
            FOR UPDATE
            USING (
                EXISTS (
                    SELECT 1
                    FROM memberships actor
                    WHERE actor.organization_id = memberships.organization_id
                      AND actor.user_id = app_setting_uuid('app.current_user_id')
                      AND actor.role IN ('owner', 'admin')
                )
            )
            WITH CHECK (
                EXISTS (
                    SELECT 1
                    FROM memberships actor
                    WHERE actor.organization_id = memberships.organization_id
                      AND actor.user_id = app_setting_uuid('app.current_user_id')
                      AND actor.role IN ('owner', 'admin')
                )
                AND (
                    memberships.role <> 'owner'
                    OR EXISTS (
                        SELECT 1
                        FROM memberships actor_owner
                        WHERE actor_owner.organization_id = memberships.organization_id
                          AND actor_owner.user_id = app_setting_uuid('app.current_user_id')
                          AND actor_owner.role = 'owner'
                    )
                )
            );
        """
    )

    op.execute("DROP POLICY IF EXISTS org_memberships_delete ON memberships")
    op.execute(
        """
        CREATE POLICY org_memberships_delete ON memberships
            FOR DELETE
            USING (
                EXISTS (
                    SELECT 1
                    FROM memberships actor
                    WHERE actor.organization_id = memberships.organization_id
                      AND actor.user_id = app_setting_uuid('app.current_user_id')
                      AND actor.role IN ('owner', 'admin')
                )
                AND (
                    memberships.user_id <> app_setting_uuid('app.current_user_id')
                    OR EXISTS (
                        SELECT 1
                        FROM memberships actor_owner
                        WHERE actor_owner.organization_id = memberships.organization_id
                          AND actor_owner.user_id = app_setting_uuid('app.current_user_id')
                          AND actor_owner.role = 'owner'
                    )
                )
            );
        """
    )

    # -- organizations -------------------------------------------------------
    op.execute("DROP POLICY IF EXISTS org_organizations_select ON organizations")
    op.execute(
        """
        CREATE POLICY org_organizations_select ON organizations
            FOR SELECT
            USING (
                EXISTS (
                    SELECT 1
                    FROM memberships m
                    WHERE m.organization_id = organizations.id
                      AND m.user_id = app_setting_uuid('app.current_user_id')
                )
            );
        """
    )

    op.execute("DROP POLICY IF EXISTS org_organizations_insert ON organizations")
    op.execute(
        """
        CREATE POLICY org_organizations_insert ON organizations
            FOR INSERT
            WITH CHECK (app_setting_uuid('app.current_user_id') IS NOT NULL);
        """
    )

    op.execute("DROP POLICY IF EXISTS org_organizations_update ON organizations")
    op.execute(
        """
        CREATE POLICY org_organizations_update ON organizations
            FOR UPDATE
            USING (
                EXISTS (
                    SELECT 1
                    FROM memberships m
                    WHERE m.organization_id = organizations.id
                      AND m.user_id = app_setting_uuid('app.current_user_id')
                      AND m.role IN ('owner', 'admin')
                )
            )
            WITH CHECK (
                EXISTS (
                    SELECT 1
                    FROM memberships m
                    WHERE m.organization_id = organizations.id
                      AND m.user_id = app_setting_uuid('app.current_user_id')
                      AND m.role IN ('owner', 'admin')
                )
            );
        """
    )

    op.execute("DROP POLICY IF EXISTS org_organizations_delete ON organizations")
    op.execute(
        """
        CREATE POLICY org_organizations_delete ON organizations
            FOR DELETE
            USING (
                EXISTS (
                    SELECT 1
                    FROM memberships m
                    WHERE m.organization_id = organizations.id
                      AND m.user_id = app_setting_uuid('app.current_user_id')
                      AND m.role = 'owner'
                )
            );
        """
    )

    # -- projects ------------------------------------------------------------
    op.execute("DROP POLICY IF EXISTS org_isolation_projects_select ON projects")
    op.execute(
        """
        CREATE POLICY org_isolation_projects_select ON projects
            FOR SELECT
            USING (organization_id = app_setting_uuid('app.current_org_id'));
        """
    )

    op.execute("DROP POLICY IF EXISTS org_isolation_projects_insert ON projects")
    op.execute(
        """
        CREATE POLICY org_isolation_projects_insert ON projects
            FOR INSERT
            WITH CHECK (organization_id = app_setting_uuid('app.current_org_id'));
        """
    )

    op.execute("DROP POLICY IF EXISTS org_isolation_projects_update ON projects")
    op.execute(
        """
        CREATE POLICY org_isolation_projects_update ON projects
            FOR UPDATE
            USING (organization_id = app_setting_uuid('app.current_org_id'))
            WITH CHECK (organization_id = app_setting_uuid('app.current_org_id'));
        """
    )

    op.execute("DROP POLICY IF EXISTS org_isolation_projects_delete ON projects")
    op.execute(
        """
        CREATE POLICY org_isolation_projects_delete ON projects
            FOR DELETE
            USING (organization_id = app_setting_uuid('app.current_org_id'));
        """
    )

    # -- environments --------------------------------------------------------
    op.execute("DROP POLICY IF EXISTS org_isolation_environments_select ON environments")
    op.execute(
        """
        CREATE POLICY org_isolation_environments_select ON environments
            FOR SELECT
            USING (project_id IN (
                SELECT id FROM projects
                WHERE organization_id = app_setting_uuid('app.current_org_id')
            ));
        """
    )

    op.execute("DROP POLICY IF EXISTS org_isolation_environments_insert ON environments")
    op.execute(
        """
        CREATE POLICY org_isolation_environments_insert ON environments
            FOR INSERT
            WITH CHECK (project_id IN (
                SELECT id FROM projects
                WHERE organization_id = app_setting_uuid('app.current_org_id')
            ));
        """
    )

    op.execute("DROP POLICY IF EXISTS org_isolation_environments_update ON environments")
    op.execute(
        """
        CREATE POLICY org_isolation_environments_update ON environments
            FOR UPDATE
            USING (project_id IN (
                SELECT id FROM projects
                WHERE organization_id = app_setting_uuid('app.current_org_id')
            ))
            WITH CHECK (project_id IN (
                SELECT id FROM projects
                WHERE organization_id = app_setting_uuid('app.current_org_id')
            ));
        """
    )

    op.execute("DROP POLICY IF EXISTS org_isolation_environments_delete ON environments")
    op.execute(
        """
        CREATE POLICY org_isolation_environments_delete ON environments
            FOR DELETE
            USING (project_id IN (
                SELECT id FROM projects
                WHERE organization_id = app_setting_uuid('app.current_org_id')
            ));
        """
    )

    # -- secrets -------------------------------------------------------------
    op.execute("DROP POLICY IF EXISTS org_isolation_secrets_select ON secrets")
    op.execute(
        """
        CREATE POLICY org_isolation_secrets_select ON secrets
            FOR SELECT
            USING (environment_id IN (
                SELECT e.id FROM environments e
                JOIN projects p ON p.id = e.project_id
                WHERE p.organization_id = app_setting_uuid('app.current_org_id')
            ));
        """
    )

    op.execute("DROP POLICY IF EXISTS org_isolation_secrets_insert ON secrets")
    op.execute(
        """
        CREATE POLICY org_isolation_secrets_insert ON secrets
            FOR INSERT
            WITH CHECK (environment_id IN (
                SELECT e.id FROM environments e
                JOIN projects p ON p.id = e.project_id
                WHERE p.organization_id = app_setting_uuid('app.current_org_id')
            ));
        """
    )

    op.execute("DROP POLICY IF EXISTS org_isolation_secrets_update ON secrets")
    op.execute(
        """
        CREATE POLICY org_isolation_secrets_update ON secrets
            FOR UPDATE
            USING (environment_id IN (
                SELECT e.id FROM environments e
                JOIN projects p ON p.id = e.project_id
                WHERE p.organization_id = app_setting_uuid('app.current_org_id')
            ))
            WITH CHECK (environment_id IN (
                SELECT e.id FROM environments e
                JOIN projects p ON p.id = e.project_id
                WHERE p.organization_id = app_setting_uuid('app.current_org_id')
            ));
        """
    )

    op.execute("DROP POLICY IF EXISTS org_isolation_secrets_delete ON secrets")
    op.execute(
        """
        CREATE POLICY org_isolation_secrets_delete ON secrets
            FOR DELETE
            USING (environment_id IN (
                SELECT e.id FROM environments e
                JOIN projects p ON p.id = e.project_id
                WHERE p.organization_id = app_setting_uuid('app.current_org_id')
            ));
        """
    )

    # -- secret_versions -----------------------------------------------------
    op.execute(
        "DROP POLICY IF EXISTS org_isolation_secret_versions_select ON secret_versions"
    )
    op.execute(
        """
        CREATE POLICY org_isolation_secret_versions_select ON secret_versions
            FOR SELECT
            USING (secret_id IN (
                SELECT s.id FROM secrets s
                JOIN environments e ON e.id = s.environment_id
                JOIN projects p ON p.id = e.project_id
                WHERE p.organization_id = app_setting_uuid('app.current_org_id')
            ));
        """
    )

    op.execute(
        "DROP POLICY IF EXISTS org_isolation_secret_versions_insert ON secret_versions"
    )
    op.execute(
        """
        CREATE POLICY org_isolation_secret_versions_insert ON secret_versions
            FOR INSERT
            WITH CHECK (secret_id IN (
                SELECT s.id FROM secrets s
                JOIN environments e ON e.id = s.environment_id
                JOIN projects p ON p.id = e.project_id
                WHERE p.organization_id = app_setting_uuid('app.current_org_id')
            ));
        """
    )

    op.execute(
        "DROP POLICY IF EXISTS org_isolation_secret_versions_update ON secret_versions"
    )
    op.execute(
        """
        CREATE POLICY org_isolation_secret_versions_update ON secret_versions
            FOR UPDATE
            USING (secret_id IN (
                SELECT s.id FROM secrets s
                JOIN environments e ON e.id = s.environment_id
                JOIN projects p ON p.id = e.project_id
                WHERE p.organization_id = app_setting_uuid('app.current_org_id')
            ))
            WITH CHECK (secret_id IN (
                SELECT s.id FROM secrets s
                JOIN environments e ON e.id = s.environment_id
                JOIN projects p ON p.id = e.project_id
                WHERE p.organization_id = app_setting_uuid('app.current_org_id')
            ));
        """
    )

    op.execute(
        "DROP POLICY IF EXISTS org_isolation_secret_versions_delete ON secret_versions"
    )
    op.execute(
        """
        CREATE POLICY org_isolation_secret_versions_delete ON secret_versions
            FOR DELETE
            USING (secret_id IN (
                SELECT s.id FROM secrets s
                JOIN environments e ON e.id = s.environment_id
                JOIN projects p ON p.id = e.project_id
                WHERE p.organization_id = app_setting_uuid('app.current_org_id')
            ));
        """
    )

    # -- encryption_keys -----------------------------------------------------
    op.execute(
        "DROP POLICY IF EXISTS org_isolation_encryption_keys_select ON encryption_keys"
    )
    op.execute(
        """
        CREATE POLICY org_isolation_encryption_keys_select ON encryption_keys
            FOR SELECT
            USING (environment_id IN (
                SELECT e.id FROM environments e
                JOIN projects p ON p.id = e.project_id
                WHERE p.organization_id = app_setting_uuid('app.current_org_id')
            ));
        """
    )

    op.execute(
        "DROP POLICY IF EXISTS org_isolation_encryption_keys_insert ON encryption_keys"
    )
    op.execute(
        """
        CREATE POLICY org_isolation_encryption_keys_insert ON encryption_keys
            FOR INSERT
            WITH CHECK (environment_id IN (
                SELECT e.id FROM environments e
                JOIN projects p ON p.id = e.project_id
                WHERE p.organization_id = app_setting_uuid('app.current_org_id')
            ));
        """
    )

    op.execute(
        "DROP POLICY IF EXISTS org_isolation_encryption_keys_update ON encryption_keys"
    )
    op.execute(
        """
        CREATE POLICY org_isolation_encryption_keys_update ON encryption_keys
            FOR UPDATE
            USING (environment_id IN (
                SELECT e.id FROM environments e
                JOIN projects p ON p.id = e.project_id
                WHERE p.organization_id = app_setting_uuid('app.current_org_id')
            ))
            WITH CHECK (environment_id IN (
                SELECT e.id FROM environments e
                JOIN projects p ON p.id = e.project_id
                WHERE p.organization_id = app_setting_uuid('app.current_org_id')
            ));
        """
    )

    op.execute(
        "DROP POLICY IF EXISTS org_isolation_encryption_keys_delete ON encryption_keys"
    )
    op.execute(
        """
        CREATE POLICY org_isolation_encryption_keys_delete ON encryption_keys
            FOR DELETE
            USING (environment_id IN (
                SELECT e.id FROM environments e
                JOIN projects p ON p.id = e.project_id
                WHERE p.organization_id = app_setting_uuid('app.current_org_id')
            ));
        """
    )

    # -- api_tokens ----------------------------------------------------------
    op.execute("DROP POLICY IF EXISTS org_isolation_api_tokens_select ON api_tokens")
    op.execute(
        """
        CREATE POLICY org_isolation_api_tokens_select ON api_tokens
            FOR SELECT
            USING (project_id IN (
                SELECT id FROM projects
                WHERE organization_id = app_setting_uuid('app.current_org_id')
            ));
        """
    )

    op.execute("DROP POLICY IF EXISTS org_isolation_api_tokens_insert ON api_tokens")
    op.execute(
        """
        CREATE POLICY org_isolation_api_tokens_insert ON api_tokens
            FOR INSERT
            WITH CHECK (project_id IN (
                SELECT id FROM projects
                WHERE organization_id = app_setting_uuid('app.current_org_id')
            ));
        """
    )

    op.execute("DROP POLICY IF EXISTS org_isolation_api_tokens_update ON api_tokens")
    op.execute(
        """
        CREATE POLICY org_isolation_api_tokens_update ON api_tokens
            FOR UPDATE
            USING (project_id IN (
                SELECT id FROM projects
                WHERE organization_id = app_setting_uuid('app.current_org_id')
            ))
            WITH CHECK (project_id IN (
                SELECT id FROM projects
                WHERE organization_id = app_setting_uuid('app.current_org_id')
            ));
        """
    )

    op.execute("DROP POLICY IF EXISTS org_isolation_api_tokens_delete ON api_tokens")
    op.execute(
        """
        CREATE POLICY org_isolation_api_tokens_delete ON api_tokens
            FOR DELETE
            USING (project_id IN (
                SELECT id FROM projects
                WHERE organization_id = app_setting_uuid('app.current_org_id')
            ));
        """
    )

    # -- audit_logs ----------------------------------------------------------
    op.execute("DROP POLICY IF EXISTS org_isolation_audit_logs_select ON audit_logs")
    op.execute(
        """
        CREATE POLICY org_isolation_audit_logs_select ON audit_logs
            FOR SELECT
            USING (organization_id = app_setting_uuid('app.current_org_id'));
        """
    )

    op.execute("DROP POLICY IF EXISTS org_isolation_audit_logs_insert ON audit_logs")
    op.execute(
        """
        CREATE POLICY org_isolation_audit_logs_insert ON audit_logs
            FOR INSERT
            WITH CHECK (organization_id = app_setting_uuid('app.current_org_id'));
        """
    )

    op.execute("DROP POLICY IF EXISTS org_isolation_audit_logs_update ON audit_logs")
    op.execute(
        """
        CREATE POLICY org_isolation_audit_logs_update ON audit_logs
            FOR UPDATE
            USING (organization_id = app_setting_uuid('app.current_org_id'))
            WITH CHECK (organization_id = app_setting_uuid('app.current_org_id'));
        """
    )

    op.execute("DROP POLICY IF EXISTS org_isolation_audit_logs_delete ON audit_logs")
    op.execute(
        """
        CREATE POLICY org_isolation_audit_logs_delete ON audit_logs
            FOR DELETE
            USING (organization_id = app_setting_uuid('app.current_org_id'));
        """
    )


def downgrade() -> None:
    # Irreversible: policies now depend on app_setting_uuid(). Restoring the
    # brittle ''::uuid casts would reintroduce production failures.
    pass
