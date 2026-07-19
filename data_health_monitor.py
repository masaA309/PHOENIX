from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from execution_core import REPORT_DIR, ROOT_DIR, bootstrap_environment, load_json, now_text, save_json
from realtime_gateway import RealtimeGateway

SUMMARY_FILE = REPORT_DIR / "data_health_summary.json"
REPORT_FILE = REPORT_DIR / "data_health_report.txt"


def _heartbeat_age(path: Path) -> float | None:
    data = load_json(path)
    text = str(data.get("timestamp", "")).strip()
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return max(0.0, (datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).total_seconds())
    except ValueError:
        return None


def main() -> None:
    boot = bootstrap_environment()
    config = boot["config"]
    gateway = RealtimeGateway()
    quotes = gateway.load_quotes()
    heartbeat_path = ROOT_DIR / str(config["rss_heartbeat_file"])
    heartbeat_age = _heartbeat_age(heartbeat_path)
    heartbeat_ok = heartbeat_age is not None and heartbeat_age <= float(config["rss_heartbeat_max_age_seconds"])

    checks: list[dict[str, Any]] = [
        {"name": "RSS heartbeat", "ok": heartbeat_ok, "detail": f"age={heartbeat_age}"},
        {"name": "RSS quote file", "ok": not quotes.empty, "detail": f"rows={len(quotes)} file={gateway.quote_file}"},
        {"name": "Analysis cache", "ok": (ROOT_DIR / "data" / "cache").exists(), "detail": "キャッシュディレクトリ確認"},
    ]
    mode = str(config.get("mode", "DRY_RUN")).upper()
    live_ready = heartbeat_ok and not quotes.empty
    summary = {
        "version": "PHOENIX v6.6", "generated_at": now_text(), "mode": mode,
        "live_data_ready": live_ready, "checks": checks,
    }
    save_json(SUMMARY_FILE, summary)
    REPORT_FILE.write_text("\n".join([
        "PHOENIX v6.6 DATA HEALTH MONITOR", "=" * 100,
        f"生成時刻: {summary['generated_at']}", f"モード: {mode}",
        f"LIVEデータ準備: {live_ready}", "",
        *[f"{'OK' if c['ok'] else 'NG'} {c['name']}: {c['detail']}" for c in checks], ""
    ]), encoding="utf-8")
    print("=" * 100)
    print("PHOENIX v6.6 DATA HEALTH MONITOR")
    print("=" * 100)
    print(f"LIVEデータ準備: {live_ready}")
    for check in checks:
        print(f"{'OK' if check['ok'] else 'NG':<3} {check['name']}: {check['detail']}")
    if mode == "LIVE" and not live_ready:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
