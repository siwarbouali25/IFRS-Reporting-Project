"""
Narrative retrieval over the generated final report Markdown.

The structured ESG tools remain the source for exact numeric questions. This
module is used for questions about what the final report says, explains,
describes, discloses, or concludes.

Design:
- selects the selected bank's latest report year;
- prefers the latest approved version for that year;
- otherwise uses the latest generated final Markdown version;
- reads artifacts from local storage or MinIO;
- chunks Markdown by heading hierarchy;
- ranks chunks using dependency-free hybrid lexical retrieval;
- returns report-version and chunk provenance for audit citations.

No embedding deployment or new Python dependency is required. The retrieval
cache is keyed by the artifact checksum, so repeated questions do not repeatedly
read and chunk the same report within a Django process.
"""

from __future__ import annotations

import importlib
import math
import re
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Iterable

from django.conf import settings
from django.db.models import Q


class ReportMarkdownNotFound(Exception):
    """Raised when a bank has no readable final Markdown artifact."""


@dataclass(frozen=True)
class MarkdownChunk:
    chunk_id: str
    chunk_index: int
    heading_path: tuple[str, ...]
    content: str

    @property
    def section_path(self) -> str:
        return " > ".join(self.heading_path) or "Report overview"


@dataclass(frozen=True)
class SelectedReport:
    artifact: object
    bank_name: str
    bank_code: str
    reporting_year: int
    version_number: int | None
    version_status: str
    report_version_id: str | None
    selection_reason: str


_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "been", "being", "but",
    "by", "can", "could", "did", "do", "does", "for", "from", "had",
    "has", "have", "how", "i", "if", "in", "into", "is", "it", "its",
    "may", "might", "of", "on", "or", "our", "should", "that", "the",
    "their", "there", "these", "they", "this", "those", "to", "was",
    "were", "what", "when", "where", "which", "who", "why", "will",
    "with", "would", "you", "your", "report", "reports", "say", "says",
    "said", "tell", "about",
}

_HEADING_RE = re.compile(
    r"^(#{1,6})\s+(.+?)\s*$"
)

_WORD_RE = re.compile(
    r"[A-Za-z0-9]+(?:[._/%+-][A-Za-z0-9]+)*"
)


def _normalise_space(text: str) -> str:
    return re.sub(
        r"[ \t]+",
        " ",
        str(text or ""),
    ).strip()


def _normalise_for_match(text: str) -> str:
    return re.sub(
        r"\s+",
        " ",
        str(text or "").lower(),
    ).strip()


def _stem(token: str) -> str:
    """
    Small deterministic stemmer used only for retrieval.

    It is intentionally conservative and does not rely on language-model
    reformulation or a hard-coded ESG synonym table.
    """

    token = token.lower()

    if len(token) > 5 and token.endswith("ies"):
        return token[:-3] + "y"

    for suffix in (
        "ments",
        "ment",
        "ations",
        "ation",
        "ingly",
        "edly",
        "ing",
        "ers",
        "er",
        "ed",
        "es",
        "s",
    ):
        if (
            len(token) > len(suffix) + 3
            and token.endswith(suffix)
        ):
            return token[:-len(suffix)]

    return token


def _tokens(text: str) -> list[str]:
    output = []

    for match in _WORD_RE.finditer(
        str(text or "")
    ):
        token = _stem(
            match.group(0)
        )

        if (
            len(token) >= 2
            and token not in _STOPWORDS
        ):
            output.append(token)

    return output


def _character_ngrams(
    text: str,
    size: int = 3,
) -> set[str]:
    normalised = re.sub(
        r"[^a-z0-9]+",
        " ",
        str(text or "").lower(),
    )
    normalised = re.sub(
        r"\s+",
        " ",
        normalised,
    ).strip()

    if len(normalised) < size:
        return (
            {normalised}
            if normalised
            else set()
        )

    return {
        normalised[index:index + size]
        for index in range(
            len(normalised) - size + 1
        )
    }


def _dice_similarity(
    left: set[str],
    right: set[str],
) -> float:
    if not left or not right:
        return 0.0

    return (
        2.0
        * len(left & right)
        / (len(left) + len(right))
    )


