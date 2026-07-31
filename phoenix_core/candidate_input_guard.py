from __future__ import annotations

import csv
from dataclasses import dataclass
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
from typing import Any, Mapping

import pandas as pd

from phoenix_core.position_sizer import normalize_candidate_frame


DECISION_COLUMN = "Trade判定"
EXECUTABLE_DECISIONS = ("BUY",)
KNOWN_DECISIONS = ("BUY", "WATCH", "SKIP")
EXECUTION_PRICE_COLUMN = "押し目価格"
TSE_CODE_CHARACTER = "0-9ACDFGHJKLMNPRSTUWXY"
TSE_TICKER_PATTERN = re.compile(
    rf"^[1-9][{TSE_CODE_CHARACTER}][0-9][{TSE_CODE_CHARACTER}]\.T$"
)


class CandidateInputError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class CandidateInputPolicy:
    enabled: bool
    path: str
    decision_column: str
    execution_price_column: str
    executable_values: tuple[str, ...]
    known_values: tuple[str, ...]
    fallback: bool

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "CandidateInputPolicy":
        if not isinstance(value, Mapping):
            raise CandidateInputError("candidate_input config must be an object")
        policy = cls(
            enabled=value.get("enabled") is True,
            path=str(value.get("path", "")).strip(),
            decision_column=str(value.get("decision_column", "")).strip(),
            execution_price_column=str(
                value.get("execution_price_column", "")
            ).strip(),
            executable_values=tuple(
                str(item).strip().upper()
                for item in value.get("executable_values", [])
            ),
            known_values=tuple(
                str(item).strip().upper()
                for item in value.get("known_values", [])
            ),
            fallback=bool(value.get("fallback", True)),
        )
        policy.validate()
        return policy

    def validate(self) -> None:
        if not self.enabled:
            raise CandidateInputError("Candidate input guard cannot be disabled")
        if self.path != "reports/trade_signals.csv":
            raise CandidateInputError(
                "Candidate input path must be reports/trade_signals.csv"
            )
        if self.decision_column != DECISION_COLUMN:
            raise CandidateInputError(f"decision_column must be {DECISION_COLUMN}")
        if self.execution_price_column != EXECUTION_PRICE_COLUMN:
            raise CandidateInputError(
                f"execution_price_column must be {EXECUTION_PRICE_COLUMN}"
            )
        if self.executable_values != EXECUTABLE_DECISIONS:
            raise CandidateInputError("Only BUY can be executable")
        if self.known_values != KNOWN_DECISIONS:
            raise CandidateInputError("known_values must be BUY, WATCH, SKIP")
        if self.fallback:
            raise CandidateInputError("Candidate file fallback is forbidden")


@dataclass(frozen=True, slots=True)
class CandidateInputAudit:
    status: str
    source_path: str
    input_sha256: str
    eligible_candidates_sha256: str
    input_rows: int
    eligible_rows: int
    rejected_rows: int
    decision_counts: tuple[tuple[str, int], ...]
    rejection_counts: tuple[tuple[str, int], ...]

    def validate(self) -> None:
        if self.status != "READY":
            raise CandidateInputError("Candidate input audit is not READY")
        for name, value in (
            ("input_sha256", self.input_sha256),
            ("eligible_candidates_sha256", self.eligible_candidates_sha256),
        ):
            if len(value) != 64 or any(
                character not in "0123456789abcdef" for character in value.lower()
            ):
                raise CandidateInputError(f"{name} must be a SHA-256 digest")
        row_counts = (self.input_rows, self.eligible_rows, self.rejected_rows)
        if any(isinstance(value, bool) or not isinstance(value, int) for value in row_counts):
            raise CandidateInputError("Candidate audit row counts must be integers")
        if min(row_counts) < 0:
            raise CandidateInputError("Candidate audit row counts cannot be negative")
        if self.eligible_rows + self.rejected_rows != self.input_rows:
            raise CandidateInputError("Candidate audit row counts are inconsistent")
        counts = dict(self.decision_counts)
        if tuple(counts) != KNOWN_DECISIONS or any(
            isinstance(value, bool) or not isinstance(value, int) or value < 0
            for value in counts.values()
        ):
            raise CandidateInputError("Candidate audit decision counts are invalid")
        if sum(counts.values()) != self.input_rows:
            raise CandidateInputError("Candidate audit decision counts are inconsistent")
        if self.eligible_rows != counts["BUY"]:
            raise CandidateInputError("Candidate audit eligible count is inconsistent")
        if self.rejected_rows != counts["WATCH"] + counts["SKIP"]:
            raise CandidateInputError("Candidate audit rejected count is inconsistent")
        expected_rejections = tuple(
            (value, counts[value])
            for value in KNOWN_DECISIONS
            if value not in EXECUTABLE_DECISIONS and counts[value] > 0
        )
        if self.rejection_counts != expected_rejections:
            raise CandidateInputError("Candidate audit rejection counts are inconsistent")

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "source_path": self.source_path,
            "input_sha256": self.input_sha256,
            "eligible_candidates_sha256": self.eligible_candidates_sha256,
            "input_rows": self.input_rows,
            "eligible_rows": self.eligible_rows,
            "rejected_rows": self.rejected_rows,
            "decision_counts": dict(self.decision_counts),
            "rejection_counts": dict(self.rejection_counts),
        }


