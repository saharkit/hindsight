"""Versioned database provider discovery and validation."""

import re
from collections.abc import Callable
from dataclasses import dataclass
from importlib import import_module, metadata
from typing import Literal

from ..sql.base import SQLDialect
from .base import DatabaseBackend
from .ops import DataAccessOps

_NAME = re.compile(r"[a-z][a-z0-9_-]*\Z")
_BUILTINS = {"postgresql", "oracle"}


@dataclass(frozen=True, kw_only=True)
class BackendProviderV1:
    """Factories and migration contract for one database implementation."""

    api_version: int
    backend_factory: Callable[[], DatabaseBackend]
    ops_factory: Callable[[], DataAccessOps]
    dialect_factory: Callable[[], SQLDialect]
    migration_dialect: str
    migration_mode: Literal["alembic", "backend"]


class BackendRegistrationError(ValueError):
    """An installed database provider cannot be selected safely."""


_PROVIDERS: dict[str, BackendProviderV1] = {}


def _lazy(module: str, symbol: str) -> Callable:
    return lambda: getattr(import_module(module), symbol)()


def _entries() -> dict[str, metadata.EntryPoint]:
    entries = {}
    for entry in metadata.entry_points(group="hindsight.database_backends"):
        distribution = entry.dist.name if entry.dist else "unknown distribution"
        # Never interpolate arbitrary metadata or exception messages into errors.
        distribution = (
            distribution if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", distribution) else "invalid distribution"
        )
        if not _NAME.fullmatch(entry.name):
            raise BackendRegistrationError(f"Invalid database backend name ({distribution})")
        if entry.name in _BUILTINS or entry.name in entries:
            raise BackendRegistrationError(f"Duplicate database backend {entry.name!r} ({distribution})")
        entries[entry.name] = entry
    return entries


def resolve_provider(name: str) -> BackendProviderV1:
    """Resolve only the selected provider, validating it before any connection."""
    if not isinstance(name, str) or not _NAME.fullmatch(name):
        raise BackendRegistrationError("Invalid database backend name")
    entries = _entries()
    if name in _PROVIDERS:
        return _PROVIDERS[name]
    if name in _BUILTINS:
        prefix = "hindsight_api.engine."
        symbol = "PostgreSQL" if name == "postgresql" else "Oracle"
        provider = BackendProviderV1(
            api_version=1,
            backend_factory=_lazy(prefix + "db." + name, symbol + "Backend"),
            ops_factory=_lazy(prefix + "db.ops_" + name, symbol + "Ops"),
            dialect_factory=_lazy(prefix + "sql." + name, symbol + "Dialect"),
            migration_dialect=name,
            migration_mode="alembic" if name == "postgresql" else "backend",
        )
    else:
        entry = entries.get(name)
        if entry is None:
            raise BackendRegistrationError(f"Unknown database backend: {name!r}")
        distribution = entry.dist.name if entry.dist else "unknown distribution"
        distribution = (
            distribution if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", distribution) else "invalid distribution"
        )
        try:
            factory = entry.load()
            provider = factory()
            if not isinstance(provider, BackendProviderV1):
                raise TypeError
            if type(provider.api_version) is not int or provider.api_version != 1:
                raise TypeError
            if not isinstance(provider.migration_dialect, str) or not _NAME.fullmatch(provider.migration_dialect):
                raise TypeError
            if provider.migration_mode not in ("alembic", "backend"):
                raise TypeError
            for constructor, base in (
                (provider.backend_factory, DatabaseBackend),
                (provider.ops_factory, DataAccessOps),
                (provider.dialect_factory, SQLDialect),
            ):
                if not callable(constructor) or not isinstance(constructor(), base):
                    raise TypeError
        except Exception:
            raise BackendRegistrationError(f"Invalid database provider {name!r} ({distribution})") from None
    _PROVIDERS[name] = provider
    return provider


def validate_backend_name(name: str) -> str:
    """Validate configuration through the same registry used by factories."""
    resolve_provider(name)
    return name
