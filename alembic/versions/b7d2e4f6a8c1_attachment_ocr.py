"""attachment ocr: znacznik tekstu rozpoznanego OCR-em ze skanu PDF

Kolumna attachments.ocr (domyslnie false) - model dostaje w naglowku pliku
ostrzezenie, ze tekst moze zawierac bledy rozpoznawania.

Revision ID: b7d2e4f6a8c1
Revises: f1a7c3e9b2d4
Create Date: 2026-10-03 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7d2e4f6a8c1'
down_revision: Union[str, Sequence[str], None] = 'f1a7c3e9b2d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('attachments') as batch:
        batch.add_column(sa.Column('ocr', sa.Boolean(), server_default=sa.false(), nullable=False))


def downgrade() -> None:
    """Downgrade schema. Znacznik OCR przepada; tekst zostaje."""
    with op.batch_alter_table('attachments') as batch:
        batch.drop_column('ocr')
