"""Alembic environment. Wires the migration runner to settings + Base metadata."""

from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

# Import each module's models so they're registered with Base.metadata.
# Add new lines here as modules introduce models.
from family_assistant.ai_gateway import models as _ai_gateway_models  # noqa: F401
from family_assistant.auth import models as _auth_models  # noqa: F401
from family_assistant.db import Base
from family_assistant.exercise import models as _exercise_models  # noqa: F401
from family_assistant.family_member import models as _family_member_models  # noqa: F401
from family_assistant.grocery import models as _grocery_models  # noqa: F401
from family_assistant.lunch_plan import models as _lunch_plan_models  # noqa: F401
from family_assistant.meal_plan import models as _meal_plan_models  # noqa: F401
from family_assistant.memory import models as _memory_models  # noqa: F401
from family_assistant.settings import get_settings

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

if not config.get_main_option("sqlalchemy.url"):
    config.set_main_option("sqlalchemy.url", get_settings().database_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
