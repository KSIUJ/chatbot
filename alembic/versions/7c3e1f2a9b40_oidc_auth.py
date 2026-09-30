"""oidc auth: users identified by Keycloak sub, server-side sessions

Stary system (haslo + kod z maila) jest usuwany w calosci:
- znikaja tabele email_codes i blacklisted_tokens,
- WSZYSTKIE konta sa kasowane (nie laczymy kont po emailu - to bylaby droga
  do przejecia konta); rozmowy zostaja jako anonimowe (user_id = NULL),
- users dostaje oidc_sub/name/last_login_at, traci password_hash/zweryfikowany,
- nowa tabela user_sessions.

Revision ID: 7c3e1f2a9b40
Revises: d509882390a9
Create Date: 2026-09-30 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7c3e1f2a9b40'
down_revision: Union[str, Sequence[str], None] = 'd509882390a9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _drop_table_with_indexes(table: str) -> None:
    """Kasuje tabele razem z indeksami, ktore faktycznie istnieja - baza
    zalozona kiedys przez create_all() nie ma czesci indeksow z migracji."""
    inspector = sa.inspect(op.get_bind())
    if table not in inspector.get_table_names():
        return
    for index in inspector.get_indexes(table):
        op.drop_index(index['name'], table_name=table)
    op.drop_table(table)


def upgrade() -> None:
    """Upgrade schema."""
    _drop_table_with_indexes('email_codes')
    _drop_table_with_indexes('blacklisted_tokens')

    op.execute(sa.text("UPDATE conversations SET user_id = NULL"))
    op.execute(sa.text("DELETE FROM users"))

    with op.batch_alter_table('users') as batch_op:
        batch_op.drop_index('ix_users_email')
        batch_op.drop_column('password_hash')
        batch_op.drop_column('zweryfikowany')
        batch_op.alter_column('email', existing_type=sa.String(length=255), nullable=True)
        # tabela jest pusta (DELETE wyzej), wiec NOT NULL bez domyslnej wartosci jest ok
        batch_op.add_column(sa.Column('oidc_sub', sa.String(length=255), nullable=False))
        batch_op.add_column(sa.Column('name', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.create_index('ix_users_oidc_sub', ['oidc_sub'], unique=True)
        batch_op.create_index('ix_users_email', ['email'], unique=False)

    op.create_table(
        'user_sessions',
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('user_id', sa.String(length=32), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('access_token_enc', sa.Text(), nullable=False),
        sa.Column('access_token_expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('refresh_token_enc', sa.Text(), nullable=True),
        sa.Column('id_token_enc', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_user_sessions_user_id', 'user_sessions', ['user_id'])


def downgrade() -> None:
    """Downgrade schema. Konta i sesje OIDC sa kasowane - hasel nie da sie odtworzyc."""
    op.drop_index('ix_user_sessions_user_id', table_name='user_sessions')
    op.drop_table('user_sessions')

    op.execute(sa.text("UPDATE conversations SET user_id = NULL"))
    op.execute(sa.text("DELETE FROM users"))

    with op.batch_alter_table('users') as batch_op:
        batch_op.drop_index('ix_users_email')
        batch_op.drop_index('ix_users_oidc_sub')
        batch_op.drop_column('last_login_at')
        batch_op.drop_column('name')
        batch_op.drop_column('oidc_sub')
        batch_op.alter_column('email', existing_type=sa.String(length=255), nullable=False)
        batch_op.add_column(sa.Column('password_hash', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('zweryfikowany', sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.create_index('ix_users_email', ['email'], unique=True)

    op.create_table(
        'blacklisted_tokens',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('token', sa.String(length=500), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_blacklisted_tokens_token'), 'blacklisted_tokens', ['token'], unique=True)
    op.create_table(
        'email_codes',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('user_id', sa.String(length=32), nullable=False),
        sa.Column('kod', sa.String(length=6), nullable=False),
        sa.Column('typ', sa.String(length=20), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('used', sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_email_codes_user_id', 'email_codes', ['user_id'])
