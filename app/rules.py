"""Mock provider rules.

Each rule is checked once per added line: a rule either matches the line or it
does not. Multiple occurrences on one line still produce a single finding,
because the brief specifies one finding per matching line per rule (and the
finding id — ruleId:path:line — could not distinguish them anyway).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# --------------------------------------------------------------------------
# Finding
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Finding:
    rule_id: str
    path: str
    line: int
    severity: str
    category: str
    title: str
    evidence: str

    @property
    def id(self) -> str:
        return f"{self.rule_id}:{self.path}:{self.line}"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "ruleId": self.rule_id,
            "path": self.path,
            "line": self.line,
            "severity": self.severity,
            "category": self.category,
            "title": self.title,
            "evidence": self.evidence,
        }


# --------------------------------------------------------------------------
# Rule metadata (severity, category, title) — kept beside the detectors
# --------------------------------------------------------------------------

RULE_META = {
    "MOCK-001": ("critical", "security", "eval usage"),
    "MOCK-002": ("critical", "security", "hardcoded credential"),
    "MOCK-003": ("high", "security", "SQL string concatenation"),
    "MOCK-004": ("high", "correctness", "swallowed exception"),
    "MOCK-005": ("medium", "correctness", "loose null comparison"),
    "MOCK-006": ("medium", "performance", "deep-clone via JSON"),
    "MOCK-007": ("low", "style", "console.log left in"),
    "MOCK-008": ("low", "style", "unresolved marker"),
    "MOCK-INJ": ("critical", "security", "prompt-injection content"),
}


# --------------------------------------------------------------------------
# Detectors
# --------------------------------------------------------------------------

# Given verbatim in the brief. Do not "improve" it — it defines correctness.
_CREDENTIAL = re.compile(
    r"(api[_-]?key|secret|token)\s*[:=]\s*['\"][A-Za-z0-9_\-]{16,}['\"]",
    re.IGNORECASE,
)

_NULL_COMPARE = re.compile(r"[=!]=\s*null")

_SQL_KEYWORD = re.compile(r"\b(SELECT|INSERT|UPDATE|DELETE)\b", re.IGNORECASE)

# String literals: single, double, or backtick quoted.
_STRING_LITERAL = re.compile(r"'[^']*'|\"[^\"]*\"|`[^`]*`")

_INJECTION_PHRASES = (
    "ignore previous instructions",
    "disregard all prior",
    "you are now",
)

_CATCH = re.compile(r"\bcatch\b")


def _has_sql_concat(content: str) -> bool:
    """SQL keyword inside a string literal, on a line using + concatenation."""
    literals = _STRING_LITERAL.findall(content)
    if not literals:
        return False
    if not any(_SQL_KEYWORD.search(lit) for lit in literals):
        return False
    # Require a + outside of string literals.
    outside = _STRING_LITERAL.sub("", content)
    return "+" in outside


def _is_empty_catch(content: str, following: list[str]) -> bool:
    """True if a catch on this line has an empty body.

    Only added lines are visible, so a catch whose body lies outside the diff
    is treated as non-empty rather than guessed at.
    """
    if not _CATCH.search(content):
        return False

    after_brace = content.split("{", 1)
    if len(after_brace) == 2 and after_brace[1].strip().startswith("}"):
        return True  # } catch (e) {}

    for nxt in following:
        stripped = nxt.strip()
        if not stripped:
            continue
        return stripped.startswith("}")
    return False


def check_line(
    path: str,
    line: int,
    content: str,
    following: list[str] | None = None,
) -> list[Finding]:
    """Return every finding triggered by one added line."""
    following = following or []
    hits: list[str] = []

    if "eval(" in content:
        hits.append("MOCK-001")

    if _CREDENTIAL.search(content):
        hits.append("MOCK-002")

    if _has_sql_concat(content):
        hits.append("MOCK-003")

    if _is_empty_catch(content, following):
        hits.append("MOCK-004")

    if _NULL_COMPARE.search(content):
        hits.append("MOCK-005")

    if "JSON.parse(JSON.stringify(" in content:
        hits.append("MOCK-006")

    if "console.log(" in content:
        hits.append("MOCK-007")

    if "TODO" in content or "FIXME" in content:
        hits.append("MOCK-008")

    lowered = content.lower()
    if any(phrase in lowered for phrase in _INJECTION_PHRASES):
        hits.append("MOCK-INJ")

    findings = []
    for rule_id in hits:
        severity, category, title = RULE_META[rule_id]
        findings.append(
            Finding(
                rule_id=rule_id,
                path=path,
                line=line,
                severity=severity,
                category=category,
                title=title,
                evidence=content,
            )
        )
    return findings


# --------------------------------------------------------------------------
# Ordering and deduplication — applied once over the full collection
# --------------------------------------------------------------------------


def order_and_dedupe(findings: list[Finding]) -> list[Finding]:
    """Sort by path, then line, then ruleId. Remove duplicate ids."""
    seen: set[str] = set()
    unique = []
    for f in findings:
        if f.id not in seen:
            seen.add(f.id)
            unique.append(f)
    return sorted(unique, key=lambda f: (f.path, f.line, f.rule_id))
