from __future__ import annotations

from datetime import datetime
from pathlib import Path
import json
import math
import sys
from typing import Any

import pandas as pd

from execution_core import bootstrap_environment

ROOT_DIR = Path(__file__).resolve().parent
REPORT_DIR = ROOT_DIR / "reports"
CONFIG_FILE = ROOT_DIR / "config" / "execution_config.json"
POSITION_PLAN_FILE = REPORT_DIR / "position_plan.csv"
RISK_SUMMARY_FILE = REPORT_DIR / "risk_controller_summary.json"
OUTPUT_FILE = REPORT_DIR / "execution_candidates.csv"
SUMMARY_FILE = REPORT_DIR / "execution_ai_summary.json"
REPORT_FILE = REPORT_DIR / "execution_ai_report.txt"


def configure_console() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or pd.isna(value):
            return default
        number = float(value)
        return number if math.isfinite(number) else default
    except (TypeError, ValueError):
        return default


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    for encoding in ("utf-8-sig", "utf-8", "cp932"):
        try:
            return pd.read_csv(path, encoding=encoding)
        except Exception:
            continue
    return pd.DataFrame()


def save_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    configure_console()
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    config = bootstrap_environment()["config"]
    risk = load_json(RISK_SUMMARY_FILE)
    plan = read_csv(POSITION_PLAN_FILE)
    if plan.empty:
        raise FileNotFoundError(f"ポジション計画がありません: {POSITION_PLAN_FILE}")

    adopted = plan[plan["Position判定"].astype(str).eq("採用")].copy() if "Position判定" in plan.columns else plan.copy()
    minimum_unit = int(safe_float(config.get("minimum_rss_trade_unit", 100), 100))
    max_position = safe_float(config.get("maximum_position_value_yen", 100000), 100000)
    max_trades = int(safe_float(config.get("maximum_daily_trades", 1), 1))
    risk_allowed = bool(risk.get("allowed", False))
    allow_kabumini = bool(config.get("allow_kabumini_auto_execution", False))

    rows: list[dict[str, Any]] = []
    for _, row in adopted.iterrows():
        shares = int(safe_float(row.get("株数", 0)))
        entry = safe_float(row.get("エントリー価格", 0))
        target = safe_float(row.get("利確価格", 0))
        stop = safe_float(row.get("損切価格", 0))
        service = str(row.get("取引サービス", ""))
        score = safe_float(row.get("OptimizerScore", row.get("PortfolioScore", row.get("AI判断点", 0))))
        rss_shares = shares if shares >= minimum_unit and shares % minimum_unit == 0 else 0
        order_value = rss_shares * entry

        decision = "READY"
        reason = "RSS現物指値条件クリア"
        if not risk_allowed:
            decision, reason = "BLOCK", "Risk ControllerがBLOCK"
        elif service == "かぶミニ" and not allow_kabumini:
            decision, reason = "MANUAL_ONLY", "かぶミニはRSS自動執行対象外"
        elif rss_shares == 0:
            decision, reason = "MANUAL_ONLY", f"RSS単元{minimum_unit}株を満たさない"
        elif order_value > max_position:
            decision, reason = "BLOCK", "1銘柄の注文金額上限超過"
        elif not (entry > 0 and target > entry and 0 < stop < entry):
            decision, reason = "BLOCK", "価格条件が不正"

        rows.append({
            "generated_at": now_text(),
            "銘柄": str(row.get("銘柄", "")),
            "ticker": str(row.get("ticker", "")),
            "side": "BUY",
            "order_type": "LIMIT",
            "shares_original": shares,
            "shares_rss": rss_shares,
            "entry_price": round(entry, 2),
            "take_profit_price": round(target, 2),
            "stop_loss_price": round(stop, 2),
            "order_value_yen": round(order_value, 2),
            "execution_score": round(score, 3),
            "execution_decision": decision,
            "reason": reason,
        })

    output = pd.DataFrame(rows)
    if not output.empty:
        output = output.sort_values(["execution_decision", "execution_score"], ascending=[True, False])
        ready_indices = output.index[output["execution_decision"].eq("READY")].tolist()
        for index in ready_indices[max_trades:]:
            output.at[index, "execution_decision"] = "BLOCK"
            output.at[index, "reason"] = "1日最大注文数超過"
    output.to_csv(OUTPUT_FILE, index=False, encoding="utf-8-sig")

    counts = output["execution_decision"].value_counts().to_dict() if not output.empty else {}
    summary = {
        "version": "PHOENIX v6.5.1",
        "generated_at": now_text(),
        "mode": str(config.get("mode", "DRY_RUN")),
        "targets": len(output),
        "ready": int(counts.get("READY", 0)),
        "manual_only": int(counts.get("MANUAL_ONLY", 0)),
        "blocked": int(counts.get("BLOCK", 0)),
        "minimum_rss_trade_unit": minimum_unit,
    }
    save_json(SUMMARY_FILE, summary)
    REPORT_FILE.write_text(
        "\n".join([
            "PHOENIX v6.5.1 EXECUTION AI",
            "=" * 100,
            f"生成時刻: {summary['generated_at']}",
            f"モード: {summary['mode']}",
            f"対象: {summary['targets']}件",
            f"RSS発注可能: {summary['ready']}件",
            f"手動のみ: {summary['manual_only']}件",
            f"停止: {summary['blocked']}件",
            "",
            output.to_string(index=False),
            "",
        ]),
        encoding="utf-8",
    )

    print("=" * 100)
    print("PHOENIX v6.5.1 EXECUTION AI")
    print("=" * 100)
    print(f"RSS発注可能 : {summary['ready']}件")
    print(f"手動のみ    : {summary['manual_only']}件")
    print(f"停止        : {summary['blocked']}件")


if __name__ == "__main__":
    main()
