from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import json
import os
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class RunPolicy:
    enabled: bool = True
    weekdays: tuple[int, ...] = (0, 1, 2, 3, 4)
    once_per_day: bool = True


class SingleInstanceLock:
    """Small cross-platform lock based on exclusive file creation."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._fd: int | None = None

    def acquire(self) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._fd = os.open(
                self.path,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
            )
        except FileExistsError:
            return False
        os.write(self._fd, str(os.getpid()).encode("ascii"))
        return True

    def release(self) -> None:
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass

    def __enter__(self) -> "SingleInstanceLock":
        if not self.acquire():
            raise RuntimeError(f"別のPHOENIX処理が実行中です: {self.path}")
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.release()


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def save_state(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary.replace(path)


def should_run(
    policy: RunPolicy,
    state: dict[str, Any],
    now: datetime,
) -> tuple[bool, str]:
    if not policy.enabled:
        return False, "scheduler disabled"
    if now.weekday() not in policy.weekdays:
        return False, "対象曜日ではありません"
    if policy.once_per_day and state.get("last_success_date") == now.date().isoformat():
        return False, "本日は実行済みです"
    return True, "実行可能"


def success_state(now: datetime, return_code: int, log_path: Path) -> dict[str, Any]:
    return {
        "last_success_date": now.date().isoformat(),
        "last_success_at": now.isoformat(timespec="seconds"),
        "last_return_code": return_code,
        "last_log": str(log_path),
    }


def failure_state(now: datetime, return_code: int, log_path: Path) -> dict[str, Any]:
    return {
        "last_failure_date": date.today().isoformat(),
        "last_failure_at": now.isoformat(timespec="seconds"),
        "last_return_code": return_code,
        "last_log": str(log_path),
    }
