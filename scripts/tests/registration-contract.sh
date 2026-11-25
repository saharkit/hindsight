#!/bin/sh
# Run from any directory after the documented frozen Python 3.12 sync.
set -eu
unset UV_PROJECT_ENVIRONMENT UV_NO_SYNC VIRTUAL_ENV PYTHONPATH
export UV_NO_SYNC=1
export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
export TOKENIZERS_PARALLELISM=false
cd "$(dirname "$0")/../../hindsight-api-slim"
mkdir -p ../artifacts/registration-contract
# Attempt both selections even when one fails, preserving pytest's actual XML.
status=0
uv run --python 3.12 --no-python-downloads pytest \
 tests/test_backend_registration.py::test_absent_migration_callback_is_noop_for_builtins \
 tests/test_backend_registration.py::test_backend_mode_bypass_off_event_loop_completion_and_failure \
 tests/test_backend_registration.py::test_default_postgresql_lowercasing_and_url_safe_errors \
 tests/test_backend_registration.py::test_external_alembic_mapping_in_both_directions \
 tests/test_backend_registration.py::test_installed_sample_provider_discovery_and_coherent_resolution \
 tests/test_backend_registration.py::test_lazy_builtins_and_broken_unselected_provider \
 tests/test_backend_registration.py::test_ops_resolution_preserves_singleton_identity \
 tests/test_backend_registration.py::test_oracle_backend_factory_selection \
 tests/test_backend_registration.py::test_registration_refuses_invalid_providers \
 tests/test_backend_registration.py::test_repeated_operations_resolution_preserves_singleton_identity \
 --junitxml=../artifacts/registration-contract/registration.xml || status=1
uv run --python 3.12 --no-python-downloads pytest \
 tests/test_db_abstraction.py::TestConfig::test_database_backend_field_exists \
 tests/test_db_abstraction.py::TestConfig::test_default_database_backend \
 tests/test_db_abstraction.py::TestFactories::test_create_postgresql_backend \
 tests/test_db_abstraction.py::TestFactories::test_create_postgresql_dialect \
 tests/test_db_abstraction.py::TestFactories::test_create_unknown_backend_raises \
 tests/test_db_abstraction.py::TestFactories::test_create_unknown_dialect_raises \
 tests/test_migration_shape.py::test_migration_uses_dialect_dispatcher \
 tests/test_operation_retention_migration.py::test_operation_retention_migration_follows_current_head_and_covers_both_dialects \
 --junitxml=../artifacts/registration-contract/builtins.xml || status=1
# Pytest can exit successfully with skips; acceptance requires every case to pass.
uv run --python 3.12 --no-python-downloads python - <<'PY' || status=1
from pathlib import Path
from xml.etree import ElementTree

for name in ("registration", "builtins"):
    path = Path("../artifacts/registration-contract") / f"{name}.xml"
    suites = ElementTree.parse(path).getroot().findall(".//testsuite")
    tests = sum(int(suite.get("tests", "0")) for suite in suites)
    rejected = sum(int(suite.get(key, "0")) for suite in suites for key in ("failures", "errors", "skipped"))
    print(f"{path}: tests={tests}, failures/errors/skips={rejected}")
    if tests <= 0 or rejected:
        raise SystemExit(1)
PY
exit "$status"
