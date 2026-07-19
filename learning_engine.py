from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import pandas as pd


VERSION = "6.9.1"
DEFAULT_INPUT_CANDIDATES = (
    Path("reports/paper_learning_data.csv"),
    Path("reports/paper_trades.csv"),
)
DEFAULT_CONFIG_PATH = Path("config/learning_config.json")


COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "ticker": ("ticker", "symbol", "code", "銘柄コード"),
    "name": ("name", "stock_name", "company", "銘柄名"),
    "entry_date": ("entry_date", "opened_at", "buy_date", "entry_time", "エントリー日"),
    "exit_date": ("exit_date", "closed_at", "sell_date", "exit_time", "決済日"),
    "entry_price": ("entry_price", "buy_price", "open_price", "取得価格"),
    "exit_price": ("exit_price", "sell_price", "close_price", "決済価格"),
    "quantity": ("quantity", "qty", "shares", "株数"),
    "trade_id": ("trade_id", "取引ID"),
    "pnl": ("pnl", "profit", "profit_loss", "realized_pnl", "損益", "損益額"),
    "pnl_pct": ("pnl_pct", "return_pct", "profit_pct", "損益率", "損益率%"),
    "holding_days": ("holding_days", "days_held", "保有日数"),
    "rsi": ("rsi", "entry_rsi", "RSI"),
    "macd": ("macd", "macd_signal", "entry_macd", "MACD", "MACD判定"),
    "volume_ratio": ("volume_ratio", "volume_multiple", "volume_rate", "出来高倍率"),
    "ai_score": ("ai_score", "final_ai_score", "AI_SCORE", "AIスコア", "AI判断点"),
    "phoenix_score": ("phoenix_score", "score", "PHOENIX_SCORE", "PHOENIXスコア"),
    "market_regime": ("market_regime", "regime", "market_phase", "地合い"),
    "result": ("result", "win_loss", "勝敗"),
    "entry_reason": ("entry_reason", "reason", "buy_reason", "エントリー理由"),
    "exit_reason": ("exit_reason", "sell_reason", "close_reason", "決済理由"),
}


@dataclass(frozen=True)
class Paths:
    input_csv: Path
    config_json: Path
    report_csv: Path
    summary_csv: Path
    adjustments_json: Path
    report_txt: Path


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"設定ファイルが見つかりません: {path}")
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def resolve_input(explicit: str | None) -> Path:
    if explicit:
        p = Path(explicit)
        if not p.exists():
            raise FileNotFoundError(f"入力CSVが見つかりません: {p}")
        return p

    for candidate in DEFAULT_INPUT_CANDIDATES:
        if candidate.exists():
            return candidate

    candidates = "\n".join(f"  - {p}" for p in DEFAULT_INPUT_CANDIDATES)
    raise FileNotFoundError(
        "Paper Traderの学習データが見つかりません。\n"
        f"確認対象:\n{candidates}"
    )


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    original_lookup = {str(c).strip().lower(): c for c in df.columns}
    rename_map: dict[Any, str] = {}

    for canonical, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            found = original_lookup.get(alias.strip().lower())
            if found is not None:
                rename_map[found] = canonical
                break

    return df.rename(columns=rename_map).copy()


def numeric(series: pd.Series) -> pd.Series:
    if series.dtype == object:
        series = (
            series.astype(str)
            .str.replace(",", "", regex=False)
            .str.replace("%", "", regex=False)
            .str.replace("円", "", regex=False)
            .str.strip()
            .replace({"": None, "None": None, "nan": None})
        )
    return pd.to_numeric(series, errors="coerce")


