from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_FILE = ROOT_DIR / "config" / "paper_trader_config.json"
OPEN_STATUS = "保有中"
CLOSED_STATUSES = {"利確", "損切", "時間切れ", "手動決済", "決済"}


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
        result = float(value)
        return result if math.isfinite(result) else default
    except (TypeError, ValueError):
        return default


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"設定ファイルがありません: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("設定ファイルのルートはJSONオブジェクトにしてください")
    return data


def resolve_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT_DIR / path


def load_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except pd.errors.EmptyDataError:
        return pd.DataFrame()


def trade_columns() -> list[str]:
    return [
        "取引ID", "銘柄", "ticker", "AI判断", "AI判断点", "PHOENIX_SCORE", "RSI", "MACD判定",
        "出来高倍率", "地合い", "エントリー理由", "基準価格", "押し目価格", "利確価格", "損切価格",
        "エントリー日時", "エントリー価格", "株数", "投資額", "買付手数料", "決済日時", "決済価格",
        "売却手数料", "決済理由", "状態", "損益額", "損益率%", "保有日数", "保有時間",
        "最高価格", "最低価格", "最大含み益率%", "最大含み損率%", "最終更新日時"
    ]


def normalize_trades(path: Path) -> pd.DataFrame:
    df = load_csv(path)
    if df.empty:
        return pd.DataFrame(columns=trade_columns())
    for column in trade_columns():
        if column not in df.columns:
            df[column] = "" if column not in {"AI判断点", "PHOENIX_SCORE", "RSI", "出来高倍率", "基準価格", "押し目価格", "利確価格", "損切価格", "エントリー価格", "株数", "投資額", "買付手数料", "決済価格", "売却手数料", "損益額", "損益率%", "保有日数", "最高価格", "最低価格", "最大含み益率%", "最大含み損率%"} else 0
    return df[trade_columns()]


