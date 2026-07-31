from __future__ import annotations

from datetime import datetime
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from phoenix_core.performance_tracker import atomic_write, resolve_path


def fingerprint_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "path": str(path),
            "exists": False,
            "size_bytes": None,
            "sha256": None,
            "error": None,
        }
    if not path.is_file():
        return {
            "path": str(path),
            "exists": True,
            "size_bytes": None,
            "sha256": None,
            "error": "Protected path is not a regular file",
        }
    try:
        content = path.read_bytes()
    except OSError as error:
        return {
            "path": str(path),
            "exists": True,
            "size_bytes": None,
            "sha256": None,
            "error": f"{type(error).__name__}: {error}",
        }
    return {
        "path": str(path),
        "exists": True,
        "size_bytes": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
        "error": None,
    }


def capture_protected_files(root: Path, values: Iterable[str]) -> dict[str, dict[str, Any]]:
    captured: dict[str, dict[str, Any]] = {}
    for value in values:
        name = str(value)
        if name in captured:
            raise ValueError(f"Duplicate protected file: {name}")
        path = resolve_path(root, name)
        try:
            path.resolve().relative_to(root.resolve())
        except ValueError as error:
            raise ValueError(f"Protected file escapes project root: {name}") from error
        captured[name] = fingerprint_file(path)
    return captured


def build_integrity_report(
    before: Mapping[str, Mapping[str, Any]],
    after: Mapping[str, Mapping[str, Any]],
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    generated_at = generated_at or datetime.now()
    changes: list[dict[str, Any]] = []
    errors: list[str] = []
    names = sorted(set(before) | set(after))
    files: list[dict[str, Any]] = []
    for name in names:
        old = dict(before.get(name, {}))
        new = dict(after.get(name, {}))
        for phase, item in (("before", old), ("after", new)):
            if item.get("error"):
                errors.append(f"{name} ({phase}): {item['error']}")
        changed = any(
            old.get(key) != new.get(key)
            for key in ("exists", "size_bytes", "sha256", "error")
        )
        if changed:
            changes.append({
                "path": name,
                "before_exists": old.get("exists"),
                "after_exists": new.get("exists"),
                "before_sha256": old.get("sha256"),
                "after_sha256": new.get("sha256"),
            })
        files.append({"path": name, "unchanged": not changed})
    ready = not changes and not errors and bool(names)
    return {
        "schema_version": 1,
        "version": "PHOENIX v7 Step16",
        "generated_at": generated_at.isoformat(timespec="seconds"),
        "mode": "DRY_RUN",
        "status": "READY" if ready else "FAILED",
        "protected_file_count": len(names),
        "unchanged_file_count": sum(item["unchanged"] for item in files),
        "changed_file_count": len(changes),
        "files": files,
        "changes": changes,
        "errors": errors,
        "orders_submitted": 0,
    }


def text_report(report: Mapping[str, Any]) -> str:
    lines = [
        "PHOENIX v7 STEP16 DRY RUN STATE INTEGRITY",
        "=" * 88,
        f"Status               : {report.get('status', '')}",
        f"Protected files      : {report.get('protected_file_count', 0)}",
        f"Unchanged files      : {report.get('unchanged_file_count', 0)}",
        f"Changed files        : {report.get('changed_file_count', 0)}",
        f"Orders submitted     : {report.get('orders_submitted', 0)}",
        "-" * 88,
    ]
    lines.extend(
        f"{'PASS' if item.get('unchanged') else 'FAIL':<6} {item.get('path', '')}"
        for item in report.get("files", [])
    )
    if report.get("errors"):
        lines.extend(["-" * 88, "Errors:"] + [f"  - {value}" for value in report["errors"]])
    return "\n".join(lines + ["=" * 88, ""])


def save_integrity_report(
    root: Path,
    config: Mapping[str, Any],
    before: Mapping[str, Mapping[str, Any]],
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    settings = config.get("dry_run_integrity", {})
    protected = [str(value) for value in settings.get("protected_files", [])]
    if set(before) != set(protected):
        raise ValueError("Protected file configuration changed during Dry Run")
    after = capture_protected_files(root, protected)
    report = build_integrity_report(before, after, generated_at)
    json_path = resolve_path(
        root,
        str(settings.get("report_json", "reports/v7_dry_run_integrity.json")),
    )
    text_path = resolve_path(
        root,
        str(settings.get("report_text", "reports/v7_dry_run_integrity.txt")),
    )
    atomic_write(json_path, json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    atomic_write(text_path, text_report(report))
    report["report_json"] = str(json_path)
    report["report_text"] = str(text_path)
    return report


def print_integrity_summary(report: Mapping[str, Any]) -> None:
    print("=" * 80)
    print("PHOENIX v7 STEP16 DRY RUN STATE INTEGRITY")
    print("=" * 80)
    print(f"Status          : {report.get('status', '')}")
    print(f"Protected files : {report.get('protected_file_count', 0)}")
    print(f"Changed files   : {report.get('changed_file_count', 0)}")
    print(f"Report          : {report.get('report_text', '')}")
    print("=" * 80)
