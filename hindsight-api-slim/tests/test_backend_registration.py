"""Provider registration contract tests using installed distribution metadata."""

import asyncio
import subprocess
import sys
import threading
import zipfile
from dataclasses import FrozenInstanceError, replace
from importlib import metadata
from types import SimpleNamespace

import pytest
from alembic.config import Config

from hindsight_api.alembic import _dialect
from hindsight_api.config import HindsightConfig
from hindsight_api.engine.db import create_data_access_ops, create_database_backend, registry
from hindsight_api.engine.db.base import DatabaseBackend
from hindsight_api.engine.db.ops_postgresql import PostgreSQLOps
from hindsight_api.engine.db.postgresql import PostgreSQLBackend
from hindsight_api.engine.db.provider_migrations import run_provider_migrations
from hindsight_api.engine.sql import create_sql_dialect
from hindsight_api.engine.sql.postgresql import PostgreSQLDialect


@pytest.fixture
def installed_provider(tmp_path, monkeypatch):
    """Install a local sample wheel without resolving any dependencies."""
    wheel = tmp_path / "registration_sample-1.0-py3-none-any.whl"
    files = {
        "registration_sample.py": """from hindsight_api.engine.db.registry import BackendProviderV1
from hindsight_api.engine.db.postgresql import PostgreSQLBackend
from hindsight_api.engine.db.ops_postgresql import PostgreSQLOps
from hindsight_api.engine.sql.postgresql import PostgreSQLDialect

def provider():
    return BackendProviderV1(api_version=1, backend_factory=PostgreSQLBackend,
        ops_factory=PostgreSQLOps, dialect_factory=PostgreSQLDialect,
        migration_dialect="sample_sql", migration_mode="backend")
""",
        "registration_sample-1.0.dist-info/METADATA": "Metadata-Version: 2.1\nName: registration-sample\nVersion: 1.0\n",
        "registration_sample-1.0.dist-info/WHEEL": "Wheel-Version: 1.0\nGenerator: registration-test\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
        "registration_sample-1.0.dist-info/entry_points.txt": "[hindsight.database_backends]\nsample = registration_sample:provider\nbroken_sample = absent_registration_sample:provider\n",
    }
    files["registration_sample-1.0.dist-info/RECORD"] = "\n".join(f"{name},," for name in files)
    with zipfile.ZipFile(wheel, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    target = tmp_path / "installed"
    result = subprocess.run(
        ["uv", "pip", "install", "--no-deps", "--no-index", "--target", str(target), str(wheel)],
        capture_output=True,
        check=False,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr.decode()
    monkeypatch.syspath_prepend(str(target))
    monkeypatch.setattr(registry, "_PROVIDERS", {})
    yield registry.resolve_provider("sample")
    sys.modules.pop("registration_sample", None)


def test_installed_sample_provider_discovery_and_coherent_resolution(installed_provider):
    """L6: catch loss of real installed entry-point wiring between factories."""
    assert "sample" in {ep.name for ep in metadata.entry_points(group="hindsight.database_backends")}
    assert isinstance(create_database_backend("sample"), PostgreSQLBackend)
    assert isinstance(create_data_access_ops("sample"), PostgreSQLOps)
    assert isinstance(create_sql_dialect("sample"), PostgreSQLDialect)
    assert registry.resolve_provider("sample") is installed_provider
    with pytest.raises(FrozenInstanceError):
        installed_provider.api_version = 2


def test_repeated_operations_resolution_preserves_singleton_identity(installed_provider):
    """L1 composition: catch external resolution bypassing the existing cache."""
    first = create_data_access_ops("sample")
    assert all(create_data_access_ops("sample") is first for _ in range(3))


def test_ops_resolution_preserves_singleton_identity():
    """L2: catch built-in operations being allocated per factory call."""
    assert create_data_access_ops("postgresql") is create_data_access_ops("postgresql")
    assert create_data_access_ops("oracle") is create_data_access_ops("oracle")


def test_lazy_builtins_and_broken_unselected_provider(installed_provider, monkeypatch):
    """L2: catch eager external loading or built-in implementation imports."""
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; from hindsight_api.engine.db.registry import resolve_provider; "
            "resolve_provider('postgresql'); resolve_provider('oracle'); "
            "assert 'hindsight_api.engine.db.postgresql' not in sys.modules; "
            "assert 'hindsight_api.engine.db.oracle' not in sys.modules",
        ],
        capture_output=True,
        check=False,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr.decode()
    monkeypatch.setattr(registry, "_PROVIDERS", {})

    def unexpected_import(*args):
        pytest.fail("resolving a built-in descriptor imported an implementation")

    monkeypatch.setattr(registry, "import_module", unexpected_import)
    assert registry.resolve_provider("postgresql").migration_mode == "alembic"
    assert registry.resolve_provider("oracle").migration_mode == "backend"
    with pytest.raises(registry.BackendRegistrationError, match="broken_sample"):
        registry.resolve_provider("broken_sample")


def test_oracle_backend_factory_selection():
    """L2: catch Oracle factories accidentally resolving PostgreSQL."""
    from hindsight_api.engine.db.oracle import OracleBackend
    from hindsight_api.engine.sql.oracle import OracleDialect

    assert isinstance(create_database_backend("oracle"), OracleBackend)
    assert isinstance(create_sql_dialect("oracle"), OracleDialect)


def test_registration_refuses_invalid_providers(installed_provider, monkeypatch):
    """L3: catch metadata, descriptor, abstract implementation and version refusals lost."""
    entry = metadata.EntryPoint(
        name="sample", value="registration_sample:provider", group="hindsight.database_backends"
    )
    for entries in (
        [metadata.EntryPoint(name="postgresql", value=entry.value, group=entry.group)],
        [entry, entry],
        [metadata.EntryPoint(name="Bad.Name", value=entry.value, group=entry.group)],
    ):
        monkeypatch.setattr(registry.metadata, "entry_points", lambda **kwargs: entries)
        with pytest.raises(registry.BackendRegistrationError):
            registry.resolve_provider("postgresql")
    monkeypatch.setattr(registry.metadata, "entry_points", lambda **kwargs: [entry])
    import registration_sample

    for descriptor in (
        object(),
        replace(installed_provider, api_version=2),
        replace(installed_provider, api_version=True),
        replace(installed_provider, backend_factory=DatabaseBackend),
        replace(installed_provider, ops_factory=lambda: object()),
        replace(installed_provider, dialect_factory=None),
        replace(installed_provider, migration_dialect="bad.name"),
        replace(installed_provider, migration_mode="implicit"),
    ):
        monkeypatch.setattr(registry, "_PROVIDERS", {})
        monkeypatch.setattr(registration_sample, "provider", lambda: descriptor)
        with pytest.raises(registry.BackendRegistrationError):
            registry.resolve_provider("sample")
    with pytest.raises(registry.BackendRegistrationError):
        registry.resolve_provider("missing")


def test_default_postgresql_lowercasing_and_url_safe_errors(monkeypatch):
    """L2: catch default/case regressions and credential disclosure on refusal."""
    monkeypatch.delenv("HINDSIGHT_API_DATABASE_BACKEND", raising=False)
    assert HindsightConfig.from_env().database_backend == "postgresql"
    monkeypatch.setenv("HINDSIGHT_API_DATABASE_BACKEND", "ORACLE")
    assert HindsightConfig.from_env().database_backend == "oracle"
    secret = "postgresql://user:password@example/db"
    monkeypatch.setenv("HINDSIGHT_API_DATABASE_BACKEND", secret)
    with pytest.raises(ValueError) as exc:
        HindsightConfig.from_env()
    assert secret not in str(exc.value)
    assert "password" not in str(exc.value)


@pytest.fixture
def migration_context(monkeypatch):
    config = Config()
    bind = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))
    monkeypatch.setattr(_dialect.op, "get_bind", lambda: bind)
    monkeypatch.setattr(_dialect.op, "get_context", lambda: SimpleNamespace(config=config))
    return config, bind


