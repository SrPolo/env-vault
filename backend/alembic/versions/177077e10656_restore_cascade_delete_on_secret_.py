"""restore cascade delete on secret_versions secret_id fk

Revision ID: 177077e10656
Revises: b7981284763f
Create Date: 2026-07-21 08:58:31.552246

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '177077e10656'
down_revision: Union[str, Sequence[str], None] = 'b7981284763f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_constraint(
        "secret_versions_secret_id_fkey", "secret_versions", type_="foreignkey"
    )
    op.create_foreign_key(
        "secret_versions_secret_id_fkey",
        "secret_versions",
        "secrets",
        ["secret_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(
        "secret_versions_secret_id_fkey", "secret_versions", type_="foreignkey"
    )
    op.create_foreign_key(
        "secret_versions_secret_id_fkey",
        "secret_versions",
        "secrets",
        ["secret_id"],
        ["id"],
    )
