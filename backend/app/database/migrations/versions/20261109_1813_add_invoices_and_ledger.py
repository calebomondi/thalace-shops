"""Add invoices and the ledger, and the per-shop invoice counter.

Revision ID: 0f3ceb3a30b7
Revises: fd3f363abd19
Create Date: 2026-11-09 18:13:10.384018+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0f3ceb3a30b7'
down_revision: Union[str, Sequence[str], None] = 'fd3f363abd19'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('invoices',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('shop_id', sa.UUID(), nullable=False),
    sa.Column('number', sa.String(length=24), nullable=False),
    sa.Column('public_token', sa.String(length=48), nullable=False),
    sa.Column('offer_id', sa.UUID(), nullable=False),
    sa.Column('title', sa.String(length=160), nullable=False),
    sa.Column('quantity', sa.Integer(), nullable=False),
    sa.Column('unit_price_cents', sa.Integer(), nullable=False),
    sa.Column('total_cents', sa.Integer(), nullable=False),
    sa.Column('fee_bps', sa.Integer(), nullable=False),
    sa.Column('buyer_kind', sa.String(length=8), nullable=False),
    sa.Column('buyer_email', sa.String(length=320), nullable=True),
    sa.Column('buyer_name', sa.String(length=120), nullable=True),
    sa.Column('ip_hash', sa.String(length=64), nullable=True),
    sa.Column('status', sa.String(length=18), server_default='open', nullable=False),
    sa.Column('pay_asset', sa.String(length=128), nullable=True),
    sa.Column('pay_amount_raw', sa.Numeric(precision=40, scale=0), nullable=True),
    sa.Column('deposit_idempotency_key', sa.String(length=128), nullable=True),
    sa.Column('deposit_correlation_id', sa.String(length=96), nullable=True),
    sa.Column('deposit_address', sa.String(length=128), nullable=True),
    sa.Column('deposit_memo', sa.String(length=128), nullable=True),
    sa.Column('deposit_expires_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('failure_code', sa.String(length=64), nullable=True),
    sa.Column('credited_raw', sa.Numeric(precision=40, scale=0), nullable=True),
    sa.Column('payment_tx_hash', sa.String(length=128), nullable=True),
    sa.Column('refund_tx_hash', sa.String(length=128), nullable=True),
    sa.Column('deliverable', sa.Text(), nullable=True),
    sa.Column('paid_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('delivered_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('checked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("buyer_kind IN ('person', 'agent', 'shop')", name=op.f('ck_invoices_buyer_kind')),
    sa.CheckConstraint("status IN ('open', 'awaiting_payment', 'paid', 'delivered', 'expired', 'refunded', 'failed')", name=op.f('ck_invoices_status')),
    sa.CheckConstraint('fee_bps >= 0 AND fee_bps <= 10000', name=op.f('ck_invoices_fee_range')),
    sa.CheckConstraint('quantity > 0 AND unit_price_cents > 0', name=op.f('ck_invoices_positive')),
    sa.CheckConstraint('total_cents = quantity * unit_price_cents', name=op.f('ck_invoices_total')),
    sa.ForeignKeyConstraint(['offer_id'], ['offers.id'], name=op.f('fk_invoices_offer_id_offers'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['shop_id'], ['shops.id'], name=op.f('fk_invoices_shop_id_shops'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_invoices')),
    sa.UniqueConstraint('deposit_correlation_id', name=op.f('uq_invoices_deposit_correlation_id')),
    sa.UniqueConstraint('deposit_idempotency_key', name=op.f('uq_invoices_deposit_idempotency_key')),
    sa.UniqueConstraint('public_token', name=op.f('uq_invoices_public_token')),
    sa.UniqueConstraint('shop_id', 'number', name='uq_invoices_shop_id_number')
    )
    op.create_index('ix_invoices_awaiting', 'invoices', ['checked_at'], unique=False, postgresql_where=sa.text("status = 'awaiting_payment'"))
    op.create_index('ix_invoices_ip_hash_created_at', 'invoices', ['ip_hash', 'created_at'], unique=False)
    op.create_index(op.f('ix_invoices_offer_id'), 'invoices', ['offer_id'], unique=False)
    op.create_index('ix_invoices_shop_id_created_at', 'invoices', ['shop_id', 'created_at'], unique=False)
    op.create_table('ledger_entries',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('shop_id', sa.UUID(), nullable=False),
    sa.Column('invoice_id', sa.UUID(), nullable=True),
    sa.Column('payee_id', sa.UUID(), nullable=True),
    sa.Column('kind', sa.String(length=8), nullable=False),
    sa.Column('status', sa.String(length=8), server_default='pending', nullable=False),
    sa.Column('asset', sa.String(length=128), nullable=False),
    sa.Column('amount_raw', sa.Numeric(precision=40, scale=0), nullable=False),
    sa.Column('amount_usd', sa.Numeric(precision=14, scale=2), nullable=True),
    sa.Column('counterparty', sa.String(length=128), nullable=True),
    sa.Column('idempotency_key', sa.String(length=128), nullable=True),
    sa.Column('correlation_id', sa.String(length=96), nullable=True),
    sa.Column('tx_hash', sa.String(length=128), nullable=True),
    sa.Column('failure_code', sa.String(length=64), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('settled_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint("kind <> 'payout' OR (payee_id IS NOT NULL AND invoice_id IS NOT NULL)", name=op.f('ck_ledger_entries_payout_has_payee')),
    sa.CheckConstraint("kind IN ('sale', 'fee', 'payout', 'refund')", name=op.f('ck_ledger_entries_kind')),
    sa.CheckConstraint("status IN ('pending', 'done', 'failed')", name=op.f('ck_ledger_entries_status')),
    sa.CheckConstraint('amount_raw >= 0', name=op.f('ck_ledger_entries_amount_not_negative')),
    sa.ForeignKeyConstraint(['invoice_id'], ['invoices.id'], name=op.f('fk_ledger_entries_invoice_id_invoices'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['payee_id'], ['payees.id'], name=op.f('fk_ledger_entries_payee_id_payees'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['shop_id'], ['shops.id'], name=op.f('fk_ledger_entries_shop_id_shops'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_ledger_entries')),
    sa.UniqueConstraint('correlation_id', name=op.f('uq_ledger_entries_correlation_id')),
    sa.UniqueConstraint('idempotency_key', name=op.f('uq_ledger_entries_idempotency_key')),
    sa.UniqueConstraint('invoice_id', 'kind', 'payee_id', name='uq_ledger_entries_invoice_id_kind_payee_id', postgresql_nulls_not_distinct=True)
    )
    op.create_index(op.f('ix_ledger_entries_payee_id'), 'ledger_entries', ['payee_id'], unique=False)
    op.create_index('ix_ledger_entries_pending', 'ledger_entries', ['shop_id'], unique=False, postgresql_where=sa.text("status = 'pending'"))
    op.create_index('ix_ledger_entries_shop_id_created_at', 'ledger_entries', ['shop_id', 'created_at'], unique=False)
    op.add_column('shops', sa.Column('invoice_seq', sa.Integer(), server_default='0', nullable=False))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('shops', 'invoice_seq')
    op.drop_index('ix_ledger_entries_shop_id_created_at', table_name='ledger_entries')
    op.drop_index('ix_ledger_entries_pending', table_name='ledger_entries', postgresql_where=sa.text("status = 'pending'"))
    op.drop_index(op.f('ix_ledger_entries_payee_id'), table_name='ledger_entries')
    op.drop_table('ledger_entries')
    op.drop_index('ix_invoices_shop_id_created_at', table_name='invoices')
    op.drop_index(op.f('ix_invoices_offer_id'), table_name='invoices')
    op.drop_index('ix_invoices_ip_hash_created_at', table_name='invoices')
    op.drop_index('ix_invoices_awaiting', table_name='invoices', postgresql_where=sa.text("status = 'awaiting_payment'"))
    op.drop_table('invoices')
