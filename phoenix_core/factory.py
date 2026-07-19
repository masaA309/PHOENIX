from __future__ import annotations

from pathlib import Path
from typing import Any

from phoenix_core.broker import BrokerAdapter, PaperBroker


def create_broker(
    config: dict[str, Any],
    root_dir: Path,
) -> BrokerAdapter:
    broker_config = config.get("broker", {})
    broker_type = str(
        broker_config.get("type", "paper")
    ).strip().lower()

    if broker_type != "paper":
        raise ValueError(
            "PHOENIX v7 Step2で利用可能なbroker.typeはpaperのみです"
        )

    state_value = str(
        broker_config.get(
            "state_file",
            "state/v7_paper_broker.json",
        )
    )
    state_path = Path(state_value)
    if not state_path.is_absolute():
        state_path = root_dir / state_path

    return PaperBroker(
        initial_cash_yen=float(
            broker_config.get("initial_cash_yen", 300_000)
        ),
        commission_rate=float(
            broker_config.get("commission_rate", 0.0)
        ),
        state_file=state_path,
    )
