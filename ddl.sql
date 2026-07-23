-- ============================================================================
-- EnvVault — Esquema de base de datos (PostgreSQL 15+)
-- ============================================================================
-- Estrategia:
--   1) Identidad: la API setea `app.current_user_id` después de validar JWT.
--   2) Contexto operativo: la API setea `app.current_org_id` solo si el usuario
--      pertenece a esa organización.
-- `memberships` y `organizations` usan policies por identidad.
-- El resto de tablas usa policies por organización + membership activa.
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;   -- gen_random_uuid(), funciones de cifrado
CREATE EXTENSION IF NOT EXISTS citext;     -- email case-insensitive

-- ============================================================================
-- ENUMS
-- ============================================================================

CREATE TYPE membership_role AS ENUM ('owner', 'admin', 'member', 'viewer');
CREATE TYPE audit_action AS ENUM (
    'create', 'update', 'delete', 'reveal', 'rollback',
    'login', 'login_failed', 'invite', 'role_change'
);
CREATE TYPE audit_resource_type AS ENUM (
    'organization', 'project', 'environment', 'secret', 'membership', 'api_token'
);

-- ============================================================================
-- FUNCIÓN AUXILIAR: updated_at automático
-- ============================================================================

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- ORGANIZATIONS — tenant raíz
-- ============================================================================

CREATE TABLE organizations (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        TEXT NOT NULL,
    slug        TEXT NOT NULL UNIQUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TRIGGER trg_organizations_updated_at
    BEFORE UPDATE ON organizations
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ============================================================================
-- USERS — cuentas de usuario, independientes de organización
-- ============================================================================

CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email           CITEXT NOT NULL UNIQUE,
    password_hash   TEXT,                       -- NULL si el usuario solo usa OAuth
    full_name       TEXT,
    totp_secret     TEXT,                        -- cifrado a nivel de aplicación
    totp_enabled    BOOLEAN NOT NULL DEFAULT false,
    oauth_provider  TEXT,                        -- 'github', 'google', NULL si password
    oauth_subject   TEXT,                        -- id del usuario en el proveedor OAuth
    is_active       BOOLEAN NOT NULL DEFAULT true,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT chk_auth_method CHECK (
        password_hash IS NOT NULL OR (oauth_provider IS NOT NULL AND oauth_subject IS NOT NULL)
    ),
    CONSTRAINT uq_users_oauth_identity UNIQUE (oauth_provider, oauth_subject)
);

CREATE TRIGGER trg_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ============================================================================
-- MEMBERSHIPS — relación N:M entre users y organizations, con rol
-- ============================================================================

CREATE TABLE memberships (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    role            membership_role NOT NULL DEFAULT 'member',
    invited_by      UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_membership UNIQUE (user_id, organization_id)
);

CREATE INDEX idx_memberships_org ON memberships(organization_id);
CREATE INDEX idx_memberships_user ON memberships(user_id);

-- ============================================================================
-- PROJECTS
-- ============================================================================

CREATE TABLE projects (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    name            TEXT NOT NULL,
    slug            TEXT NOT NULL,
    description     TEXT,
    created_by      UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_project_slug_per_org UNIQUE (organization_id, slug)
);

CREATE INDEX idx_projects_org ON projects(organization_id);

CREATE TRIGGER trg_projects_updated_at
    BEFORE UPDATE ON projects
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ============================================================================
-- ENVIRONMENTS — Desarrollo, Staging, Producción, etc. por proyecto
-- ============================================================================

CREATE TABLE environments (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id  UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,               -- ej. "development", "staging", "production"
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_environment_name_per_project UNIQUE (project_id, name)
);

CREATE INDEX idx_environments_project ON environments(project_id);

-- ============================================================================
-- ENCRYPTION_KEYS — DEK envuelta (wrapped) por environment (envelope encryption)
-- ============================================================================
-- La master key vive FUERA de la base de datos (KMS / variable de entorno segura).
-- wrapped_dek = DEK cifrada con la master key. Nunca se guarda la DEK en claro.

