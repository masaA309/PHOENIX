# ai_judgement.py

from datetime import datetime
from pathlib import Path

import pandas as pd


REPORT_DIR = Path("reports")
OUTPUT_FILE = REPORT_DIR / "ai_judgement.csv"
TEXT_OUTPUT_FILE = REPORT_DIR / "ai_judgement.txt"

TOP_STOCKS = 20


def get_latest_report_file() -> Path:
    report_files = sorted(
        REPORT_DIR.glob("report_*.csv"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )

    if not report_files:
        raise FileNotFoundError(
            "reportsフォルダにreport_*.csvがありません。"
        )

    return report_files[0]


def load_report() -> tuple[pd.DataFrame, Path]:
    report_file = get_latest_report_file()

    df = pd.read_csv(
        report_file,
    )

    required_columns = {
        "銘柄",
        "ticker",
        "価格",
        "前日比%",
        "出来高倍率",
        "RSI",
        "MACD判定",
        "PHOENIX_SCORE",
        "理由",
    }

    missing_columns = required_columns - set(
        df.columns
    )

    if missing_columns:
        missing_text = ", ".join(
            sorted(missing_columns)
        )

        raise ValueError(
            f"必要な列がありません: {missing_text}"
        )

    numeric_columns = [
        "価格",
        "前日比%",
        "出来高倍率",
        "RSI",
        "PHOENIX_SCORE",
    ]

    for column in numeric_columns:
        df[column] = pd.to_numeric(
            df[column],
            errors="coerce",
        )

    df["MACD判定"] = (
        df["MACD判定"]
        .astype(str)
        .str.upper()
        .str.strip()
    )

    df = df.dropna(
        subset=numeric_columns,
    )

    df = (
        df.sort_values(
            by=[
                "PHOENIX_SCORE",
                "出来高倍率",
                "前日比%",
            ],
            ascending=[
                False,
                False,
                False,
            ],
        )
        .head(TOP_STOCKS)
        .reset_index(drop=True)
    )

    return df, report_file


def load_optimized_tickers() -> set[str]:
    optimized_file = (
        REPORT_DIR
        / "optimized_signals.csv"
    )

    if not optimized_file.exists():
        return set()

    try:
        df = pd.read_csv(
            optimized_file,
        )

        if "ticker" not in df.columns:
            return set()

        return set(
            df["ticker"]
            .dropna()
            .astype(str)
            .str.strip()
        )

    except Exception:
        return set()


def calculate_risk_level(
    change: float,
    volume_ratio: float,
    rsi: float,
) -> tuple[str, int, list[str]]:
    risk_score = 0
    reasons = []

    if rsi >= 85:
        risk_score += 35
        reasons.append(
            f"RSI {rsi:.2f}で極端な過熱"
        )

    elif rsi >= 75:
        risk_score += 20
        reasons.append(
            f"RSI {rsi:.2f}で過熱気味"
        )

    elif rsi <= 25:
        risk_score += 25
        reasons.append(
            f"RSI {rsi:.2f}で極端な売られすぎ"
        )

    elif rsi <= 35:
        risk_score += 10
        reasons.append(
            f"RSI {rsi:.2f}で売られすぎ気味"
        )

    if change >= 8:
        risk_score += 30
        reasons.append(
            f"前日比 +{change:.2f}%の急騰"
        )

    elif change >= 5:
        risk_score += 20
        reasons.append(
            f"前日比 +{change:.2f}%の大幅上昇"
        )

    elif change <= -8:
        risk_score += 35
        reasons.append(
            f"前日比 {change:.2f}%の急落"
        )

    elif change <= -5:
        risk_score += 20
        reasons.append(
            f"前日比 {change:.2f}%の大幅下落"
        )

    if volume_ratio >= 5:
        risk_score += 20
        reasons.append(
            f"出来高 {volume_ratio:.2f}倍の異常増加"
        )

    elif volume_ratio >= 3:
        risk_score += 10
        reasons.append(
            f"出来高 {volume_ratio:.2f}倍の急増"
        )

    risk_score = min(
        risk_score,
        100,
    )

    if risk_score >= 60:
        risk_level = "高"

    elif risk_score >= 30:
        risk_level = "中"

    else:
        risk_level = "低"

    return (
        risk_level,
        risk_score,
        reasons,
    )


def make_judgement(
    row: pd.Series,
    optimized_tickers: set[str],
) -> dict:
    name = str(
        row["銘柄"]
    )

    ticker = str(
        row["ticker"]
    )

    price = float(
        row["価格"]
    )

    change = float(
        row["前日比%"]
    )

    volume_ratio = float(
        row["出来高倍率"]
    )

    rsi = float(
        row["RSI"]
    )

    phoenix_score = int(
        float(
            row["PHOENIX_SCORE"]
        )
    )

    macd = str(
        row["MACD判定"]
    ).upper()

    optimized_match = (
        ticker in optimized_tickers
    )

    risk_level, risk_score, risk_reasons = (
        calculate_risk_level(
            change=change,
            volume_ratio=volume_ratio,
            rsi=rsi,
        )
    )

    action_score = 0
    positive_reasons = []
    caution_reasons = []

    if phoenix_score >= 80:
        action_score += 35
        positive_reasons.append(
            f"PHOENIX SCORE {phoenix_score}点"
        )

    elif phoenix_score >= 70:
        action_score += 25
        positive_reasons.append(
            f"PHOENIX SCORE {phoenix_score}点"
        )

    elif phoenix_score >= 60:
        action_score += 15
        positive_reasons.append(
            f"PHOENIX SCORE {phoenix_score}点"
        )

    elif phoenix_score >= 55:
        action_score += 8
        positive_reasons.append(
            f"PHOENIX SCORE {phoenix_score}点"
        )

    if 45 <= rsi <= 65:
        action_score += 15
        positive_reasons.append(
            f"RSI {rsi:.2f}は適正範囲"
        )

    elif 35 <= rsi < 45:
        action_score += 7
        positive_reasons.append(
            f"RSI {rsi:.2f}は反発余地あり"
        )

    elif 65 < rsi <= 75:
        action_score += 5
        caution_reasons.append(
            f"RSI {rsi:.2f}はやや過熱"
        )

    elif rsi > 75:
        action_score -= 20
        caution_reasons.append(
            f"RSI {rsi:.2f}は過熱"
        )

    elif rsi < 30:
        action_score -= 10
        caution_reasons.append(
            f"RSI {rsi:.2f}は弱い状態"
        )

    if macd == "BUY":
        action_score += 15
        positive_reasons.append(
            "MACD BUY"
        )

    else:
        action_score -= 5
        caution_reasons.append(
            "MACD SELL"
        )

    if 1.2 <= volume_ratio < 2:
        action_score += 8
        positive_reasons.append(
            f"出来高 {volume_ratio:.2f}倍"
        )

    elif 2 <= volume_ratio < 4:
        action_score += 12
        positive_reasons.append(
            f"出来高 {volume_ratio:.2f}倍"
        )

    elif volume_ratio >= 4:
        action_score += 5
        caution_reasons.append(
            f"出来高 {volume_ratio:.2f}倍で過熱注意"
        )

    if 0 < change <= 4:
        action_score += 10
        positive_reasons.append(
            f"前日比 +{change:.2f}%"
        )

    elif 4 < change <= 7:
        action_score += 5
        caution_reasons.append(
            f"前日比 +{change:.2f}%で高値追い注意"
        )

    elif change > 7:
        action_score -= 15
        caution_reasons.append(
            f"前日比 +{change:.2f}%で急騰後"
        )

    elif change < -5:
        action_score -= 20
        caution_reasons.append(
            f"前日比 {change:.2f}%で急落中"
        )

    if optimized_match:
        action_score += 20
        positive_reasons.append(
            "最適シグナル条件に一致"
        )

    action_score -= int(
        risk_score * 0.25
    )

    action_score = max(
        min(
            action_score,
            100,
        ),
        0,
    )

    if (
        optimized_match
        and action_score >= 55
    ):
        judgement = "優先監視"

    elif (
        action_score >= 70
        and risk_level != "高"
    ):
        judgement = "買い候補"

    elif action_score >= 50:
        judgement = "押し目待ち"

    elif action_score >= 30:
        judgement = "様子見"

    else:
        judgement = "見送り"

    if (
        rsi >= 80
        or change >= 8
    ):
        timing = "急騰直後のため追いかけず、押し目を待つ"

    elif (
        macd == "BUY"
        and 45 <= rsi <= 70
        and change > 0
    ):
        timing = "翌営業日の寄り付き後、値動きを確認"

    elif optimized_match:
        timing = "翌営業日の反発確認後に監視"

    elif change < 0:
        timing = "下げ止まり確認まで待機"

    else:
        timing = "出来高と株価の継続を確認"

    if judgement in {
        "買い候補",
        "優先監視",
    }:
        loss_cut = round(
            price * 0.97,
            2,
        )

        target_price = round(
            price * 1.05,
            2,
        )

    elif judgement == "押し目待ち":
        loss_cut = round(
            price * 0.96,
            2,
        )

        target_price = round(
            price * 1.04,
            2,
        )

    else:
        loss_cut = None
        target_price = None

    return {
        "銘柄": name,
        "ticker": ticker,
        "価格": round(
            price,
            2,
        ),
        "前日比%": round(
            change,
            2,
        ),
        "出来高倍率": round(
            volume_ratio,
            2,
        ),
        "RSI": round(
            rsi,
            2,
        ),
        "MACD判定": macd,
        "PHOENIX_SCORE": phoenix_score,
        "最適条件一致": optimized_match,
        "AI判断": judgement,
        "AI判断点": action_score,
        "リスク": risk_level,
        "リスク点": risk_score,
        "監視タイミング": timing,
        "参考目標価格": target_price,
        "参考損切価格": loss_cut,
        "プラス材料": " / ".join(
            positive_reasons
        ),
        "注意材料": " / ".join(
            caution_reasons
            + risk_reasons
        ),
        "PHOENIX理由": str(
            row["理由"]
        ),
    }


def create_ai_judgements(
    report_df: pd.DataFrame,
    optimized_tickers: set[str],
) -> pd.DataFrame:
    results = []

    for _, row in report_df.iterrows():
        results.append(
            make_judgement(
                row=row,
                optimized_tickers=optimized_tickers,
            )
        )

    result_df = pd.DataFrame(
        results
    )

    judgement_order = {
        "優先監視": 0,
        "買い候補": 1,
        "押し目待ち": 2,
        "様子見": 3,
        "見送り": 4,
    }

    result_df["判断順"] = (
        result_df["AI判断"]
        .map(judgement_order)
        .fillna(99)
    )

    result_df = (
        result_df.sort_values(
            by=[
                "判断順",
                "AI判断点",
                "PHOENIX_SCORE",
                "出来高倍率",
            ],
            ascending=[
                True,
                False,
                False,
                False,
            ],
        )
        .drop(
            columns=[
                "判断順",
            ]
        )
        .reset_index(drop=True)
    )

    return result_df


def print_results(
    df: pd.DataFrame,
) -> None:
    print()
    print("=" * 100)
    print("PHOENIX AI JUDGEMENT")
    print("=" * 100)

    if df.empty:
        print(
            "AI判断対象がありません。"
        )
        return

    display_columns = [
        "銘柄",
        "ticker",
        "価格",
        "PHOENIX_SCORE",
        "RSI",
        "MACD判定",
        "AI判断",
        "AI判断点",
        "リスク",
        "監視タイミング",
    ]

    print(
        df[
            display_columns
        ]
        .head(TOP_STOCKS)
        .to_string(
            index=False,
        )
    )

    print()
    print("=" * 100)
    print("AI判断詳細 TOP10")
    print("=" * 100)

    for number, row in df.head(10).iterrows():
        print()
        print(
            f"[{number + 1}] "
            f"{row['銘柄']} "
            f"({row['ticker']})"
        )

        print(
            f"判断: {row['AI判断']} "
            f"/ AI判断点: {row['AI判断点']} "
            f"/ リスク: {row['リスク']}"
        )

        print(
            f"監視タイミング: "
            f"{row['監視タイミング']}"
        )

        if pd.notna(
            row["参考目標価格"]
        ):
            print(
                f"参考目標価格: "
                f"{row['参考目標価格']}"
            )

        if pd.notna(
            row["参考損切価格"]
        ):
            print(
                f"参考損切価格: "
                f"{row['参考損切価格']}"
            )

        if row["プラス材料"]:
            print(
                f"プラス材料: "
                f"{row['プラス材料']}"
            )

        if row["注意材料"]:
            print(
                f"注意材料: "
                f"{row['注意材料']}"
            )


def save_results(
    df: pd.DataFrame,
) -> None:
    REPORT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    df.to_csv(
        OUTPUT_FILE,
        index=False,
        encoding="utf-8-sig",
    )

    with open(
        TEXT_OUTPUT_FILE,
        "w",
        encoding="utf-8",
    ) as file:
        file.write(
            "PHOENIX AI JUDGEMENT\n"
        )

        file.write(
            datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            )
        )

        file.write(
            "\n\n"
        )

        for number, row in df.iterrows():
            file.write(
                f"[{number + 1}] "
                f"{row['銘柄']} "
                f"({row['ticker']})\n"
            )

            file.write(
                f"AI判断: {row['AI判断']}\n"
            )

            file.write(
                f"AI判断点: "
                f"{row['AI判断点']}\n"
            )

            file.write(
                f"PHOENIX SCORE: "
                f"{row['PHOENIX_SCORE']}\n"
            )

            file.write(
                f"リスク: {row['リスク']}\n"
            )

            file.write(
                f"監視タイミング: "
                f"{row['監視タイミング']}\n"
            )

            if pd.notna(
                row["参考目標価格"]
            ):
                file.write(
                    f"参考目標価格: "
                    f"{row['参考目標価格']}\n"
                )

            if pd.notna(
                row["参考損切価格"]
            ):
                file.write(
                    f"参考損切価格: "
                    f"{row['参考損切価格']}\n"
                )

            file.write(
                f"プラス材料: "
                f"{row['プラス材料']}\n"
            )

            file.write(
                f"注意材料: "
                f"{row['注意材料']}\n"
            )

            file.write(
                "-" * 70
                + "\n"
            )

    print()
    print(
        f"保存完了 : {OUTPUT_FILE}"
    )

    print(
        f"保存完了 : {TEXT_OUTPUT_FILE}"
    )


def main() -> None:
    print("=" * 100)
    print("PHOENIX AI JUDGEMENT GENERATOR")
    print("=" * 100)

    try:
        report_df, report_file = load_report()

        optimized_tickers = (
            load_optimized_tickers()
        )

        print(
            f"使用レポート : {report_file}"
        )

        print(
            f"判断対象銘柄数 : "
            f"{len(report_df)}"
        )

        print(
            f"最適条件一致銘柄数 : "
            f"{len(optimized_tickers)}"
        )

        result_df = create_ai_judgements(
            report_df=report_df,
            optimized_tickers=optimized_tickers,
        )

        print_results(
            result_df
        )

        save_results(
            result_df
        )

    except Exception as error:
        print(
            f"エラー: {error}"
        )

        raise SystemExit(1)


if __name__ == "__main__":
    main()