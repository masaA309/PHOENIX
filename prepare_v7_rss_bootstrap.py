from __future__ import annotations

import argparse
import ctypes
import hashlib
import os
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable


ROOT_DIR = Path(__file__).resolve().parent
WORKBOOK_RELATIVE = Path("runtime") / "v7_rss_production" / "PHOENIX_RSS_PRODUCTION.xlsm"
MANIFEST_RELATIVE = Path("runtime") / "v7_rss_production" / "PHOENIX_RSS_PRODUCTION.bootstrap_manifest.txt"
BACKUP_RELATIVE = Path("backup") / "v7_rss_bootstrap" / "PHOENIX_RSS_PRODUCTION.bootstrap_backup.xlsm"
SOURCE_RELATIVE = {
    "PHOENIX_RSS_ORDER_BRIDGE": Path("vba") / "PHOENIX_RSS_ORDER_BRIDGE.bas",
    "ThisWorkbook": Path("vba") / "ThisWorkbook.cls",
}
MANIFEST_SCHEMA_VERSION = 1
GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
FILE_SHARE_NONE = 0
OPEN_EXISTING = 3
FILE_ATTRIBUTE_NORMAL = 0x80
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value


class BootstrapPreparationError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class BootstrapPreparationResult:
    root_dir: Path
    workbook_path: Path
    backup_path: Path
    manifest_path: Path
    workbook_sha256: str
    backup_sha256: str
    source_hashes: dict[str, str]
    reused_backup: bool
    reused_manifest: bool