def require_watchlist(path: Path) -> pd.DataFrame:
    df = load_csv(path)
    if df.empty:
        raise FileNotFoundError(f"監視リストがありません: {path}")
    aliases = {"name": "銘柄", "symbol": "ticker", "score": "PHOENIX_SCORE", "ai_score": "AI判断点"}
    df = df.rename(columns={k: v for k, v in aliases.items() if k in df.columns and v not in df.columns})
    required = {"銘柄", "ticker", "AI判断", "AI判断点", "PHOENIX_SCORE", "RSI", "MACD判定", "利確価格", "損切価格"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError("監視リストに必要な列がありません: " + ", ".join(sorted(missing)))
    for column in ["基準価格", "押し目価格", "出来高倍率", "地合い", "エントリー理由"]:
        if column not in df.columns:
            df[column] = "" if column in {"地合い", "エントリー理由"} else 0
    return df


def normalize_events(path: Path) -> pd.DataFrame:
    df = load_csv(path)
    if df.empty:
        return pd.DataFrame(columns=["日時", "イベント", "銘柄", "ticker", "現在価格"])
    aliases = {"datetime": "日時", "event": "イベント", "symbol": "ticker", "price": "現在価格", "name": "銘柄"}
    df = df.rename(columns={k: v for k, v in aliases.items() if k in df.columns and v not in df.columns})
    required = {"日時", "イベント", "ticker", "現在価格"}
    if not required.issubset(df.columns):
        return pd.DataFrame(columns=["日時", "イベント", "銘柄", "ticker", "現在価格"])
    if "銘柄" not in df.columns:
        df["銘柄"] = ""
    df["日時"] = pd.to_datetime(df["日時"], errors="coerce")
    df["現在価格"] = pd.to_numeric(df["現在価格"], errors="coerce")
    return df.dropna(subset=["日時", "イベント", "ticker", "現在価格"]).sort_values("日時").reset_index(drop=True)


def normalize_state(path: Path) -> pd.DataFrame:
    df = load_csv(path)
    if df.empty:
        return pd.DataFrame(columns=["ticker", "最新価格", "更新日時"])
    aliases = {"symbol": "ticker", "price": "最新価格", "datetime": "更新日時"}
    df = df.rename(columns={k: v for k, v in aliases.items() if k in df.columns and v not in df.columns})
    if "ticker" not in df.columns or "最新価格" not in df.columns:
        return pd.DataFrame(columns=["ticker", "最新価格", "更新日時"])
    df["最新価格"] = pd.to_numeric(df["最新価格"], errors="coerce")
    if "更新日時" not in df.columns:
        df["更新日時"] = now_text()
    return df.dropna(subset=["ticker", "最新価格"])


def buy_price(market: float, slippage: float) -> float:
    return round(market * (1.0 + slippage), 2)


def sell_price(market: float, slippage: float) -> float:
    return round(market * (1.0 - slippage), 2)


def available_cash(trades: pd.DataFrame, initial_capital: float) -> float:
    realized = pd.to_numeric(trades.get("損益額", pd.Series(dtype=float)), errors="coerce").fillna(0).sum()
    open_investment = pd.to_numeric(trades.loc[trades["状態"] == OPEN_STATUS, "投資額"], errors="coerce").fillna(0).sum() if not trades.empty else 0.0
    return max(0.0, initial_capital + float(realized) - float(open_investment))


def calculate_quantity(entry_price: float, cash: float, config: dict[str, Any]) -> int:
    if entry_price <= 0 or cash <= 0:
        return 0

    risk = config.get("risk", {})
    commission_rate = max(0.0, safe_float(config.get("costs", {}).get("commission_rate"), 0.0))
    lot = max(1, safe_int(risk.get("lot_size"), 100))
    allow_odd_lot = bool(risk.get("allow_odd_lot", False))

    cost_per_share = entry_price * (1.0 + commission_rate)
    if cost_per_share <= 0:
        return 0

    maximum_shares = int(cash // cost_per_share)
    if allow_odd_lot:
        return max(0, maximum_shares)

    return max(0, (maximum_shares // lot) * lot)


def already_processed(trades: pd.DataFrame, ticker: str, event_type: str, event_time: pd.Timestamp) -> bool:
    if trades.empty:
        return False
    column = "エントリー日時" if event_type == "ENTRY" else "決済日時"
    times = pd.to_datetime(trades[column], errors="coerce")
    return bool(((trades["ticker"].astype(str) == str(ticker)) & (times == event_time)).any())


def open_trade(trades: pd.DataFrame, event: pd.Series, row: pd.Series, config: dict[str, Any]) -> pd.DataFrame:
    ticker = str(event["ticker"])
    if ((trades["ticker"].astype(str) == ticker) & (trades["状態"] == OPEN_STATUS)).any():
        return trades
    max_positions = safe_int(config.get("risk", {}).get("max_open_positions"), 3)
    if int((trades["状態"] == OPEN_STATUS).sum()) >= max_positions:
        print(f"新規見送り: 最大保有数 {max_positions} に到達")
        return trades
    ai_score = safe_float(row.get("AI判断点"))
    phoenix_score = safe_float(row.get("PHOENIX_SCORE"))
    minimum_ai = safe_float(config.get("entry", {}).get("minimum_ai_score"), 70)
    minimum_phoenix = safe_float(config.get("entry", {}).get("minimum_phoenix_score"), 70)
    allowed = {str(x).upper() for x in config.get("entry", {}).get("allowed_ai_judgements", ["BUY", "STRONG BUY", "買い", "強い買い"])}
    if str(row.get("AI判断", "")).upper() not in allowed or ai_score < minimum_ai or phoenix_score < minimum_phoenix:
        print(f"新規見送り: {ticker} エントリー条件未達")
        return trades
    initial_capital = safe_float(config.get("capital", {}).get("initial_capital_yen"), 300000)
    cash = available_cash(trades, initial_capital)
    slippage = safe_float(config.get("costs", {}).get("slippage_rate"), 0.001)
    commission_rate = safe_float(config.get("costs", {}).get("commission_rate"), 0.0)
    entry = buy_price(safe_float(event["現在価格"]), slippage)
    quantity = calculate_quantity(entry, cash, config)
    if quantity <= 0:
        lot = max(1, safe_int(config.get("risk", {}).get("lot_size"), 100))
        minimum_required = entry * lot
        print(
            f"新規見送り: {ticker} 購入可能株数なし "
            f"(現金 {cash:,.0f}円 / 最低必要額 約{minimum_required:,.0f}円)"
        )
        return trades
    gross = round(entry * quantity, 2)
    fee = round(gross * commission_rate, 2)
    total = gross + fee
    event_time = pd.Timestamp(event["日時"])
    new_trade = {
        "取引ID": f"{ticker}_{event_time.strftime('%Y%m%d%H%M%S')}", "銘柄": str(row.get("銘柄", event.get("銘柄", ""))), "ticker": ticker,
        "AI判断": str(row.get("AI判断", "")), "AI判断点": ai_score, "PHOENIX_SCORE": phoenix_score, "RSI": safe_float(row.get("RSI")),
        "MACD判定": str(row.get("MACD判定", "")), "出来高倍率": safe_float(row.get("出来高倍率")), "地合い": str(row.get("地合い", "")),
        "エントリー理由": str(row.get("エントリー理由", "AIシグナル")), "基準価格": safe_float(row.get("基準価格")), "押し目価格": safe_float(row.get("押し目価格")),
        "利確価格": safe_float(row.get("利確価格")), "損切価格": safe_float(row.get("損切価格")), "エントリー日時": event_time.strftime("%Y-%m-%d %H:%M:%S"),
        "エントリー価格": entry, "株数": quantity, "投資額": total, "買付手数料": fee, "決済日時": "", "決済価格": 0.0, "売却手数料": 0.0,
        "決済理由": "", "状態": OPEN_STATUS, "損益額": 0.0, "損益率%": 0.0, "保有日数": 0, "保有時間": "", "最高価格": entry,
        "最低価格": entry, "最大含み益率%": 0.0, "最大含み損率%": 0.0, "最終更新日時": now_text()
    }
    remaining_cash = max(0.0, cash - total)
    print(
        f"仮想買付: {new_trade['銘柄']} {ticker} {quantity}株 {entry:,.2f}円 "
        f"投資額 {total:,.0f}円 / 残金 {remaining_cash:,.0f}円"
    )
    return pd.concat([trades, pd.DataFrame([new_trade])], ignore_index=True)[trade_columns()]


def close_position(trades: pd.DataFrame, index: int, market_price: float, when: pd.Timestamp, reason: str, config: dict[str, Any]) -> None:
    slippage = safe_float(config.get("costs", {}).get("slippage_rate"), 0.001)
    commission_rate = safe_float(config.get("costs", {}).get("commission_rate"), 0.0)
    exit_value = sell_price(market_price, slippage)
    quantity = safe_int(trades.at[index, "株数"])
    gross = round(exit_value * quantity, 2)
    fee = round(gross * commission_rate, 2)
    proceeds = gross - fee
    invested = safe_float(trades.at[index, "投資額"])
    pnl = round(proceeds - invested, 2)
    pnl_pct = round((pnl / invested * 100) if invested > 0 else 0.0, 4)
    entered = pd.to_datetime(trades.at[index, "エントリー日時"], errors="coerce")
    delta = when - entered if pd.notna(entered) else pd.Timedelta(0)
    trades.at[index, "決済日時"] = when.strftime("%Y-%m-%d %H:%M:%S")
    trades.at[index, "決済価格"] = exit_value
    trades.at[index, "売却手数料"] = fee
    trades.at[index, "決済理由"] = reason
    trades.at[index, "状態"] = reason
    trades.at[index, "損益額"] = pnl
    trades.at[index, "損益率%"] = pnl_pct
    trades.at[index, "保有日数"] = max(0, delta.days)
    trades.at[index, "保有時間"] = str(delta)
    trades.at[index, "最終更新日時"] = now_text()
    print(f"仮想決済: {trades.at[index, '銘柄']} {trades.at[index, 'ticker']} {reason} {pnl:+,.2f}円 ({pnl_pct:+.2f}%)")


def process_events(trades: pd.DataFrame, events: pd.DataFrame, watchlist: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
    reason_map = {
        "TAKE_PROFIT": "利確",
        "TARGET": "利確",
        "STOP_LOSS": "損切",
        "STOP": "損切",
        "EXIT": "手動決済",
        "CLOSE": "手動決済",
    }

    exit_events = events[events["イベント"].astype(str).str.strip().str.upper() != "ENTRY"].sort_values("日時")
    for _, event in exit_events.iterrows():
        ticker = str(event["ticker"])
        kind = str(event["イベント"]).strip().upper()
        when = pd.Timestamp(event["日時"])
        if already_processed(trades, ticker, kind, when):
            continue
        reason = reason_map.get(kind)
        if not reason:
            continue
        open_indexes = trades.index[(trades["ticker"].astype(str) == ticker) & (trades["状態"] == OPEN_STATUS)].tolist()
        if open_indexes:
            close_position(trades, open_indexes[-1], safe_float(event["現在価格"]), when, reason, config)

    entry_events = events[events["イベント"].astype(str).str.strip().str.upper() == "ENTRY"].copy()
    if entry_events.empty:
        return trades

    entry_events = entry_events.sort_values("日時").drop_duplicates(subset=["ticker"], keep="last")
    candidates = entry_events.merge(watchlist, on="ticker", how="left", suffixes=("_event", ""))
    candidates["AI判断点"] = pd.to_numeric(candidates.get("AI判断点"), errors="coerce").fillna(0)
    candidates["PHOENIX_SCORE"] = pd.to_numeric(candidates.get("PHOENIX_SCORE"), errors="coerce").fillna(0)
    candidates["総合優先点"] = candidates["AI判断点"] * 0.6 + candidates["PHOENIX_SCORE"] * 0.4
    candidates = candidates.sort_values(["総合優先点", "AI判断点", "PHOENIX_SCORE", "日時"], ascending=[False, False, False, True])

    max_positions = max(1, safe_int(config.get("risk", {}).get("max_open_positions"), 3))
    for _, candidate in candidates.iterrows():
        ticker = str(candidate["ticker"])
        when = pd.Timestamp(candidate["日時"])
        if already_processed(trades, ticker, "ENTRY", when):
            continue
        if int((trades["状態"] == OPEN_STATUS).sum()) >= max_positions:
            print(f"新規受付終了: 最大保有数 {max_positions} に到達")
            break
        event = pd.Series({
            "日時": when,
            "イベント": "ENTRY",
            "銘柄": candidate.get("銘柄_event", candidate.get("銘柄", "")),
            "ticker": ticker,
            "現在価格": candidate.get("現在価格", 0),
        })
        trades = open_trade(trades, event, candidate, config)

    return trades


def update_open_positions(trades: pd.DataFrame, state: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
    if trades.empty or state.empty:
        return trades
    max_holding_days = safe_int(config.get("exit", {}).get("max_holding_days"), 10)
    for index in trades.index[trades["状態"] == OPEN_STATUS].tolist():
        ticker = str(trades.at[index, "ticker"])
        matched = state[state["ticker"].astype(str) == ticker]
        if matched.empty:
            continue
        latest = matched.iloc[-1]
        price = safe_float(latest["最新価格"])
        when = pd.to_datetime(latest.get("更新日時"), errors="coerce")
        when = pd.Timestamp.now() if pd.isna(when) else pd.Timestamp(when)
        entry = safe_float(trades.at[index, "エントリー価格"])
        trades.at[index, "最高価格"] = max(safe_float(trades.at[index, "最高価格"], entry), price)
        trades.at[index, "最低価格"] = min(safe_float(trades.at[index, "最低価格"], entry), price)
        if entry > 0:
            trades.at[index, "最大含み益率%"] = round((safe_float(trades.at[index, "最高価格"]) / entry - 1) * 100, 4)
            trades.at[index, "最大含み損率%"] = round((safe_float(trades.at[index, "最低価格"]) / entry - 1) * 100, 4)
        target = safe_float(trades.at[index, "利確価格"])
        stop = safe_float(trades.at[index, "損切価格"])
        entered = pd.to_datetime(trades.at[index, "エントリー日時"], errors="coerce")
        holding_days = max(0, (when - entered).days) if pd.notna(entered) else 0
        trades.at[index, "保有日数"] = holding_days
        trades.at[index, "最終更新日時"] = now_text()
        if target > 0 and price >= target:
            close_position(trades, index, price, when, "利確", config)
        elif stop > 0 and price <= stop:
            close_position(trades, index, price, when, "損切", config)
        elif max_holding_days > 0 and holding_days >= max_holding_days:
            close_position(trades, index, price, when, "時間切れ", config)
    return trades


def build_learning_data(trades: pd.DataFrame) -> pd.DataFrame:
    closed = trades[trades["状態"].isin(CLOSED_STATUSES)].copy()
    if closed.empty:
        return pd.DataFrame(columns=["取引ID", "ticker", "AI判断点", "PHOENIX_SCORE", "RSI", "MACD判定", "出来高倍率", "地合い", "保有日数", "損益額", "損益率%", "勝敗", "エントリー理由", "決済理由"])
    closed["勝敗"] = pd.to_numeric(closed["損益額"], errors="coerce").fillna(0).map(lambda x: "WIN" if x > 0 else ("LOSS" if x < 0 else "EVEN"))
    return closed[["取引ID", "ticker", "AI判断点", "PHOENIX_SCORE", "RSI", "MACD判定", "出来高倍率", "地合い", "保有日数", "損益額", "損益率%", "勝敗", "エントリー理由", "決済理由"]]


def summary(trades: pd.DataFrame, config: dict[str, Any]) -> dict[str, Any]:
    initial = safe_float(config.get("capital", {}).get("initial_capital_yen"), 300000)
    closed = trades[trades["状態"].isin(CLOSED_STATUSES)].copy()
    pnl = pd.to_numeric(closed["損益額"], errors="coerce").fillna(0) if not closed.empty else pd.Series(dtype=float)
    wins = pnl[pnl > 0]
    losses = pnl[pnl < 0]
    realized = float(pnl.sum())
    open_count = int((trades["状態"] == OPEN_STATUS).sum()) if not trades.empty else 0
    return {
        "version": "6.8", "generated_at": now_text(), "initial_capital_yen": initial, "closed_trades": int(len(closed)), "open_trades": open_count,
        "wins": int(len(wins)), "losses": int(len(losses)), "win_rate_percent": round(len(wins) / len(closed) * 100, 4) if len(closed) else 0.0,
        "realized_pnl_yen": round(realized, 2), "ending_capital_yen": round(initial + realized, 2), "available_cash_yen": round(available_cash(trades, initial), 2)
    }


def save_outputs(trades: pd.DataFrame, config: dict[str, Any]) -> dict[str, Any]:
    files = config.get("files", {})
    trade_path = resolve_path(files.get("trades", "reports/paper_trades.csv"))
    learning_path = resolve_path(files.get("learning", "reports/paper_learning_data.csv"))
    summary_path = resolve_path(files.get("summary", "reports/paper_trade_summary.json"))
    report_path = resolve_path(files.get("report", "reports/paper_trade_report.txt"))
    for path in [trade_path, learning_path, summary_path, report_path]:
        path.parent.mkdir(parents=True, exist_ok=True)
    trades.to_csv(trade_path, index=False, encoding="utf-8-sig")
    build_learning_data(trades).to_csv(learning_path, index=False, encoding="utf-8-sig")
    result = summary(trades, config)
    summary_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    report = ["=" * 100, "PHOENIX v6.8 PAPER TRADER PRO", "=" * 100,
              f"作成日時             : {result['generated_at']}", f"初期資金             : {result['initial_capital_yen']:,.0f}円",
              f"保有中               : {result['open_trades']}件", f"決済済み             : {result['closed_trades']}件",
              f"勝率                 : {result['win_rate_percent']:.2f}%", f"確定損益             : {result['realized_pnl_yen']:+,.0f}円",
              f"現在資産             : {result['ending_capital_yen']:,.0f}円", f"利用可能現金         : {result['available_cash_yen']:,.0f}円",
              "-" * 100, "Paper Tradeの結果であり、実際の約定や将来の利益を保証しません。", "=" * 100]
    report_path.write_text("\n".join(report) + "\n", encoding="utf-8")
    print("\n".join(report))
    return result


def run(config: dict[str, Any]) -> dict[str, Any]:
    files = config.get("files", {})
    trades_path = resolve_path(files.get("trades", "reports/paper_trades.csv"))
    watchlist = require_watchlist(resolve_path(files.get("watchlist", "reports/price_watchlist.csv")))
    events = normalize_events(resolve_path(files.get("events", "reports/price_alert_history.csv")))
    state = normalize_state(resolve_path(files.get("state", "reports/price_monitor_state.csv")))
    trades = normalize_trades(trades_path)
    trades = process_events(trades, events, watchlist, config)
    trades = update_open_positions(trades, state, config)
    return save_outputs(trades, config)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="PHOENIX v6.8 Paper Trader Pro")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_FILE), help="設定JSON")
    return parser.parse_args()


def main() -> None:
    configure_console()
    args = parse_args()
    config = load_json(Path(args.config))
    print("=" * 100)
    print("PHOENIX v6.8 PAPER TRADER PRO")
    print("=" * 100)
    run(config)


if __name__ == "__main__":
    main()
