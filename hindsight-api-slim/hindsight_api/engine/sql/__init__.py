"""SQL dialect abstraction layer.

Isolates database-specific SQL syntax (parameter placeholders, JSON operators,
vector distance functions, etc.) behind a common interface.

Usage:
    from hindsight_api.engine.sql import create_sql_dialect, SQLDialect

    dialect = create_sql_dialect("postgresql")
    placeholder = dialect.param(1)  # "$1" for PG, ":1" for Oracle
"""

from .base import SQLDialect

__all__ = [
    "SQLDialect",
    "create_sql_dialect",
]


def create_sql_dialect(backend_type: str) -> SQLDialect:
    """Factory: create a SQLDialect by backend name.

    Args:
        backend_type: One of "postgresql" or "oracle".

    Returns:
        A SQLDialect instance.

    Raises:
        ValueError: If backend_type is not recognized.
    """
    from ..db.registry import BackendRegistrationError, resolve_provider

    try:
        provider = resolve_provider(backend_type)
    except BackendRegistrationError as exc:
        raise BackendRegistrationError(f"Unknown SQL dialect: {exc}") from None
    return provider.dialect_factory()
