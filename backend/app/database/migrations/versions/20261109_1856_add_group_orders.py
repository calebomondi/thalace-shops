"""Add group orders, their members and offer volume tiers.

Revision ID: 84cb0f6630f5
Revises: 7f81f4fcbbee
Create Date: 2026-11-09 18:56:56.245357+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '84cb0f6630f5'
down_revision: Union[str, Sequence[str], None] = '7f81f4fcbbee'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('group_orders',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('shop_id', sa.UUID(), nullable=False),
    sa.Column('offer_id', sa.UUID(), nullable=False),
    sa.Column('public_token', sa.String(length=48), nullable=False),
    sa.Column('opened_by', sa.String(length=120), nullable=False),
    sa.Column('status', sa.String(length=10), server_default='open', nullable=False),
    sa.Column('deadline', sa.DateTime(timezone=True), nullable=False),
    sa.Column('unit_price_cents', sa.Integer(), nullable=True),
    sa.Column('total_quantity', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('closed_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint("status <> 'closed' OR (unit_price_cents IS NOT NULL AND total_quantity > 0)", name=op.f('ck_group_orders_closed_has_price')),
    sa.CheckConstraint("status IN ('open', 'closed', 'cancelled')", name=op.f('ck_group_orders_status')),
    sa.ForeignKeyConstraint(['offer_id'], ['offers.id'], name=op.f('fk_group_orders_offer_id_offers'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['shop_id'], ['shops.id'], name=op.f('fk_group_orders_shop_id_shops'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_group_orders')),
    sa.UniqueConstraint('public_token', name=op.f('uq_group_orders_public_token'))
    )
    op.create_index(op.f('ix_group_orders_offer_id'), 'group_orders', ['offer_id'], unique=False)
    op.create_index('ix_group_orders_open_deadline', 'group_orders', ['deadline'], unique=False, postgresql_where=sa.text("status = 'open'"))
    op.create_index('ix_group_orders_shop_id_created_at', 'group_orders', ['shop_id', 'created_at'], unique=False)
    op.create_index('uq_group_orders_open_offer', 'group_orders', ['offer_id'], unique=True, postgresql_where=sa.text("status = 'open'"))
    op.create_table('offer_tiers',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('offer_id', sa.UUID(), nullable=False),
    sa.Column('min_quantity', sa.Integer(), nullable=False),
    sa.Column('unit_price_cents', sa.Integer(), nullable=False),
    sa.CheckConstraint('min_quantity > 0 AND unit_price_cents > 0', name=op.f('ck_offer_tiers_positive')),
    sa.ForeignKeyConstraint(['offer_id'], ['offers.id'], name=op.f('fk_offer_tiers_offer_id_offers'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_offer_tiers')),
    sa.UniqueConstraint('offer_id', 'min_quantity', name='uq_offer_tiers_offer_id_min_quantity')
    )
    op.create_table('group_order_members',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('group_order_id', sa.UUID(), nullable=False),
    sa.Column('public_token', sa.String(length=48), nullable=False),
    sa.Column('buyer_kind', sa.String(length=8), nullable=False),
    sa.Column('buyer_name', sa.String(length=120), nullable=False),
    sa.Column('buyer_email', sa.String(length=320), nullable=True),
    sa.Column('quantity', sa.Integer(), nullable=False),
    sa.Column('invoice_id', sa.UUID(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("buyer_kind IN ('person', 'agent', 'shop')", name=op.f('ck_group_order_members_buyer_kind')),
    sa.CheckConstraint('quantity > 0', name=op.f('ck_group_order_members_quantity_positive')),
    sa.ForeignKeyConstraint(['group_order_id'], ['group_orders.id'], name=op.f('fk_group_order_members_group_order_id_group_orders'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['invoice_id'], ['invoices.id'], name=op.f('fk_group_order_members_invoice_id_invoices'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_group_order_members')),
    sa.UniqueConstraint('public_token', name=op.f('uq_group_order_members_public_token'))
    )
    op.create_index('ix_group_order_members_group_order_id_created_at', 'group_order_members', ['group_order_id', 'created_at'], unique=False)
    op.create_index(op.f('ix_group_order_members_invoice_id'), 'group_order_members', ['invoice_id'], unique=False)
    op.add_column('offers', sa.Column('group_buy_enabled', sa.Boolean(), server_default=sa.text('false'), nullable=False))
    op.add_column('offers', sa.Column('group_window_hours', sa.Integer(), server_default='72', nullable=False))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('offers', 'group_window_hours')
    op.drop_column('offers', 'group_buy_enabled')
    op.drop_index(op.f('ix_group_order_members_invoice_id'), table_name='group_order_members')
    op.drop_index('ix_group_order_members_group_order_id_created_at', table_name='group_order_members')
    op.drop_table('group_order_members')
    op.drop_table('offer_tiers')
    op.drop_index('uq_group_orders_open_offer', table_name='group_orders', postgresql_where=sa.text("status = 'open'"))
    op.drop_index('ix_group_orders_shop_id_created_at', table_name='group_orders')
    op.drop_index('ix_group_orders_open_deadline', table_name='group_orders', postgresql_where=sa.text("status = 'open'"))
    op.drop_index(op.f('ix_group_orders_offer_id'), table_name='group_orders')
    op.drop_table('group_orders')