def _split_oversized_block(
    block: str,
    max_chars: int,
) -> list[str]:
    """
    Split a long paragraph or Markdown table without silently dropping text.
    """

    lines = [
        line.rstrip()
        for line in block.splitlines()
        if line.strip()
    ]

    if not lines:
        return []

    parts = []
    current = ""

    for line in lines:
        candidate = (
            f"{current}\n{line}"
            if current
            else line
        )

        if (
            current
            and len(candidate) > max_chars
        ):
            parts.append(
                current.strip()
            )
            current = line
        else:
            current = candidate

    if current:
        parts.append(
            current.strip()
        )

    final_parts = []

    for part in parts:
        if len(part) <= max_chars:
            final_parts.append(part)
            continue

        start = 0

        while start < len(part):
            end = min(
                len(part),
                start + max_chars,
            )

            if end < len(part):
                boundary = max(
                    part.rfind(
                        ". ",
                        start,
                        end,
                    ),
                    part.rfind(
                        "; ",
                        start,
                        end,
                    ),
                    part.rfind(
                        " ",
                        start,
                        end,
                    ),
                )

                if boundary > start + max_chars // 2:
                    end = boundary + 1

            final_parts.append(
                part[start:end].strip()
            )
            start = end

    return [
        part
        for part in final_parts
        if part
    ]


def _pack_blocks(
    blocks: list[str],
    max_chars: int,
    overlap_chars: int,
) -> list[str]:
    output = []
    current_blocks: list[str] = []
    current_length = 0

    for raw_block in blocks:
        expanded = (
            [raw_block]
            if len(raw_block) <= max_chars
            else _split_oversized_block(
                raw_block,
                max_chars,
            )
        )

        for block in expanded:
            projected = (
                current_length
                + len(block)
                + (
                    2
                    if current_blocks
                    else 0
                )
            )

            if (
                current_blocks
                and projected > max_chars
            ):
                chunk = "\n\n".join(
                    current_blocks
                ).strip()
                output.append(chunk)

                overlap = (
                    chunk[-overlap_chars:]
                    .lstrip()
                    if overlap_chars > 0
                    else ""
                )
                current_blocks = (
                    [overlap, block]
                    if overlap
                    else [block]
                )
                current_length = sum(
                    len(item)
                    for item in current_blocks
                ) + 2 * max(
                    len(current_blocks) - 1,
                    0,
                )
            else:
                current_blocks.append(block)
                current_length = projected

    if current_blocks:
        output.append(
            "\n\n".join(
                current_blocks
            ).strip()
        )

    return [
        chunk
        for chunk in output
        if chunk
    ]


def chunk_markdown(
    markdown: str,
    *,
    artifact_id: str = "artifact",
    max_chars: int = 1400,
    overlap_chars: int = 180,
) -> list[MarkdownChunk]:
    """
    Create heading-aware chunks from Markdown.

    Heading hierarchy is metadata rather than duplicated in every excerpt.
    Tables, lists, and paragraphs are retained in the content.
    """

    markdown = str(markdown or "").replace(
        "\r\n",
        "\n",
    )

    heading_stack: list[str] = []
    sections: list[
        tuple[tuple[str, ...], list[str]]
    ] = []
    current_lines: list[str] = []
    current_path: tuple[str, ...] = ()

    # Generated reports normally begin with one H1 document title. That title
    # is report metadata and should not be repeated in every section path.
    document_title: str | None = None
    first_heading_seen = False

    def flush_section() -> None:
        nonlocal current_lines

        body = "\n".join(
            current_lines
        ).strip()

        if body:
            sections.append(
                (
                    current_path,
                    body.split("\n\n"),
                )
            )

        current_lines = []

    for line in markdown.splitlines():
        match = _HEADING_RE.match(line)

        if not match:
            current_lines.append(
                line.rstrip()
            )
            continue

        # Save the body belonging to the previous heading before changing the
        # active hierarchy.
        flush_section()

        level = len(
            match.group(1)
        )
        title = _normalise_space(
            match.group(2)
        )

        # Only the first H1 is treated as the report title.
        if (
            not first_heading_seen
            and level == 1
        ):
            document_title = title
            first_heading_seen = True
            heading_stack = []
            current_path = ()
            continue

        first_heading_seen = True

        # Removing the document title shifts later levels by one:
        # H2 -> top-level section, H3 -> subsection.
        effective_level = (
            max(level - 1, 1)
            if document_title is not None
            else level
        )

        heading_stack = (
            heading_stack[
                :effective_level - 1
            ]
        )

        while (
            len(heading_stack)
            < effective_level - 1
        ):
            heading_stack.append("")

        heading_stack.append(title)
        current_path = tuple(
            heading
            for heading in heading_stack
            if heading
        )

    flush_section()

    if not sections and markdown.strip():
        sections = [
            (
                (),
                markdown.strip().split(
                    "\n\n"
                ),
            )
        ]

    chunks = []
    chunk_index = 0

    for heading_path, raw_blocks in sections:
        blocks = [
            block.strip()
            for block in raw_blocks
            if block.strip()
        ]

        for content in _pack_blocks(
            blocks,
            max_chars=max_chars,
            overlap_chars=overlap_chars,
        ):
            chunks.append(
                MarkdownChunk(
                    chunk_id=(
                        f"{artifact_id}:"
                        f"{chunk_index}"
                    ),
                    chunk_index=chunk_index,
                    heading_path=heading_path,
                    content=content,
                )
            )
            chunk_index += 1

    return chunks


