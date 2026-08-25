import unittest

import price_monitor


class BuyPriceAlertConditionTest(unittest.TestCase):
    def test_a_crossing_above_stop_triggers_buy_alert(self) -> None:
        self.assertTrue(
            price_monitor.should_trigger_buy_price_alert(
                previous_price=2200,
                current_price=2160,
                entry_price=2171,
                stop_price=2149,
            )
        )

    def test_b_below_stop_blocks_buy_alert(self) -> None:
        self.assertFalse(
            price_monitor.should_trigger_buy_price_alert(
                previous_price=2200,
                current_price=2141,
                entry_price=2171,
                stop_price=2149,
            )
        )

    def test_c_same_price_below_stop_blocks_buy_alert(self) -> None:
        self.assertFalse(
            price_monitor.should_trigger_buy_price_alert(
                previous_price=2141,
                current_price=2141,
                entry_price=2171,
                stop_price=2149,
            )
        )

    def test_d_same_price_repeat_does_not_retrigger(self) -> None:
        self.assertTrue(
            price_monitor.should_trigger_buy_price_alert(
                previous_price=2200,
                current_price=2160,
                entry_price=2171,
                stop_price=2149,
            )
        )
        self.assertFalse(
            price_monitor.should_trigger_buy_price_alert(
                previous_price=2160,
                current_price=2160,
                entry_price=2171,
                stop_price=2149,
            )
        )

    def test_initial_observation_can_trigger_when_previous_price_is_missing(self) -> None:
        self.assertTrue(
            price_monitor.should_trigger_buy_price_alert(
                previous_price=0,
                current_price=2160,
                entry_price=2171,
                stop_price=2149,
            )
        )


if __name__ == "__main__":
    unittest.main()
