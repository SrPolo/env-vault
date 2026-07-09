"""initial_schema

Revision ID: 412ab868f224
Revises:
Create Date: 2026-07-09 11:21:21.384429

"""
import textwrap
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "412ab868f224"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


membership_role_enum = postgresql.ENUM(
    "owner",
    "admin",
    "member",
    "viewer",
    name="membership_role",
    create_type=False,
)

audit_action_enum = postgresql.ENUM(
    "create",
    "update",
    "delete",
    "reveal",
    "rollback",
    "login",
    "login_failed",
    "invite",
    "role_change",
    name="audit_action",
    create_type=False,
)

audit_resource_type_enum = postgresql.ENUM(
    "organization",
    "project",
    "environment",
    "secret",
    "membership",
    "api_token",
    name="audit_resource_type",
    create_type=False,
)


def _execute_statements(*statements: str) -> None:
    for statement in statements:
        op.execute(textwrap.dedent(statement).strip())


def upgrade() -> None:
    """Upgrade schema."""
    # -- Schema.sql reference: extensions
    _execute_statements(
        """
        -- EXTENSIONS
        CREATE EXTENSION IF NOT EXISTS pgcrypto;
        """,
        """
        -- EXTENSIONS
        CREATE EXTENSION IF NOT EXISTS citext;
        """,
    )

    # -- Schema.sql reference: enums
    _execute_statements(
        """
        -- ENUMS
        CREATE TYPE membership_role AS ENUM ('owner', 'admin', 'member', 'viewer');
        """,
        """
        -- ENUMS
        CREATE TYPE audit_action AS ENUM (
            'create', 'update', 'delete', 'reveal', 'rollback',
            'login', 'login_failed', 'invite', 'role_change'
        );
        """,
        """
        -- ENUMS
        CREATE TYPE audit_resource_type AS ENUM (
            'organization', 'project', 'environment', 'secret', 'membership', 'api_token'
        );
        """,
    )

    op.create_table(
        "organizations",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("email", postgresql.CITEXT(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=True),
        sa.Column("full_name", sa.Text(), nullable=True),
        sa.Column("totp_secret", sa.Text(), nullable=True),
        sa.Column("totp_enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("oauth_provider", sa.Text(), nullable=True),
        sa.Column("oauth_subject", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "password_hash IS NOT NULL OR (oauth_provider IS NOT NULL AND oauth_subject IS NOT NULL)",
            name="chk_auth_method",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
        sa.UniqueConstraint("oauth_provider", "oauth_subject", name="uq_users_oauth_identity"),
    )
    op.create_table(
        "memberships",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("role", membership_role_enum, server_default=sa.text("'member'"), nullable=False),
        sa.Column("invited_by", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["invited_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "organization_id", name="uq_membership"),
    )
    op.create_index("idx_memberships_org", "memberships", ["organization_id"], unique=False)
    op.create_index("idx_memberships_user", "memberships", ["user_id"], unique=False)
    op.create_table(
        "projects",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "slug", name="uq_project_slug_per_org"),
    )
    op.create_index("idx_projects_org", "projects", ["organization_id"], unique=False)
    op.create_table(
        "environments",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "name", name="uq_environment_name_per_project"),
    )
    op.create_index("idx_environments_project", "environments", ["project_id"], unique=False)
    op.create_table(
        "encryption_keys",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("environment_id", sa.UUID(), nullable=False),
        sa.Column("wrapped_dek", postgresql.BYTEA(), nullable=False),
        sa.Column("key_version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("algorithm", sa.Text(), server_default=sa.text("'AES-256-GCM'"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("rotated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("algorithm IN ('AES-256-GCM')", name="chk_encryption_keys_algorithm"),
        sa.ForeignKeyConstraint(["environment_id"], ["environments.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("environment_id", "key_version", name="uq_key_version_per_env"),
    )
    op.create_index(
        "idx_encryption_keys_env",
        "encryption_keys",
        ["environment_id"],
        unique=False,
        postgresql_where=sa.text("is_active = true"),
    )
    op.create_index(
        "uq_one_active_key_per_env",
        "encryption_keys",
        ["environment_id"],
        unique=True,
        postgresql_where=sa.text("is_active = true"),
    )
    op.create_table(
        "secrets",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("environment_id", sa.UUID(), nullable=False),
        sa.Column("key_name", sa.Text(), nullable=False),
        sa.Column("current_version_id", sa.UUID(), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["environment_id"], ["environments.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("environment_id", "key_name", name="uq_secret_key_per_env"),
    )
    op.create_index(
        "idx_secrets_env",
        "secrets",
        ["environment_id"],
        unique=False,
        postgresql_where=sa.text("is_deleted = false"),
    )
    op.create_table(
        "secret_versions",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("secret_id", sa.UUID(), nullable=False),
        sa.Column("encryption_key_id", sa.UUID(), nullable=False),
        sa.Column("encrypted_value", postgresql.BYTEA(), nullable=False),
        sa.Column("iv", postgresql.BYTEA(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["encryption_key_id"], ["encryption_keys.id"]),
        sa.ForeignKeyConstraint(["secret_id"], ["secrets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("encryption_key_id", "iv", name="uq_secret_versions_key_iv"),
        sa.UniqueConstraint("secret_id", "version_number", name="uq_secret_version"),
    )
    op.create_index("idx_secret_versions_secret", "secret_versions", ["secret_id"], unique=False)
    op.create_foreign_key(
        "fk_secrets_current_version",
        "secrets",
        "secret_versions",
        ["current_version_id"],
        ["id"],
        ondelete="SET NULL",
        deferrable=True,
        initially="DEFERRED",
    )
    op.create_table(
        "api_tokens",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("scope", sa.Text(), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index(
        "idx_api_tokens_project",
        "api_tokens",
        ["project_id"],
        unique=False,
        postgresql_where=sa.text("revoked_at IS NULL"),
    )
    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index(
        "idx_refresh_tokens_user",
        "refresh_tokens",
        ["user_id"],
        unique=False,
        postgresql_where=sa.text("revoked_at IS NULL"),
    )
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=True),
        sa.Column("user_id", sa.UUID(), nullable=True),
        sa.Column("action", audit_action_enum, nullable=False),
        sa.Column("resource_type", audit_resource_type_enum, nullable=False),
        sa.Column("resource_id", sa.UUID(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_audit_logs_org",
        "audit_logs",
        ["organization_id", sa.literal_column("created_at DESC")],
        unique=False,
    )
    op.create_index("idx_audit_logs_resource", "audit_logs", ["resource_type", "resource_id"], unique=False)

    # -- Schema.sql reference: función auxiliar / validación de current_version
    _execute_statements(
        """
        -- FUNCION AUXILIAR: updated_at automatico
        CREATE OR REPLACE FUNCTION set_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = now();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """,
        """
        -- FK diferida: current_version_id debe pertenecer al mismo secret
        CREATE OR REPLACE FUNCTION validate_secret_current_version_belongs_to_secret()
        RETURNS TRIGGER AS $$
        BEGIN
            IF NEW.current_version_id IS NULL THEN
                RETURN NEW;
            END IF;

            IF NOT EXISTS (
                SELECT 1
                FROM secret_versions sv
                WHERE sv.id = NEW.current_version_id
                  AND sv.secret_id = NEW.id
            ) THEN
                RAISE EXCEPTION 'current_version_id % no pertenece al secret %', NEW.current_version_id, NEW.id;
            END IF;

            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """,
    )

    # -- Schema.sql reference: triggers updated_at / current_version / audit_logs
    _execute_statements(
        """
        -- Trigger: updated_at
        CREATE TRIGGER trg_organizations_updated_at
            BEFORE UPDATE ON organizations
            FOR EACH ROW EXECUTE FUNCTION set_updated_at();
        """,
        """
        -- Trigger: updated_at
        CREATE TRIGGER trg_users_updated_at
            BEFORE UPDATE ON users
            FOR EACH ROW EXECUTE FUNCTION set_updated_at();
        """,
        """
        -- Trigger: updated_at
        CREATE TRIGGER trg_projects_updated_at
            BEFORE UPDATE ON projects
            FOR EACH ROW EXECUTE FUNCTION set_updated_at();
        """,
        """
        -- Trigger: updated_at
        CREATE TRIGGER trg_secrets_updated_at
            BEFORE UPDATE ON secrets
            FOR EACH ROW EXECUTE FUNCTION set_updated_at();
        """,
        """
        -- Trigger: current_version validation
        CREATE CONSTRAINT TRIGGER trg_secrets_current_version_matches_secret
            AFTER INSERT OR UPDATE OF current_version_id ON secrets
            DEFERRABLE INITIALLY DEFERRED
            FOR EACH ROW EXECUTE FUNCTION validate_secret_current_version_belongs_to_secret();
        """,
    )

    # -- Schema.sql reference: función reject_audit_log_mutation y sus triggers
    _execute_statements(
        """
        -- Funcion: reject_audit_log_mutation
        CREATE OR REPLACE FUNCTION reject_audit_log_mutation()
        RETURNS TRIGGER AS $$
        BEGIN
            RAISE EXCEPTION 'audit_logs es de solo escritura (append-only); % no permitido', TG_OP;
        END;
        $$ LANGUAGE plpgsql;
        """,
        """
        -- Trigger: audit_logs inmutable
        CREATE TRIGGER trg_audit_logs_no_update
            BEFORE UPDATE ON audit_logs
            FOR EACH ROW EXECUTE FUNCTION reject_audit_log_mutation();
        """,
        """
        -- Trigger: audit_logs inmutable
        CREATE TRIGGER trg_audit_logs_no_delete
            BEFORE DELETE ON audit_logs
            FOR EACH ROW EXECUTE FUNCTION reject_audit_log_mutation();
        """,
    )

    # -- Schema.sql reference: row level security / helper function
    _execute_statements(
        """
        -- RLS: habilitacion
        ALTER TABLE organizations ENABLE ROW LEVEL SECURITY;
        """,
        """
        -- RLS: habilitacion
        ALTER TABLE memberships ENABLE ROW LEVEL SECURITY;
        """,
        """
        -- RLS: habilitacion
        ALTER TABLE projects ENABLE ROW LEVEL SECURITY;
        """,
        """
        -- RLS: habilitacion
        ALTER TABLE environments ENABLE ROW LEVEL SECURITY;
        """,
        """
        -- RLS: habilitacion
        ALTER TABLE secrets ENABLE ROW LEVEL SECURITY;
        """,
        """
        -- RLS: habilitacion
        ALTER TABLE secret_versions ENABLE ROW LEVEL SECURITY;
        """,
        """
        -- RLS: habilitacion
        ALTER TABLE encryption_keys ENABLE ROW LEVEL SECURITY;
        """,
        """
        -- RLS: habilitacion
        ALTER TABLE api_tokens ENABLE ROW LEVEL SECURITY;
        """,
        """
        -- RLS: habilitacion
        ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY;
        """,
        """
        -- RLS: force
        ALTER TABLE organizations FORCE ROW LEVEL SECURITY;
        """,
        """
        -- RLS: force
        ALTER TABLE memberships FORCE ROW LEVEL SECURITY;
        """,
        """
        -- RLS: force
        ALTER TABLE projects FORCE ROW LEVEL SECURITY;
        """,
        """
        -- RLS: force
        ALTER TABLE environments FORCE ROW LEVEL SECURITY;
        """,
        """
        -- RLS: force
        ALTER TABLE secrets FORCE ROW LEVEL SECURITY;
        """,
        """
        -- RLS: force
        ALTER TABLE secret_versions FORCE ROW LEVEL SECURITY;
        """,
        """
        -- RLS: force
        ALTER TABLE encryption_keys FORCE ROW LEVEL SECURITY;
        """,
        """
        -- RLS: force
        ALTER TABLE api_tokens FORCE ROW LEVEL SECURITY;
        """,
        """
        -- RLS: force
        ALTER TABLE audit_logs FORCE ROW LEVEL SECURITY;
        """,
        """
        -- Funcion: current_user_belongs_to_current_org
        CREATE OR REPLACE FUNCTION current_user_belongs_to_current_org()
        RETURNS BOOLEAN
        LANGUAGE SQL
        STABLE
        AS $$
            SELECT EXISTS (
                SELECT 1
                FROM memberships m
                WHERE m.organization_id = current_setting('app.current_org_id', true)::uuid
                  AND m.user_id = current_setting('app.current_user_id', true)::uuid
            );
        $$;
        """,
    )

    # -- Schema.sql reference: RLS policies / restrictive membership guard
    _execute_statements(
        """
        -- RLS: restrictive membership guard
        CREATE POLICY org_context_member_projects ON projects
            AS RESTRICTIVE
            FOR ALL
            USING (current_user_belongs_to_current_org())
            WITH CHECK (current_user_belongs_to_current_org());
        """,
        """
        -- RLS: restrictive membership guard
        CREATE POLICY org_context_member_environments ON environments
            AS RESTRICTIVE
            FOR ALL
            USING (current_user_belongs_to_current_org())
            WITH CHECK (current_user_belongs_to_current_org());
        """,
        """
        -- RLS: restrictive membership guard
        CREATE POLICY org_context_member_secrets ON secrets
            AS RESTRICTIVE
            FOR ALL
            USING (current_user_belongs_to_current_org())
            WITH CHECK (current_user_belongs_to_current_org());
        """,
        """
        -- RLS: restrictive membership guard
        CREATE POLICY org_context_member_secret_versions ON secret_versions
            AS RESTRICTIVE
            FOR ALL
            USING (current_user_belongs_to_current_org())
            WITH CHECK (current_user_belongs_to_current_org());
        """,
        """
        -- RLS: restrictive membership guard
        CREATE POLICY org_context_member_encryption_keys ON encryption_keys
            AS RESTRICTIVE
            FOR ALL
            USING (current_user_belongs_to_current_org())
            WITH CHECK (current_user_belongs_to_current_org());
        """,
        """
        -- RLS: restrictive membership guard
        CREATE POLICY org_context_member_api_tokens ON api_tokens
            AS RESTRICTIVE
            FOR ALL
            USING (current_user_belongs_to_current_org())
            WITH CHECK (current_user_belongs_to_current_org());
        """,
        """
        -- RLS: restrictive membership guard
        CREATE POLICY org_context_member_audit_logs ON audit_logs
            AS RESTRICTIVE
            FOR ALL
            USING (current_user_belongs_to_current_org())
            WITH CHECK (current_user_belongs_to_current_org());
        """,
    )

    # -- Schema.sql reference: RLS policies / memberships
    _execute_statements(
        """
        -- RLS: memberships
        CREATE POLICY org_memberships_select ON memberships
            FOR SELECT
            USING (user_id = current_setting('app.current_user_id', true)::uuid);
        """,
        """
        -- RLS: memberships
        CREATE POLICY org_memberships_insert ON memberships
            FOR INSERT
            WITH CHECK (
                (
                    EXISTS (
                        SELECT 1
                        FROM memberships actor
                        WHERE actor.organization_id = memberships.organization_id
                          AND actor.user_id = current_setting('app.current_user_id', true)::uuid
                          AND actor.role IN ('owner', 'admin')
                    )
                    AND memberships.role IN ('admin', 'member', 'viewer')
                )
                OR (
                    memberships.user_id = current_setting('app.current_user_id', true)::uuid
                    AND memberships.role = 'owner'
                    AND NOT EXISTS (
                        SELECT 1
                        FROM memberships existing
                        WHERE existing.organization_id = memberships.organization_id
                    )
                )
            );
        """,
        """
        -- RLS: memberships
        CREATE POLICY org_memberships_update ON memberships
            FOR UPDATE
            USING (
                EXISTS (
                    SELECT 1
                    FROM memberships actor
                    WHERE actor.organization_id = memberships.organization_id
                      AND actor.user_id = current_setting('app.current_user_id', true)::uuid
                      AND actor.role IN ('owner', 'admin')
                )
            )
            WITH CHECK (
                EXISTS (
                    SELECT 1
                    FROM memberships actor
                    WHERE actor.organization_id = memberships.organization_id
                      AND actor.user_id = current_setting('app.current_user_id', true)::uuid
                      AND actor.role IN ('owner', 'admin')
                )
                AND (
                    memberships.role <> 'owner'
                    OR EXISTS (
                        SELECT 1
                        FROM memberships actor_owner
                        WHERE actor_owner.organization_id = memberships.organization_id
                          AND actor_owner.user_id = current_setting('app.current_user_id', true)::uuid
                          AND actor_owner.role = 'owner'
                    )
                )
            );
        """,
        """
        -- RLS: memberships
        CREATE POLICY org_memberships_delete ON memberships
            FOR DELETE
            USING (
                EXISTS (
                    SELECT 1
                    FROM memberships actor
                    WHERE actor.organization_id = memberships.organization_id
                      AND actor.user_id = current_setting('app.current_user_id', true)::uuid
                      AND actor.role IN ('owner', 'admin')
                )
                AND (
                    memberships.user_id <> current_setting('app.current_user_id', true)::uuid
                    OR EXISTS (
                        SELECT 1
                        FROM memberships actor_owner
                        WHERE actor_owner.organization_id = memberships.organization_id
                          AND actor_owner.user_id = current_setting('app.current_user_id', true)::uuid
                          AND actor_owner.role = 'owner'
                    )
                )
            );
        """,
    )

    # -- Schema.sql reference: RLS policies / organizations
    _execute_statements(
        """
        -- RLS: organizations
        CREATE POLICY org_organizations_select ON organizations
            FOR SELECT
            USING (
                EXISTS (
                    SELECT 1
                    FROM memberships m
                    WHERE m.organization_id = organizations.id
                      AND m.user_id = current_setting('app.current_user_id', true)::uuid
                )
            );
        """,
        """
        -- RLS: organizations
        CREATE POLICY org_organizations_insert ON organizations
            FOR INSERT
            WITH CHECK (current_setting('app.current_user_id', true) IS NOT NULL);
        """,
        """
        -- RLS: organizations
        CREATE POLICY org_organizations_update ON organizations
            FOR UPDATE
            USING (
                EXISTS (
                    SELECT 1
                    FROM memberships m
                    WHERE m.organization_id = organizations.id
                      AND m.user_id = current_setting('app.current_user_id', true)::uuid
                      AND m.role IN ('owner', 'admin')
                )
            )
            WITH CHECK (
                EXISTS (
                    SELECT 1
                    FROM memberships m
                    WHERE m.organization_id = organizations.id
                      AND m.user_id = current_setting('app.current_user_id', true)::uuid
                      AND m.role IN ('owner', 'admin')
                )
            );
        """,
        """
        -- RLS: organizations
        CREATE POLICY org_organizations_delete ON organizations
            FOR DELETE
            USING (
                EXISTS (
                    SELECT 1
                    FROM memberships m
                    WHERE m.organization_id = organizations.id
                      AND m.user_id = current_setting('app.current_user_id', true)::uuid
                      AND m.role = 'owner'
                )
            );
        """,
    )

    # -- Schema.sql reference: RLS policies / projects
    _execute_statements(
        """
        -- RLS: projects
        CREATE POLICY org_isolation_projects_select ON projects
            FOR SELECT
            USING (organization_id = current_setting('app.current_org_id', true)::uuid);
        """,
        """
        -- RLS: projects
        CREATE POLICY org_isolation_projects_insert ON projects
            FOR INSERT
            WITH CHECK (organization_id = current_setting('app.current_org_id', true)::uuid);
        """,
        """
        -- RLS: projects
        CREATE POLICY org_isolation_projects_update ON projects
            FOR UPDATE
            USING (organization_id = current_setting('app.current_org_id', true)::uuid)
            WITH CHECK (organization_id = current_setting('app.current_org_id', true)::uuid);
        """,
        """
        -- RLS: projects
        CREATE POLICY org_isolation_projects_delete ON projects
            FOR DELETE
            USING (organization_id = current_setting('app.current_org_id', true)::uuid);
        """,
    )

    # -- Schema.sql reference: RLS policies / environments
    _execute_statements(
        """
        -- RLS: environments
        CREATE POLICY org_isolation_environments_select ON environments
            FOR SELECT
            USING (project_id IN (
                SELECT id FROM projects
                WHERE organization_id = current_setting('app.current_org_id', true)::uuid
            ));
        """,
        """
        -- RLS: environments
        CREATE POLICY org_isolation_environments_insert ON environments
            FOR INSERT
            WITH CHECK (project_id IN (
                SELECT id FROM projects
                WHERE organization_id = current_setting('app.current_org_id', true)::uuid
            ));
        """,
        """
        -- RLS: environments
        CREATE POLICY org_isolation_environments_update ON environments
            FOR UPDATE
            USING (project_id IN (
                SELECT id FROM projects
                WHERE organization_id = current_setting('app.current_org_id', true)::uuid
            ))
            WITH CHECK (project_id IN (
                SELECT id FROM projects
                WHERE organization_id = current_setting('app.current_org_id', true)::uuid
            ));
        """,
        """
        -- RLS: environments
        CREATE POLICY org_isolation_environments_delete ON environments
            FOR DELETE
            USING (project_id IN (
                SELECT id FROM projects
                WHERE organization_id = current_setting('app.current_org_id', true)::uuid
            ));
        """,
    )

    # -- Schema.sql reference: RLS policies / secrets
    _execute_statements(
        """
        -- RLS: secrets
        CREATE POLICY org_isolation_secrets_select ON secrets
            FOR SELECT
            USING (environment_id IN (
                SELECT e.id FROM environments e
                JOIN projects p ON p.id = e.project_id
                WHERE p.organization_id = current_setting('app.current_org_id', true)::uuid
            ));
        """,
        """
        -- RLS: secrets
        CREATE POLICY org_isolation_secrets_insert ON secrets
            FOR INSERT
            WITH CHECK (environment_id IN (
                SELECT e.id FROM environments e
                JOIN projects p ON p.id = e.project_id
                WHERE p.organization_id = current_setting('app.current_org_id', true)::uuid
            ));
        """,
        """
        -- RLS: secrets
        CREATE POLICY org_isolation_secrets_update ON secrets
            FOR UPDATE
            USING (environment_id IN (
                SELECT e.id FROM environments e
                JOIN projects p ON p.id = e.project_id
                WHERE p.organization_id = current_setting('app.current_org_id', true)::uuid
            ))
            WITH CHECK (environment_id IN (
                SELECT e.id FROM environments e
                JOIN projects p ON p.id = e.project_id
                WHERE p.organization_id = current_setting('app.current_org_id', true)::uuid
            ));
        """,
        """
        -- RLS: secrets
        CREATE POLICY org_isolation_secrets_delete ON secrets
            FOR DELETE
            USING (environment_id IN (
                SELECT e.id FROM environments e
                JOIN projects p ON p.id = e.project_id
                WHERE p.organization_id = current_setting('app.current_org_id', true)::uuid
            ));
        """,
    )

    # -- Schema.sql reference: RLS policies / secret_versions
    _execute_statements(
        """
        -- RLS: secret_versions
        CREATE POLICY org_isolation_secret_versions_select ON secret_versions
            FOR SELECT
            USING (secret_id IN (
                SELECT s.id FROM secrets s
                JOIN environments e ON e.id = s.environment_id
                JOIN projects p ON p.id = e.project_id
                WHERE p.organization_id = current_setting('app.current_org_id', true)::uuid
            ));
        """,
        """
        -- RLS: secret_versions
        CREATE POLICY org_isolation_secret_versions_insert ON secret_versions
            FOR INSERT
            WITH CHECK (secret_id IN (
                SELECT s.id FROM secrets s
                JOIN environments e ON e.id = s.environment_id
                JOIN projects p ON p.id = e.project_id
                WHERE p.organization_id = current_setting('app.current_org_id', true)::uuid
            ));
        """,
        """
        -- RLS: secret_versions
        CREATE POLICY org_isolation_secret_versions_update ON secret_versions
            FOR UPDATE
            USING (secret_id IN (
                SELECT s.id FROM secrets s
                JOIN environments e ON e.id = s.environment_id
                JOIN projects p ON p.id = e.project_id
                WHERE p.organization_id = current_setting('app.current_org_id', true)::uuid
            ))
            WITH CHECK (secret_id IN (
                SELECT s.id FROM secrets s
                JOIN environments e ON e.id = s.environment_id
                JOIN projects p ON p.id = e.project_id
                WHERE p.organization_id = current_setting('app.current_org_id', true)::uuid
            ));
        """,
        """
        -- RLS: secret_versions
        CREATE POLICY org_isolation_secret_versions_delete ON secret_versions
            FOR DELETE
            USING (secret_id IN (
                SELECT s.id FROM secrets s
                JOIN environments e ON e.id = s.environment_id
                JOIN projects p ON p.id = e.project_id
                WHERE p.organization_id = current_setting('app.current_org_id', true)::uuid
            ));
        """,
    )

    # -- Schema.sql reference: RLS policies / encryption_keys
    _execute_statements(
        """
        -- RLS: encryption_keys
        CREATE POLICY org_isolation_encryption_keys_select ON encryption_keys
            FOR SELECT
            USING (environment_id IN (
                SELECT e.id FROM environments e
                JOIN projects p ON p.id = e.project_id
                WHERE p.organization_id = current_setting('app.current_org_id', true)::uuid
            ));
        """,
        """
        -- RLS: encryption_keys
        CREATE POLICY org_isolation_encryption_keys_insert ON encryption_keys
            FOR INSERT
            WITH CHECK (environment_id IN (
                SELECT e.id FROM environments e
                JOIN projects p ON p.id = e.project_id
                WHERE p.organization_id = current_setting('app.current_org_id', true)::uuid
            ));
        """,
        """
        -- RLS: encryption_keys
        CREATE POLICY org_isolation_encryption_keys_update ON encryption_keys
            FOR UPDATE
            USING (environment_id IN (
                SELECT e.id FROM environments e
                JOIN projects p ON p.id = e.project_id
                WHERE p.organization_id = current_setting('app.current_org_id', true)::uuid
            ))
            WITH CHECK (environment_id IN (
                SELECT e.id FROM environments e
                JOIN projects p ON p.id = e.project_id
                WHERE p.organization_id = current_setting('app.current_org_id', true)::uuid
            ));
        """,
        """
        -- RLS: encryption_keys
        CREATE POLICY org_isolation_encryption_keys_delete ON encryption_keys
            FOR DELETE
            USING (environment_id IN (
                SELECT e.id FROM environments e
                JOIN projects p ON p.id = e.project_id
                WHERE p.organization_id = current_setting('app.current_org_id', true)::uuid
            ));
        """,
    )

    # -- Schema.sql reference: RLS policies / api_tokens
    _execute_statements(
        """
        -- RLS: api_tokens
        CREATE POLICY org_isolation_api_tokens_select ON api_tokens
            FOR SELECT
            USING (project_id IN (
                SELECT id FROM projects
                WHERE organization_id = current_setting('app.current_org_id', true)::uuid
            ));
        """,
        """
        -- RLS: api_tokens
        CREATE POLICY org_isolation_api_tokens_insert ON api_tokens
            FOR INSERT
            WITH CHECK (project_id IN (
                SELECT id FROM projects
                WHERE organization_id = current_setting('app.current_org_id', true)::uuid
            ));
        """,
        """
        -- RLS: api_tokens
        CREATE POLICY org_isolation_api_tokens_update ON api_tokens
            FOR UPDATE
            USING (project_id IN (
                SELECT id FROM projects
                WHERE organization_id = current_setting('app.current_org_id', true)::uuid
            ))
            WITH CHECK (project_id IN (
                SELECT id FROM projects
                WHERE organization_id = current_setting('app.current_org_id', true)::uuid
            ));
        """,
        """
        -- RLS: api_tokens
        CREATE POLICY org_isolation_api_tokens_delete ON api_tokens
            FOR DELETE
            USING (project_id IN (
                SELECT id FROM projects
                WHERE organization_id = current_setting('app.current_org_id', true)::uuid
            ));
        """,
    )

    # -- Schema.sql reference: RLS policies / audit_logs
    _execute_statements(
        """
        -- RLS: audit_logs
        CREATE POLICY org_isolation_audit_logs_select ON audit_logs
            FOR SELECT
            USING (organization_id = current_setting('app.current_org_id', true)::uuid);
        """,
        """
        -- RLS: audit_logs
        CREATE POLICY org_isolation_audit_logs_insert ON audit_logs
            FOR INSERT
            WITH CHECK (organization_id = current_setting('app.current_org_id', true)::uuid);
        """,
        """
        -- RLS: audit_logs
        CREATE POLICY org_isolation_audit_logs_update ON audit_logs
            FOR UPDATE
            USING (organization_id = current_setting('app.current_org_id', true)::uuid)
            WITH CHECK (organization_id = current_setting('app.current_org_id', true)::uuid);
        """,
        """
        -- RLS: audit_logs
        CREATE POLICY org_isolation_audit_logs_delete ON audit_logs
            FOR DELETE
            USING (organization_id = current_setting('app.current_org_id', true)::uuid);
        """,
    )


def downgrade() -> None:
    """Downgrade schema."""
    # -- Schema.sql reference: RLS policies / audit_logs -> api_tokens -> encryption_keys -> secret_versions -> secrets -> environments -> projects -> organizations/memberships -> restrictive membership guard
    _execute_statements(
        """
        -- RLS: audit_logs
        DROP POLICY org_isolation_audit_logs_delete ON audit_logs;
        """,
        """
        -- RLS: audit_logs
        DROP POLICY org_isolation_audit_logs_update ON audit_logs;
        """,
        """
        -- RLS: audit_logs
        DROP POLICY org_isolation_audit_logs_insert ON audit_logs;
        """,
        """
        -- RLS: audit_logs
        DROP POLICY org_isolation_audit_logs_select ON audit_logs;
        """,
        """
        -- RLS: api_tokens
        DROP POLICY org_isolation_api_tokens_delete ON api_tokens;
        """,
        """
        -- RLS: api_tokens
        DROP POLICY org_isolation_api_tokens_update ON api_tokens;
        """,
        """
        -- RLS: api_tokens
        DROP POLICY org_isolation_api_tokens_insert ON api_tokens;
        """,
        """
        -- RLS: api_tokens
        DROP POLICY org_isolation_api_tokens_select ON api_tokens;
        """,
        """
        -- RLS: encryption_keys
        DROP POLICY org_isolation_encryption_keys_delete ON encryption_keys;
        """,
        """
        -- RLS: encryption_keys
        DROP POLICY org_isolation_encryption_keys_update ON encryption_keys;
        """,
        """
        -- RLS: encryption_keys
        DROP POLICY org_isolation_encryption_keys_insert ON encryption_keys;
        """,
        """
        -- RLS: encryption_keys
        DROP POLICY org_isolation_encryption_keys_select ON encryption_keys;
        """,
        """
        -- RLS: secret_versions
        DROP POLICY org_isolation_secret_versions_delete ON secret_versions;
        """,
        """
        -- RLS: secret_versions
        DROP POLICY org_isolation_secret_versions_update ON secret_versions;
        """,
        """
        -- RLS: secret_versions
        DROP POLICY org_isolation_secret_versions_insert ON secret_versions;
        """,
        """
        -- RLS: secret_versions
        DROP POLICY org_isolation_secret_versions_select ON secret_versions;
        """,
        """
        -- RLS: secrets
        DROP POLICY org_isolation_secrets_delete ON secrets;
        """,
        """
        -- RLS: secrets
        DROP POLICY org_isolation_secrets_update ON secrets;
        """,
        """
        -- RLS: secrets
        DROP POLICY org_isolation_secrets_insert ON secrets;
        """,
        """
        -- RLS: secrets
        DROP POLICY org_isolation_secrets_select ON secrets;
        """,
        """
        -- RLS: environments
        DROP POLICY org_isolation_environments_delete ON environments;
        """,
        """
        -- RLS: environments
        DROP POLICY org_isolation_environments_update ON environments;
        """,
        """
        -- RLS: environments
        DROP POLICY org_isolation_environments_insert ON environments;
        """,
        """
        -- RLS: environments
        DROP POLICY org_isolation_environments_select ON environments;
        """,
        """
        -- RLS: projects
        DROP POLICY org_isolation_projects_delete ON projects;
        """,
        """
        -- RLS: projects
        DROP POLICY org_isolation_projects_update ON projects;
        """,
        """
        -- RLS: projects
        DROP POLICY org_isolation_projects_insert ON projects;
        """,
        """
        -- RLS: projects
        DROP POLICY org_isolation_projects_select ON projects;
        """,
        """
        -- RLS: organizations
        DROP POLICY org_organizations_delete ON organizations;
        """,
        """
        -- RLS: organizations
        DROP POLICY org_organizations_update ON organizations;
        """,
        """
        -- RLS: organizations
        DROP POLICY org_organizations_insert ON organizations;
        """,
        """
        -- RLS: organizations
        DROP POLICY org_organizations_select ON organizations;
        """,
        """
        -- RLS: memberships
        DROP POLICY org_memberships_delete ON memberships;
        """,
        """
        -- RLS: memberships
        DROP POLICY org_memberships_update ON memberships;
        """,
        """
        -- RLS: memberships
        DROP POLICY org_memberships_insert ON memberships;
        """,
        """
        -- RLS: memberships
        DROP POLICY org_memberships_select ON memberships;
        """,
        """
        -- RLS: restrictive membership guard
        DROP POLICY org_context_member_audit_logs ON audit_logs;
        """,
        """
        -- RLS: restrictive membership guard
        DROP POLICY org_context_member_api_tokens ON api_tokens;
        """,
        """
        -- RLS: restrictive membership guard
        DROP POLICY org_context_member_encryption_keys ON encryption_keys;
        """,
        """
        -- RLS: restrictive membership guard
        DROP POLICY org_context_member_secret_versions ON secret_versions;
        """,
        """
        -- RLS: restrictive membership guard
        DROP POLICY org_context_member_secrets ON secrets;
        """,
        """
        -- RLS: restrictive membership guard
        DROP POLICY org_context_member_environments ON environments;
        """,
        """
        -- RLS: restrictive membership guard
        DROP POLICY org_context_member_projects ON projects;
        """,
    )

    # -- Schema.sql reference: triggers / reverse order
    _execute_statements(
        """
        -- Trigger: audit_logs inmutable
        DROP TRIGGER trg_audit_logs_no_delete ON audit_logs;
        """,
        """
        -- Trigger: audit_logs inmutable
        DROP TRIGGER trg_audit_logs_no_update ON audit_logs;
        """,
        """
        -- Trigger: current_version validation
        DROP TRIGGER trg_secrets_current_version_matches_secret ON secrets;
        """,
        """
        -- Trigger: updated_at
        DROP TRIGGER trg_secrets_updated_at ON secrets;
        """,
        """
        -- Trigger: updated_at
        DROP TRIGGER trg_projects_updated_at ON projects;
        """,
        """
        -- Trigger: updated_at
        DROP TRIGGER trg_users_updated_at ON users;
        """,
        """
        -- Trigger: updated_at
        DROP TRIGGER trg_organizations_updated_at ON organizations;
        """,
    )

    # -- Schema.sql reference: functions / reverse order
    _execute_statements(
        """
        -- Funcion: current_user_belongs_to_current_org
        DROP FUNCTION current_user_belongs_to_current_org();
        """,
        """
        -- Funcion: reject_audit_log_mutation
        DROP FUNCTION reject_audit_log_mutation();
        """,
        """
        -- Funcion: validate_secret_current_version_belongs_to_secret
        DROP FUNCTION validate_secret_current_version_belongs_to_secret();
        """,
        """
        -- Funcion auxiliar: set_updated_at
        DROP FUNCTION set_updated_at();
        """,
    )

    op.drop_index("idx_audit_logs_resource", table_name="audit_logs")
    op.drop_index("idx_audit_logs_org", table_name="audit_logs")
    op.drop_table("audit_logs")

    op.drop_index("idx_refresh_tokens_user", table_name="refresh_tokens", postgresql_where=sa.text("revoked_at IS NULL"))
    op.drop_table("refresh_tokens")

    op.drop_index("idx_api_tokens_project", table_name="api_tokens", postgresql_where=sa.text("revoked_at IS NULL"))
    op.drop_table("api_tokens")

    op.drop_constraint("fk_secrets_current_version", "secrets", type_="foreignkey")
    op.drop_index("idx_secret_versions_secret", table_name="secret_versions")
    op.drop_table("secret_versions")

    op.drop_index("idx_secrets_env", table_name="secrets", postgresql_where=sa.text("is_deleted = false"))
    op.drop_table("secrets")

    op.drop_index("uq_one_active_key_per_env", table_name="encryption_keys", postgresql_where=sa.text("is_active = true"))
    op.drop_index("idx_encryption_keys_env", table_name="encryption_keys", postgresql_where=sa.text("is_active = true"))
    op.drop_table("encryption_keys")

    op.drop_index("idx_environments_project", table_name="environments")
    op.drop_table("environments")

    op.drop_index("idx_projects_org", table_name="projects")
    op.drop_table("projects")

    op.drop_index("idx_memberships_user", table_name="memberships")
    op.drop_index("idx_memberships_org", table_name="memberships")
    op.drop_table("memberships")

    op.drop_table("users")
    op.drop_table("organizations")

    # -- Schema.sql reference: enums
    _execute_statements(
        """
        -- ENUMS
        DROP TYPE audit_resource_type;
        """,
        """
        -- ENUMS
        DROP TYPE audit_action;
        """,
        """
        -- ENUMS
        DROP TYPE membership_role;
        """,
    )

    # -- Schema.sql reference: extensions
    _execute_statements(
        """
        -- EXTENSIONS
        DROP EXTENSION citext;
        """,
        """
        -- EXTENSIONS
        DROP EXTENSION pgcrypto;
        """,
    )
