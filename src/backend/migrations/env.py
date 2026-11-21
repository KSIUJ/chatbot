"""Migracje na tej samej bazie (DATABASE_URL) i tych samych modelach co aplikacja."""

import logging

from sqlalchemy import engine_from_config, pool

from alembic import context
from src.backend.database import DATABASE_URL
from src.backend.models import Base

config = context.config


def _configure_logging() -> None:
    """Ostrzezenia na stderr i postep migracji (logger alembic na INFO).
    Konfiguracja jest w pyproject.toml, wiec nie ma alembic.ini z sekcja logow."""
    logging.basicConfig(level=logging.WARNING, format="%(levelname)-5.5s [%(name)s] %(message)s")
    logging.getLogger("alembic").setLevel(logging.INFO)


# tylko z linii polecen (python -m alembic ...): testy wolaja command.upgrade
# bez cmd_opts i nie chca zmienionych loggerow
if config.cmd_opts is not None:
    _configure_logging()

target_metadata = Base.metadata

# ConfigParser traktuje "%" jako interpolacje, wiec w URL trzeba go podwoic
config.set_main_option("sqlalchemy.url", DATABASE_URL.replace("%", "%%"))


def run_migrations_offline() -> None:
    """Generuje SQL bez polaczenia z baza (alembic upgrade --sql)."""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        # SQLite nie umie ALTER/DROP COLUMN - batch mode przebudowuje tabele
        render_as_batch=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Wykonuje migracje na polaczeniu z baza."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
