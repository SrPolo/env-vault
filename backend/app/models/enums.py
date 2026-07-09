from sqlalchemy.dialects import postgresql

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
