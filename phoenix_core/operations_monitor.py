from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Callable, Mapping
from urllib import error as urllib_error
from urllib import request as urllib_request


PostCallable = Callable[..., Any]


class HttpStatusResponse:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


def default_post(url: str, **kwargs: Any) -> HttpStatusResponse:
    payload = kwargs.get("json", {})
    timeout = int(kwargs.get("timeout", 15))
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib_request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib_request.urlopen(request, timeout=timeout) as response:
            return HttpStatusResponse(int(response.status))
    except urllib_error.HTTPError as error:
        return HttpStatusResponse(int(error.code))


def resolve_path(root: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def load_json_object(path: Path) -> tuple[dict[str, Any], str | None]:
    if not path.is_file():
        return {}, "file_not_found"
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        return {}, f"{type(error).__name__}: {error}"
    if not isinstance(payload, dict):
        return {}, "JSON root is not an object"
    return payload, None


def add_alert(
    alerts: list[dict[str, str]],
    level: str,
    code: str,
    message: str,
) -> None:
    alerts.append({"level": level, "code": code, "message": message})


def report_status(alerts: list[dict[str, str]]) -> str:
    levels = {alert["level"] for alert in alerts}
    if levels & {"CRITICAL", "ERROR"}:
        return "FAILED"
    if "WARNING" in levels:
        return "WARNING"
    return "SUCCESS"


def build_operations_report(
    root: Path,
    config: Mapping[str, Any],
    return_code: int,
    log_path: Path,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    generated_at = generated_at or datetime.now()
    files = config.get("files", {})
    scheduler = config.get("scheduler", {})
    operations = config.get("operations", {})

    scheduler_state_path = resolve_path(
        root,
        str(files.get("scheduler_state", "state/v7_scheduler_state.json")),
    )
    pipeline_summary_path = resolve_path(
        root,
        str(
            operations.get(
                "pipeline_summary",
                "reports/v7_direct_pipeline_summary.json",
            )
        ),
    )

    alerts: list[dict[str, str]] = []
    if return_code != 0:
        add_alert(
            alerts,
            "CRITICAL",
            "PIPELINE_FAILED",
            f"Scheduled pipeline returned {return_code}",
        )

    log_exists = log_path.is_file()
    log_size = log_path.stat().st_size if log_exists else 0
    if not log_exists:
        add_alert(alerts, "WARNING", "LOG_MISSING", f"Log not found: {log_path}")
    elif log_size <= 0:
        add_alert(alerts, "WARNING", "LOG_EMPTY", f"Log is empty: {log_path}")

    pipeline_summary, pipeline_error = load_json_object(pipeline_summary_path)
    if pipeline_error:
        add_alert(
            alerts,
            "WARNING" if return_code == 0 else "ERROR",
            "PIPELINE_SUMMARY_UNAVAILABLE",
            f"{pipeline_summary_path}: {pipeline_error}",
        )
    elif bool(pipeline_summary.get("halted", False)):
        add_alert(
            alerts,
            "CRITICAL",
            "RISK_HALTED",
            str(pipeline_summary.get("halt_reason", "Risk controller halted the pipeline")),
        )

    dry_run = bool(scheduler.get("dry_run", False))
    if pipeline_summary and not dry_run:
        approved = int(pipeline_summary.get("approved_count", 0) or 0)
        filled = int(pipeline_summary.get("filled_count", 0) or 0)
        if approved > filled:
            add_alert(
                alerts,
                "WARNING",
                "UNFILLED_APPROVED_ORDERS",
                f"Approved {approved}, filled {filled}",
            )

    scheduler_state, scheduler_error = load_json_object(scheduler_state_path)
    if scheduler_error:
        add_alert(
            alerts,
            "WARNING",
            "SCHEDULER_STATE_UNAVAILABLE",
            f"{scheduler_state_path}: {scheduler_error}",
        )

    return {
        "schema_version": 1,
        "version": "PHOENIX v7 Step9",
        "generated_at": generated_at.isoformat(timespec="seconds"),
        "status": report_status(alerts),
        "return_code": int(return_code),
        "dry_run": dry_run,
        "log": {
            "path": str(log_path),
            "exists": log_exists,
            "size_bytes": log_size,
        },
        "pipeline": {
            "summary_path": str(pipeline_summary_path),
            "summary_available": pipeline_error is None,
            "candidate_count": int(pipeline_summary.get("candidate_count", 0) or 0),
            "ready_count": int(pipeline_summary.get("ready_count", 0) or 0),
            "approved_count": int(pipeline_summary.get("approved_count", 0) or 0),
            "filled_count": int(pipeline_summary.get("filled_count", 0) or 0),
            "halted": bool(pipeline_summary.get("halted", False)),
            "halt_reason": str(pipeline_summary.get("halt_reason", "") or ""),
        },
        "scheduler": {
            "state_path": str(scheduler_state_path),
            "state_available": scheduler_error is None,
            "last_success_at": scheduler_state.get("last_success_at"),
            "last_failure_at": scheduler_state.get("last_failure_at"),
            "last_return_code": scheduler_state.get("last_return_code"),
        },
        "alerts": alerts,
        "notification": {
            "enabled": False,
            "attempted": False,
            "success": None,
            "message": "Not evaluated",
        },
    }


def notification_message(report: Mapping[str, Any]) -> str:
    pipeline = report.get("pipeline", {})
    alerts = report.get("alerts", [])
    lines = [
        f"PHOENIX v7 Step9: {report.get('status', 'UNKNOWN')}",
        f"Time: {report.get('generated_at', '')}",
        f"Return code: {report.get('return_code', '')}",
        (
            "Pipeline: "
            f"candidates={pipeline.get('candidate_count', 0)}, "
            f"approved={pipeline.get('approved_count', 0)}, "
            f"filled={pipeline.get('filled_count', 0)}"
        ),
        f"Risk halted: {pipeline.get('halted', False)}",
    ]
    if alerts:
        lines.append("Alerts:")
        for alert in alerts[:10]:
            lines.append(
                f"- [{alert.get('level', '')}] "
                f"{alert.get('code', '')}: {alert.get('message', '')}"
            )
    return "\n".join(lines)[:1900]


def send_discord_notification(
    report: Mapping[str, Any],
    notification_config: Mapping[str, Any],
    environment: Mapping[str, str] | None = None,
    post: PostCallable = default_post,
) -> dict[str, Any]:
    enabled = bool(notification_config.get("enabled", False))
    result: dict[str, Any] = {
        "enabled": enabled,
        "attempted": False,
        "success": None,
        "message": "Notification disabled",
    }
    if not enabled:
        return result

    status = str(report.get("status", "UNKNOWN"))
    notify_on_success = bool(notification_config.get("notify_on_success", False))
    notify_on_failure = bool(notification_config.get("notify_on_failure", True))
    should_notify = notify_on_success if status == "SUCCESS" else notify_on_failure
    if not should_notify:
        result["message"] = f"Notification skipped for status {status}"
        return result

    environment = environment or os.environ
    webhook_env = str(
        notification_config.get("webhook_env", "PHOENIX_V7_DISCORD_WEBHOOK_URL")
    )
    webhook_url = str(environment.get(webhook_env, "")).strip()
    if not webhook_url:
        result.update(
            {
                "success": False,
                "message": f"Environment variable is not set: {webhook_env}",
            }
        )
        return result

    result["attempted"] = True
    timeout = max(1, int(notification_config.get("timeout_seconds", 15)))
    payload = {
        "username": "PHOENIX v7",
        "content": notification_message(report),
        "allowed_mentions": {"parse": []},
    }
    try:
        response = post(webhook_url, json=payload, timeout=timeout)
    except (OSError, TimeoutError) as error:
        result.update(
            {"success": False, "message": f"Discord request failed: {error}"}
        )
        return result

    if response.status_code in {200, 204}:
        result.update({"success": True, "message": "Discord notification sent"})
    else:
        result.update(
            {
                "success": False,
                "message": f"Discord returned HTTP {response.status_code}",
            }
        )
    return result


def atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as file:
            file.write(content)
            file.flush()
            os.fsync(file.fileno())
            temporary_path = Path(file.name)
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            try:
                temporary_path.unlink()
            except OSError:
                pass


def text_report(report: Mapping[str, Any]) -> str:
    pipeline = report.get("pipeline", {})
    notification = report.get("notification", {})
    lines = [
        "PHOENIX v7 STEP9 OPERATIONS REPORT",
        "=" * 80,
        f"Generated       : {report.get('generated_at', '')}",
        f"Status          : {report.get('status', '')}",
        f"Return code     : {report.get('return_code', '')}",
        f"Dry run         : {report.get('dry_run', False)}",
        f"Candidates      : {pipeline.get('candidate_count', 0)}",
        f"Ready           : {pipeline.get('ready_count', 0)}",
        f"Approved        : {pipeline.get('approved_count', 0)}",
        f"Filled          : {pipeline.get('filled_count', 0)}",
        f"Risk halted     : {pipeline.get('halted', False)}",
        f"Notification    : {notification.get('message', '')}",
        "-" * 80,
    ]
    alerts = report.get("alerts", [])
    if not alerts:
        lines.append("No alerts")
    else:
        for alert in alerts:
            lines.append(
                f"{alert.get('level', ''):<8} "
                f"{alert.get('code', ''):<32} "
                f"{alert.get('message', '')}"
            )
    lines.append("=" * 80)
    return "\n".join(lines) + "\n"


def save_operations_report(
    root: Path,
    config: Mapping[str, Any],
    report: Mapping[str, Any],
) -> tuple[Path, Path]:
    operations = config.get("operations", {})
    json_path = resolve_path(
        root,
        str(operations.get("report_json", "reports/v7_operations_report.json")),
    )
    text_path = resolve_path(
        root,
        str(operations.get("report_text", "reports/v7_operations_report.txt")),
    )
    atomic_write_text(
        json_path,
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
    )
    atomic_write_text(text_path, text_report(report))
    return json_path, text_path


def run_operations_monitor(
    root: Path,
    config: Mapping[str, Any],
    return_code: int,
    log_path: Path,
    environment: Mapping[str, str] | None = None,
    post: PostCallable = default_post,
) -> dict[str, Any]:
    report = build_operations_report(root, config, return_code, log_path)
    operations = config.get("operations", {})
    notification_config = operations.get("notification", {})
    notification = send_discord_notification(
        report,
        notification_config,
        environment=environment,
        post=post,
    )
    report["notification"] = notification
    if notification.get("enabled") and notification.get("success") is False:
        add_alert(
            report["alerts"],
            "WARNING",
            "NOTIFICATION_FAILED",
            str(notification.get("message", "Notification failed")),
        )
        report["status"] = report_status(report["alerts"])
    json_path, text_path = save_operations_report(root, config, report)
    report["report_json"] = str(json_path)
    report["report_text"] = str(text_path)
    return report


def print_operations_summary(report: Mapping[str, Any]) -> None:
    pipeline = report.get("pipeline", {})
    print("=" * 80)
    print("PHOENIX v7 STEP9 OPERATIONS MONITOR")
    print("=" * 80)
    print(f"Status       : {report.get('status', '')}")
    print(f"Return code  : {report.get('return_code', '')}")
    print(f"Approved     : {pipeline.get('approved_count', 0)}")
    print(f"Filled       : {pipeline.get('filled_count', 0)}")
    print(f"Risk halted  : {pipeline.get('halted', False)}")
    print(f"Alerts       : {len(report.get('alerts', []))}")
    print(f"Report       : {report.get('report_json', '')}")
    print(f"Notification : {report.get('notification', {}).get('message', '')}")
    print("=" * 80)