def _version_metadata(
    artifact,
) -> tuple[
    int,
    int | None,
    str,
    str | None,
]:
    version = getattr(
        artifact,
        "report_version",
        None,
    )

    if version is not None:
        return (
            int(version.reporting_year),
            int(version.version_number),
            str(version.status),
            str(version.id),
        )

    job = getattr(
        artifact,
        "job",
        None,
    )

    if job is None:
        raise ReportMarkdownNotFound(
            "The Markdown artifact is not linked "
            "to a report version or generation job."
        )

    return (
        int(job.reporting_year),
        None,
        "generated",
        None,
    )


def select_final_markdown(
    bank_identifier: str,
    *,
    reporting_year: int | None = None,
    approved_only: bool = False,
) -> SelectedReport:
    from organizations.models import Bank
    from report_artifacts.models import (
        ReportArtifact,
    )
    from report_generation.models import (
        ReportVersion,
    )

    bank = (
        Bank.objects.filter(
            Q(
                code__iexact=bank_identifier
            )
            | Q(
                name__iexact=bank_identifier
            )
        )
        .first()
    )

    if bank is None:
        raise ReportMarkdownNotFound(
            f"No bank matches "
            f"'{bank_identifier}'."
        )

    queryset = (
        ReportArtifact.objects
        .select_related(
            "job",
            "job__bank",
            "report_version",
            "report_version__bank",
        )
        .filter(
            artifact_type=(
                ReportArtifact
                .ArtifactType
                .FINAL_MARKDOWN
            ),
        )
        .filter(
            Q(
                report_version__bank=bank
            )
            | Q(
                report_version__isnull=True,
                job__bank=bank,
            )
        )
    )

    if reporting_year is not None:
        queryset = queryset.filter(
            Q(
                report_version__reporting_year=(
                    reporting_year
                )
            )
            | Q(
                report_version__isnull=True,
                job__reporting_year=(
                    reporting_year
                ),
            )
        )

    candidates = list(queryset)

    if not candidates:
        raise ReportMarkdownNotFound(
            f"No final Markdown report is "
            f"available for {bank.name}"
            + (
                f" in {reporting_year}."
                if reporting_year is not None
                else "."
            )
        )

    metadata = [
        (
            artifact,
            *_version_metadata(artifact),
        )
        for artifact in candidates
    ]

    if reporting_year is None:
        target_year = max(
            row[1]
            for row in metadata
        )
        metadata = [
            row
            for row in metadata
            if row[1] == target_year
        ]
    else:
        target_year = reporting_year

    approved = [
        row
        for row in metadata
        if row[3]
        == ReportVersion.Status.APPROVED
    ]

    if approved_only and not approved:
        raise ReportMarkdownNotFound(
            f"No approved final Markdown report "
            f"is available for {bank.name} "
            f"in {target_year}."
        )

    pool = (
        approved
        if approved
        else metadata
    )
    selection_reason = (
        "latest_approved_version"
        if approved
        else "latest_generated_version"
    )

    selected = max(
        pool,
        key=lambda row: (
            row[2] or 0,
            getattr(
                row[0],
                "created_at",
                None,
            ),
        ),
    )

    (
        artifact,
        year,
        version_number,
        version_status,
        report_version_id,
    ) = selected

    return SelectedReport(
        artifact=artifact,
        bank_name=bank.name,
        bank_code=bank.code,
        reporting_year=year,
        version_number=version_number,
        version_status=version_status,
        report_version_id=(
            report_version_id
        ),
        selection_reason=(
            selection_reason
        ),
    )


