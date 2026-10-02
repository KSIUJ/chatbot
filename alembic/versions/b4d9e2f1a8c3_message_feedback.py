"""message feedback: oceny (lapki) i zgloszenia odpowiedzi z kopia pytania i odpowiedzi

Nowa tabela message_feedback - jeden wiersz na (uzytkownik, wiadomosc).
message_id i user_id przechodza na NULL po usunieciu wiadomosci/konta, wiec
oceny przezywaja kasowanie rozmow po CHAT_HISTORY_RETENTION_DAYS.

Revision ID: b4d9e2f1a8c3
Revises: 3f8a2c1d5e67
Create Date: 2026-10-02 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b4d9e2f1a8c3'
down_revision: Union[str, Sequence[str], None] = '3f8a2c1d5e67'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'message_feedback',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('message_id', sa.String(length=32), nullable=True),
        sa.Column('user_id', sa.String(length=32), nullable=True),
        sa.Column('rating', sa.SmallInteger(), nullable=True),
        sa.Column('report_reason', sa.String(length=20), nullable=True),
        sa.Column('comment', sa.Text(), nullable=True),
        sa.Column('reported_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('report_status', sa.String(length=20), nullable=True),
        sa.Column('admin_note', sa.Text(), nullable=True),
        sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('reviewed_by', sa.String(length=32), nullable=True),
        sa.Column('question', sa.Text(), nullable=True),
        sa.Column('answer', sa.Text(), nullable=False),
        sa.Column('sources', sa.JSON(), nullable=False),
        sa.Column('language', sa.String(length=5), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint('rating IN (1, -1)', name='ck_message_feedback_rating'),
        sa.ForeignKeyConstraint(['message_id'], ['messages.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['reviewed_by'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'message_id', name='uq_message_feedback_user_message'),
    )
    op.create_index('ix_message_feedback_message_id', 'message_feedback', ['message_id'])
    op.create_index('ix_message_feedback_user_id', 'message_feedback', ['user_id'])
    op.create_index('ix_message_feedback_report_status', 'message_feedback', ['report_status'])


def downgrade() -> None:
    """Downgrade schema. Oceny i zgloszenia przepadaja razem z tabela."""
    op.drop_index('ix_message_feedback_report_status', table_name='message_feedback')
    op.drop_index('ix_message_feedback_user_id', table_name='message_feedback')
    op.drop_index('ix_message_feedback_message_id', table_name='message_feedback')
    op.drop_table('message_feedback')
