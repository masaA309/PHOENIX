from __future__ import annotations

from pathlib import Path
import py_compile
from typing import Any

from execution_core import ROOT_DIR, REPORT_DIR, bootstrap_environment, configure_console, now_text, save_json, validate_execution_config

SUMMARY_FILE = REPORT_DIR / "system_auditor_summary.json"
REPORT_FILE = REPORT_DIR / "system_auditor_report.txt"
REQUIRED_EXECUTION_FILES = [
    "execution_core.py", "market_data_gateway.py", "realtime_gateway.py", "data_health_monitor.py",
    "risk_controller.py", "execution_ai.py", "order_manager.py", "broker_gateway.py", "phoenix.py",
]


def main() -> None:
    configure_console(); boot = bootstrap_environment(); config = boot["config"]
    checks: list[dict[str, Any]] = []
    def add(name: str, ok: bool, detail: str) -> None: checks.append({"name": name, "ok": bool(ok), "detail": detail})

    for filename in REQUIRED_EXECUTION_FILES:
        path = ROOT_DIR / filename
        add(f"ファイル:{filename}", path.exists(), "存在" if path.exists() else "不足")
        if path.exists():
            try:
                py_compile.compile(str(path), doraise=True)
                add(f"構文:{filename}", True, "py_compile OK")
            except py_compile.PyCompileError as error:
                add(f"構文:{filename}", False, str(error))

    errors = validate_execution_config(config)
    add("設定スキーマ", not errors, "正常" if not errors else " / ".join(errors))
    add("DRY_RUN安全性", str(config.get("mode", "DRY_RUN")).upper() != "DRY_RUN" or not bool(config.get("live_trading", False)), "DRY_RUNでは実売買無効")
    roles = {str(member.get("role")) for member in boot.get("team", {}).get("members", [])}
    required_roles = {"プロトレーダー", "プロコーダー", "デバッカー", "QAテスター", "データエンジニア"}
    add("プロチーム定義", required_roles.issubset(roles), f"登録役割={sorted(roles)}")
    add("RSS価格設定", bool(config.get("rss_quote_file")) and float(config.get("rss_quote_max_age_seconds", 0)) > 0, "リアルタイム価格鮮度を強制")
    add("Yahoo過剰アクセス対策", bool(config.get("analysis_reuse_today_cache", False)) and int(config.get("yahoo_max_attempts", 0)) <= 3, "当日キャッシュ・Circuit Breaker有効")

    passed = all(item["ok"] for item in checks)
    summary = {"version": "PHOENIX v6.6", "generated_at": now_text(), "status": "PASS" if passed else "FAIL", "passed": passed, "checks": checks}
    save_json(SUMMARY_FILE, summary)
    REPORT_FILE.write_text("\n".join(["PHOENIX v6.6 PROFESSIONAL CODER / DEBUGGER / QA AUDIT", "="*110,
        f"生成時刻: {summary['generated_at']}", f"判定: {summary['status']}", "",
        *[f"{'OK' if c['ok'] else 'ERROR':<7} {c['name']}: {c['detail']}" for c in checks], ""]), encoding="utf-8")
    print("="*110); print("PHOENIX v6.6 PROFESSIONAL CODER / DEBUGGER / QA"); print("="*110); print(f"監査判定 : {summary['status']}")
    if not passed:
        for item in checks:
            if not item["ok"]: print(f"ERROR {item['name']}: {item['detail']}")
        raise SystemExit(1)


if __name__ == "__main__": main()
