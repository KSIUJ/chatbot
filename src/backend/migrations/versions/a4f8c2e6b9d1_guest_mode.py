"""guest mode: wersja testowa czatu bez konta KSI

users.is_guest, a tokeny Keycloaka w user_sessions moga byc puste - sesja
goscia ich nie ma. Limit sesji gosci z jednego adresu liczy usage_counters.

Revision ID: a4f8c2e6b9d1
Revises: e5c2a9d4f1b8
Create Date: 2026-11-27 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a4f8c2e6b9d1'
down_revision: Union[str, Sequence[str], None] = 'e5c2a9d4f1b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('users') as batch:
        batch.add_column(sa.Column('is_guest', sa.Boolean(), nullable=False, server_default=sa.false()))
    with op.batch_alter_table('user_sessions') as batch:
        batch.alter_column('access_token_enc', existing_type=sa.Text(), nullable=True)
        batch.alter_column('access_token_expires_at', existing_type=sa.DateTime(timezone=True), nullable=True)


def downgrade() -> None:
    """Downgrade schema. Sesje i konta gosci znikaja - bez Keycloaka nie da sie
    ich zapisac w starym schemacie."""
    op.execute("DELETE FROM user_sessions WHERE access_token_enc IS NULL")
    with op.batch_alter_table('user_sessions') as batch:
        batch.alter_column('access_token_expires_at', existing_type=sa.DateTime(timezone=True), nullable=False)
        batch.alter_column('access_token_enc', existing_type=sa.Text(), nullable=False)
    op.execute("DELETE FROM users WHERE is_guest")
    with op.batch_alter_table('users') as batch:
        batch.drop_column('is_guest')
