"""Add locked_deals table for crypto payments

Revision ID: 001_add_locked_deals
Revises: 77450f9e9330
Create Date: 2026-01-29

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "001_add_locked_deals"
down_revision: str | None = "77450f9e9330"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create locked_deals table with indexes."""
    # Create enum type for deal status
    deal_status_enum = postgresql.ENUM("PENDING", "PAID", "EXPIRED", name="dealstatus")
    deal_status_enum.create(op.get_bind(), checkfirst=True)

    # Create locked_deals table
    op.create_table(
        "locked_deals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("item_id", sa.String(), nullable=False),
        sa.Column("item_name", sa.String(), nullable=False),
        sa.Column("final_price", sa.Float(), nullable=False),
        sa.Column("currency", sa.String(), nullable=False),
        sa.Column("payment_memo", sa.String(), nullable=False),
        sa.Column("secret_content", sa.LargeBinary(), nullable=False),
        sa.Column("status", deal_status_enum, nullable=False),
        sa.Column("buyer_did", sa.String(), nullable=True),
        sa.Column("transaction_hash", sa.String(), nullable=True),
        sa.Column("block_number", sa.String(), nullable=True),
        sa.Column("from_address", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("paid_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )

    # Create indexes for performance
    op.create_index(
        "ix_locked_deals_payment_memo", "locked_deals", ["payment_memo"], unique=True
    )
    op.create_index("ix_locked_deals_status", "locked_deals", ["status"])
    op.create_index("ix_locked_deals_expires_at", "locked_deals", ["expires_at"])
    op.create_index("ix_locked_deals_item_id", "locked_deals", ["item_id"])
    op.create_index("ix_locked_deals_buyer_did", "locked_deals", ["buyer_did"])


def downgrade() -> None:
    """Drop locked_deals table and enum type."""
    op.drop_index("ix_locked_deals_buyer_did", table_name="locked_deals")
    op.drop_index("ix_locked_deals_item_id", table_name="locked_deals")
    op.drop_index("ix_locked_deals_expires_at", table_name="locked_deals")
    op.drop_index("ix_locked_deals_status", table_name="locked_deals")
    op.drop_index("ix_locked_deals_payment_memo", table_name="locked_deals")
    op.drop_table("locked_deals")
    sa.Enum("PENDING", "PAID", "EXPIRED", name="dealstatus").drop(op.get_bind())