def _read_with_project_storage_helper(
    artifact,
) -> bytes | None:
    """
    Use a project-provided read helper when one exists.

    Different project revisions used different helper names, so this checks a
    small set of explicit read-only contracts before using the local/MinIO
    fallback.
    """

    try:
        storage = importlib.import_module(
            "report_artifacts.storage"
        )
    except ImportError:
        return None

    for function_name in (
        "read_artifact_bytes",
        "load_artifact_bytes",
        "get_artifact_bytes",
        "download_artifact_bytes",
    ):
        function = getattr(
            storage,
            function_name,
            None,
        )

        if not callable(function):
            continue

        try:
            value = function(artifact)
        except TypeError:
            value = function(
                artifact.bucket,
                artifact.object_key,
            )

        if isinstance(value, str):
            return value.encode(
                "utf-8"
            )

        if isinstance(
            value,
            (bytes, bytearray),
        ):
            return bytes(value)

    return None


def _read_local_artifact(
    artifact,
) -> bytes:
    root = Path(
        settings.ARTIFACT_LOCAL_ROOT
    )

    candidates = [
        root / artifact.object_key,
        root
        / str(artifact.bucket)
        / artifact.object_key,
    ]

    for candidate in candidates:
        resolved = candidate.resolve()

        try:
            resolved.relative_to(
                root.resolve()
            )
        except ValueError:
            continue

        if (
            resolved.exists()
            and resolved.is_file()
        ):
            return resolved.read_bytes()

    raise ReportMarkdownNotFound(
        "The final Markdown metadata exists, "
        "but the local artifact file was not found."
    )


def _get_minio_client():
    try:
        module = importlib.import_module(
            "object_storage.minio_client"
        )
        function = getattr(
            module,
            "get_minio_client",
            None,
        )

        if callable(function):
            return function()
    except ImportError:
        pass

    try:
        from minio import Minio
    except ImportError as exc:
        raise ReportMarkdownNotFound(
            "MinIO artifact storage is configured, "
            "but the minio package is unavailable."
        ) from exc

    return Minio(
        endpoint=settings.MINIO_ENDPOINT,
        access_key=settings.MINIO_ACCESS_KEY,
        secret_key=settings.MINIO_SECRET_KEY,
        secure=settings.MINIO_SECURE,
    )


def _read_minio_artifact(
    artifact,
) -> bytes:
    client = _get_minio_client()
    response = None

    try:
        response = client.get_object(
            str(artifact.bucket),
            artifact.object_key,
        )
        return response.read()
    except Exception as exc:
        raise ReportMarkdownNotFound(
            "The final Markdown metadata exists, "
            "but the MinIO object could not be read."
        ) from exc
    finally:
        if response is not None:
            response.close()
            response.release_conn()


def read_artifact_text(
    artifact,
) -> str:
    content = (
        _read_with_project_storage_helper(
            artifact
        )
    )

    if content is None:
        backend = str(
            getattr(
                settings,
                "ARTIFACT_STORAGE_BACKEND",
                "local",
            )
        ).lower()

        if backend == "minio":
            content = _read_minio_artifact(
                artifact
            )
        else:
            content = _read_local_artifact(
                artifact
            )

    try:
        return content.decode(
            "utf-8-sig"
        )
    except UnicodeDecodeError as exc:
        raise ReportMarkdownNotFound(
            "The final report artifact is not "
            "valid UTF-8 Markdown."
        ) from exc


@lru_cache(maxsize=32)
def _cached_chunks(
    artifact_id: str,
    checksum: str,
    markdown: str,
) -> tuple[MarkdownChunk, ...]:
    del checksum

    return tuple(
        chunk_markdown(
            markdown,
            artifact_id=artifact_id,
        )
    )


