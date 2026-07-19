from __future__ import annotations

from pathlib import Path
import shutil
import tempfile

import pandas as pd

from phoenix_core import (
    OrderRequest,
    OrderSide,
    OrderStatus,
    OrderType,
    PaperBroker,
)
from phoenix_core.portfolio import (
    build_portfolio_summary,
    save_portfolio_outputs,
    update_market_prices,
)


def main() -> None:
    temp_root = Path(
        tempfile.mkdtemp(
            prefix="phoenix_v7_step3_"
        )
    )

    try:
        state_file = temp_root / "state" / "paper.json"
        reports = temp_root / "reports"
        reports.mkdir(parents=True)

        broker = PaperBroker(
            initial_cash_yen=300000,
            state_file=state_file,
        )

        buy = broker.submit_order(
            OrderRequest(
                ticker="4005.T",
                side=OrderSide.BUY,
                quantity=100,
                order_type=OrderType.LIMIT,
                limit_price=500.0,
                client_order_id="STEP3-BUY-001",
            )
        )

        assert buy.status is OrderStatus.FILLED

        quote_file = reports / "quotes.csv"

        pd.DataFrame(
            [
                {
                    "ticker": "4005.T",
                    "最新価格": 525.0,
                }
            ]
        ).to_csv(
            quote_file,
            index=False,
            encoding="utf-8-sig",
        )

        updated = update_market_prices(
            broker,
            quote_file,
        )
        assert updated == 1

        payload = build_portfolio_summary(
            broker
        )

        assert payload["account"]["cash_yen"] == 250000
        assert payload["account"]["market_value_yen"] == 52500
        assert payload["account"]["equity_yen"] == 302500
        assert payload["account"]["unrealized_pnl_yen"] == 2500
        assert payload["account"]["position_count"] == 1
        assert round(
            payload["risk"]["invested_ratio"],
            6,
        ) == round(52500 / 302500, 6)

        summary_path = reports / "summary.json"
        positions_path = reports / "positions.csv"
        report_path = reports / "report.txt"

        saved = save_portfolio_outputs(
            broker=broker,
            summary_path=summary_path,
            positions_path=positions_path,
            report_path=report_path,
        )

        assert summary_path.exists()
        assert positions_path.exists()
        assert report_path.exists()
        assert saved["account"]["equity_yen"] == 302500

        restored = PaperBroker(
            initial_cash_yen=300000,
            state_file=state_file,
        )
        restored_payload = build_portfolio_summary(
            restored
        )
        assert (
            restored_payload["account"]["equity_yen"]
            == 302500
        )

        print("=" * 90)
        print("PHOENIX v7 CORE STEP3 VERIFY")
        print("=" * 90)
        print("Broker口座取得       : PASS")
        print("保有株取得           : PASS")
        print("現在価格更新         : PASS")
        print("買付余力計算         : PASS")
        print("評価額計算           : PASS")
        print("含み損益計算         : PASS")
        print("資産合計計算         : PASS")
        print("投資比率計算         : PASS")
        print("JSON保存             : PASS")
        print("CSV保存              : PASS")
        print("TXT保存              : PASS")
        print("再起動後状態復元     : PASS")
        print(
            f"現在資産             : "
            f"{saved['account']['equity_yen']:,.0f}円"
        )
        print(
            f"含み損益             : "
            f"{saved['account']['unrealized_pnl_yen']:+,.0f}円"
        )
        print("=" * 90)
        print("PHOENIX v7 Step3検証: PASS")
    finally:
        shutil.rmtree(
            temp_root,
            ignore_errors=True,
        )


if __name__ == "__main__":
    main()
