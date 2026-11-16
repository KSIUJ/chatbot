"""chat blocks: blokada czatu po ostrzezeniach za proby obejscia promptu

Kolumny users.chat_blocked_at (NULL = brak blokady) i users.warnings_reset_at
(ostrzezenia sprzed tej chwili sie nie licza - ustawiane przy zdjeciu blokady
przez zarzad). Liczba ostrzezen wynika z tabeli security_incidents.

Revision ID: a9c4e7b2d1f3
Revises: b7d2e4f6a8c1
Create Date: 2026-10-11 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a9c4e7b2d1f3'
down_revision: Union[str, Sequence[str], None] = 'b7d2e4f6a8c1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('users') as batch:
        batch.add_column(sa.Column('chat_blocked_at', sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column('warnings_reset_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    """Downgrade schema. Blokady przepadaja - zablokowane osoby znow moga pytac."""
    with op.batch_alter_table('users') as batch:
        batch.drop_column('warnings_reset_at')
        batch.drop_column('chat_blocked_at')
