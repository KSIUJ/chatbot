"""message personal data: odpowiedz oparta na danych osoby z USOS

Kolumna messages.personal_data - odpowiedz, przy ktorej model uzyl narzedzi
z danymi osoby z USOS (plan, przedmioty, oceny). Kopia takiej odpowiedzi nie
trafia do ocen i zgloszen przegladanych przez zarzad (feedback/service.py).

Revision ID: e5c2a9d4f1b8
Revises: d3b8f1c6e2a7
Create Date: 2026-10-26 22:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e5c2a9d4f1b8'
down_revision: Union[str, Sequence[str], None] = 'd3b8f1c6e2a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('messages') as batch:
        batch.add_column(sa.Column('personal_data', sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('messages') as batch:
        batch.drop_column('personal_data')
