"""Split a diff into chunks on file boundaries.

Chunking never changes findings — the brief requires identical results to an
unchunked scan. It partitions work so that one file's diff is never split
across two chunks.
"""

from __future__ import annotations

from app import config
from app.diff_parser import ParsedFile


def chunk_files(files: list[ParsedFile], limit: int | None = None) -> list[list[ParsedFile]]:
    """Greedy bin-pack by byte size, never splitting a single file."""
    limit = limit if limit is not None else config.CHUNK_BYTES
    if not files:
        return []

    chunks: list[list[ParsedFile]] = []
    current: list[ParsedFile] = []
    current_size = 0

    for parsed in files:
        size = len(parsed.raw_text.encode("utf-8"))

        # A file larger than the limit is its own chunk.
        if size >= limit:
            if current:
                chunks.append(current)
                current, current_size = [], 0
            chunks.append([parsed])
            continue

        if current and current_size + size > limit:
            chunks.append(current)
            current, current_size = [], 0

        current.append(parsed)
        current_size += size

    if current:
        chunks.append(current)

    return chunks
