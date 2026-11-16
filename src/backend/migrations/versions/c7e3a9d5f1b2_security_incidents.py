"""security incidents: proby obejscia promptu systemowego do przegladu przez zarzad

Nowa tabela security_incidents - najwyzej jeden wiersz na pytanie uzytkownika
(message_id). conversation_id i message_id sa kopiami bez FK (rozmowy sa
kasowane), user_id i reviewed_by przechodza na NULL po usunieciu konta.

Revision ID: c7e3a9d5f1b2
Revises: b4d9e2f1a8c3
Create Date: 2026-10-02 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c7e3a9d5f1b2'
down_revision: Union[str, Sequence[str], None] = 'b4d9e2f1a8c3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'security_incidents',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('user_id', sa.String(length=32), nullable=True),
        sa.Column('conversation_id', sa.String(length=32), nullable=True),
        sa.Column('message_id', sa.String(length=32), nullable=True),
        sa.Column('question', sa.Text(), nullable=False),
        sa.Column('source', sa.String(length=10), nullable=False),
        sa.Column('rules', sa.JSON(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('admin_note', sa.Text(), nullable=True),
        sa.Column('reviewed_by', sa.String(length=32), nullable=True),
        sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("source IN ('heuristic', 'model', 'both')", name='ck_security_incidents_source'),
        sa.CheckConstraint("status IN ('open', 'resolved', 'dismissed')", name='ck_security_incidents_status'),
        sa.ForeignKeyConstraint(['reviewed_by'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('message_id', name='uq_security_incidents_message'),
    )
    op.create_index('ix_security_incidents_user_id', 'security_incidents', ['user_id'])
    op.create_index('ix_security_incidents_status', 'security_incidents', ['status'])
    op.create_index('ix_security_incidents_created_at', 'security_incidents', ['created_at'])


def downgrade() -> None:
    """Downgrade schema. Incydenty przepadaja razem z tabela."""
    op.drop_index('ix_security_incidents_created_at', table_name='security_incidents')
    op.drop_index('ix_security_incidents_status', table_name='security_incidents')
    op.drop_index('ix_security_incidents_user_id', table_name='security_incidents')
    op.drop_table('security_incidents')