def test_absent_migration_callback_is_noop_for_builtins(migration_context):
    """L2: catch intentional missing built-in callbacks becoming errors."""
    _, bind = migration_context
    for name in ("postgresql", "oracle"):
        bind.dialect.name = name
        _dialect.run_for_dialect()


def test_external_alembic_mapping_in_both_directions(installed_provider, migration_context, monkeypatch):
    """L3: catch implicit external no-ops, false registration and direction mixing."""
    config, bind = migration_context
    monkeypatch.setitem(registry._PROVIDERS, "sample", replace(installed_provider, migration_mode="alembic"))
    config.set_main_option("hindsight_backend", "sample")
    config.set_main_option("hindsight_migration_dialect", "sample_sql")
    bind.dialect.name = "sample_sql"
    calls = []
    # Fixture revision directions deliberately own separate callback mappings.
    upgrade = {"sample_sql": lambda: calls.append("upgrade")}
    downgrade = {"sample_sql": lambda: calls.append("downgrade")}
    for mapping in (upgrade, downgrade):
        _dialect.run_for_dialect(external=mapping)
        _dialect.run_for_dialect(external={"sample_sql": None})
        with pytest.raises(_dialect.MigrationDialectError):
            _dialect.run_for_dialect(external={})
    assert calls == ["upgrade", "downgrade"]
    bind.dialect.name = "unregistered"
    with pytest.raises(_dialect.MigrationDialectError):
        _dialect.run_for_dialect(external={"unregistered": lambda: calls.append("bad")})
    config.set_main_option("hindsight_migration_dialect", "unregistered")
    with pytest.raises(_dialect.MigrationDialectError):
        _dialect.run_for_dialect(external={"unregistered": None})
    config.set_main_option("hindsight_backend", "missing")
    with pytest.raises(_dialect.MigrationDialectError):
        _dialect.run_for_dialect(external={"unregistered": None})


