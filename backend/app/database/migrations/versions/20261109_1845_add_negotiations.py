"""Add negotiations and their moves.

Revision ID: 7f81f4fcbbee
Revises: 0f3ceb3a30b7
Create Date: 2026-11-09 18:45:20.430601+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7f81f4fcbbee'
down_revision: Union[str, Sequence[str], None] = '0f3ceb3a30b7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('negotiations',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('shop_id', sa.UUID(), nullable=False),
    sa.Column('offer_id', sa.UUID(), nullable=False),
    sa.Column('public_token', sa.String(length=48), nullable=False),
    sa.Column('buyer_kind', sa.String(length=8), nullable=False),
    sa.Column('buyer_name', sa.String(length=120), nullable=False),
    sa.Column('quantity', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(length=12), server_default='open', nullable=False),
    sa.Column('agreed_unit_cents', sa.Integer(), nullable=True),
    sa.Column('invoice_id', sa.UUID(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("buyer_kind IN ('person', 'agent', 'shop')", name=op.f('ck_negotiations_buyer_kind')),
    sa.CheckConstraint("status IN ('open', 'agreed', 'walked_away', 'invoiced')", name=op.f('ck_negotiations_status')),
    sa.CheckConstraint("status NOT IN ('agreed', 'invoiced') OR agreed_unit_cents IS NOT NULL", name=op.f('ck_negotiations_agreed_has_price')),
    sa.CheckConstraint('quantity > 0', name=op.f('ck_negotiations_quantity_positive')),
    sa.ForeignKeyConstraint(['invoice_id'], ['invoices.id'], name=op.f('fk_negotiations_invoice_id_invoices'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['offer_id'], ['offers.id'], name=op.f('fk_negotiations_offer_id_offers'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['shop_id'], ['shops.id'], name=op.f('fk_negotiations_shop_id_shops'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_negotiations')),
    sa.UniqueConstraint('public_token', name=op.f('uq_negotiations_public_token'))
    )
    op.create_index(op.f('ix_negotiations_invoice_id'), 'negotiations', ['invoice_id'], unique=False)
    op.create_index(op.f('ix_negotiations_offer_id'), 'negotiations', ['offer_id'], unique=False)
    op.create_index('ix_negotiations_shop_id_created_at', 'negotiations', ['shop_id', 'created_at'], unique=False)
    op.create_table('negotiation_moves',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('negotiation_id', sa.UUID(), nullable=False),
    sa.Column('side', sa.String(length=8), nullable=False),
    sa.Column('move', sa.String(length=10), nullable=False),
    sa.Column('unit_price_cents', sa.Integer(), nullable=True),
    sa.Column('message', sa.Text(), server_default='', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("move IN ('offer', 'counter', 'accept', 'walk_away')", name=op.f('ck_negotiation_moves_move')),
    sa.CheckConstraint("move NOT IN ('offer', 'counter') OR unit_price_cents > 0", name=op.f('ck_negotiation_moves_priced')),
    sa.CheckConstraint("side IN ('buyer', 'seller')", name=op.f('ck_negotiation_moves_side')),
    sa.ForeignKeyConstraint(['negotiation_id'], ['negotiations.id'], name=op.f('fk_negotiation_moves_negotiation_id_negotiations'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_negotiation_moves'))
    )
    op.create_index('ix_negotiation_moves_negotiation_id_created_at', 'negotiation_moves', ['negotiation_id', 'created_at'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_negotiation_moves_negotiation_id_created_at', table_name='negotiation_moves')
    op.drop_table('negotiation_moves')
    op.drop_index('ix_negotiations_shop_id_created_at', table_name='negotiations')
    op.drop_index(op.f('ix_negotiations_offer_id'), table_name='negotiations')
    op.drop_index(op.f('ix_negotiations_invoice_id'), table_name='negotiations')
    op.drop_table('negotiations')
