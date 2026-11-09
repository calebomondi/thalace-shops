"""Add shop_messages: the owner's conversation with each shop's agent.

Revision ID: a86a884ebea5
Revises: f2e819083dc1
Create Date: 2026-11-09 17:44:45.612081+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'a86a884ebea5'
down_revision: Union[str, Sequence[str], None] = 'f2e819083dc1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('shop_messages',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('shop_id', sa.UUID(), nullable=False),
    sa.Column('role', sa.String(length=10), nullable=False),
    sa.Column('content', sa.Text(), server_default='', nullable=False),
    sa.Column('tool_calls', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('tool_call_id', sa.String(length=128), nullable=True),
    sa.Column('tool_name', sa.String(length=64), nullable=True),
    sa.Column('author_id', sa.UUID(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("role <> 'tool' OR tool_call_id IS NOT NULL", name=op.f('ck_shop_messages_tool_has_call_id')),
    sa.CheckConstraint("role IN ('user', 'assistant', 'tool')", name=op.f('ck_shop_messages_role')),
    sa.ForeignKeyConstraint(['shop_id'], ['shops.id'], name=op.f('fk_shop_messages_shop_id_shops'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_shop_messages'))
    )
    op.create_index('ix_shop_messages_shop_id_created_at', 'shop_messages', ['shop_id', 'created_at'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_shop_messages_shop_id_created_at', table_name='shop_messages')
    op.drop_table('shop_messages')
