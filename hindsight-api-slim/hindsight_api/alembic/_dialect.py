"""Dispatch revision callbacks using the selected provider's migration contract."""

from collections.abc import Callable, Mapping

from alembic import op

from hindsight_api.engine.db.registry import resolve_provider

DialectFn = Callable[[], None]


class MigrationDialectError(RuntimeError):
    """The migration dialect or its revision callback is not registered."""


def run_for_dialect(
    *,
    pg: DialectFn | None = None,
    oracle: DialectFn | None = None,
    external: Mapping[str, DialectFn | None] | None = None,
) -> None:
    """Run the active dialect's callback, refusing implicit external no-ops."""
    live = op.get_bind().dialect.name
    config = op.get_context().config
    selected = config.get_main_option("hindsight_backend") if config else None
    declared = config.get_main_option("hindsight_migration_dialect") if config else None
    provider = None
    if selected is not None:
        try:
            provider = resolve_provider(selected)
        except ValueError:
            raise MigrationDialectError("Invalid selected migration provider") from None
        if declared != provider.migration_dialect:
            raise MigrationDialectError("Migration dialect disagrees with selected provider")
    if declared is not None and declared != live:
        raise MigrationDialectError("Migration dialect disagrees with SQLAlchemy dialect")
    name = declared if declared is not None else live
    if name not in ("postgresql", "oracle") and (provider is None or name != provider.migration_dialect):
        raise MigrationDialectError("Unregistered migration dialect")
    if selected and selected not in ("postgresql", "oracle"):
        if provider.migration_mode != "alembic":
            raise MigrationDialectError("Backend-owned migrations cannot run Alembic revisions")
        if external is None or name not in external:
            raise MigrationDialectError("Missing external migration callback")
        fn = external[name]
    else:
        fn = {"postgresql": pg, "oracle": oracle}.get(name)
    if fn is not None:
        fn()