def prepare_trade_data(df: pd.DataFrame) -> pd.DataFrame:
    df = normalize_columns(df)

    for col in ("entry_price", "exit_price", "quantity", "pnl", "pnl_pct",
                "holding_days", "rsi", "volume_ratio", "ai_score", "phoenix_score"):
        if col in df.columns:
            df[col] = numeric(df[col])

    if "pnl" not in df.columns:
        needed = {"entry_price", "exit_price", "quantity"}
        if needed.issubset(df.columns):
            df["pnl"] = (df["exit_price"] - df["entry_price"]) * df["quantity"]
        else:
            raise ValueError(
                "損益列がありません。pnl、または entry_price/exit_price/quantity が必要です。"
            )

    if "pnl_pct" not in df.columns and {"entry_price", "exit_price"}.issubset(df.columns):
        valid = df["entry_price"].replace(0, pd.NA)
        df["pnl_pct"] = (df["exit_price"] - df["entry_price"]) / valid * 100.0

    if "holding_days" not in df.columns and {"entry_date", "exit_date"}.issubset(df.columns):
        entry = pd.to_datetime(df["entry_date"], errors="coerce")
        exit_ = pd.to_datetime(df["exit_date"], errors="coerce")
        df["holding_days"] = (exit_ - entry).dt.days.clip(lower=0)

    # Closed trades only. Open trades normally have no realized P/L.
    df = df[df["pnl"].notna()].copy()
    df["is_win"] = df["pnl"] > 0
    df["is_loss"] = df["pnl"] < 0
    return df


def assign_bins(
    series: pd.Series,
    edges: list[float],
    labels: list[str],
) -> pd.Series:
    if len(labels) != len(edges) - 1:
        raise ValueError("bin labels数はedges数-1である必要があります。")
    return pd.cut(
        numeric(series),
        bins=edges,
        labels=labels,
        include_lowest=True,
        right=False,
    ).astype("object").fillna("不明")


def safe_pf(profits: pd.Series) -> float | None:
    gross_profit = profits[profits > 0].sum()
    gross_loss = abs(profits[profits < 0].sum())
    if gross_loss == 0:
        return None if gross_profit == 0 else math.inf
    return float(gross_profit / gross_loss)


def grade_group(
    trades: int,
    expectancy: float,
    pf: float | None,
    min_samples: int,
    strengthen_expectancy: float,
    weaken_expectancy: float,
    strengthen_pf: float,
    weaken_pf: float,
) -> tuple[str, int]:
    if trades < min_samples:
        return "観察", 0

    pf_value = float("inf") if pf is not None and math.isinf(pf) else (pf or 0.0)

    if expectancy >= strengthen_expectancy and pf_value >= strengthen_pf:
        return "強化", 1
    if expectancy <= weaken_expectancy or pf_value <= weaken_pf:
        return "抑制", -1
    return "維持", 0


