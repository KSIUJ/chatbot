"""attachments: pliki dolaczane do pytan i dzienny licznik wyslanych plikow

Nowe tabele: attachments (metadane pliku z dysku, wyciagniety tekst,
powiazanie z rozmowa i pytaniem po wyslaniu) i daily_attachment_usage
(liczba wyslanych plikow osoby w danym dniu wg czasu polskiego - limit
attachments.max_per_day).

Revision ID: f1a7c3e9b2d4
Revises: e5b8c2d4f6a1
Create Date: 2026-10-02 23:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f1a7c3e9b2d4'
down_revision: Union[str, Sequence[str], None] = 'e5b8c2d4f6a1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'attachments',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('user_id', sa.String(length=32), nullable=False),
        sa.Column('conversation_id', sa.String(length=32), nullable=True),
        sa.Column('message_id', sa.String(length=32), nullable=True),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('kind', sa.String(length=10), nullable=False),
        sa.Column('mime', sa.String(length=100), nullable=False),
        sa.Column('size', sa.Integer(), nullable=False),
        sa.Column('storage_key', sa.String(length=64), nullable=False),
        sa.Column('text', sa.Text(), nullable=True),
        sa.Column('pages', sa.Integer(), nullable=True),
        sa.Column('injection_rules', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "kind IN ('pdf', 'docx', 'txt', 'png', 'jpeg', 'webp')", name='ck_attachments_kind'
        ),
        sa.CheckConstraint('size >= 0', name='ck_attachments_size'),
        sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['message_id'], ['messages.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('storage_key', name='uq_attachments_storage_key'),
    )
    op.create_index('ix_attachments_user_id', 'attachments', ['user_id'])
    op.create_index('ix_attachments_conversation_id', 'attachments', ['conversation_id'])
    op.create_index('ix_attachments_message_id', 'attachments', ['message_id'])
    op.create_index('ix_attachments_created_at', 'attachments', ['created_at'])

    op.create_table(
        'daily_attachment_usage',
        sa.Column('user_id', sa.String(length=32), nullable=False),
        sa.Column('day', sa.Date(), nullable=False),
        sa.Column('count', sa.Integer(), nullable=False),
        sa.CheckConstraint('count >= 0', name='ck_daily_attachment_usage_count'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('user_id', 'day'),
    )
    op.create_index('ix_daily_attachment_usage_day', 'daily_attachment_usage', ['day'])


def downgrade() -> None:
    """Downgrade schema. Wiersze zalacznikow i liczniki przepadaja razem
    z tabelami; pliki w ATTACHMENTS_DIR trzeba wtedy usunac recznie
    (np. wyczyscic wolumen chatbot-uploads)."""
    op.drop_index('ix_daily_attachment_usage_day', table_name='daily_attachment_usage')
    op.drop_table('daily_attachment_usage')
    op.drop_index('ix_attachments_created_at', table_name='attachments')
    op.drop_index('ix_attachments_message_id', table_name='attachments')
    op.drop_index('ix_attachments_conversation_id', table_name='attachments')
    op.drop_index('ix_attachments_user_id', table_name='attachments')
    op.drop_table('attachments')