def _bm25_scores(
    query_tokens: list[str],
    document_tokens: list[list[str]],
    *,
    k1: float = 1.5,
    b: float = 0.75,
) -> list[float]:
    if (
        not query_tokens
        or not document_tokens
    ):
        return [
            0.0
            for _ in document_tokens
        ]

    document_count = len(
        document_tokens
    )
    average_length = (
        sum(
            len(tokens)
            for tokens in document_tokens
        )
        / max(document_count, 1)
    )

    document_frequency = Counter()

    for tokens in document_tokens:
        document_frequency.update(
            set(tokens)
        )

    scores = []

    for tokens in document_tokens:
        frequencies = Counter(tokens)
        document_length = len(tokens)
        score = 0.0

        for term in set(query_tokens):
            frequency = frequencies.get(
                term,
                0,
            )

            if frequency <= 0:
                continue

            df = document_frequency.get(
                term,
                0,
            )
            idf = math.log(
                1.0
                + (
                    document_count
                    - df
                    + 0.5
                )
                / (df + 0.5)
            )
            denominator = (
                frequency
                + k1
                * (
                    1.0
                    - b
                    + b
                    * document_length
                    / max(
                        average_length,
                        1.0,
                    )
                )
            )
            score += (
                idf
                * frequency
                * (k1 + 1.0)
                / denominator
            )

        scores.append(score)

    return scores


def _lexical_ranked_all(
    query: str,
    chunks: list[MarkdownChunk],
) -> list[dict]:
    """
    Score every chunk with the heading-aware lexical hybrid and return them
    sorted best-first, without applying any top_k cap or acceptance threshold.

    This is the shared core used both by the public lexical ``rank_chunks`` and
    by the dense-fusion ranker, so the two paths stay perfectly consistent.
    """

    if not chunks:
        return []

    query_tokens = _tokens(query)

    if not query_tokens:
        return []

    document_tokens = [
        _tokens(
            (
                chunk.section_path
                + "\n"
                + chunk.content
            )
        )
        for chunk in chunks
    ]
    raw_bm25 = _bm25_scores(
        query_tokens,
        document_tokens,
    )
    max_bm25 = max(
        raw_bm25,
        default=0.0,
    )

    query_set = set(
        query_tokens
    )
    query_ngrams = (
        _character_ngrams(query)
    )
    normalised_query = (
        _normalise_for_match(query)
    )

    ranked = []

    for chunk, tokens, bm25 in zip(
        chunks,
        document_tokens,
        raw_bm25,
    ):
        token_set = set(tokens)
        heading_tokens = set(
            _tokens(
                chunk.section_path
            )
        )

        token_coverage = (
            len(query_set & token_set)
            / max(len(query_set), 1)
        )
        heading_coverage = (
            len(
                query_set
                & heading_tokens
            )
            / max(len(query_set), 1)
        )
        character_similarity = (
            _dice_similarity(
                query_ngrams,
                _character_ngrams(
                    chunk.section_path
                    + "\n"
                    + chunk.content
                ),
            )
        )
        phrase_bonus = (
            1.0
            if (
                normalised_query
                and normalised_query
                in _normalise_for_match(
                    chunk.section_path
                    + "\n"
                    + chunk.content
                )
            )
            else 0.0
        )
        bm25_normalised = (
            bm25 / max_bm25
            if max_bm25 > 0
            else 0.0
        )

        score = (
            0.58 * bm25_normalised
            + 0.18 * token_coverage
            + 0.14 * heading_coverage
            + 0.07 * character_similarity
            + 0.03 * phrase_bonus
        )

        if (
            bm25 <= 0
            and token_coverage <= 0
            and character_similarity < 0.08
        ):
            continue

        ranked.append(
            {
                "chunk": chunk,
                "score": round(
                    score,
                    6,
                ),
                "bm25_score": round(
                    bm25,
                    6,
                ),
                "token_coverage": round(
                    token_coverage,
                    6,
                ),
            }
        )

    ranked.sort(
        key=lambda item: (
            item["score"],
            item["bm25_score"],
        ),
        reverse=True,
    )

    return ranked


