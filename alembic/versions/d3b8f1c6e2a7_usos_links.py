"""usos links: polaczenia kont z USOS (OAuth 1.0a)

Nowa tabela usos_links - najwyzej jeden wiersz na konto (user_id = klucz
glowny, ON DELETE CASCADE). Token i sekret USOS sa w jednym szyfrogramie
(token_enc) razem z id konta; z USOS tylko id osoby i imie z nazwiskiem.

Revision ID: d3b8f1c6e2a7
Revises: a9c4e7b2d1f3
Create Date: 2026-10-26 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd3b8f1c6e2a7'
down_revision: Union[str, Sequence[str], None] = 'a9c4e7b2d1f3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'usos_links',
        sa.Column('user_id', sa.String(length=32), nullable=False),
        sa.Column('usos_user_id', sa.String(length=32), nullable=False),
        sa.Column('usos_name', sa.String(length=255), nullable=True),
        sa.Column('token_enc', sa.Text(), nullable=False),
        sa.Column('scopes', sa.String(length=255), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('needs_reconnect_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('user_id'),
    )


def downgrade() -> None:
    """Downgrade schema. Polaczenia z USOS przepadaja (tokeny w USOS zostaja
    wazne do cofniecia przez uzytkownika)."""
    op.drop_table('usos_links')
