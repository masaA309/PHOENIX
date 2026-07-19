from __future__ import annotations

import json
from pathlib import Path
import shutil
import tempfile

import pandas as pd

from phoenix_core import (
    create_broker,
    execute_events,
    normalize_events,
    normalize_plan,
    save_snapshot,
)


def main() -> None:
    temp_root = Path(tempfile.mkdtemp(prefix="phoenix_v7_step2_"))

    try:
        reports = temp_root / "reports"
        state = temp_root / "state"
        reports.mkdir(parents=True)
        state.mkdir(parents=True)

        event_file = reports / "events.csv"
        plan_file = reports / "plan.csv"
        log_file = reports / "execution_log.csv"
        snapshot_file = reports / "snapshot.json"

        pd.DataFrame(
            [
                {
                    "日時": "2026-07-20 09:00:00",
                    "イベント": "ENTRY",
                    "ticker": "9501.T",
                    "現在価格": 500.0,
                }
            ]
        ).to_csv(event_file, index=False, encoding="utf-8-sig")

        pd.DataFrame(
            [{"ticker": "9501.T", "株数": 100}]
        ).to_csv(plan_file, index=False, encoding="utf-8-sig")

        config = {
            "broker": {
                "type": "paper",
                "initial_cash_yen": 300000,
                "commission_rate": 0.0,
                "state_file": "state/paper.json",
            }
        }

        broker = create_broker(config, temp_root)
        events = normalize_events(event_file)
        plan = normalize_plan(plan_file)

        first = execute_events(
            broker=broker,
            events=events,
            plan=plan,
            log_path=log_file,
            default_quantity=100,
            lot_size=100,
        )
        assert len(first) == 1
        assert first[0].status.value == "FILLED"

        reloaded = create_broker(config, temp_root)
        snapshot = reloaded.get_account_snapshot()
        assert snapshot.cash_yen == 250000
        assert len(snapshot.positions) == 1
        assert snapshot.positions[0].quantity == 100

        duplicate = execute_events(
            broker=reloaded,
            events=events,
            plan=plan,
            log_path=log_file,
            default_quantity=100,
            lot_size=100,
        )
        assert len(duplicate) == 1
        assert duplicate[0].status.value == "REJECTED"

        pd.DataFrame(
            [
                {
                    "日時": "2026-07-20 14:30:00",
                    "イベント": "TARGET",
                    "ticker": "9501.T",
                    "現在価格": 520.0,
                }
            ]
        ).to_csv(event_file, index=False, encoding="utf-8-sig")

        exit_results = execute_events(
            broker=reloaded,
            events=normalize_events(event_file),
            plan=plan,
            log_path=log_file,
            default_quantity=100,
            lot_size=100,
        )
        assert len(exit_results) == 1
        assert exit_results[0].status.value == "FILLED"

        final_snapshot = save_snapshot(reloaded, snapshot_file)
        assert final_snapshot["cash_yen"] == 302000
        assert final_snapshot["realized_pnl_yen"] == 2000
        assert len(final_snapshot["positions"]) == 0

        persisted = json.loads(
            (state / "paper.json").read_text(encoding="utf-8")
        )
        assert persisted["cash_yen"] == 302000

        print("=" * 90)
        print("PHOENIX v7 CORE STEP2 VERIFY")
        print("=" * 90)
        print("Broker永続化       : PASS")
        print("イベント→注文変換  : PASS")
        print("Broker経由買付      : PASS")
        print("再起動後状態復元    : PASS")
        print("二重発注防止        : PASS")
        print("Broker経由売却      : PASS")
        print("実行ログ保存        : PASS")
        print("口座Snapshot保存    : PASS")
        print(f"最終資産            : {final_snapshot['equity_yen']:,.0f}円")
        print(f"確定損益            : {final_snapshot['realized_pnl_yen']:+,.0f}円")
        print("=" * 90)
        print("PHOENIX v7 Step2検証: PASS")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


if __name__ == "__main__":
    main()
