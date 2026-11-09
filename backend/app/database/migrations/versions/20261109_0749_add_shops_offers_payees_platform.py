"""Add shops, offers, payees, platform settings and the admin audit log.

Revision ID: f2e819083dc1
Revises: 
Create Date: 2026-11-09 07:49:57.143847+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'f2e819083dc1'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('admin_audit_log',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('actor_id', sa.UUID(), nullable=False),
    sa.Column('actor_email', sa.String(length=320), nullable=True),
    sa.Column('action', sa.String(length=64), nullable=False),
    sa.Column('target', sa.String(length=128), nullable=False),
    sa.Column('before', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('after', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_admin_audit_log'))
    )
    op.create_index(op.f('ix_admin_audit_log_actor_id'), 'admin_audit_log', ['actor_id'], unique=False)
    op.create_index('ix_admin_audit_log_created_at', 'admin_audit_log', ['created_at'], unique=False)
    op.create_table('platform_settings',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('fee_bps', sa.Integer(), nullable=False),
    sa.Column('max_fee_bps', sa.Integer(), nullable=False),
    sa.Column('fee_account', sa.String(length=128), nullable=False),
    sa.Column('updated_by', sa.UUID(), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('fee_bps >= 0 AND fee_bps <= max_fee_bps', name=op.f('ck_platform_settings_fee_within_max')),
    sa.CheckConstraint('id = 1', name=op.f('ck_platform_settings_single_row')),
    sa.CheckConstraint('max_fee_bps >= 0 AND max_fee_bps <= 10000', name=op.f('ck_platform_settings_max_fee_range')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_platform_settings'))
    )
    op.create_table('shops',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('owner_id', sa.UUID(), nullable=False),
    sa.Column('slug', sa.String(length=48), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('tagline', sa.String(length=200), server_default='', nullable=False),
    sa.Column('description', sa.Text(), server_default='', nullable=False),
    sa.Column('website', sa.String(length=300), nullable=True),
    sa.Column('status', sa.String(length=8), server_default='draft', nullable=False),
    sa.Column('settlement_asset', sa.String(length=128), nullable=False),
    sa.Column('daily_budget_usd', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('agent_id', sa.String(length=96), nullable=True),
    sa.Column('wallet_account_id', sa.String(length=128), nullable=True),
    sa.Column('frozen_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('live_since', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("slug ~ '^[a-z0-9](?:[a-z0-9-]{1,46}[a-z0-9])$'", name=op.f('ck_shops_slug_format')),
    sa.CheckConstraint("status = 'draft' OR agent_id IS NOT NULL", name=op.f('ck_shops_live_has_agent')),
    sa.CheckConstraint("status IN ('draft', 'live', 'paused')", name=op.f('ck_shops_status')),
    sa.CheckConstraint('daily_budget_usd >= 0', name=op.f('ck_shops_budget_not_negative')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_shops')),
    sa.UniqueConstraint('agent_id', name=op.f('uq_shops_agent_id')),
    sa.UniqueConstraint('slug', name=op.f('uq_shops_slug'))
    )
    op.create_index('ix_shops_owner_id_created_at', 'shops', ['owner_id', 'created_at'], unique=False)
    op.create_table('offers',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('shop_id', sa.UUID(), nullable=False),
    sa.Column('title', sa.String(length=160), nullable=False),
    sa.Column('description', sa.Text(), server_default='', nullable=False),
    sa.Column('kind', sa.String(length=8), nullable=False),
    sa.Column('price_cents', sa.Integer(), nullable=False),
    sa.Column('floor_cents', sa.Integer(), nullable=False),
    sa.Column('delivery', sa.String(length=10), nullable=False),
    sa.Column('delivery_url', sa.Text(), nullable=True),
    sa.Column('delivery_note', sa.Text(), server_default='', nullable=False),
    sa.Column('status', sa.String(length=8), server_default='draft', nullable=False),
    sa.Column('position', sa.Integer(), server_default='0', nullable=False),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("delivery <> 'link' OR delivery_url IS NOT NULL", name=op.f('ck_offers_link_has_url')),
    sa.CheckConstraint("delivery IN ('link', 'markdown', 'service')", name=op.f('ck_offers_delivery')),
    sa.CheckConstraint("kind IN ('digital', 'service')", name=op.f('ck_offers_kind')),
    sa.CheckConstraint("status IN ('draft', 'active', 'archived')", name=op.f('ck_offers_status')),
    sa.CheckConstraint('floor_cents > 0 AND floor_cents <= price_cents', name=op.f('ck_offers_floor_within_price')),
    sa.CheckConstraint('price_cents > 0', name=op.f('ck_offers_price_positive')),
    sa.ForeignKeyConstraint(['shop_id'], ['shops.id'], name=op.f('fk_offers_shop_id_shops'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_offers'))
    )
    op.create_index('ix_offers_shop_id_status_position', 'offers', ['shop_id', 'status', 'position'], unique=False)
    op.create_table('payees',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('shop_id', sa.UUID(), nullable=False),
    sa.Column('label', sa.String(length=80), nullable=False),
    sa.Column('route', sa.String(length=10), nullable=False),
    sa.Column('chain', sa.String(length=24), nullable=True),
    sa.Column('address', sa.String(length=128), nullable=False),
    sa.Column('memo', sa.String(length=128), nullable=True),
    sa.Column('share_bps', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("(route = 'withdraw') = (chain IS NOT NULL)", name=op.f('ck_payees_withdraw_has_chain')),
    sa.CheckConstraint("route IN ('transfer', 'withdraw')", name=op.f('ck_payees_route')),
    sa.CheckConstraint('share_bps > 0 AND share_bps <= 10000', name=op.f('ck_payees_share_range')),
    sa.ForeignKeyConstraint(['shop_id'], ['shops.id'], name=op.f('fk_payees_shop_id_shops'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_payees')),
    sa.UniqueConstraint('shop_id', 'route', 'chain', 'address', name='uq_payees_destination', postgresql_nulls_not_distinct=True)
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('payees')
    op.drop_index('ix_offers_shop_id_status_position', table_name='offers')
    op.drop_table('offers')
    op.drop_index('ix_shops_owner_id_created_at', table_name='shops')
    op.drop_table('shops')
    op.drop_table('platform_settings')
    op.drop_index('ix_admin_audit_log_created_at', table_name='admin_audit_log')
    op.drop_index(op.f('ix_admin_audit_log_actor_id'), table_name='admin_audit_log')
    op.drop_table('admin_audit_log')
