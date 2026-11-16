"""Database backend abstraction layer.

Provides a uniform interface over different database drivers (asyncpg, oracledb, etc.)
so that business logic is decoupled from any specific database platform.

Usage:
    from hindsight_api.engine.db import create_database_backend, DatabaseBackend

    backend = create_database_backend("postgresql")
    await backend.initialize(dsn="postgresql://...")
    async with backend.acquire() as conn:
        rows = await conn.fetch("SELECT ...")
"""

from .base import DatabaseBackend, DatabaseConnection
from .ops import DataAccessOps
from .registry import BackendProviderV1, resolve_provider
from .result import ResultRow

__all__ = [
    "BackendProviderV1",
    "DataAccessOps",
    "DatabaseBackend",
    "DatabaseConnection",
    "ResultRow",
    "create_data_access_ops",
    "create_database_backend",
]


def create_database_backend(backend_type: str) -> DatabaseBackend:
    """Factory: create a DatabaseBackend by name.

    Args:
        backend_type: One of "postgresql" or "oracle".

    Returns:
        An uninitialized DatabaseBackend instance.

    Raises:
        ValueError: If backend_type is not recognized.
    """
    return resolve_provider(backend_type).backend_factory()


_OPS_CACHE: dict[str, DataAccessOps] = {}


def create_data_access_ops(backend_type: str) -> DataAccessOps:
    """Factory: the DataAccessOps for a backend name.

    Returns a per-dialect SINGLETON: ``DataAccessOps`` is stateless (it only builds and runs SQL),
    so one shared instance per dialect is correct — and it means the database backend and the
    memories store hold the *same* ops object, so a test that patches a method on it (e.g.
    ``enqueue_graph_maintenance``) observes every caller regardless of which layer issued it.

    Args:
        backend_type: One of "postgresql" or "oracle".

    Returns:
        The shared DataAccessOps instance for that backend.

    Raises:
        ValueError: If backend_type is not recognized.
    """
    ops = _OPS_CACHE.get(backend_type)
    if ops is None:
        ops = resolve_provider(backend_type).ops_factory()
        _OPS_CACHE[backend_type] = ops
    return ops
