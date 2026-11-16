"""Memory engine interfaces, resolved lazily on first access.

Database provider registration can be used without importing model wrappers or
any built-in database driver. Public engine exports retain their import paths.
"""

from importlib import import_module
from typing import TYPE_CHECKING

_LAZY_EXPORTS = {
    "get_current_schema": ("..schema_context", "get_current_schema"),
    "CrossEncoderModel": (".cross_encoder", "CrossEncoderModel"),
    "LocalSTCrossEncoder": (".cross_encoder", "LocalSTCrossEncoder"),
    "RemoteTEICrossEncoder": (".cross_encoder", "RemoteTEICrossEncoder"),
    "acquire_with_retry": (".db_utils", "acquire_with_retry"),
    "Embeddings": (".embeddings", "Embeddings"),
    "LocalSTEmbeddings": (".embeddings", "LocalSTEmbeddings"),
    "RemoteTEIEmbeddings": (".embeddings", "RemoteTEIEmbeddings"),
    "LLMConfig": (".llm_wrapper", "LLMConfig"),
    "MemoryEngine": (".memory_engine", "MemoryEngine"),
    "UnqualifiedTableError": (".memory_engine", "UnqualifiedTableError"),
    "validate_sql_schema": (".memory_engine", "validate_sql_schema"),
    "MemoryFact": (".response_models", "MemoryFact"),
    "RecallResult": (".response_models", "RecallResult"),
    "ReflectResult": (".response_models", "ReflectResult"),
    "fq_table": (".schema", "fq_table"),
    "EntryPoint": (".search.trace", "EntryPoint"),
    "NodeVisit": (".search.trace", "NodeVisit"),
    "QueryInfo": (".search.trace", "QueryInfo"),
    "SearchPhaseMetrics": (".search.trace", "SearchPhaseMetrics"),
    "SearchSummary": (".search.trace", "SearchSummary"),
    "SearchTrace": (".search.trace", "SearchTrace"),
    "WeightComponents": (".search.trace", "WeightComponents"),
    "SearchTracer": (".search.tracer", "SearchTracer"),
}

__all__ = [
    "CrossEncoderModel",
    "Embeddings",
    "EntryPoint",
    "LLMConfig",
    "LocalSTCrossEncoder",
    "LocalSTEmbeddings",
    "MemoryEngine",
    "MemoryFact",
    "NodeVisit",
    "QueryInfo",
    "RecallResult",
    "ReflectResult",
    "RemoteTEICrossEncoder",
    "RemoteTEIEmbeddings",
    "SearchPhaseMetrics",
    "SearchSummary",
    "SearchTrace",
    "SearchTracer",
    "UnqualifiedTableError",
    "WeightComponents",
    "acquire_with_retry",
    "fq_table",
    "get_current_schema",
    "validate_sql_schema",
]


def __getattr__(name: str):
    """Resolve and cache a public engine interface."""
    try:
        module, attribute = _LAZY_EXPORTS[name]
    except KeyError:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from None
    value = getattr(import_module(module, __name__), attribute)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    """List public interfaces before they have been imported."""
    return sorted([*__all__, "__name__"])


if TYPE_CHECKING:
    from ..schema_context import get_current_schema
    from .cross_encoder import CrossEncoderModel, LocalSTCrossEncoder, RemoteTEICrossEncoder
    from .db_utils import acquire_with_retry
    from .embeddings import Embeddings, LocalSTEmbeddings, RemoteTEIEmbeddings
    from .llm_wrapper import LLMConfig
    from .memory_engine import MemoryEngine, UnqualifiedTableError, validate_sql_schema
    from .response_models import MemoryFact, RecallResult, ReflectResult
    from .schema import fq_table
    from .search.trace import (
        EntryPoint,
        NodeVisit,
        QueryInfo,
        SearchPhaseMetrics,
        SearchSummary,
        SearchTrace,
        WeightComponents,
    )
    from .search.tracer import SearchTracer
