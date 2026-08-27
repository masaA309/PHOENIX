from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata
from typing import Sequence

__all__ = ["RedundancyFinding", "RedundancyResult", "validate_prompt_redundancy"]

_LEADING_MARKERS_RE = re.compile(r"^(?:[-*•]+|\d+[.)])\s*")
_WHITESPACE_RE = re.compile(r"\s+")
_SENTENCE_SPLIT_RE = re.compile(r"[。．\.！？!?]+|\n+")
_TRAILING_PUNCTUATION = " \t\r\n:：,，;；、。．.！？!?)]}>'\"`"
_LEADING_PUNCTUATION = " \t\r\n([<{`'\""


@dataclass(frozen=True)
class RedundancyFinding:
    rule: str
    left: str
    right: str
    detail: str


@dataclass(frozen=True)
class RedundancyResult:
    passed: bool
    findings: tuple[RedundancyFinding, ...]


def _normalize_unit(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text)
    normalized = normalized.replace("\u3000", " ")
    normalized = normalized.strip()
    normalized = _LEADING_MARKERS_RE.sub("", normalized)
    normalized = normalized.strip(_LEADING_PUNCTUATION)
    normalized = normalized.strip(_TRAILING_PUNCTUATION)
    normalized = _WHITESPACE_RE.sub(" ", normalized)
    return normalized


def _split_units(text: str) -> tuple[str, ...]:
    units: list[str] = []
    for raw_line in unicodedata.normalize("NFKC", text).splitlines():
        if not raw_line.strip():
            continue
        pieces = [piece for piece in _SENTENCE_SPLIT_RE.split(raw_line) if piece.strip()]
        if not pieces:
            pieces = [raw_line]
        for piece in pieces:
            normalized = _normalize_unit(piece)
            if normalized:
                units.append(normalized)
    return tuple(units)


def _contains_complete_overlap(left: str, right: str) -> bool:
    if not left or not right:
        return False
    if left == right:
        return True
    if left in right or right in left:
        return True
    left_units = set(_split_units(left))
    right_units = set(_split_units(right))
    if not left_units or not right_units:
        return False
    if left_units == right_units:
        return True
    return left_units.issubset(right_units) or right_units.issubset(left_units)


def validate_prompt_redundancy(
    prompt_text: str,
    agents_text: str,
    proof_targets: Sequence[str],
) -> RedundancyResult:
    findings: list[RedundancyFinding] = []

    prompt_units = _split_units(prompt_text)
    agents_units = _split_units(agents_text)
    for prompt_unit in prompt_units:
        for agents_unit in agents_units:
            if prompt_unit == agents_unit:
                findings.append(
                    RedundancyFinding(
                        rule="prompt_vs_agents",
                        left=prompt_unit,
                        right=agents_unit,
                        detail="normalized sentence matches AGENTS.md exactly",
                    )
                )
            elif prompt_unit and agents_unit and (
                prompt_unit in agents_unit or agents_unit in prompt_unit
            ):
                findings.append(
                    RedundancyFinding(
                        rule="prompt_vs_agents",
                        left=prompt_unit,
                        right=agents_unit,
                        detail="normalized sentence is a direct containment match with AGENTS.md",
                    )
                )

    seen_prompt_units: set[str] = set()
    for prompt_unit in prompt_units:
        if prompt_unit in seen_prompt_units:
            findings.append(
                RedundancyFinding(
                    rule="prompt_internal_duplicate",
                    left=prompt_unit,
                    right=prompt_unit,
                    detail="duplicate normalized constraint sentence in the same prompt",
                )
            )
        else:
            seen_prompt_units.add(prompt_unit)

    normalized_targets = tuple(_normalize_unit(target) for target in proof_targets if _normalize_unit(target))
    for index, left in enumerate(normalized_targets):
        for right in normalized_targets[index + 1 :]:
            if _contains_complete_overlap(left, right):
                findings.append(
                    RedundancyFinding(
                        rule="proof_target_overlap",
                        left=left,
                        right=right,
                        detail="one proof target fully contains the other",
                    )
                )

    return RedundancyResult(passed=not findings, findings=tuple(findings))