@dataclass(frozen=True, slots=True)
class CandidateInputBatch:
    candidates: pd.DataFrame
    audit: CandidateInputAudit


def candidate_execution_sha256(candidates: pd.DataFrame) -> str:
    rows: list[dict[str, Any]] = []
    for _, row in candidates.iterrows():
        rows.append(
            {
                "ticker": str(row.get("ticker", "")).strip().upper(),
                "name": str(row.get("銘柄", "")).strip(),
                "entry_price": float(row.get("エントリー価格", 0.0)),
                "stop_price": float(row.get("損切価格", 0.0)),
                "ranking_score": float(row.get("ランキング点", 0.0)),
                "decision": str(row.get(DECISION_COLUMN, "")).strip().upper(),
            }
        )
    payload = json.dumps(
        rows,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _validate_csv_shape(decoded: str, path: Path) -> None:
    try:
        rows = list(csv.reader(io.StringIO(decoded), strict=True))
    except csv.Error as error:
        raise CandidateInputError(f"Candidate CSV has no valid header: {path}") from error
    if not rows:
        raise CandidateInputError(f"Candidate CSV has no valid header: {path}")
    header = rows[0]
    normalized = [str(value).strip().casefold() for value in header]
    if not normalized or any(not value for value in normalized):
        raise CandidateInputError(f"Candidate CSV contains a blank header: {path}")
    if len(normalized) != len(set(normalized)):
        raise CandidateInputError(f"Candidate CSV contains duplicate columns: {path}")
    for row_number, row in enumerate(rows[1:], start=2):
        if len(row) != len(header):
            raise CandidateInputError(
                f"Candidate CSV row {row_number} has {len(row)} fields; "
                f"expected {len(header)}"
            )


def _validated_execution_prices(raw: pd.DataFrame, column: str) -> pd.Series:
    if column not in raw.columns:
        raise CandidateInputError(
            f"Candidate execution price column is missing: {column}"
        )
    values = pd.to_numeric(raw[column], errors="coerce")
    valid = values.notna() & values.map(
        lambda value: math.isfinite(float(value)) and float(value) > 0
    )
    if not bool(valid.all()):
        raise CandidateInputError(
            f"Every candidate row must have a finite positive execution price: {column}"
        )
    return values.astype(float)


def load_execution_candidates(
    path: Path,
    policy: CandidateInputPolicy,
    *,
    repository_root: Path,
) -> CandidateInputBatch:
    policy.validate()
    root = repository_root.resolve()
    expected_path = root / policy.path
    if os.path.normcase(os.path.abspath(path)) != os.path.normcase(
        os.path.abspath(expected_path)
    ):
        raise CandidateInputError(
            f"Candidate path does not match the configured execution source: {path}"
        )
    resolved_expected = expected_path.resolve()
    if os.path.normcase(str(resolved_expected)) != os.path.normcase(
        str(expected_path.absolute())
    ):
        raise CandidateInputError(
            f"Candidate path cannot contain a symbolic/reparse alias: {expected_path}"
        )
    try:
        resolved_expected.relative_to(root)
    except ValueError as error:
        raise CandidateInputError("Candidate path escapes repository root") from error
    current = expected_path
    while current != root:
        if current.is_symlink():
            raise CandidateInputError(
                f"Candidate path cannot contain a symbolic link: {current}"
            )
        current = current.parent
    if not path.is_file():
        raise FileNotFoundError(f"Candidate CSV not found: {path}")
    if path.stat().st_nlink > 1:
        raise CandidateInputError(f"Candidate path cannot be a hard-link alias: {path}")
    try:
        content = path.read_bytes()
        decoded = content.decode("utf-8-sig")
    except (OSError, UnicodeError) as error:
        raise CandidateInputError(f"Could not read candidate CSV: {path}: {error}") from error
    _validate_csv_shape(decoded, path)
    try:
        raw = pd.read_csv(io.StringIO(decoded))
    except (pd.errors.EmptyDataError, pd.errors.ParserError, UnicodeError) as error:
        raise CandidateInputError(f"Could not parse candidate CSV: {path}: {error}") from error

    for required in (policy.decision_column, "ticker"):
        if required not in raw.columns:
            raise CandidateInputError(f"Required candidate column is missing: {required}")

    decisions = raw[policy.decision_column].map(
        lambda value: "" if pd.isna(value) else str(value).strip().upper()
    )
    unknown = sorted(set(decisions) - set(policy.known_values))
    if unknown:
        raise CandidateInputError(
            "Unknown candidate decisions are forbidden: " + ", ".join(unknown)
        )

    tickers = raw["ticker"].map(
        lambda value: "" if pd.isna(value) else str(value).strip().upper()
    )
    if tickers.eq("").any() or tickers.str.casefold().eq("nan").any():
        raise CandidateInputError("Candidate ticker must be present on every row")
    duplicates = sorted(tickers[tickers.duplicated(keep=False)].unique())
    if duplicates:
        raise CandidateInputError(
            "Duplicate candidate tickers are forbidden: " + ", ".join(duplicates)
        )
    invalid_tickers = sorted(
        ticker for ticker in tickers.unique() if not TSE_TICKER_PATTERN.fullmatch(ticker)
    )
    if invalid_tickers:
        raise CandidateInputError(
            "Candidate ticker is not a TSE code: " + ", ".join(invalid_tickers)
        )

    raw = raw.copy()
    raw["ticker"] = tickers
    raw["エントリー価格"] = _validated_execution_prices(
        raw,
        policy.execution_price_column,
    )
    normalized = normalize_candidate_frame(raw, apply_portfolio_filter=False)
    if len(normalized) != len(raw):
        raise CandidateInputError(
            "Every candidate row must have a valid ticker and positive execution price"
        )
    for column in ("エントリー価格", "損切価格", "ランキング点"):
        if not bool(
            normalized[column].map(lambda value: math.isfinite(float(value))).all()
        ):
            raise CandidateInputError(
                f"Candidate execution field must be finite: {column}"
            )

    executable = set(policy.executable_values)
    eligible_tickers = set(tickers[decisions.isin(executable)])
    candidates = normalized[normalized["ticker"].isin(eligible_tickers)].copy()
    candidates = candidates.reset_index(drop=True)
    decision_counts = tuple(
        (value, int((decisions == value).sum())) for value in policy.known_values
    )
    rejection_counts = tuple(
        (value, count)
        for value, count in decision_counts
        if value not in executable and count > 0
    )
    audit = CandidateInputAudit(
        status="READY",
        source_path=str(path),
        input_sha256=hashlib.sha256(content).hexdigest(),
        eligible_candidates_sha256=candidate_execution_sha256(candidates),
        input_rows=len(raw),
        eligible_rows=len(candidates),
        rejected_rows=len(raw) - len(candidates),
        decision_counts=decision_counts,
        rejection_counts=rejection_counts,
    )
    audit.validate()
    return CandidateInputBatch(candidates=candidates, audit=audit)
