"""Add owner passkeys and shop signature requests, and the wallet and grant columns on shops.

Revision ID: fd3f363abd19
Revises: a86a884ebea5
Create Date: 2026-11-09 17:52:21.291752+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'fd3f363abd19'
down_revision: Union[str, Sequence[str], None] = 'a86a884ebea5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('owner_passkeys',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('credential_id', sa.String(length=512), nullable=False),
    sa.Column('public_key', sa.String(length=256), nullable=False),
    sa.Column('rp_id', sa.String(length=253), nullable=False),
    sa.Column('origin', sa.String(length=255), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_owner_passkeys')),
    sa.UniqueConstraint('credential_id', name=op.f('uq_owner_passkeys_credential_id')),
    sa.UniqueConstraint('user_id', 'rp_id', name='uq_owner_passkeys_user_id_rp_id')
    )
    op.create_table('shop_intents',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('shop_id', sa.UUID(), nullable=False),
    sa.Column('correlation_id', sa.String(length=96), nullable=False),
    sa.Column('type', sa.String(length=16), nullable=False),
    sa.Column('status', sa.String(length=20), server_default='awaiting_signature', nullable=False),
    sa.Column('requested_by', sa.UUID(), nullable=False),
    sa.Column('grant_token_enc', sa.Text(), nullable=True),
    sa.Column('failure_code', sa.String(length=64), nullable=True),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint("status IN ('awaiting_signature', 'submitted', 'succeeded', 'failed', 'expired')", name=op.f('ck_shop_intents_status')),
    sa.CheckConstraint("type IN ('agent_create', 'grant_issue', 'policy_update', 'agent_freeze', 'agent_unfreeze')", name=op.f('ck_shop_intents_type')),
    sa.ForeignKeyConstraint(['shop_id'], ['shops.id'], name=op.f('fk_shop_intents_shop_id_shops'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_shop_intents')),
    sa.UniqueConstraint('correlation_id', name=op.f('uq_shop_intents_correlation_id'))
    )
    op.create_index(op.f('ix_shop_intents_requested_by'), 'shop_intents', ['requested_by'], unique=False)
    op.create_index('ix_shop_intents_shop_id_created_at', 'shop_intents', ['shop_id', 'created_at'], unique=False)
    op.add_column('shops', sa.Column('owner_passkey_id', sa.UUID(), nullable=True))
    op.add_column('shops', sa.Column('owner_account_id', sa.String(length=128), nullable=True))
    op.add_column('shops', sa.Column('policy_revision', sa.Integer(), nullable=True))
    op.add_column('shops', sa.Column('grant_id', sa.String(length=96), nullable=True))
    op.add_column('shops', sa.Column('grant_token_enc', sa.Text(), nullable=True))
    op.add_column('shops', sa.Column('grant_expires_at', sa.DateTime(timezone=True), nullable=True))
    op.create_index(op.f('ix_shops_owner_passkey_id'), 'shops', ['owner_passkey_id'], unique=False)
    op.create_foreign_key(op.f('fk_shops_owner_passkey_id_owner_passkeys'), 'shops', 'owner_passkeys', ['owner_passkey_id'], ['id'], ondelete='RESTRICT')


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(op.f('fk_shops_owner_passkey_id_owner_passkeys'), 'shops', type_='foreignkey')
    op.drop_index(op.f('ix_shops_owner_passkey_id'), table_name='shops')
    op.drop_column('shops', 'grant_expires_at')
    op.drop_column('shops', 'grant_token_enc')
    op.drop_column('shops', 'grant_id')
    op.drop_column('shops', 'policy_revision')
    op.drop_column('shops', 'owner_account_id')
    op.drop_column('shops', 'owner_passkey_id')
    op.drop_index('ix_shop_intents_shop_id_created_at', table_name='shop_intents')
    op.drop_index(op.f('ix_shop_intents_requested_by'), table_name='shop_intents')
    op.drop_table('shop_intents')
    op.drop_table('owner_passkeys')