CREATE TABLE encryption_keys (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    environment_id  UUID NOT NULL REFERENCES environments(id) ON DELETE CASCADE,
    wrapped_dek     BYTEA NOT NULL,
    key_version     INTEGER NOT NULL DEFAULT 1,
    algorithm       TEXT NOT NULL DEFAULT 'AES-256-GCM',
    is_active       BOOLEAN NOT NULL DEFAULT true,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    rotated_at      TIMESTAMPTZ,

    CONSTRAINT uq_key_version_per_env UNIQUE (environment_id, key_version),
    CONSTRAINT chk_encryption_keys_algorithm CHECK (algorithm IN ('AES-256-GCM'))
);

CREATE INDEX idx_encryption_keys_env ON encryption_keys(environment_id) WHERE is_active = true;
CREATE UNIQUE INDEX uq_one_active_key_per_env
    ON encryption_keys(environment_id)
    WHERE is_active = true;

-- ============================================================================
-- SECRETS — "puntero" a la variable; el valor real vive en secret_versions
-- ============================================================================

CREATE TABLE secrets (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    environment_id      UUID NOT NULL REFERENCES environments(id) ON DELETE CASCADE,
    key_name            TEXT NOT NULL,          -- ej. "DATABASE_URL"
    current_version_id  UUID,                    -- FK a secret_versions, se setea tras insertar la 1ra versión
    is_deleted          BOOLEAN NOT NULL DEFAULT false,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_secret_key_per_env UNIQUE (environment_id, key_name)
);

CREATE INDEX idx_secrets_env ON secrets(environment_id) WHERE is_deleted = false;

CREATE TRIGGER trg_secrets_updated_at
    BEFORE UPDATE ON secrets
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ============================================================================
-- SECRET_VERSIONS — historial completo de valores (permite rollback)
-- ============================================================================

CREATE TABLE secret_versions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    secret_id       UUID NOT NULL REFERENCES secrets(id) ON DELETE CASCADE,
    encryption_key_id UUID NOT NULL REFERENCES encryption_keys(id),
    encrypted_value BYTEA NOT NULL,
    iv              BYTEA NOT NULL,              -- nonce único por versión, NUNCA reutilizado
    version_number  INTEGER NOT NULL,
    created_by      UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_secret_version UNIQUE (secret_id, version_number),
    CONSTRAINT uq_secret_versions_key_iv UNIQUE (encryption_key_id, iv)
);

CREATE INDEX idx_secret_versions_secret ON secret_versions(secret_id);

-- FK diferida: secrets.current_version_id apunta a secret_versions
ALTER TABLE secrets
    ADD CONSTRAINT fk_secrets_current_version
    FOREIGN KEY (current_version_id) REFERENCES secret_versions(id) ON DELETE SET NULL
    DEFERRABLE INITIALLY DEFERRED;

-- Garantiza que current_version_id pertenezca al mismo secret
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

CREATE CONSTRAINT TRIGGER trg_secrets_current_version_matches_secret
    AFTER INSERT OR UPDATE OF current_version_id ON secrets
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION validate_secret_current_version_belongs_to_secret();

-- ============================================================================
-- API_TOKENS — tokens de servicio (CLI, CI/CD) con scope limitado
-- ============================================================================

