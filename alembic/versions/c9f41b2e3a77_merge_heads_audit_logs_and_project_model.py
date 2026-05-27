"""merge heads: audit logs + project model

Revision ID: c9f41b2e3a77
Revises: c4c8f6b2e1a9, 9b2b0a7f5d2a
Create Date: 2026-05-27

"""

from typing import Sequence, Union

from alembic import op


revision: str = "c9f41b2e3a77"
down_revision: Union[str, tuple[str, str], None] = ("c4c8f6b2e1a9", "9b2b0a7f5d2a")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # This is a merge revision; no schema changes.
    pass


def downgrade() -> None:
    # This is a merge revision; no schema changes.
    pass