def rank_chunks(
    query: str,
    chunks: Iterable[MarkdownChunk],
    *,
    top_k: int = 5,
) -> list[dict]:
    """Pure lexical ranking with the original acceptance thresholds."""

    chunks = list(chunks)
    top_k = max(1, min(int(top_k), 8))

    ranked = _lexical_ranked_all(query, chunks)

    if not ranked:
        return []

    best_score = ranked[0]["score"]

    return [
        item
        for item in ranked[:top_k]
        if (
            item["score"] >= 0.10
            or item["score"] >= best_score * 0.45
        )
    ]


def rank_chunks_multiquery(
    query: str,
    chunks: Iterable[MarkdownChunk],
    *,
    top_k: int = 5,
) -> tuple[list[dict], str, dict]:
    """
    Improve lexical retrieval with generative query expansion.

    The chat deployment rewrites the question into several vocabulary-rich
    variants (and one hypothetical report sentence, HyDE-style). Each variant is
    ranked with the existing lexical hybrid, the rankings are fused with
    Reciprocal Rank Fusion, and MMR removes near-duplicate passages.

    This recovers most of the vocabulary-mismatch benefit of dense embeddings
    without any embedding model, extra dependency, or model download: it uses
    only the Azure chat deployment already configured for the assistant. If
    expansion is disabled or the chat call fails, it degrades to the original
    single-query lexical ranking.

    Returns ``(hits, retrieval_method, expansion_meta)``.
    """

    chunks = list(chunks)
    top_k = max(1, min(int(top_k), 8))

    from .expansion import expand_query

    expansion = expand_query(query)
    variants = expansion.queries or [query]

    rankings: list[list[dict]] = []
    for variant in variants:
        ranked = _lexical_ranked_all(variant, chunks)
        if ranked:
            rankings.append(ranked)

    meta = {
        "used_llm": expansion.used_llm,
        "query_variants": variants,
    }

    # No expansion happened (disabled or failed): keep the exact original
    # single-query lexical behaviour, thresholds included.
    if not expansion.used_llm or len(rankings) <= 1:
        primary = rankings[0] if rankings else []
        return (
            _apply_lexical_threshold(primary, top_k),
            "heading_aware_hybrid_lexical",
            meta,
        )

    fused = _reciprocal_rank_fusion(rankings)
    if not fused:
        return [], "lexical_multiquery_rrf", meta

    text_lookup = {
        id(chunk): (chunk.section_path + "\n" + chunk.content)
        for chunk in chunks
    }
    selected = _mmr_select(
        fused,
        text_lookup,
        top_k=top_k,
        lambda_weight=0.65,
    )
    return selected, "lexical_multiquery_rrf", meta


def _apply_lexical_threshold(
    lexical_all: list[dict],
    top_k: int,
) -> list[dict]:
    if not lexical_all:
        return []
    best_score = lexical_all[0]["score"]
    return [
        item
        for item in lexical_all[:top_k]
        if (
            item["score"] >= 0.10
            or item["score"] >= best_score * 0.45
        )
    ]


def _reciprocal_rank_fusion(
    rankings: list[list[dict]],
    *,
    k: int = 60,
) -> list[dict]:
    """
    Fuse several rankings of the same chunks by summed reciprocal rank, keyed by
    chunk identity. Scale-free, so different query variants combine cleanly
    without calibrating their raw scores.
    """

    contributions: dict[int, dict] = {}

    for ranking in rankings:
        for rank, item in enumerate(ranking):
            chunk = item["chunk"]
            entry = contributions.setdefault(
                id(chunk),
                {
                    "chunk": chunk,
                    "rrf": 0.0,
                    "best_rank": None,
                    "hit_count": 0,
                    "lexical_score": item.get("score", 0.0),
                },
            )
            entry["rrf"] += 1.0 / (k + rank + 1)
            entry["hit_count"] += 1
            if entry["best_rank"] is None or (rank + 1) < entry["best_rank"]:
                entry["best_rank"] = rank + 1
            entry["lexical_score"] = max(
                entry["lexical_score"],
                item.get("score", 0.0),
            )

    fused = list(contributions.values())
    fused.sort(
        key=lambda entry: (entry["rrf"], entry["hit_count"]),
        reverse=True,
    )
    return fused


