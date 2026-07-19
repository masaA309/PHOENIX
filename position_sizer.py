# position_sizer.py

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import json
import math
import sys
from typing import Any

import pandas as pd


# =========================================================
# 基本設定
# =========================================================

ROOT_DIR = Path(__file__).resolve().parent
REPORT_DIR = ROOT_DIR / "reports"

WATCHLIST_FILE = REPORT_DIR / "price_watchlist.csv"
AI_PARAMETER_FILE = REPORT_DIR / "ai_parameter.json"
MARKET_REGIME_FILE = REPORT_DIR / "market_regime.json"

POSITION_PLAN_FILE = REPORT_DIR / "position_plan.csv"
POSITION_REPORT_FILE = REPORT_DIR / "position_sizer_report.txt"
POSITION_SUMMARY_FILE = REPORT_DIR / "position_sizer_summary.json"

DEFAULT_ACCOUNT_CAPITAL = 300_000
DEFAULT_RISK_PER_TRADE_PERCENT = 1.0
DEFAULT_MAX_TOTAL_EXPOSURE_PERCENT = 80.0
DEFAULT_MAX_SINGLE_POSITION_PERCENT = 30.0
DEFAULT_MAX_OPEN_POSITIONS = 3

JAPAN_STANDARD_LOT = 100
ALLOW_ODD_LOT = False

MIN_STOP_DISTANCE_PERCENT = 0.5
MAX_STOP_DISTANCE_PERCENT = 15.0

BUY_PRIORITY = 0
WATCH_PRIORITY = 1


# =========================================================
# 共通
# =========================================================

def configure_console() -> None:
    try:
        sys.stdout.reconfigure(
            encoding="utf-8",
            errors="replace",
        )
        sys.stderr.reconfigure(
            encoding="utf-8",
            errors="replace",
        )
    except (
        AttributeError,
        OSError,
    ):
        pass


def now_text() -> str:
    return datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )


def safe_float(
    value: Any,
    default: float = 0.0,
) -> float:
    try:
        if pd.isna(value):
            return default

        result = float(value)

        if not math.isfinite(result):
            return default

        return result

    except (
        TypeError,
        ValueError,
    ):
        return default


def safe_int(
    value: Any,
    default: int = 0,
) -> int:
    try:
        return int(
            round(
                safe_float(
                    value,
                    default,
                )
            )
        )
    except (
        TypeError,
        ValueError,
    ):
        return default


def read_csv_safe(
    file_path: Path,
) -> pd.DataFrame:
    if not file_path.exists():
        return pd.DataFrame()

    last_error: Exception | None = None

    for encoding in (
        "utf-8-sig",
        "utf-8",
        "cp932",
    ):
        try:
            return pd.read_csv(
                file_path,
                encoding=encoding,
            )
        except Exception as error:
            last_error = error

    if last_error is not None:
        raise last_error

    return pd.DataFrame()


def read_json_safe(
    file_path: Path,
) -> dict[str, Any]:
    if not file_path.exists():
        return {}

    with open(
        file_path,
        "r",
        encoding="utf-8",
    ) as file:
        data = json.load(file)

    if not isinstance(
        data,
        dict,
    ):
        return {}

    return data


def write_json(
    file_path: Path,
    data: dict[str, Any],
) -> None:
    with open(
        file_path,
        "w",
        encoding="utf-8",
        newline="\n",
    ) as file:
        json.dump(
            data,
            file,
            ensure_ascii=False,
            indent=2,
        )


# =========================================================
# 設定読込
# =========================================================

