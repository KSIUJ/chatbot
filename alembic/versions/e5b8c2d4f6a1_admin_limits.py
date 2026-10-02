"""admin limits: globalne ustawienia, wyjatki per osoba i dzienne zuzycie

Nowe tabele: app_settings (klucz -> wartosc JSON, np. dzienny limit pytan
i limity zalacznikow; brak wiersza = wartosc z env), user_limits (wyjatek od
limitu dla jednej osoby; daily_limit NULL = bez limitu) i daily_usage (liczba
pytan osoby w danym dniu wg czasu polskiego).

Revision ID: e5b8c2d4f6a1
Revises: c7e3a9d5f1b2
Create Date: 2026-10-02 21:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e5b8c2d4f6a1'
down_revision: Union[str, Sequence[str], None] = 'c7e3a9d5f1b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'app_settings',
        sa.Column('key', sa.String(length=64), nullable=False),
        sa.Column('value', sa.JSON(), nullable=False),
        sa.Column('updated_by', sa.String(length=32), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['updated_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('key'),
    )
    op.create_table(
        'user_limits',
        sa.Column('user_id', sa.String(length=32), nullable=False),
        sa.Column('daily_limit', sa.Integer(), nullable=True),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('updated_by', sa.String(length=32), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint('daily_limit IS NULL OR daily_limit >= 0', name='ck_user_limits_daily_limit'),
        sa.ForeignKeyConstraint(['updated_by'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('user_id'),
    )
    op.create_table(
        'daily_usage',
        sa.Column('user_id', sa.String(length=32), nullable=False),
        sa.Column('day', sa.Date(), nullable=False),
        sa.Column('count', sa.Integer(), nullable=False),
        sa.CheckConstraint('count >= 0', name='ck_daily_usage_count'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('user_id', 'day'),
    )
    op.create_index('ix_daily_usage_day', 'daily_usage', ['day'])


def downgrade() -> None:
    """Downgrade schema. Ustawienia, wyjatki i liczniki przepadaja razem z
    tabelami - limity wracaja do wartosci z env."""
    op.drop_index('ix_daily_usage_day', table_name='daily_usage')
    op.drop_table('daily_usage')
    op.drop_table('user_limits')
    op.drop_table('app_settings')
