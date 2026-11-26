"""Sequential migration execution for external database providers."""

import asyncio
from collections.abc import Iterable
from pathlib import Path

from .base import DatabaseBackend
from .registry import resolve_provider


def _run_alembic(name: str, dsn: str, schema: str | None) -> None:
    from alembic import command
    from alembic.config import Config

    from hindsight_api.migrations import _alembic_lock, _set_alembic_main_option

    provider = resolve_provider(name)
    config = Config()
    config.set_main_option("script_location", str(Path(__file__).parents[2] / "alembic"))
    _set_alembic_main_option(config, "sqlalchemy.url", dsn)
    config.set_main_option("hindsight_backend", name)
    config.set_main_option("hindsight_migration_dialect", provider.migration_dialect)
    if schema:
        config.set_main_option("target_schema", schema)
    with _alembic_lock:
        command.upgrade(config, "heads")


async def run_provider_migrations(name: str, backend: DatabaseBackend, dsn: str, schemas: Iterable[str | None]) -> None:
    """Normalize and deduplicate schemas, awaiting each migration off the loop."""
    provider = resolve_provider(name)
    normalized = list(dict.fromkeys(backend.normalize_schema(schema) for schema in schemas if schema))
    for schema in normalized or [None]:
        if provider.migration_mode == "backend":
            await asyncio.to_thread(backend.run_migrations, dsn, schema=schema)
        else:
            await asyncio.to_thread(_run_alembic, name, dsn, schema)
