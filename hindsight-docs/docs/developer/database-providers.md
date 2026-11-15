# Database providers

PostgreSQL is the default database backend; Oracle is also built in. Set
`HINDSIGHT_API_DATABASE_BACKEND` to the name of an installed provider. Names are
lowercased and must match `[a-z][a-z0-9_-]*`. Unknown names fail at startup;
configuration never imports an arbitrary module or installs a package.

Third-party distributions register a zero-argument factory in the
`hindsight.database_backends` entry-point group:

```toml
[project.entry-points."hindsight.database_backends"]
example = "example_database.plugin:provider"
```

The factory returns `BackendProviderV1` from `hindsight_api.engine.db`, a frozen,
keyword-only dataclass with six required members: `api_version=1`,
`backend_factory`, `ops_factory`, `dialect_factory`, `migration_dialect`, and
`migration_mode`. The three factories take no arguments and return concrete
`DatabaseBackend`, `DataAccessOps`, and `SQLDialect` implementations respectively.
Factories must create uninitialized objects without opening connections.
Operations are stateless and shared as one instance per backend name.

The migration dialect must match `[a-z][a-z0-9_-]*` and the SQLAlchemy dialect
name. It is independent of the provider entry name. Migration mode is explicitly
`alembic` or `backend`. Backend mode calls synchronous
`backend.run_migrations(dsn, schema=schema)` off the event loop and awaits
completion. External tenant schemas are normalized by the backend, deduplicated
in order and migrated sequentially; an empty selection runs once with `None`.
The first failure stops initialization without falling back to Alembic.

Alembic revisions may supply direction-specific mappings:

```python
def upgrade():
    run_for_dialect(pg=_pg_upgrade, oracle=_oracle_upgrade, external=_EXTERNAL_UPGRADE)


def downgrade():
    run_for_dialect(pg=_pg_downgrade, oracle=_oracle_downgrade, external=_EXTERNAL_DOWNGRADE)
```

A present external mapping value of `None` explicitly does nothing. Missing
entries refuse execution. Mapping keys do not register a dialect. The selected
validated provider establishes its migration dialect, and Alembic checks that
identity against the live dialect before invoking callbacks. Shipped revisions
currently contain only built-in callbacks, so selecting an external Alembic
provider against those revisions fails rather than silently skipping them.

External entries cannot replace built-ins or duplicate another entry name.
Only the selected external factory is loaded; a broken unselected package does
not prevent built-in startup. Invalid descriptors and incompatible API versions
are refused before database initialization. No third-party database driver is
included with this registration interface.