def _mmr_select(
    fused: list[dict],
    text_lookup: dict[int, str],
    *,
    top_k: int,
    lambda_weight: float = 0.65,
    pool_size: int = 20,
) -> list[dict]:
    """
    Maximal Marginal Relevance over the fused candidates. Redundancy between
    passages is measured with character-trigram Dice similarity (no embeddings
    required), so overlapping/near-duplicate chunks do not crowd out
    complementary sections.
    """

    pool = fused[:pool_size]
    if not pool:
        return []

    max_rrf = max(entry["rrf"] for entry in pool) or 1.0
    ngram_cache: dict[int, set] = {}

    def ngrams_for(chunk) -> set:
        key = id(chunk)
        if key not in ngram_cache:
            ngram_cache[key] = _character_ngrams(
                text_lookup.get(key, "")
            )
        return ngram_cache[key]

    for entry in pool:
        entry["_relevance"] = entry["rrf"] / max_rrf

    selected: list[dict] = []
    remaining = list(pool)

    while remaining and len(selected) < top_k:
        best_entry = None
        best_value = float("-inf")

        for entry in remaining:
            candidate_ngrams = ngrams_for(entry["chunk"])
            redundancy = 0.0
            for chosen in selected:
                redundancy = max(
                    redundancy,
                    _dice_similarity(
                        candidate_ngrams,
                        ngrams_for(chosen["chunk"]),
                    ),
                )

            value = (
                lambda_weight * entry["_relevance"]
                - (1.0 - lambda_weight) * redundancy
            )
            if value > best_value:
                best_value = value
                best_entry = entry

        selected.append(best_entry)
        remaining.remove(best_entry)

    return [
        {
            "chunk": entry["chunk"],
            "score": round(entry["rrf"], 6),
            "best_rank": entry["best_rank"],
            "hit_count": entry["hit_count"],
            "lexical_score": round(entry["lexical_score"], 6),
        }
        for entry in selected
    ]



def search_final_report_markdown(
    bank_identifier: str,
    query: str,
    *,
    reporting_year: int | None = None,
    approved_only: bool = False,
    top_k: int = 5,
) -> dict:
    selected = select_final_markdown(
        bank_identifier,
        reporting_year=(
            reporting_year
        ),
        approved_only=approved_only,
    )
    markdown = read_artifact_text(
        selected.artifact
    )

    checksum = str(
        getattr(
            selected.artifact,
            "checksum",
            "",
        )
        or ""
    )
    artifact_id = str(
        selected.artifact.id
    )
    chunks = _cached_chunks(
        artifact_id,
        checksum,
        markdown,
    )
    ranked, retrieval_method, expansion_meta = (
        rank_chunks_multiquery(
            query,
            chunks,
            top_k=top_k,
        )
    )

    hits = []

    for item in ranked:
        chunk = item["chunk"]

        hits.append(
            {
                "chunk_id": (
                    chunk.chunk_id
                ),
                "chunk_index": (
                    chunk.chunk_index
                ),
                "section_path": (
                    chunk.section_path
                ),
                "score": item["score"],
                "excerpt": (
                    chunk.content
                ),
            }
        )

    provenance = {
        "source": (
            "ReportArtifact.final_markdown"
        ),
        "bank_name": (
            selected.bank_name
        ),
        "bank_code": (
            selected.bank_code
        ),
        "reporting_year": (
            selected.reporting_year
        ),
        "report_version_id": (
            selected.report_version_id
        ),
        "version_number": (
            selected.version_number
        ),
        "version_status": (
            selected.version_status
        ),
        "selection_reason": (
            selected.selection_reason
        ),
        "artifact_id": artifact_id,
        "artifact_type": (
            "final_markdown"
        ),
        "object_key": (
            selected.artifact.object_key
        ),
        "checksum": checksum,
        "retrieved_chunk_ids": [
            hit["chunk_id"]
            for hit in hits
        ],
        "retrieval_method": (
            retrieval_method
        ),
        "query_expansion_used": (
            expansion_meta.get("used_llm", False)
        ),
        "query_variants": (
            expansion_meta.get("query_variants", [])
        ),
    }

    return {
        "ok": True,
        "bank_name": (
            selected.bank_name
        ),
        "bank_code": (
            selected.bank_code
        ),
        "data": hits,
        "provenance": provenance,
        "data_gaps": [],
        "message": (
            None
            if hits
            else (
                "The final report exists, but "
                "no relevant Markdown passage "
                "was found for this query."
            )
        ),
    }
