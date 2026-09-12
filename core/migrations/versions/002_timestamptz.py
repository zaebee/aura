"""Timestamps to timestamptz for the async driver

Revision ID: 002_timestamptz
Revises: 001_add_locked_deals
Create Date: 2026-09-12

asyncpg refuses timezone-aware datetimes for TIMESTAMP WITHOUT TIME ZONE
columns, while psycopg2 silently stripped the offset. The models emit
aware datetimes (`datetime.now(UTC)`), so the columns become TIMESTAMPTZ
instead of coercing the values. Existing naive values are interpreted in
the server timezone (UTC on our images).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "002_timestamptz"
down_revision: str | None = "001_add_locked_deals"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ALTERS: tuple[tuple[str, str], ...] = (
    ("locked_deals", "created_at"),
    ("locked_deals", "expires_at"),
    ("locked_deals", "paid_at"),
    ("locked_deals", "updated_at"),
    ("sanctified_wallets", "created_at"),
    ("metabolic_costs", "timestamp"),
    ("decision_receipts", "recorded_at"),
)


def upgrade() -> None:
    """TIMESTAMP -> TIMESTAMPTZ on all model datetime columns."""
    for table, column in _ALTERS:
        op.alter_column(
            table,
            column,
            existing_type=sa.DateTime(),
            type_=sa.DateTime(timezone=True),
            existing_nullable=column in ("paid_at",),
        )


def downgrade() -> None:
    """TIMESTAMPTZ -> TIMESTAMP (offsets are dropped on the way back)."""
    for table, column in reversed(_ALTERS):
        op.alter_column(
            table,
            column,
            existing_type=sa.DateTime(timezone=True),
            type_=sa.DateTime(),
            existing_nullable=column in ("paid_at",),
        )