@pytest.mark.asyncio
async def test_backend_mode_bypass_off_event_loop_completion_and_failure(installed_provider, monkeypatch):
    """L6: catch loop blocking, unawaited completion, schema repeats and fallback."""
    from hindsight_api.engine.db import provider_migrations

    backend = create_database_backend("sample")
    loop_thread = threading.get_ident()
    calls = []

    def migrate(dsn, *, schema=None):
        assert threading.get_ident() != loop_thread
        assert dsn == "sample-dsn"
        calls.append(schema)

    def unexpected_alembic(*args):
        pytest.fail("backend mode fell back to Alembic")

    monkeypatch.setattr(backend, "run_migrations", migrate)
    monkeypatch.setattr(backend, "normalize_schema", lambda schema: schema.lower())
    monkeypatch.setattr(provider_migrations, "_run_alembic", unexpected_alembic)
    await asyncio.wait_for(run_provider_migrations("sample", backend, "sample-dsn", ["A", "a", "B", ""]), 5)
    assert calls == ["a", "b"], "migration completion must be awaited and schemas deduplicated"
    await asyncio.wait_for(run_provider_migrations("sample", backend, "sample-dsn", []), 5)
    assert calls == ["a", "b", None]

    def fail(dsn, *, schema=None):
        calls.append(schema)
        raise RuntimeError("migration failed")

    monkeypatch.setattr(backend, "run_migrations", fail)
    with pytest.raises(RuntimeError, match="migration failed"):
        await asyncio.wait_for(run_provider_migrations("sample", backend, "sample-dsn", ["C", "D"]), 5)
    assert calls == ["a", "b", None, "c"], "failure must stop before the next tenant"

    alembic_calls = []

    def migrate_alembic(name, dsn, schema):
        assert threading.get_ident() != loop_thread
        alembic_calls.append((name, dsn, schema))

    monkeypatch.setitem(registry._PROVIDERS, "sample", replace(installed_provider, migration_mode="alembic"))
    monkeypatch.setattr(provider_migrations, "_run_alembic", migrate_alembic)
    await asyncio.wait_for(run_provider_migrations("sample", backend, "sample-dsn", ["A", "a", "B"]), 5)
    await asyncio.wait_for(run_provider_migrations("sample", backend, "sample-dsn", []), 5)
    assert alembic_calls == [
        ("sample", "sample-dsn", "a"),
        ("sample", "sample-dsn", "b"),
        ("sample", "sample-dsn", None),
    ]
