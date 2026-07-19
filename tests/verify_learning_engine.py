from pathlib import Path
import json
import subprocess
import sys
import tempfile

import pandas as pd


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    engine = root / "learning_engine.py"
    config = root / "config" / "learning_config.json"

    rows = []
    for i in range(40):
        strong = i < 20
        pnl = 700 if strong and i % 5 != 0 else (-250 if strong else (-550 if i % 4 != 0 else 300))
        rows.append({
            "取引ID": i + 1,
            "ticker": f"{1000+i}.T",
            "AI判断点": 92 if strong else 64,
            "PHOENIX_SCORE": 95 if strong else 65,
            "RSI": 52 if strong else 76,
            "MACD判定": "BUY" if strong else "SELL",
            "出来高倍率": 2.3 if strong else 0.8,
            "地合い": "BULL" if strong else "BEAR",
            "保有日数": 3,
            "損益額": pnl,
            "損益率%": pnl / 1000,
            "勝敗": "勝" if pnl > 0 else "負",
            "エントリー理由": "trend" if strong else "rebound",
            "決済理由": "take_profit" if pnl > 0 else "stop_loss",
        })

    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        input_csv = td / "paper_learning_data.csv"
        report_dir = td / "reports"
        pd.DataFrame(rows).to_csv(input_csv, index=False, encoding="utf-8-sig")

        completed = subprocess.run(
            [
                sys.executable,
                str(engine),
                "--input",
                str(input_csv),
                "--config",
                str(config),
                "--report-dir",
                str(report_dir),
            ],
            cwd=root,
            text=True,
            capture_output=True,
            encoding="utf-8",
        )
        if completed.returncode != 0:
            print(completed.stdout)
            print(completed.stderr)
            return completed.returncode

        required = (
            report_dir / "learning_summary.csv",
            report_dir / "learning_statistics.csv",
            report_dir / "learning_adjustments.json",
            report_dir / "learning_report.txt",
        )
        for path in required:
            if not path.exists():
                raise AssertionError(f"出力不足: {path}")

        stats = pd.read_csv(report_dir / "learning_statistics.csv", encoding="utf-8-sig")
        high_ai = stats[(stats["dimension"] == "AI_SCORE") & (stats["group"] == "90-100")]
        low_ai = stats[(stats["dimension"] == "AI_SCORE") & (stats["group"] == "60-69")]
        assert not high_ai.empty
        assert not low_ai.empty
        assert high_ai.iloc[0]["judgement"] == "強化"
        assert low_ai.iloc[0]["judgement"] == "抑制"

        adjustments = json.loads(
            (report_dir / "learning_adjustments.json").read_text(encoding="utf-8")
        )
        assert adjustments["adjustments"]["AI_SCORE"]["90-100"] > 0
        assert adjustments["adjustments"]["AI_SCORE"]["60-69"] < 0

    print("PHOENIX v6.9.1 Japanese schema verification: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