CREATE TABLE api_tokens (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id  UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,                   -- ej. "GitHub Actions - prod deploy"
    token_hash  TEXT NOT NULL UNIQUE,             -- SHA-256 del token; el token real solo se muestra 1 vez
    scope       TEXT NOT NULL,                    -- ej. "read:production", "read:*"
    created_by  UUID REFERENCES users(id) ON DELETE SET NULL,
    last_used_at TIMESTAMPTZ,
    expires_at  TIMESTAMPTZ,
    revoked_at  TIMESTAMPTZ,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_api_tokens_project ON api_tokens(project_id) WHERE revoked_at IS NULL;

-- ============================================================================
-- REFRESH_TOKENS — rotación de JWT
-- ============================================================================

CREATE TABLE refresh_tokens (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash  TEXT NOT NULL UNIQUE,
    expires_at  TIMESTAMPTZ NOT NULL,
    revoked_at  TIMESTAMPTZ,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_refresh_tokens_user ON refresh_tokens(user_id) WHERE revoked_at IS NULL;

-- ============================================================================
-- AUDIT_LOGS — registro inmutable de actividad
-- ============================================================================

CREATE TABLE audit_logs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID REFERENCES organizations(id) ON DELETE SET NULL,
    user_id         UUID REFERENCES users(id) ON DELETE SET NULL,
    action          audit_action NOT NULL,
    resource_type   audit_resource_type NOT NULL,
    resource_id     UUID,
    metadata        JSONB,                        -- contexto adicional (ip, user_agent, diff, etc.)
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_audit_logs_org ON audit_logs(organization_id, created_at DESC);
CREATE INDEX idx_audit_logs_resource ON audit_logs(resource_type, resource_id);

-- Inmutabilidad: bloquear UPDATE y DELETE a nivel de base de datos
CREATE OR REPLACE FUNCTION reject_audit_log_mutation()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'audit_logs es de solo escritura (append-only); % no permitido', TG_OP;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_audit_logs_no_update
    BEFORE UPDATE ON audit_logs
    FOR EACH ROW EXECUTE FUNCTION reject_audit_log_mutation();

CREATE TRIGGER trg_audit_logs_no_delete
    BEFORE DELETE ON audit_logs
    FOR EACH ROW EXECUTE FUNCTION reject_audit_log_mutation();

-- ============================================================================
-- ROW LEVEL SECURITY (RLS)
-- ============================================================================
-- Estrategia: cada request de la API setea `app.current_org_id` vía
--   SET LOCAL app.current_org_id = '<uuid>';
-- al inicio de la transacción (después de validar el JWT y la membership).
-- Las policies filtran automáticamente cualquier query por esa organización,
-- como segunda capa de defensa además del filtrado en la capa de servicio.

ALTER TABLE organizations   ENABLE ROW LEVEL SECURITY;
ALTER TABLE memberships     ENABLE ROW LEVEL SECURITY;
ALTER TABLE projects        ENABLE ROW LEVEL SECURITY;
ALTER TABLE environments     ENABLE ROW LEVEL SECURITY;
ALTER TABLE secrets          ENABLE ROW LEVEL SECURITY;
ALTER TABLE secret_versions  ENABLE ROW LEVEL SECURITY;
ALTER TABLE encryption_keys  ENABLE ROW LEVEL SECURITY;
ALTER TABLE api_tokens       ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_logs       ENABLE ROW LEVEL SECURITY;

ALTER TABLE organizations   FORCE ROW LEVEL SECURITY;
ALTER TABLE memberships     FORCE ROW LEVEL SECURITY;
ALTER TABLE projects        FORCE ROW LEVEL SECURITY;
ALTER TABLE environments    FORCE ROW LEVEL SECURITY;
ALTER TABLE secrets         FORCE ROW LEVEL SECURITY;
ALTER TABLE secret_versions FORCE ROW LEVEL SECURITY;
ALTER TABLE encryption_keys FORCE ROW LEVEL SECURITY;
ALTER TABLE api_tokens      FORCE ROW LEVEL SECURITY;
ALTER TABLE audit_logs      FORCE ROW LEVEL SECURITY;


-- Lectura segura de GUCs de sesión: '' (o unset) → NULL, nunca ''::uuid.
CREATE OR REPLACE FUNCTION app_setting_uuid(p_name text)
RETURNS uuid
LANGUAGE sql
STABLE
AS $$
    SELECT NULLIF(current_setting(p_name, true), '')::uuid;
$$;

CREATE OR REPLACE FUNCTION current_user_belongs_to_current_org()
RETURNS BOOLEAN
LANGUAGE SQL
STABLE
AS $$
    SELECT EXISTS (
        SELECT 1
        FROM memberships m
        WHERE m.organization_id = app_setting_uuid('app.current_org_id')
          AND m.user_id = app_setting_uuid('app.current_user_id')
    );
$$;

-- Bootstrap de organización bajo FORCE RLS.
-- INSERT ... RETURNING evalúa también la policy SELECT (que exige membership),
-- así que org+owner se crean de forma atómica como SECURITY DEFINER.
-- EXECUTE solo para envvault_app (nunca PUBLIC).
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

REVOKE ALL ON FUNCTION create_organization_with_owner(text, text, uuid) FROM PUBLIC;
-- Requiere que envvault_app ya exista (NO se crea aquí).
-- Provisioning: backend/scripts/provision_app_role.sh  (LOGIN + PASSWORD fuera de Alembic)
-- Ver backend/README.md → "Database roles".
GRANT EXECUTE ON FUNCTION create_organization_with_owner(text, text, uuid) TO envvault_app;

CREATE POLICY org_context_member_projects ON projects
    AS RESTRICTIVE
    FOR ALL
    USING (current_user_belongs_to_current_org())
    WITH CHECK (current_user_belongs_to_current_org());

CREATE POLICY org_context_member_environments ON environments
    AS RESTRICTIVE
    FOR ALL
    USING (current_user_belongs_to_current_org())
    WITH CHECK (current_user_belongs_to_current_org());

CREATE POLICY org_context_member_secrets ON secrets
    AS RESTRICTIVE
    FOR ALL
    USING (current_user_belongs_to_current_org())
    WITH CHECK (current_user_belongs_to_current_org());

CREATE POLICY org_context_member_secret_versions ON secret_versions
    AS RESTRICTIVE
    FOR ALL
    USING (current_user_belongs_to_current_org())
    WITH CHECK (current_user_belongs_to_current_org());

CREATE POLICY org_context_member_encryption_keys ON encryption_keys
    AS RESTRICTIVE
    FOR ALL
    USING (current_user_belongs_to_current_org())
    WITH CHECK (current_user_belongs_to_current_org());

CREATE POLICY org_context_member_api_tokens ON api_tokens
    AS RESTRICTIVE
    FOR ALL
    USING (current_user_belongs_to_current_org())
    WITH CHECK (current_user_belongs_to_current_org());

CREATE POLICY org_context_member_audit_logs ON audit_logs
    AS RESTRICTIVE
    FOR ALL
    USING (current_user_belongs_to_current_org())
    WITH CHECK (current_user_belongs_to_current_org());

CREATE POLICY org_memberships_select ON memberships
    FOR SELECT
    USING (user_id = app_setting_uuid('app.current_user_id'));

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

CREATE POLICY org_organizations_insert ON organizations
    FOR INSERT
    WITH CHECK (app_setting_uuid('app.current_user_id') IS NOT NULL);

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

CREATE POLICY org_isolation_projects_select ON projects
    FOR SELECT
    USING (organization_id = app_setting_uuid('app.current_org_id'));

CREATE POLICY org_isolation_projects_insert ON projects
    FOR INSERT
    WITH CHECK (organization_id = app_setting_uuid('app.current_org_id'));

CREATE POLICY org_isolation_projects_update ON projects
    FOR UPDATE
    USING (organization_id = app_setting_uuid('app.current_org_id'))
    WITH CHECK (organization_id = app_setting_uuid('app.current_org_id'));

CREATE POLICY org_isolation_projects_delete ON projects
    FOR DELETE
    USING (organization_id = app_setting_uuid('app.current_org_id'));

CREATE POLICY org_isolation_environments_select ON environments
    FOR SELECT
    USING (project_id IN (
        SELECT id FROM projects
        WHERE organization_id = app_setting_uuid('app.current_org_id')
    ));

CREATE POLICY org_isolation_environments_insert ON environments
    FOR INSERT
    WITH CHECK (project_id IN (
        SELECT id FROM projects
        WHERE organization_id = app_setting_uuid('app.current_org_id')
    ));

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

CREATE POLICY org_isolation_environments_delete ON environments
    FOR DELETE
    USING (project_id IN (
        SELECT id FROM projects
        WHERE organization_id = app_setting_uuid('app.current_org_id')
    ));

CREATE POLICY org_isolation_secrets_select ON secrets
    FOR SELECT
    USING (environment_id IN (
        SELECT e.id FROM environments e
        JOIN projects p ON p.id = e.project_id
        WHERE p.organization_id = app_setting_uuid('app.current_org_id')
    ));

CREATE POLICY org_isolation_secrets_insert ON secrets
    FOR INSERT
    WITH CHECK (environment_id IN (
        SELECT e.id FROM environments e
        JOIN projects p ON p.id = e.project_id
        WHERE p.organization_id = app_setting_uuid('app.current_org_id')
    ));

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

CREATE POLICY org_isolation_secrets_delete ON secrets
    FOR DELETE
    USING (environment_id IN (
        SELECT e.id FROM environments e
        JOIN projects p ON p.id = e.project_id
        WHERE p.organization_id = app_setting_uuid('app.current_org_id')
    ));

CREATE POLICY org_isolation_secret_versions_select ON secret_versions
    FOR SELECT
    USING (secret_id IN (
        SELECT s.id FROM secrets s
        JOIN environments e ON e.id = s.environment_id
        JOIN projects p ON p.id = e.project_id
        WHERE p.organization_id = app_setting_uuid('app.current_org_id')
    ));

CREATE POLICY org_isolation_secret_versions_insert ON secret_versions
    FOR INSERT
    WITH CHECK (secret_id IN (
        SELECT s.id FROM secrets s
        JOIN environments e ON e.id = s.environment_id
        JOIN projects p ON p.id = e.project_id
        WHERE p.organization_id = app_setting_uuid('app.current_org_id')
    ));

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

CREATE POLICY org_isolation_secret_versions_delete ON secret_versions
    FOR DELETE
    USING (secret_id IN (
        SELECT s.id FROM secrets s
        JOIN environments e ON e.id = s.environment_id
        JOIN projects p ON p.id = e.project_id
        WHERE p.organization_id = app_setting_uuid('app.current_org_id')
    ));

CREATE POLICY org_isolation_encryption_keys_select ON encryption_keys
    FOR SELECT
    USING (environment_id IN (
        SELECT e.id FROM environments e
        JOIN projects p ON p.id = e.project_id
        WHERE p.organization_id = app_setting_uuid('app.current_org_id')
    ));

CREATE POLICY org_isolation_encryption_keys_insert ON encryption_keys
    FOR INSERT
    WITH CHECK (environment_id IN (
        SELECT e.id FROM environments e
        JOIN projects p ON p.id = e.project_id
        WHERE p.organization_id = app_setting_uuid('app.current_org_id')
    ));

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

CREATE POLICY org_isolation_encryption_keys_delete ON encryption_keys
    FOR DELETE
    USING (environment_id IN (
        SELECT e.id FROM environments e
        JOIN projects p ON p.id = e.project_id
        WHERE p.organization_id = app_setting_uuid('app.current_org_id')
    ));

CREATE POLICY org_isolation_api_tokens_select ON api_tokens
    FOR SELECT
    USING (project_id IN (
        SELECT id FROM projects
        WHERE organization_id = app_setting_uuid('app.current_org_id')
    ));

CREATE POLICY org_isolation_api_tokens_insert ON api_tokens
    FOR INSERT
    WITH CHECK (project_id IN (
        SELECT id FROM projects
        WHERE organization_id = app_setting_uuid('app.current_org_id')
    ));

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

CREATE POLICY org_isolation_api_tokens_delete ON api_tokens
    FOR DELETE
    USING (project_id IN (
        SELECT id FROM projects
        WHERE organization_id = app_setting_uuid('app.current_org_id')
    ));

CREATE POLICY org_isolation_audit_logs_select ON audit_logs
    FOR SELECT
    USING (organization_id = app_setting_uuid('app.current_org_id'));

CREATE POLICY org_isolation_audit_logs_insert ON audit_logs
    FOR INSERT
    WITH CHECK (organization_id = app_setting_uuid('app.current_org_id'));

CREATE POLICY org_isolation_audit_logs_update ON audit_logs
    FOR UPDATE
    USING (organization_id = app_setting_uuid('app.current_org_id'))
    WITH CHECK (organization_id = app_setting_uuid('app.current_org_id'));

CREATE POLICY org_isolation_audit_logs_delete ON audit_logs
    FOR DELETE
    USING (organization_id = app_setting_uuid('app.current_org_id'));

-- Rol de aplicación: SIN BYPASSRLS (los superusers ignoran FORCE RLS).
-- Creación + LOGIN/PASSWORD: fuera de este archivo y fuera de Alembic.
--   backend/scripts/provision_app_role.sh
--   (requiere conectar como superuser o rol con CREATEROLE)
-- Después de crear tablas: ./scripts/provision_app_role.sh --grants
-- Documentación: backend/README.md → "Database roles".

-- ============================================================================
-- FIN DEL ESQUEMA BASE
-- ============================================================================