def _normalize_path(path: Path) -> str:
    return path.resolve().as_posix()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def _extract_vba_code_body(text: str) -> str:
    lines = [line.rstrip() for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    start_index: int | None = None

    for index, line in enumerate(lines):
        token = line.strip()
        if not token:
            continue
        if token.startswith("Attribute "):
            continue
        if token.startswith("VERSION ") or token in {"BEGIN", "END"}:
            continue
        start_index = index
        break

    if start_index is None:
        return ""

    body_lines: list[str] = []
    for line in lines[start_index:]:
        token = line.strip()
        if token.startswith("Attribute "):
            continue
        if token.startswith("VERSION ") or token in {"BEGIN", "END"}:
            continue
        body_lines.append(line)
    return "\n".join(body_lines).strip()


def _assert_contains(text: str, needle: str, context: str) -> None:
    if needle not in text:
        raise BootstrapPreparationError(f"Missing required marker in {context}: {needle}")


def _assert_not_contains(text: str, needle: str, context: str) -> None:
    if needle in text:
        raise BootstrapPreparationError(f"Forbidden marker found in {context}: {needle}")


def _read_source_bodies(root_dir: Path) -> dict[str, str]:
    source_bodies: dict[str, str] = {}
    for component_name, relative_path in SOURCE_RELATIVE.items():
        path = root_dir / relative_path
        if not path.is_file():
            raise BootstrapPreparationError(f"Missing VBA source file: {path}")
        source_bodies[component_name] = _extract_vba_code_body(_read_text(path))
    return source_bodies


def _source_hashes(root_dir: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for component_name, relative_path in SOURCE_RELATIVE.items():
        path = root_dir / relative_path
        if not path.is_file():
            raise BootstrapPreparationError(f"Missing VBA source file: {path}")
        hashes[component_name] = _sha256_file(path)
    return hashes


def _validate_source_contracts(source_bodies: dict[str, str]) -> None:
    bridge_body = source_bodies["PHOENIX_RSS_ORDER_BRIDGE"]
    workbook_body = source_bodies["ThisWorkbook"]

    _assert_contains(bridge_body, "Public Sub RunPhoenixRssOrderBridgeConsumer()", "bridge source")
    _assert_contains(bridge_body, "Public Sub StartPhoenixRssOrderBridgeScheduler()", "bridge source")
    _assert_contains(bridge_body, "Public Sub StopPhoenixRssOrderBridgeScheduler()", "bridge source")
    _assert_contains(bridge_body, "Private Const OBR_BRIDGE_ARMED As Boolean = False", "bridge source")
    _assert_contains(bridge_body, "OBR_ReadBridgeReadyState readyState", "bridge source")
    _assert_contains(bridge_body, "If Not readyState.Ready Then GoTo CleanExit", "bridge source")
    _assert_contains(bridge_body, "Application.OnTime", "bridge source")
    _assert_contains(bridge_body, "Schedule:=True", "bridge source")
    _assert_contains(bridge_body, "Schedule:=False", "bridge source")
    _assert_not_contains(bridge_body, "RssStockOrder_V(", "bridge source")
    _assert_not_contains(bridge_body, "RssCancelOrder_V(", "bridge source")

    _assert_contains(workbook_body, "Private Sub Workbook_Open()", "ThisWorkbook source")
    _assert_contains(workbook_body, "Private Sub Workbook_BeforeClose(Cancel As Boolean)", "ThisWorkbook source")
    _assert_contains(workbook_body, "StartPhoenixStep44ReceiverScheduler", "ThisWorkbook source")
    _assert_contains(workbook_body, "StopPhoenixStep44ReceiverScheduler", "ThisWorkbook source")
    _assert_contains(workbook_body, "StartPhoenixRssOrderBridgeScheduler", "ThisWorkbook source")
    _assert_contains(workbook_body, "StopPhoenixRssOrderBridgeScheduler", "ThisWorkbook source")


def _assert_workbook_unlocked(workbook_path: Path) -> None:
    _assert_exclusive_access(workbook_path)


def _assert_exclusive_access(workbook_path: Path) -> None:
    if os.name != "nt":
        raise BootstrapPreparationError("Workbook lock preflight is only supported on Windows")

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateFileW.argtypes = [
        ctypes.c_wchar_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_void_p,
    ]
    kernel32.CreateFileW.restype = ctypes.c_void_p
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel32.CloseHandle.restype = ctypes.c_int

    handle = kernel32.CreateFileW(
        str(workbook_path),
        GENERIC_READ | GENERIC_WRITE,
        FILE_SHARE_NONE,
        None,
        OPEN_EXISTING,
        FILE_ATTRIBUTE_NORMAL,
        None,
    )
    handle_value = int(getattr(handle, "value", handle) or 0)
    if handle_value in (0, INVALID_HANDLE_VALUE):
        error = ctypes.get_last_error()
        raise BootstrapPreparationError(f"Production workbook is locked or unavailable: {error}")

    try:
        if not kernel32.CloseHandle(handle):
            error = ctypes.get_last_error()
            raise BootstrapPreparationError(f"Could not release workbook probe handle: {error}")
    except Exception:
        raise


def _manifest_path(root_dir: Path) -> Path:
    return root_dir / MANIFEST_RELATIVE


def _backup_path(root_dir: Path) -> Path:
    return root_dir / BACKUP_RELATIVE


def _render_manifest(
    *,
    root_dir: Path,
    workbook_path: Path,
    backup_path: Path,
    workbook_sha256: str,
    backup_sha256: str,
    source_hashes: dict[str, str],
    created_at: datetime,
) -> str:
    workbook_abs = workbook_path.resolve().as_posix()
    backup_abs = backup_path.resolve().as_posix()
    lines = [
        f"schema_version={MANIFEST_SCHEMA_VERSION}",
        f"workbook_name={workbook_path.name}",
        f"workbook_path={workbook_abs}",
        f"workbook_sha256={workbook_sha256}",
        f"backup_path={backup_abs}",
        f"backup_sha256={backup_sha256}",
        f"source_order_bridge_path={SOURCE_RELATIVE['PHOENIX_RSS_ORDER_BRIDGE'].as_posix()}",
        f"source_order_bridge_sha256={source_hashes['PHOENIX_RSS_ORDER_BRIDGE']}",
        f"source_thisworkbook_path={SOURCE_RELATIVE['ThisWorkbook'].as_posix()}",
        f"source_thisworkbook_sha256={source_hashes['ThisWorkbook']}",
        "bridge_armed=False",
        "real_order_calls=absent",
        f"created_at={created_at.isoformat(timespec='seconds')}",
    ]
    return "\n".join(lines) + "\n"


def _parse_manifest(text: str) -> dict[str, str]:
    manifest: dict[str, str] = {}
    for raw_line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise BootstrapPreparationError(f"Invalid manifest line: {raw_line!r}")
        key, value = line.split("=", 1)
        manifest[key.strip()] = value.strip()
    return manifest


def _validate_manifest(
    manifest: dict[str, str],
    *,
    root_dir: Path,
    workbook_path: Path,
    backup_path: Path,
    source_hashes: dict[str, str],
) -> None:
    workbook_abs = workbook_path.resolve().as_posix()
    backup_abs = backup_path.resolve().as_posix()
    expected = {
        "schema_version": str(MANIFEST_SCHEMA_VERSION),
        "workbook_name": workbook_path.name,
        "workbook_path": workbook_abs,
        "backup_path": backup_abs,
        "source_order_bridge_path": SOURCE_RELATIVE["PHOENIX_RSS_ORDER_BRIDGE"].as_posix(),
        "source_thisworkbook_path": SOURCE_RELATIVE["ThisWorkbook"].as_posix(),
        "bridge_armed": "False",
        "real_order_calls": "absent",
    }
    for key, value in expected.items():
        if manifest.get(key) != value:
            raise BootstrapPreparationError(f"Bootstrap manifest mismatch for {key}: {manifest.get(key)!r}")
    if manifest.get("workbook_sha256") != _sha256_file(workbook_path):
        raise BootstrapPreparationError("Bootstrap manifest workbook SHA-256 is stale or invalid")
    if manifest.get("backup_sha256") != _sha256_file(backup_path):
        raise BootstrapPreparationError("Bootstrap manifest backup SHA-256 is stale or invalid")
    if manifest.get("source_order_bridge_sha256") != source_hashes["PHOENIX_RSS_ORDER_BRIDGE"]:
        raise BootstrapPreparationError("Bootstrap manifest bridge source SHA-256 is stale or invalid")
    if manifest.get("source_thisworkbook_sha256") != source_hashes["ThisWorkbook"]:
        raise BootstrapPreparationError("Bootstrap manifest ThisWorkbook SHA-256 is stale or invalid")


def prepare_v7_rss_bootstrap(
    root_dir: Path = ROOT_DIR,
    *,
    timestamp_factory: Callable[[], datetime] | None = None,
) -> BootstrapPreparationResult:
    root_dir = root_dir.resolve()
    timestamp_factory = timestamp_factory or datetime.now

    workbook_path = root_dir / WORKBOOK_RELATIVE
    manifest_path = _manifest_path(root_dir)
    backup_path = _backup_path(root_dir)
    backup_existed = backup_path.is_file()

    if not workbook_path.is_file():
        raise BootstrapPreparationError(f"Production workbook not found: {workbook_path}")
    if not workbook_path.name == "PHOENIX_RSS_PRODUCTION.xlsm":
        raise BootstrapPreparationError(f"Unexpected production workbook name: {workbook_path.name}")

    _assert_workbook_unlocked(workbook_path)

    source_bodies = _read_source_bodies(root_dir)
    _validate_source_contracts(source_bodies)
    source_hashes = _source_hashes(root_dir)
    workbook_sha256 = _sha256_file(workbook_path)

    if manifest_path.is_file():
        existing_manifest = _parse_manifest(_read_text(manifest_path))
        _validate_manifest(
            existing_manifest,
            root_dir=root_dir,
            workbook_path=workbook_path,
            backup_path=backup_path,
            source_hashes=source_hashes,
        )
        if not backup_path.is_file():
            raise BootstrapPreparationError(f"Bootstrap backup is missing: {backup_path}")
        backup_sha256 = _sha256_file(backup_path)
        if backup_sha256 != workbook_sha256:
            raise BootstrapPreparationError("Bootstrap backup hash does not match the production workbook")
        return BootstrapPreparationResult(
            root_dir=root_dir,
            workbook_path=workbook_path,
            backup_path=backup_path,
            manifest_path=manifest_path,
            workbook_sha256=workbook_sha256,
            backup_sha256=backup_sha256,
            source_hashes=source_hashes,
            reused_backup=True,
            reused_manifest=True,
        )

    if backup_path.is_file():
        backup_sha256 = _sha256_file(backup_path)
        if backup_sha256 != workbook_sha256:
            raise BootstrapPreparationError(
                f"Existing bootstrap backup hash mismatch: expected {workbook_sha256}, got {backup_sha256}"
            )
    else:
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(workbook_path, backup_path)
        backup_sha256 = _sha256_file(backup_path)
        if backup_sha256 != workbook_sha256:
            raise BootstrapPreparationError("Backup hash mismatch after copy")

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_text = _render_manifest(
        root_dir=root_dir,
        workbook_path=workbook_path,
        backup_path=backup_path,
        workbook_sha256=workbook_sha256,
        backup_sha256=backup_sha256,
        source_hashes=source_hashes,
        created_at=timestamp_factory(),
    )
    manifest_path.write_text(manifest_text, encoding="utf-8")

    return BootstrapPreparationResult(
        root_dir=root_dir,
        workbook_path=workbook_path,
        backup_path=backup_path,
        manifest_path=manifest_path,
        workbook_sha256=workbook_sha256,
        backup_sha256=backup_sha256,
        source_hashes=source_hashes,
        reused_backup=backup_existed,
        reused_manifest=False,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prepare the PHOENIX VBA bootstrap deployment.")
    parser.add_argument(
        "--root",
        type=Path,
        default=ROOT_DIR,
        help="Repository root (defaults to the current repository).",
    )
    args = parser.parse_args(argv)

    try:
        result = prepare_v7_rss_bootstrap(args.root)
    except BootstrapPreparationError as exc:
        print("PRE_BOOTSTRAP_READY: NO")
        print(f"ERROR: {exc}")
        return 1

    print("PRE_BOOTSTRAP_READY: YES")
    print(f"WORKBOOK: {result.workbook_path}")
    print(f"BACKUP: {result.backup_path}")
    print(f"MANIFEST: {result.manifest_path}")
    print(f"REUSED_BACKUP: {'YES' if result.reused_backup else 'NO'}")
    print(f"REUSED_MANIFEST: {'YES' if result.reused_manifest else 'NO'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
