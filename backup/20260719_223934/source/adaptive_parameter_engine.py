from __future__ import annotations

from datetime import datetime
import csv
import json
import math
from pathlib import Path
import shutil
import sys
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent
REPORT_DIR = ROOT_DIR / "reports"
OPTIMIZATION_CANDIDATE_FILE = REPORT_DIR / "optimization_candidate.json"
OPTIMIZATION_BEST_FILE = REPORT_DIR / "optimization_best.json"
WALK_FORWARD_FILE = REPORT_DIR / "walk_forward_summary.json"
ACTIVE_PARAMETER_FILE = REPORT_DIR / "ai_parameter.json"
ADAPTIVE_PARAMETER_FILE = REPORT_DIR / "adaptive_parameter.json"
ADAPTIVE_HISTORY_FILE = REPORT_DIR / "adaptive_history.csv"
ADAPTIVE_REPORT_FILE = REPORT_DIR / "adaptive_report.txt"

PARAMETER_KEYS = (
    "rsi_min", "rsi_max", "stop_atr_multiplier", "target_r_multiplier",
    "ma_short", "ma_mid", "ma_long", "signal_score_threshold", "max_hold_days",
)


def configure_console() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_json_atomic(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    temp.replace(path)


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
        return number if math.isfinite(number) else default
    except (TypeError, ValueError):
        return default


def candidate_parameters(candidate: dict[str, Any]) -> dict[str, Any]:
    params = candidate.get("parameters", {})
    if not isinstance(params, dict):
        params = {}
    return {key: params.get(key) for key in PARAMETER_KEYS if key in params}


def calculate_confidence(walk: dict[str, Any]) -> float:
    success = min(max(safe_float(walk.get("success_rate_pct")), 0.0), 100.0)
    pf = min(max(safe_float(walk.get("average_profit_factor")), 0.0), 2.0) / 2.0 * 100.0
    sharpe = min(max(safe_float(walk.get("average_sharpe_ratio")), 0.0), 1.5) / 1.5 * 100.0
    dd = max(0.0, 100.0 - min(safe_float(walk.get("average_max_drawdown_pct")), 30.0) / 30.0 * 100.0)
    return round(success * 0.40 + pf * 0.25 + sharpe * 0.20 + dd * 0.15, 2)


def append_history(summary: dict[str, Any]) -> None:
    exists = ADAPTIVE_HISTORY_FILE.exists()
    fields = [
        "generated_at", "decision", "walk_forward_status", "action", "confidence",
        "average_profit_factor", "average_sharpe_ratio", "average_max_drawdown_pct",
        "success_rate_pct", "reason",
    ]
    ADAPTIVE_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    with ADAPTIVE_HISTORY_FILE.open("a", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        if not exists:
            writer.writeheader()
        writer.writerow({key: summary.get(key, "") for key in fields})


def build_active_payload(parameters: dict[str, Any], candidate: dict[str, Any], walk: dict[str, Any], confidence: float) -> dict[str, Any]:
    payload = load_json(ACTIVE_PARAMETER_FILE)
    payload.update(parameters)
    payload.update({
        "version": "PHOENIX v6.2",
        "updated_at": now_text(),
        "source": "adaptive_parameter_engine",
        "adaptive_status": "ACTIVE",
        "adaptive_confidence": confidence,
        "optimization": {
            "parameters": parameters,
            "performance": candidate.get("performance", {}),
            "period": candidate.get("period", ""),
            "tested_combinations": candidate.get("tested_combinations", 0),
        },
        "walk_forward": walk,
    })
    return payload


def run() -> dict[str, Any]:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    candidate = load_json(OPTIMIZATION_CANDIDATE_FILE)
    if not candidate:
        best = load_json(OPTIMIZATION_BEST_FILE)
        if best:
            candidate = {
                "parameters": best.get("parameters", {}),
                "performance": best.get("performance", {}),
                "period": best.get("period", ""),
                "tested_combinations": best.get("tested_combinations", 0),
            }
    walk = load_json(WALK_FORWARD_FILE)
    if not candidate:
        raise FileNotFoundError("最適化候補がありません。optimization_engine.pyを先に実行してください。")
    if not walk:
        raise FileNotFoundError("Walk-Forward結果がありません。walk_forward_engine.pyを先に実行してください。")

    status = str(walk.get("status", "FAIL")).upper()
    confidence = calculate_confidence(walk)
    parameters = candidate_parameters(candidate)
    previous = load_json(ACTIVE_PARAMETER_FILE)
    previous_available = all(key in previous for key in PARAMETER_KEYS)

    if status == "PASS" and len(parameters) == len(PARAMETER_KEYS):
        action = "UPDATED"
        decision = "PASS"
        reason = "Walk-Forward PASSのため候補パラメータを採用"
        active = build_active_payload(parameters, candidate, walk, confidence)
        if ACTIVE_PARAMETER_FILE.exists():
            shutil.copy2(ACTIVE_PARAMETER_FILE, REPORT_DIR / "ai_parameter_previous.json")
        save_json_atomic(ACTIVE_PARAMETER_FILE, active)
    elif previous_available:
        action = "KEPT_PREVIOUS"
        decision = "FAIL"
        reason = "Walk-Forward FAILのため前回パラメータを維持"
        active = previous
    else:
        action = "BOOTSTRAP"
        decision = "CAUTION"
        reason = "前回パラメータがないため候補を初期値として保存。実運用は禁止"
        active = build_active_payload(parameters, candidate, walk, confidence)
        active["adaptive_status"] = "BOOTSTRAP_CAUTION"
        save_json_atomic(ACTIVE_PARAMETER_FILE, active)

    summary = {
        "version": "PHOENIX v6.2",
        "generated_at": now_text(),
        "decision": decision,
        "walk_forward_status": status,
        "action": action,
        "confidence": confidence,
        "reason": reason,
        "active_parameters": {key: active.get(key) for key in PARAMETER_KEYS},
        "candidate_parameters": parameters,
        "average_profit_factor": safe_float(walk.get("average_profit_factor")),
        "average_sharpe_ratio": safe_float(walk.get("average_sharpe_ratio")),
        "average_max_drawdown_pct": safe_float(walk.get("average_max_drawdown_pct")),
        "success_rate_pct": safe_float(walk.get("success_rate_pct")),
    }
    save_json_atomic(ADAPTIVE_PARAMETER_FILE, summary)
    append_history(summary)
    lines = [
        "PHOENIX v6.2 ADAPTIVE PARAMETER REPORT", "=" * 110,
        f"生成時刻       : {summary['generated_at']}",
        f"判定           : {decision}", f"処理           : {action}",
        f"Walk Forward   : {status}", f"信頼度         : {confidence:.2f}%",
        f"理由           : {reason}", "", "ACTIVE PARAMETERS", "=" * 110,
    ]
    for key in PARAMETER_KEYS:
        lines.append(f"{key:<24}: {summary['active_parameters'].get(key)}")
    ADAPTIVE_REPORT_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return summary


def main() -> None:
    configure_console()
    try:
        summary = run()
        print("=" * 110)
        print("PHOENIX v6.2 ADAPTIVE PARAMETER ENGINE")
        print("=" * 110)
        print(f"判定           : {summary['decision']}")
        print(f"処理           : {summary['action']}")
        print(f"Walk Forward   : {summary['walk_forward_status']}")
        print(f"信頼度         : {summary['confidence']:.2f}%")
        print(f"理由           : {summary['reason']}")
        print(f"保存完了       : {ADAPTIVE_PARAMETER_FILE}")
        print(f"履歴保存       : {ADAPTIVE_HISTORY_FILE}")
    except Exception as error:
        print(f"Adaptive Parameter Engineエラー: {error}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
