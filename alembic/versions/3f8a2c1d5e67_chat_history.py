"""chat history: conversation title + last_message_at, stats counters, drop unused columns

- conversations.title (pierwsze pytanie) i conversations.last_message_at
  (kolejnosc historii, wygasanie po CHAT_HISTORY_RETENTION_DAYS) - wypelniane
  z istniejacych wiadomosci,
- usage_counters: liczniki /api/stats, ktore nie maleja przy kasowaniu rozmow -
  startuja od obecnych wartosci,
- usuniete nieuzywane: messages.feedback (lapki) i users.context_count.

Revision ID: 3f8a2c1d5e67
Revises: 7c3e1f2a9b40
Create Date: 2026-10-01 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3f8a2c1d5e67'
down_revision: Union[str, Sequence[str], None] = '7c3e1f2a9b40'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TITLE_LENGTH = 80


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()

    with op.batch_alter_table('conversations') as batch_op:
        batch_op.add_column(sa.Column('title', sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column('last_message_at', sa.DateTime(timezone=True), nullable=True))

    op.execute(sa.text(
        "UPDATE conversations SET last_message_at = COALESCE("
        "(SELECT MAX(m.created_at) FROM messages m WHERE m.conversation_id = conversations.id), "
        "conversations.created_at)"
    ))
    op.execute(sa.text(
        "UPDATE conversations SET title = ("
        f"SELECT SUBSTR(m.content, 1, {TITLE_LENGTH}) FROM messages m "
        "WHERE m.conversation_id = conversations.id AND m.role = 'USER' "
        "ORDER BY m.created_at LIMIT 1)"
    ))

    with op.batch_alter_table('conversations') as batch_op:
        batch_op.alter_column('last_message_at', existing_type=sa.DateTime(timezone=True), nullable=False)
        batch_op.create_index('ix_conversations_last_message_at', ['last_message_at'])

    with op.batch_alter_table('messages') as batch_op:
        batch_op.drop_column('feedback')
    if bind.dialect.name == 'postgresql':
        sa.Enum(name='messagefeedback').drop(bind, checkfirst=True)

    with op.batch_alter_table('users') as batch_op:
        batch_op.drop_column('context_count')

    counters = op.create_table(
        'usage_counters',
        sa.Column('key', sa.String(length=50), nullable=False),
        sa.Column('value', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('key'),
    )
    prompts = bind.execute(sa.text("SELECT COUNT(*) FROM messages WHERE role = 'USER'")).scalar_one()
    anonymous = bind.execute(sa.text("SELECT COUNT(*) FROM conversations WHERE user_id IS NULL")).scalar_one()
    op.bulk_insert(counters, [
        {'key': 'total_prompts', 'value': int(prompts)},
        {'key': 'anonymous_conversations', 'value': int(anonymous)},
    ])

    # Bazy zalozone kiedys przez create_all() nie maja tych indeksow z migracji
    # poczatkowej - a historia filtruje po nich przy kazdym zapytaniu.
    inspector = sa.inspect(bind)
    for table, index, column in (
        ('conversations', 'ix_conversations_user_id', 'user_id'),
        ('messages', 'ix_messages_conversation_id', 'conversation_id'),
    ):
        if index not in {i['name'] for i in inspector.get_indexes(table)}:
            op.create_index(index, table, [column])


def downgrade() -> None:
    """Downgrade schema. Oceny (feedback) i liczniki nie wracaja - kolumny sa puste."""
    bind = op.get_bind()

    op.drop_table('usage_counters')

    with op.batch_alter_table('users') as batch_op:
        batch_op.add_column(sa.Column('context_count', sa.Integer(), nullable=False, server_default='5'))

    feedback = sa.Enum('UP', 'DOWN', name='messagefeedback')
    if bind.dialect.name == 'postgresql':
        feedback.create(bind, checkfirst=True)
    with op.batch_alter_table('messages') as batch_op:
        batch_op.add_column(sa.Column('feedback', feedback, nullable=True))

    with op.batch_alter_table('conversations') as batch_op:
        batch_op.drop_index('ix_conversations_last_message_at')
        batch_op.drop_column('last_message_at')
        batch_op.drop_column('title')