def load_risk_settings() -> dict[str, Any]:
    parameters = read_json_safe(
        AI_PARAMETER_FILE
    )

    risk = parameters.get(
        "risk_management",
        {},
    )

    if not isinstance(
        risk,
        dict,
    ):
        risk = {}

    account_capital = safe_int(
        risk.get(
            "account_capital_yen",
            parameters.get(
                "account_capital_yen",
                DEFAULT_ACCOUNT_CAPITAL,
            ),
        ),
        DEFAULT_ACCOUNT_CAPITAL,
    )

    risk_per_trade_percent = safe_float(
        risk.get(
            "default_risk_per_trade_percent",
            DEFAULT_RISK_PER_TRADE_PERCENT,
        ),
        DEFAULT_RISK_PER_TRADE_PERCENT,
    )

    maximum_total_exposure_percent = safe_float(
        risk.get(
            "maximum_total_exposure_percent",
            DEFAULT_MAX_TOTAL_EXPOSURE_PERCENT,
        ),
        DEFAULT_MAX_TOTAL_EXPOSURE_PERCENT,
    )

    maximum_single_position_percent = safe_float(
        risk.get(
            "maximum_single_position_percent",
            DEFAULT_MAX_SINGLE_POSITION_PERCENT,
        ),
        DEFAULT_MAX_SINGLE_POSITION_PERCENT,
    )

    maximum_open_positions = safe_int(
        risk.get(
            "maximum_open_positions",
            DEFAULT_MAX_OPEN_POSITIONS,
        ),
        DEFAULT_MAX_OPEN_POSITIONS,
    )

    return {
        "account_capital_yen": max(
            account_capital,
            1,
        ),
        "risk_per_trade_percent": max(
            risk_per_trade_percent,
            0.1,
        ),
        "maximum_total_exposure_percent": min(
            max(
                maximum_total_exposure_percent,
                1.0,
            ),
            100.0,
        ),
        "maximum_single_position_percent": min(
            max(
                maximum_single_position_percent,
                1.0,
            ),
            100.0,
        ),
        "maximum_open_positions": max(
            maximum_open_positions,
            1,
        ),
        "source": (
            str(AI_PARAMETER_FILE)
            if AI_PARAMETER_FILE.exists()
            else "初期設定"
        ),
    }



def apply_market_regime_to_settings(settings: dict[str, Any]) -> dict[str, Any]:
    regime = read_json_safe(MARKET_REGIME_FILE)
    values = regime.get("settings", {})
    if not isinstance(values, dict):
        values = {}
    result = dict(settings)
    capital_usage = safe_float(values.get("capital_usage_percent", 70.0), 70.0)
    risk_multiplier = safe_float(values.get("risk_per_trade_multiplier", 1.0), 1.0)
    result["maximum_total_exposure_percent"] = min(result["maximum_total_exposure_percent"], capital_usage)
    result["risk_per_trade_percent"] = max(0.1, result["risk_per_trade_percent"] * risk_multiplier)
    result["maximum_open_positions"] = max(1, safe_int(values.get("max_positions", result["maximum_open_positions"]), result["maximum_open_positions"]))
    result["market_regime"] = str(regime.get("regime", "SIDEWAYS"))
    result["regime_confidence"] = safe_float(regime.get("confidence", 0.0))
    return result

# =========================================================
# 監視リスト読込
# =========================================================

