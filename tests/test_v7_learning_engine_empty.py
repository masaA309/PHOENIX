from __future__ import annotations

import json
from pathlib import Path
import unittest

import pandas as pd

from learning_engine import build_adjustments, build_statistics


class LearningEngineEmptyInputTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = json.loads(
            Path("config/learning_config.json").read_text(encoding="utf-8-sig")
        )

    def test_empty_trade_frame_returns_schema_and_no_adjustments(self) -> None:
        columns = [
            "pnl", "rsi", "ai_score", "phoenix_score", "volume_ratio",
            "holding_days", "macd", "market_regime", "entry_reason", "exit_reason",
        ]
        stats = build_statistics(pd.DataFrame(columns=columns), self.config)
        self.assertTrue(stats.empty)
        self.assertIn("dimension", stats.columns)
        self.assertIn("direction", stats.columns)
        adjustments = build_adjustments(stats, self.config)
        self.assertEqual({}, adjustments["adjustments"])
        self.assertEqual({}, adjustments["evidence"])

    def test_empty_input_is_deterministic(self) -> None:
        data = pd.DataFrame(columns=["pnl", "rsi"])
        first = build_statistics(data, self.config)
        second = build_statistics(data, self.config)
        pd.testing.assert_frame_equal(first, second)


if __name__ == "__main__":
    unittest.main()
