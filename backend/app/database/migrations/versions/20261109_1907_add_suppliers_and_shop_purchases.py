"""Add allowed suppliers, shop purchases (a ledger kind and buyer shops) and pending rules on owner signatures.

Revision ID: fd43b53ca092
Revises: 84cb0f6630f5
Create Date: 2026-11-09 19:07:59.865070+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'fd43b53ca092'
down_revision: Union[str, Sequence[str], None] = '84cb0f6630f5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Autogenerate doesn't see CHECK changes: the ledger gains 'purchase'.
    op.drop_constraint(op.f('ck_ledger_entries_kind'), 'ledger_entries', type_='check')
    op.create_check_constraint(op.f('ck_ledger_entries_kind'), 'ledger_entries',
                               "kind IN ('sale', 'fee', 'payout', 'refund', 'purchase')")
    op.create_table('shop_suppliers',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('shop_id', sa.UUID(), nullable=False),
    sa.Column('supplier_shop_id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('shop_id <> supplier_shop_id', name=op.f('ck_shop_suppliers_not_itself')),
    sa.ForeignKeyConstraint(['shop_id'], ['shops.id'], name=op.f('fk_shop_suppliers_shop_id_shops'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['supplier_shop_id'], ['shops.id'], name=op.f('fk_shop_suppliers_supplier_shop_id_shops'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_shop_suppliers')),
    sa.UniqueConstraint('shop_id', 'supplier_shop_id', name='uq_shop_suppliers_shop_id_supplier_shop_id')
    )
    op.create_index(op.f('ix_shop_suppliers_supplier_shop_id'), 'shop_suppliers', ['supplier_shop_id'], unique=False)
    op.add_column('group_order_members', sa.Column('buyer_shop_id', sa.UUID(), nullable=True))
    op.create_index(op.f('ix_group_order_members_buyer_shop_id'), 'group_order_members', ['buyer_shop_id'], unique=False)
    op.create_foreign_key(op.f('fk_group_order_members_buyer_shop_id_shops'), 'group_order_members', 'shops', ['buyer_shop_id'], ['id'], ondelete='SET NULL')
    op.add_column('invoices', sa.Column('buyer_shop_id', sa.UUID(), nullable=True))
    op.create_index(op.f('ix_invoices_buyer_shop_id'), 'invoices', ['buyer_shop_id'], unique=False)
    op.create_foreign_key(op.f('fk_invoices_buyer_shop_id_shops'), 'invoices', 'shops', ['buyer_shop_id'], ['id'], ondelete='SET NULL')
    op.add_column('shop_intents', sa.Column('pending_rules', postgresql.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    # Fails if purchase lines exist: they are records of money moved, never dropped silently.
    op.drop_constraint(op.f('ck_ledger_entries_kind'), 'ledger_entries', type_='check')
    op.create_check_constraint(op.f('ck_ledger_entries_kind'), 'ledger_entries',
                               "kind IN ('sale', 'fee', 'payout', 'refund')")
    op.drop_column('shop_intents', 'pending_rules')
    op.drop_constraint(op.f('fk_invoices_buyer_shop_id_shops'), 'invoices', type_='foreignkey')
    op.drop_index(op.f('ix_invoices_buyer_shop_id'), table_name='invoices')
    op.drop_column('invoices', 'buyer_shop_id')
    op.drop_constraint(op.f('fk_group_order_members_buyer_shop_id_shops'), 'group_order_members', type_='foreignkey')
    op.drop_index(op.f('ix_group_order_members_buyer_shop_id'), table_name='group_order_members')
    op.drop_column('group_order_members', 'buyer_shop_id')
    op.drop_index(op.f('ix_shop_suppliers_supplier_shop_id'), table_name='shop_suppliers')
    op.drop_table('shop_suppliers')
