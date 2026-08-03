"""Unified diff parser.

Produces (path, line_number, content) for every added line, where line_number
is the line's position in the NEW file.

Structural boundaries come from hunk header arithmetic, never from scanning
line content. An added line containing text that looks like diff syntax is
therefore inert.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# @@ -oldStart,oldCount +newStart,newCount @@ optional trailing text
# The counts are optional; "@@ -3 +3 @@" means a count of 1.
_HUNK_HEADER = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


@dataclass
class AddedLine:
    """One added line and its position in the new file."""

    line: int
    content: str


@dataclass
class ParsedFile:
    """All added lines for a single file, plus that file's verbatim diff text."""

    path: str
    added_lines: list[AddedLine] = field(default_factory=list)
    raw_text: str = ""


def _strip_prefix(path: str) -> str:
    """Remove git's a/ or b/ prefix. 'b/src/db.ts' -> 'src/db.ts'."""
    if path.startswith(("a/", "b/")):
        return path[2:]
    return path


def parse_unified_diff(diff: str) -> list[ParsedFile]:
    """Parse a unified diff. Returns [] if nothing parseable is found."""
    lines = diff.splitlines()
    files: list[ParsedFile] = []

    current: ParsedFile | None = None
    current_raw: list[str] = []

    i = 0
    while i < len(lines):
        line = lines[i]

        # --- New file section -------------------------------------------
        if line.startswith("+++ "):
            if current is not None:
                current.raw_text = "\n".join(current_raw)
                files.append(current)

            path = _strip_prefix(line[4:].strip())
            current = ParsedFile(path=path)
            current_raw = [line]
            i += 1
            continue

        # --- Hunk header ------------------------------------------------
        match = _HUNK_HEADER.match(line)
        if match and current is not None:
            current_raw.append(line)

            new_start = int(match.group(3))
            new_count = int(match.group(4)) if match.group(4) else 1

            counter = new_start          # the ticket currently in hand
            consumed = 0                 # how many new-file lines seen so far
            i += 1

            # Read exactly new_count new-file lines. Content is never
            # inspected for structure.
            while i < len(lines) and consumed < new_count:
                body = lines[i]
                current_raw.append(body)

                if body.startswith("+"):
                    current.added_lines.append(
                        AddedLine(line=counter, content=body[1:])
                    )
                    counter += 1
                    consumed += 1
                elif body.startswith("-"):
                    pass                 # not in the new file: no ticket
                elif body.startswith("\\"):
                    pass                 # "\ No newline at end of file"
                else:
                    counter += 1         # context line (space, or empty)
                    consumed += 1

                i += 1
            continue

        # --- Anything else ----------------------------------------------
        if current is not None:
            current_raw.append(line)
        i += 1

    if current is not None:
        current.raw_text = "\n".join(current_raw)
        files.append(current)

    return files
