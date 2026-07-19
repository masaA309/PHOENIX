from __future__ import annotations

from datetime import datetime
from pathlib import Path
import json
import math
import sys
from typing import Any

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent
CONFIG_DIR = ROOT_DIR / "config"
REPORT_DIR = ROOT_DIR / "reports"
EXECUTION_DIR = ROOT_DIR / "execution"
STATE_DIR = ROOT_DIR / "state"
LOG_DIR = ROOT_DIR / "logs"
CONFIG_FILE = CONFIG_DIR / "execution_config.json"
TEAM_FILE = CONFIG_DIR / "professional_team.json"

DEFAULT_EXECUTION_CONFIG: dict[str, Any] = {
    "version": "PHOENIX v6.5.1",
    "broker": "楽天証券",
    "gateway": "MarketSpeed II RSS CSV Bridge",
    "mode": "DRY_RUN",
    "live_trading": False,
    "live_unlock_phrase": "",
    "account_capital_yen": 300000,
    "account_type": "特定",
    "allow_margin": False,
    "allow_market_order": False,
    "allow_kabumini_auto_execution": False,
    "minimum_rss_trade_unit": 100,
    "maximum_daily_trades": 1,
    "maximum_daily_loss_yen": 1500,
    "maximum_position_value_yen": 100000,
    "maximum_total_exposure_percent": 30.0,
    "maximum_order_age_minutes": 15,
    "maximum_signal_age_minutes": 180,
    "entry_price_tolerance_percent": 1.0,
    "cancel_unfilled_after_minutes": 15,
    "use_settlement_orders": True,
    "emergency_stop_file": "EMERGENCY_STOP",
    "rss_heartbeat_file": "state/rss_bridge_heartbeat.json",
    "rss_heartbeat_max_age_seconds": 90,
    "order_queue_file": "execution/rss_order_queue.csv",
    "order_status_file": "execution/rss_order_status.csv",
    "execution_ledger_file": "execution/execution_ledger.csv",
}

DEFAULT_TEAM_CONFIG: dict[str, Any] = {
    "version": "PHOENIX v6.5.1",
    "team_name": "PHOENIX Professional Trading & Engineering Team",
    "members": [
        {"role": "プロトレーダー", "responsibility": "売買戦略・相場判断・執行ルール監督"},
        {"role": "リスクマネージャー", "responsibility": "損失上限・資金配分・緊急停止監督"},
        {"role": "クオンツ", "responsibility": "期待値・バックテスト・最適化検証"},
        {"role": "プロコーダー", "responsibility": "実装品質・保守性・互換性監督"},
        {"role": "デバッカー", "responsibility": "構文・入出力・設定・異常系の自動検査"},
    ],
}


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


def read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    for encoding in ("utf-8-sig", "utf-8", "cp932"):
        try:
            return pd.read_csv(path, encoding=encoding)
        except (UnicodeDecodeError, pd.errors.ParserError):
            continue
    return pd.DataFrame()


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def merge_defaults(current: dict[str, Any], defaults: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    merged = dict(defaults)
    merged.update(current)
    return merged, merged != current


def bootstrap_environment() -> dict[str, Any]:
    for directory in (CONFIG_DIR, REPORT_DIR, EXECUTION_DIR, STATE_DIR, LOG_DIR):
        directory.mkdir(parents=True, exist_ok=True)

    current_config = load_json(CONFIG_FILE)
    config, config_changed = merge_defaults(current_config, DEFAULT_EXECUTION_CONFIG)
    if config_changed or not CONFIG_FILE.exists():
        save_json(CONFIG_FILE, config)

    current_team = load_json(TEAM_FILE)
    team, team_changed = merge_defaults(current_team, DEFAULT_TEAM_CONFIG)
    if team_changed or not TEAM_FILE.exists():
        save_json(TEAM_FILE, team)

    return {
        "config": config,
        "team": team,
        "config_created": not bool(current_config),
        "config_updated": config_changed and bool(current_config),
        "team_created": not bool(current_team),
        "team_updated": team_changed and bool(current_team),
    }


def validate_execution_config(config: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    mode = str(config.get("mode", "DRY_RUN")).upper()
    if mode not in {"DRY_RUN", "LIVE"}:
        errors.append("mode は DRY_RUN または LIVE である必要があります")
    if safe_float(config.get("account_capital_yen"), 0) <= 0:
        errors.append("account_capital_yen は0より大きい必要があります")
    if int(safe_float(config.get("minimum_rss_trade_unit"), 0)) <= 0:
        errors.append("minimum_rss_trade_unit は1以上である必要があります")
    if int(safe_float(config.get("maximum_daily_trades"), 0)) < 0:
        errors.append("maximum_daily_trades は0以上である必要があります")
    if safe_float(config.get("maximum_daily_loss_yen"), 0) <= 0:
        errors.append("maximum_daily_loss_yen は0より大きい必要があります")
    exposure = safe_float(config.get("maximum_total_exposure_percent"), -1)
    if not 0 <= exposure <= 100:
        errors.append("maximum_total_exposure_percent は0～100である必要があります")
    if mode != "LIVE" and bool(config.get("live_trading", False)):
        errors.append("DRY_RUN時は live_trading=false である必要があります")
    return errors
