"""
Local open-source embeddings for dense narrative retrieval.

Runs a sentence-transformers model on the machine hosting Django -- no Azure
deployment, no per-call cost, offline after the one-time model download.

Default model: BAAI/bge-small-en-v1.5 (384-dim, English, ~130 MB, CPU-fast).
Override with ASSISTANT_EMBEDDING_MODEL. bge models are asymmetric: passages are
embedded as-is, queries get a short instruction prefix.

If sentence-transformers is not installed, or the model cannot be loaded (for
example the first-run download is blocked), ``is_available()`` /
``EmbeddingUnavailable`` let the retriever fall back to lexical ranking. Nothing
here ever blocks an answer.

Install:  pip install sentence-transformers
"""

from __future__ import annotations

import importlib.util
import json
import logging
import os
import re
import threading
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "BAAI/bge-small-en-v1.5"
_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "

_model = None
_model_lock = threading.Lock()
_model_failed = False


class EmbeddingUnavailable(RuntimeError):
    """Raised when local embeddings cannot be produced."""


def _django_setting(name: str) -> Any:
    try:
        from django.conf import settings

        if settings.configured:
            return getattr(settings, name, None)
    except Exception:
        return None
    return None


def _model_name() -> str:
    return str(
        os.getenv("ASSISTANT_EMBEDDING_MODEL")
        or _django_setting("ASSISTANT_EMBEDDING_MODEL")
        or _DEFAULT_MODEL
    )


def is_available() -> bool:
    """
    True when sentence-transformers is importable and the model has not already
    failed to load. The model itself is loaded lazily on first use.
    """
    if _model_failed:
        return False
    return importlib.util.find_spec("sentence_transformers") is not None


def _get_model():
    global _model, _model_failed

    if _model is not None:
        return _model
    if _model_failed:
        raise EmbeddingUnavailable("Embedding model previously failed to load.")

    with _model_lock:
        if _model is not None:
            return _model
        try:
            from sentence_transformers import SentenceTransformer

            name = _model_name()
            logger.info("Loading embedding model '%s' (first load may download).", name)
            _model = SentenceTransformer(name)
            return _model
        except Exception as exc:  # import error, download blocked, OOM, etc.
            _model_failed = True
            raise EmbeddingUnavailable(
                f"Could not load embedding model: {exc}"
            ) from exc


def _encode(texts: list[str]) -> list[list[float]]:
    model = _get_model()
    try:
        vectors = model.encode(
            texts,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
    except Exception as exc:
        raise EmbeddingUnavailable(
            f"Embedding encode failed: {exc}"
        ) from exc
    return [row.tolist() for row in vectors]


def embed_passages(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    safe = [t if t and t.strip() else " " for t in texts]
    return _encode(safe)


def embed_query(text: str) -> list[float]:
    safe = text if text and text.strip() else " "
    return _encode([_QUERY_PREFIX + safe])[0]


# --------------------------------------------------------------------------- #
# best-effort on-disk vector cache (survives restarts)
# --------------------------------------------------------------------------- #
def _cache_dir() -> Optional[Path]:
    raw = (
        os.getenv("ASSISTANT_EMBED_CACHE_DIR")
        or _django_setting("ASSISTANT_EMBED_CACHE_DIR")
    )
    if raw:
        directory = Path(str(raw))
    else:
        base = _django_setting("BASE_DIR")
        if base:
            directory = Path(str(base)) / ".assistant_embeddings"
        else:
            return None
    try:
        directory.mkdir(parents=True, exist_ok=True)
        return directory
    except Exception:
        return None


def _cache_path(artifact_id: str, checksum: str) -> Optional[Path]:
    directory = _cache_dir()
    if directory is None:
        return None
    safe_id = re.sub(r"[^A-Za-z0-9_.-]", "_", str(artifact_id))[:80]
    safe_sum = re.sub(r"[^A-Za-z0-9_.-]", "_", str(checksum or "nochecksum"))[:80]
    return directory / f"{safe_id}__{safe_sum}__{_model_name().replace('/', '_')}.json"


def load_cached_vectors(
    artifact_id: str,
    checksum: str,
) -> Optional[list[list[float]]]:
    path = _cache_path(artifact_id, checksum)
    if path is None or not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        if isinstance(data, list) and all(isinstance(v, list) for v in data):
            return data
    except Exception:
        return None
    return None


def save_cached_vectors(
    artifact_id: str,
    checksum: str,
    vectors: list[list[float]],
) -> None:
    path = _cache_path(artifact_id, checksum)
    if path is None:
        return
    try:
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(vectors, handle)
    except Exception:
        # Cache is an optimisation only; ignore write failures.
        pass