def summarize_group(
    data: pd.DataFrame,
    dimension: str,
    group_col: str,
    config: dict[str, Any],
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    learn = config["learning"]

    for group_value, g in data.groupby(group_col, dropna=False, observed=False):
        pnl = g["pnl"].dropna()
        trades = int(len(g))
        wins = int((pnl > 0).sum())
        losses = int((pnl < 0).sum())
        win_rate = wins / trades * 100 if trades else 0.0
        avg_profit = pnl[pnl > 0].mean() if wins else 0.0
        avg_loss = pnl[pnl < 0].mean() if losses else 0.0
        expectancy = pnl.mean() if trades else 0.0
        total_pnl = pnl.sum() if trades else 0.0
        pf = safe_pf(pnl)

        judgement, direction = grade_group(
            trades=trades,
            expectancy=float(expectancy),
            pf=pf,
            min_samples=int(learn["minimum_samples"]),
            strengthen_expectancy=float(learn["strengthen_expectancy_yen"]),
            weaken_expectancy=float(learn["weaken_expectancy_yen"]),
            strengthen_pf=float(learn["strengthen_profit_factor"]),
            weaken_pf=float(learn["weaken_profit_factor"]),
        )

        rows.append({
            "dimension": dimension,
            "group": str(group_value),
            "trades": trades,
            "wins": wins,
            "losses": losses,
            "win_rate_pct": round(win_rate, 2),
            "gross_profit_yen": round(float(pnl[pnl > 0].sum()), 2),
            "gross_loss_yen": round(float(pnl[pnl < 0].sum()), 2),
            "profit_factor": "INF" if pf is not None and math.isinf(pf) else (
                round(pf, 4) if pf is not None else ""
            ),
            "average_profit_yen": round(float(avg_profit), 2),
            "average_loss_yen": round(float(avg_loss), 2),
            "expectancy_yen": round(float(expectancy), 2),
            "total_pnl_yen": round(float(total_pnl), 2),
            "judgement": judgement,
            "direction": direction,
        })

    return pd.DataFrame(rows)


def build_statistics(data: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    bins = config["bins"]

    numeric_dimensions = (
        ("RSI", "rsi", bins["rsi"]),
        ("AI_SCORE", "ai_score", bins["ai_score"]),
        ("PHOENIX_SCORE", "phoenix_score", bins["phoenix_score"]),
        ("VOLUME_RATIO", "volume_ratio", bins["volume_ratio"]),
        ("HOLDING_DAYS", "holding_days", bins["holding_days"]),
    )

    for dimension, column, definition in numeric_dimensions:
        if column not in data.columns:
            continue
        working = data.copy()
        working["_group"] = assign_bins(
            working[column],
            [float(v) for v in definition["edges"]],
            [str(v) for v in definition["labels"]],
        )
        frames.append(summarize_group(working, dimension, "_group", config))

    categorical_dimensions = (
        ("MACD", "macd"),
        ("MARKET_REGIME", "market_regime"),
        ("ENTRY_REASON", "entry_reason"),
        ("EXIT_REASON", "exit_reason"),
    )

    for dimension, column in categorical_dimensions:
        if column not in data.columns:
            continue
        working = data.copy()
        working["_group"] = (
            working[column]
            .fillna("不明")
            .astype(str)
            .str.strip()
            .replace({"": "不明"})
        )
        frames.append(summarize_group(working, dimension, "_group", config))

    if not frames:
        return pd.DataFrame(columns=[
            "dimension", "group", "trades", "wins", "losses",
            "win_rate_pct", "gross_profit_yen", "gross_loss_yen",
            "profit_factor", "average_profit_yen", "average_loss_yen",
            "expectancy_yen", "total_pnl_yen", "judgement", "direction",
        ])

    result = pd.concat(frames, ignore_index=True)
    return result.sort_values(
        ["dimension", "trades", "expectancy_yen"],
        ascending=[True, False, False],
    ).reset_index(drop=True)


def build_adjustments(stats: pd.DataFrame, config: dict[str, Any]) -> dict[str, Any]:
    learn = config["learning"]
    step = int(learn["adjustment_step"])
    max_abs = int(learn["maximum_absolute_adjustment"])

    adjustments: dict[str, dict[str, int]] = {}
    evidence: dict[str, dict[str, dict[str, Any]]] = {}

    for row in stats.to_dict(orient="records"):
        dimension = str(row["dimension"])
        group = str(row["group"])
        direction = int(row["direction"])
        adjustment = max(-max_abs, min(max_abs, direction * step))

        adjustments.setdefault(dimension, {})[group] = adjustment
        evidence.setdefault(dimension, {})[group] = {
            "trades": int(row["trades"]),
            "win_rate_pct": float(row["win_rate_pct"]),
            "profit_factor": row["profit_factor"],
            "expectancy_yen": float(row["expectancy_yen"]),
            "judgement": str(row["judgement"]),
        }

    return {
        "version": VERSION,
        "mode": "statistical_rule_adjustment",
        "minimum_samples": int(learn["minimum_samples"]),
        "adjustments": adjustments,
        "evidence": evidence,
        "safety": {
            "apply_only_after_minimum_samples": True,
            "maximum_absolute_adjustment_per_condition": max_abs,
            "note": "このファイルは統計的補正候補です。実売買へ直接接続しないでください。",
        },
    }


def overall_summary(data: pd.DataFrame) -> pd.DataFrame:
    pnl = data["pnl"].dropna()
    trades = int(len(data))
    wins = int((pnl > 0).sum())
    losses = int((pnl < 0).sum())
    pf = safe_pf(pnl)

    row = {
        "version": VERSION,
        "closed_trades": trades,
        "wins": wins,
        "losses": losses,
        "win_rate_pct": round(wins / trades * 100, 2) if trades else 0.0,
        "gross_profit_yen": round(float(pnl[pnl > 0].sum()), 2),
        "gross_loss_yen": round(float(pnl[pnl < 0].sum()), 2),
        "profit_factor": "INF" if pf is not None and math.isinf(pf) else (
            round(pf, 4) if pf is not None else ""
        ),
        "expectancy_yen": round(float(pnl.mean()), 2) if trades else 0.0,
        "total_pnl_yen": round(float(pnl.sum()), 2),
    }
    return pd.DataFrame([row])


def render_text(
    input_path: Path,
    summary: pd.DataFrame,
    stats: pd.DataFrame,
) -> str:
    s = summary.iloc[0].to_dict()
    lines = [
        "=" * 72,
        f"PHOENIX v{VERSION} LEARNING ENGINE 2.0",
        "=" * 72,
        f"入力: {input_path}",
        f"決済済み取引: {int(s['closed_trades'])}件",
        f"勝率: {s['win_rate_pct']}%",
        f"Profit Factor: {s['profit_factor']}",
        f"期待値: {s['expectancy_yen']}円/取引",
        f"累計損益: {s['total_pnl_yen']}円",
        "",
        "強化候補 TOP10",
        "-" * 72,
    ]

    strengthen = (
        stats[stats["judgement"] == "強化"]
        .sort_values(["expectancy_yen", "trades"], ascending=[False, False])
        .head(10)
    )
    if strengthen.empty:
        lines.append("該当なし（サンプル不足または基準未達）")
    else:
        for _, r in strengthen.iterrows():
            lines.append(
                f"{r['dimension']} / {r['group']} | "
                f"{int(r['trades'])}件 | 勝率 {r['win_rate_pct']}% | "
                f"PF {r['profit_factor']} | 期待値 {r['expectancy_yen']}円"
            )

    lines += ["", "抑制候補 TOP10", "-" * 72]
    weaken = (
        stats[stats["judgement"] == "抑制"]
        .sort_values(["expectancy_yen", "trades"], ascending=[True, False])
        .head(10)
    )
    if weaken.empty:
        lines.append("該当なし（サンプル不足または基準未達）")
    else:
        for _, r in weaken.iterrows():
            lines.append(
                f"{r['dimension']} / {r['group']} | "
                f"{int(r['trades'])}件 | 勝率 {r['win_rate_pct']}% | "
                f"PF {r['profit_factor']} | 期待値 {r['expectancy_yen']}円"
            )

    lines += [
        "",
        "安全条件",
        "-" * 72,
        "・最低サンプル数未満は補正しません。",
        "・学習結果はPaper Trade検証用です。",
        "・実売買へ直接接続しません。",
        "=" * 72,
    ]
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=f"PHOENIX v{VERSION} Learning Engine 2.0"
    )
    parser.add_argument("--input", help="Paper Trade履歴CSV")
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_PATH),
        help="設定JSON",
    )
    parser.add_argument(
        "--report-dir",
        default="reports",
        help="出力ディレクトリ",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_path = resolve_input(args.input)
    config_path = Path(args.config)
    report_dir = Path(args.report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)

    paths = Paths(
        input_csv=input_path,
        config_json=config_path,
        report_csv=report_dir / "learning_statistics.csv",
        summary_csv=report_dir / "learning_summary.csv",
        adjustments_json=report_dir / "learning_adjustments.json",
        report_txt=report_dir / "learning_report.txt",
    )

    config = load_json(paths.config_json)
    raw = pd.read_csv(paths.input_csv, encoding="utf-8-sig")
    data = prepare_trade_data(raw)
    summary = overall_summary(data)
    stats = build_statistics(data, config)
    adjustments = build_adjustments(stats, config)
    report_text = render_text(paths.input_csv, summary, stats)

    summary.to_csv(paths.summary_csv, index=False, encoding="utf-8-sig")
    stats.to_csv(paths.report_csv, index=False, encoding="utf-8-sig")
    with paths.adjustments_json.open("w", encoding="utf-8") as f:
        json.dump(adjustments, f, ensure_ascii=False, indent=2)
    paths.report_txt.write_text(report_text, encoding="utf-8-sig")

    print(report_text)
    print("保存完了:")
    print(f"  {paths.summary_csv}")
    print(f"  {paths.report_csv}")
    print(f"  {paths.adjustments_json}")
    print(f"  {paths.report_txt}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