def load_watchlist() -> pd.DataFrame:
    if not WATCHLIST_FILE.exists():
        raise FileNotFoundError(
            f"監視リストがありません: "
            f"{WATCHLIST_FILE}"
        )

    watchlist = read_csv_safe(
        WATCHLIST_FILE
    )

    if watchlist.empty:
        raise ValueError(
            "price_watchlist.csv が空です。"
        )

    required_columns = {
        "銘柄",
        "ticker",
        "AI判断",
        "AI判断点",
        "PHOENIX_SCORE",
        "Trade判定",
        "ロット比率",
        "基準価格",
        "押し目価格",
        "利確価格",
        "損切価格",
        "MarketRiskScore",
        "MarketRiskLevel",
    }

    missing_columns = (
        required_columns
        - set(watchlist.columns)
    )

    if missing_columns:
        raise ValueError(
            "price_watchlist.csv に必要な列がありません: "
            + ", ".join(
                sorted(missing_columns)
            )
        )

    numeric_columns = [
        "AI判断点",
        "PHOENIX_SCORE",
        "ロット比率",
        "基準価格",
        "押し目価格",
        "利確価格",
        "損切価格",
        "MarketRiskScore",
    ]

    for column in numeric_columns:
        watchlist[column] = pd.to_numeric(
            watchlist[column],
            errors="coerce",
        )

    watchlist["ticker"] = (
        watchlist["ticker"]
        .astype(str)
        .str.strip()
    )

    watchlist["Trade判定"] = (
        watchlist["Trade判定"]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    watchlist = watchlist[
        watchlist["Trade判定"].isin(
            [
                "BUY",
                "WATCH",
            ]
        )
    ].copy()

    watchlist = watchlist.dropna(
        subset=[
            "銘柄",
            "ticker",
            "押し目価格",
            "利確価格",
            "損切価格",
        ]
    )

    watchlist = watchlist[
        (
            watchlist["押し目価格"] > 0
        )
        & (
            watchlist["利確価格"]
            > watchlist["押し目価格"]
        )
        & (
            watchlist["損切価格"]
            < watchlist["押し目価格"]
        )
    ].copy()

    if watchlist.empty:
        raise ValueError(
            "有効なポジション計算対象がありません。"
        )

    return watchlist.reset_index(
        drop=True
    )


# =========================================================
# 補正
# =========================================================

def trade_priority(
    trade_decision: str,
) -> int:
    return (
        BUY_PRIORITY
        if trade_decision == "BUY"
        else WATCH_PRIORITY
    )


def decision_weight(
    trade_decision: str,
) -> float:
    if trade_decision == "BUY":
        return 1.0

    if trade_decision == "WATCH":
        return 0.70

    return 0.0


def ai_score_weight(
    ai_score: float,
) -> float:
    if ai_score >= 85:
        return 1.00

    if ai_score >= 80:
        return 0.95

    if ai_score >= 75:
        return 0.90

    if ai_score >= 70:
        return 0.80

    if ai_score >= 65:
        return 0.70

    return 0.60


def phoenix_score_weight(
    phoenix_score: float,
) -> float:
    if phoenix_score >= 90:
        return 1.00

    if phoenix_score >= 80:
        return 0.95

    if phoenix_score >= 70:
        return 0.90

    if phoenix_score >= 60:
        return 0.80

    return 0.70


def market_risk_weight(
    risk_score: float,
    risk_level: str,
) -> float:
    level = str(
        risk_level
    ).strip().upper()

    if level in {
        "DANGER",
        "STOP",
        "CRITICAL",
    }:
        return 0.0

    if level in {
        "HIGH",
        "RISK",
    }:
        return 0.35

    if level == "WATCH":
        return 0.50

    if level in {
        "SAFE",
        "LOW",
        "NORMAL",
    }:
        return 1.0

    if risk_score >= 80:
        return 0.25

    if risk_score >= 60:
        return 0.50

    if risk_score >= 40:
        return 0.70

    return 1.0


def source_lot_weight(
    value: float,
) -> float:
    if value <= 0:
        return 1.0

    return min(
        max(
            value,
            0.10,
        ),
        1.0,
    )


def stop_distance_percent(
    entry_price: float,
    stop_price: float,
) -> float:
    if entry_price <= 0:
        return 0.0

    return (
        entry_price
        - stop_price
    ) / entry_price * 100.0


def reward_risk_ratio(
    entry_price: float,
    target_price: float,
    stop_price: float,
) -> float:
    risk = (
        entry_price
        - stop_price
    )

    reward = (
        target_price
        - entry_price
    )

    if risk <= 0:
        return 0.0

    return reward / risk


# =========================================================
# 株数計算
# =========================================================

def floor_to_lot(
    shares: float,
) -> int:
    if shares <= 0:
        return 0

    if ALLOW_ODD_LOT:
        return max(
            int(
                math.floor(
                    shares
                )
            ),
            0,
        )

    return max(
        int(
            math.floor(
                shares
                / JAPAN_STANDARD_LOT
            )
            * JAPAN_STANDARD_LOT
        ),
        0,
    )


def calculate_position_row(
    row: pd.Series,
    settings: dict[str, Any],
) -> dict[str, Any]:
    account_capital = safe_float(
        settings["account_capital_yen"]
    )

    base_risk_percent = safe_float(
        settings["risk_per_trade_percent"]
    )

    maximum_single_position_percent = safe_float(
        settings[
            "maximum_single_position_percent"
        ]
    )

    entry_price = safe_float(
        row["押し目価格"]
    )

    target_price = safe_float(
        row["利確価格"]
    )

    stop_price = safe_float(
        row["損切価格"]
    )

    ai_score = safe_float(
        row["AI判断点"]
    )

    phoenix_score = safe_float(
        row["PHOENIX_SCORE"]
    )

    trade_decision = str(
        row["Trade判定"]
    ).strip().upper()

    market_risk_score = safe_float(
        row["MarketRiskScore"]
    )

    market_risk_level = str(
        row["MarketRiskLevel"]
    ).strip()

    lot_ratio = source_lot_weight(
        safe_float(
            row["ロット比率"]
        )
    )

    decision_factor = decision_weight(
        trade_decision
    )

    ai_factor = ai_score_weight(
        ai_score
    )

    phoenix_factor = phoenix_score_weight(
        phoenix_score
    )

    market_factor = market_risk_weight(
        market_risk_score,
        market_risk_level,
    )

    combined_factor = (
        lot_ratio
        * decision_factor
        * ai_factor
        * phoenix_factor
        * market_factor
    )

    combined_factor = min(
        max(
            combined_factor,
            0.0,
        ),
        1.0,
    )

    stop_distance_yen = (
        entry_price
        - stop_price
    )

    stop_percent = stop_distance_percent(
        entry_price,
        stop_price,
    )

    rr = reward_risk_ratio(
        entry_price,
        target_price,
        stop_price,
    )

    base_risk_yen = (
        account_capital
        * base_risk_percent
        / 100.0
    )

    adjusted_risk_yen = (
        base_risk_yen
        * combined_factor
    )

    maximum_position_amount = (
        account_capital
        * maximum_single_position_percent
        / 100.0
    )

    risk_based_shares = (
        adjusted_risk_yen
        / stop_distance_yen
        if stop_distance_yen > 0
        else 0.0
    )

    capital_based_shares = (
        maximum_position_amount
        / entry_price
        if entry_price > 0
        else 0.0
    )

    raw_shares = min(
        risk_based_shares,
        capital_based_shares,
    )

    shares = floor_to_lot(
        raw_shares
    )

    reason_parts: list[str] = []

    if market_factor <= 0:
        shares = 0
        reason_parts.append(
            "Market Risk停止"
        )

    if stop_percent < MIN_STOP_DISTANCE_PERCENT:
        shares = 0
        reason_parts.append(
            "損切幅が狭すぎる"
        )

    if stop_percent > MAX_STOP_DISTANCE_PERCENT:
        shares = 0
        reason_parts.append(
            "損切幅が広すぎる"
        )

    if rr < 1.0:
        shares = 0
        reason_parts.append(
            "リスクリワード1未満"
        )

    minimum_lot_cost = (
        entry_price
        * JAPAN_STANDARD_LOT
    )

    if (
        not ALLOW_ODD_LOT
        and shares <= 0
        and minimum_lot_cost
        > maximum_position_amount
    ):
        reason_parts.append(
            "100株購入額が上限超過"
        )

    investment_amount = (
        shares
        * entry_price
    )

    expected_profit_yen = (
        shares
        * (
            target_price
            - entry_price
        )
    )

    expected_loss_yen = (
        shares
        * (
            entry_price
            - stop_price
        )
    )

    exposure_percent = (
        investment_amount
        / account_capital
        * 100.0
        if account_capital > 0
        else 0.0
    )

    actual_risk_percent = (
        expected_loss_yen
        / account_capital
        * 100.0
        if account_capital > 0
        else 0.0
    )

    if shares > 0:
        position_status = "採用"
        if not reason_parts:
            reason_parts.append(
                "資金管理条件クリア"
            )
    else:
        position_status = "見送り"

        if not reason_parts:
            reason_parts.append(
                "計算株数が最低売買単位未満"
            )

    return {
        "作成日時": now_text(),
        "銘柄": str(
            row["銘柄"]
        ),
        "ticker": str(
            row["ticker"]
        ),
        "AI判断": str(
            row["AI判断"]
        ),
        "AI判断点": safe_int(
            ai_score
        ),
        "PHOENIX_SCORE": safe_int(
            phoenix_score
        ),
        "Trade判定": trade_decision,
        "MarketRiskScore": round(
            market_risk_score,
            2,
        ),
        "MarketRiskLevel": market_risk_level,
        "基準価格": round(
            safe_float(
                row["基準価格"]
            ),
            2,
        ),
        "エントリー価格": round(
            entry_price,
            2,
        ),
        "利確価格": round(
            target_price,
            2,
        ),
        "損切価格": round(
            stop_price,
            2,
        ),
        "損切幅円": round(
            stop_distance_yen,
            2,
        ),
        "損切幅%": round(
            stop_percent,
            4,
        ),
        "リスクリワード": round(
            rr,
            3,
        ),
        "元ロット比率": round(
            lot_ratio,
            4,
        ),
        "Trade補正": round(
            decision_factor,
            4,
        ),
        "AI点補正": round(
            ai_factor,
            4,
        ),
        "PHOENIX補正": round(
            phoenix_factor,
            4,
        ),
        "市場リスク補正": round(
            market_factor,
            4,
        ),
        "最終リスク係数": round(
            combined_factor,
            4,
        ),
        "基準許容損失円": round(
            base_risk_yen,
            0,
        ),
        "補正後許容損失円": round(
            adjusted_risk_yen,
            0,
        ),
        "株数": shares,
        "投資金額円": round(
            investment_amount,
            0,
        ),
        "口座比率%": round(
            exposure_percent,
            2,
        ),
        "想定利益円": round(
            expected_profit_yen,
            0,
        ),
        "想定損失円": round(
            expected_loss_yen,
            0,
        ),
        "実損失率%": round(
            actual_risk_percent,
            4,
        ),
        "Position判定": position_status,
        "判定理由": " / ".join(
            reason_parts
        ),
        "_優先順位": trade_priority(
            trade_decision
        ),
    }


def calculate_position_plan(
    watchlist: pd.DataFrame,
    settings: dict[str, Any],
) -> pd.DataFrame:
    rows = [
        calculate_position_row(
            row=row,
            settings=settings,
        )
        for _, row in watchlist.iterrows()
    ]

    plan = pd.DataFrame(
        rows
    )

    plan = plan.sort_values(
        by=[
            "_優先順位",
            "AI判断点",
            "PHOENIX_SCORE",
            "リスクリワード",
        ],
        ascending=[
            True,
            False,
            False,
            False,
        ],
    ).reset_index(
        drop=True
    )

    maximum_open_positions = safe_int(
        settings["maximum_open_positions"]
    )

    maximum_total_exposure = (
        safe_float(
            settings["account_capital_yen"]
        )
        * safe_float(
            settings[
                "maximum_total_exposure_percent"
            ]
        )
        / 100.0
    )

    selected_count = 0
    selected_exposure = 0.0

    for index, row in plan.iterrows():
        if row["Position判定"] != "採用":
            continue

        investment_amount = safe_float(
            row["投資金額円"]
        )

        if selected_count >= maximum_open_positions:
            plan.at[
                index,
                "Position判定",
            ] = "見送り"

            plan.at[
                index,
                "判定理由",
            ] = (
                str(
                    row["判定理由"]
                )
                + " / 最大保有数超過"
            )

            plan.at[
                index,
                "株数",
            ] = 0

            plan.at[
                index,
                "投資金額円",
            ] = 0

            plan.at[
                index,
                "口座比率%",
            ] = 0

            plan.at[
                index,
                "想定利益円",
            ] = 0

            plan.at[
                index,
                "想定損失円",
            ] = 0

            plan.at[
                index,
                "実損失率%",
            ] = 0

            continue

        if (
            selected_exposure
            + investment_amount
            > maximum_total_exposure
        ):
            plan.at[
                index,
                "Position判定",
            ] = "見送り"

            plan.at[
                index,
                "判定理由",
            ] = (
                str(
                    row["判定理由"]
                )
                + " / 総投資上限超過"
            )

            plan.at[
                index,
                "株数",
            ] = 0

            plan.at[
                index,
                "投資金額円",
            ] = 0

            plan.at[
                index,
                "口座比率%",
            ] = 0

            plan.at[
                index,
                "想定利益円",
            ] = 0

            plan.at[
                index,
                "想定損失円",
            ] = 0

            plan.at[
                index,
                "実損失率%",
            ] = 0

            continue

        selected_count += 1
        selected_exposure += investment_amount

    plan["優先順位"] = range(
        1,
        len(plan) + 1,
    )

    columns = [
        "優先順位",
        "作成日時",
        "銘柄",
        "ticker",
        "AI判断",
        "AI判断点",
        "PHOENIX_SCORE",
        "Trade判定",
        "MarketRiskScore",
        "MarketRiskLevel",
        "基準価格",
        "エントリー価格",
        "利確価格",
        "損切価格",
        "損切幅円",
        "損切幅%",
        "リスクリワード",
        "元ロット比率",
        "Trade補正",
        "AI点補正",
        "PHOENIX補正",
        "市場リスク補正",
        "最終リスク係数",
        "基準許容損失円",
        "補正後許容損失円",
        "株数",
        "投資金額円",
        "口座比率%",
        "想定利益円",
        "想定損失円",
        "実損失率%",
        "Position判定",
        "判定理由",
    ]

    return plan[
        columns
    ].copy()


# =========================================================
# 保存・表示
# =========================================================

def build_summary(
    plan: pd.DataFrame,
    settings: dict[str, Any],
) -> dict[str, Any]:
    adopted = plan[
        plan["Position判定"]
        == "採用"
    ].copy()

    total_investment = safe_float(
        adopted["投資金額円"].sum()
        if not adopted.empty
        else 0.0
    )

    total_expected_profit = safe_float(
        adopted["想定利益円"].sum()
        if not adopted.empty
        else 0.0
    )

    total_expected_loss = safe_float(
        adopted["想定損失円"].sum()
        if not adopted.empty
        else 0.0
    )

    account_capital = safe_float(
        settings["account_capital_yen"]
    )

    return {
        "version": "PHOENIX v3.5",
        "generated_at": now_text(),
        "settings": settings,
        "result": {
            "targets": len(plan),
            "adopted_positions": len(adopted),
            "rejected_positions": (
                len(plan)
                - len(adopted)
            ),
            "total_investment_yen": round(
                total_investment,
                0,
            ),
            "total_exposure_percent": round(
                total_investment
                / account_capital
                * 100.0
                if account_capital > 0
                else 0.0,
                2,
            ),
            "total_expected_profit_yen": round(
                total_expected_profit,
                0,
            ),
            "total_expected_loss_yen": round(
                total_expected_loss,
                0,
            ),
            "total_expected_loss_percent": round(
                total_expected_loss
                / account_capital
                * 100.0
                if account_capital > 0
                else 0.0,
                4,
            ),
        },
    }


def save_outputs(
    plan: pd.DataFrame,
    summary: dict[str, Any],
) -> None:
    REPORT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    plan.to_csv(
        POSITION_PLAN_FILE,
        index=False,
        encoding="utf-8-sig",
    )

    write_json(
        POSITION_SUMMARY_FILE,
        summary,
    )

    result = summary["result"]
    settings = summary["settings"]

    with open(
        POSITION_REPORT_FILE,
        "w",
        encoding="utf-8",
        newline="\n",
    ) as file:
        file.write(
            "PHOENIX POSITION SIZER REPORT\n"
        )
        file.write(
            now_text()
            + "\n"
        )
        file.write(
            "=" * 120
            + "\n"
        )
        file.write(
            f"口座資金: "
            f"{safe_int(settings['account_capital_yen']):,}円\n"
        )
        file.write(
            f"1取引リスク: "
            f"{safe_float(settings['risk_per_trade_percent']):.2f}%\n"
        )
        file.write(
            f"最大総投資比率: "
            f"{safe_float(settings['maximum_total_exposure_percent']):.2f}%\n"
        )
        file.write(
            f"最大1銘柄比率: "
            f"{safe_float(settings['maximum_single_position_percent']):.2f}%\n"
        )
        file.write(
            f"最大保有数: "
            f"{safe_int(settings['maximum_open_positions'])}件\n"
        )
        file.write(
            f"採用数: "
            f"{safe_int(result['adopted_positions'])}件\n"
        )
        file.write(
            f"総投資額: "
            f"{safe_int(result['total_investment_yen']):,}円\n"
        )
        file.write(
            f"総想定損失: "
            f"{safe_int(result['total_expected_loss_yen']):,}円\n"
        )
        file.write(
            "\n"
        )
        file.write(
            plan.to_string(
                index=False
            )
        )
        file.write(
            "\n"
        )


def print_result(
    plan: pd.DataFrame,
    summary: dict[str, Any],
) -> None:
    settings = summary["settings"]
    result = summary["result"]

    print("=" * 120)
    print("PHOENIX POSITION SIZER")
    print("=" * 120)
    print(
        f"口座資金       : "
        f"{safe_int(settings['account_capital_yen']):,}円"
    )
    print(
        f"1取引リスク   : "
        f"{safe_float(settings['risk_per_trade_percent']):.2f}%"
    )
    print(
        f"最大総投資比率 : "
        f"{safe_float(settings['maximum_total_exposure_percent']):.2f}%"
    )
    print(
        f"最大1銘柄比率 : "
        f"{safe_float(settings['maximum_single_position_percent']):.2f}%"
    )
    print(
        f"最大保有数     : "
        f"{safe_int(settings['maximum_open_positions'])}件"
    )
    print(
        f"設定読込元     : "
        f"{settings['source']}"
    )

    print()
    print("=" * 120)
    print("ポジション計画")
    print("=" * 120)

    display_columns = [
        "優先順位",
        "銘柄",
        "ticker",
        "Trade判定",
        "AI判断点",
        "PHOENIX_SCORE",
        "エントリー価格",
        "損切価格",
        "リスクリワード",
        "株数",
        "投資金額円",
        "想定利益円",
        "想定損失円",
        "Position判定",
        "判定理由",
    ]

    print(
        plan[
            display_columns
        ].to_string(
            index=False
        )
    )

    print()
    print("=" * 120)
    print("集計")
    print("=" * 120)
    print(
        f"計算対象       : "
        f"{safe_int(result['targets'])}件"
    )
    print(
        f"採用           : "
        f"{safe_int(result['adopted_positions'])}件"
    )
    print(
        f"見送り         : "
        f"{safe_int(result['rejected_positions'])}件"
    )
    print(
        f"総投資額       : "
        f"{safe_int(result['total_investment_yen']):,}円"
    )
    print(
        f"総投資比率     : "
        f"{safe_float(result['total_exposure_percent']):.2f}%"
    )
    print(
        f"総想定利益     : "
        f"{safe_int(result['total_expected_profit_yen']):,}円"
    )
    print(
        f"総想定損失     : "
        f"{safe_int(result['total_expected_loss_yen']):,}円"
    )
    print(
        f"総想定損失率   : "
        f"{safe_float(result['total_expected_loss_percent']):.4f}%"
    )

    print()
    print(
        f"保存完了: {POSITION_PLAN_FILE}"
    )
    print(
        f"保存完了: {POSITION_SUMMARY_FILE}"
    )
    print(
        f"保存完了: {POSITION_REPORT_FILE}"
    )


# =========================================================
# メイン
# =========================================================

def main() -> None:
    configure_console()

    try:
        REPORT_DIR.mkdir(
            parents=True,
            exist_ok=True,
        )

        settings = apply_market_regime_to_settings(load_risk_settings())

        watchlist = load_watchlist()

        plan = calculate_position_plan(
            watchlist=watchlist,
            settings=settings,
        )

        summary = build_summary(
            plan=plan,
            settings=settings,
        )

        save_outputs(
            plan=plan,
            summary=summary,
        )

        print_result(
            plan=plan,
            summary=summary,
        )

    except Exception as error:
        print(
            f"エラー: {error}"
        )

        raise SystemExit(
            1
        )


if __name__ == "__main__":
    main()
