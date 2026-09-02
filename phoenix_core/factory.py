from __future__ import annotations

from pathlib import Path
from typing import Any

from phoenix_core.broker import BrokerAdapter, PaperBroker
from phoenix_core.rakuten_rss_adapter import MockRakutenRssAdapter
from phoenix_core.production_rakuten_rss_adapter import ProductionRakutenRssAdapter
from phoenix_core.production_rakuten_rss_transport import (
    DEFAULT_WORKBOOK_PATH,
    ProductionRakutenRssTransport,
)
from phoenix_core.rakuten_rss_broker import RakutenRssBroker


_OPERATING_MODE_BROKER_PROFILES: dict[str, dict[str, Any]] = {
    "PAPER_SAFE": {
        "broker_type": "paper",
        "transport_mode": "paper",
        "live_trading_enabled": False,
        "production_transport_enabled": False,
        "production_live_fire_armed": False,
    },
    "LIVE_ACTIVE": {
        "broker_type": "rakuten_rss",
        "transport_mode": "production",
        "live_trading_enabled": True,
        "production_transport_enabled": True,
        "production_live_fire_armed": True,
    },
    "LIVE_RECONCILE_ONLY": {
        "broker_type": "rakuten_rss",
        "transport_mode": "production",
        "live_trading_enabled": True,
        "production_transport_enabled": True,
        "production_live_fire_armed": False,
    },
}


def _operating_mode_profile(config: dict[str, Any]) -> dict[str, Any]:
    operating_mode = str(config.get("operating_mode", "PAPER_SAFE")).strip().upper()
    profile = _OPERATING_MODE_BROKER_PROFILES.get(operating_mode)
    if profile is None:
        raise ValueError(
            "operating_mode must be PAPER_SAFE, LIVE_ACTIVE, or LIVE_RECONCILE_ONLY"
        )
    return profile


def create_broker(
    config: dict[str, Any],
    root_dir: Path,
) -> BrokerAdapter:
    broker_config = config.get("broker", {})
    profile = _operating_mode_profile(config)
    broker_type = str(
        broker_config.get("type", profile["broker_type"])
    ).strip().lower()
    transport_mode = str(
        broker_config.get("transport_mode", profile["transport_mode"])
    ).strip().lower()
    live_enabled = bool(
        broker_config.get(
            "live_trading_enabled",
            broker_config.get("live_enabled", profile["live_trading_enabled"]),
        )
    )
    production_transport_enabled = bool(
        broker_config.get("production_transport_enabled", profile["production_transport_enabled"])
    )
    production_live_fire_armed = bool(
        broker_config.get("production_live_fire_armed", profile["production_live_fire_armed"])
    )

    if broker_type != profile["broker_type"]:
        raise ValueError(
            f"operating_mode={str(config.get('operating_mode', '')).strip().upper()} requires broker.type={profile['broker_type']}"
        )
    if transport_mode != profile["transport_mode"]:
        raise ValueError(
            f"operating_mode={str(config.get('operating_mode', '')).strip().upper()} requires transport_mode={profile['transport_mode']}"
        )
    if live_enabled != profile["live_trading_enabled"]:
        raise ValueError(
            f"operating_mode={str(config.get('operating_mode', '')).strip().upper()} requires live_trading_enabled={profile['live_trading_enabled']}"
        )
    if production_transport_enabled != profile["production_transport_enabled"]:
        raise ValueError(
            f"operating_mode={str(config.get('operating_mode', '')).strip().upper()} requires production_transport_enabled={profile['production_transport_enabled']}"
        )
    if production_live_fire_armed != profile["production_live_fire_armed"]:
        raise ValueError(
            f"operating_mode={str(config.get('operating_mode', '')).strip().upper()} requires production_live_fire_armed={profile['production_live_fire_armed']}"
        )

    state_value = str(
        broker_config.get(
            "state_file",
            "state/v7_paper_broker.json"
            if broker_type != "rakuten_rss"
            else "state/v7_rakuten_rss_broker.json",
        )
    )
    state_path = Path(state_value)
    if not state_path.is_absolute():
        state_path = root_dir / state_path

    if broker_type == "paper":
        return PaperBroker(
            initial_cash_yen=float(
                broker_config.get("initial_cash_yen", 300_000)
            ),
            commission_rate=float(
                broker_config.get("commission_rate", 0.0)
            ),
            state_file=state_path,
        )

    if broker_type == "rakuten_rss":
        if transport_mode == "production":
            return RakutenRssBroker(
                initial_cash_yen=float(
                    broker_config.get("initial_cash_yen", 300_000)
                ),
                commission_rate=float(
                    broker_config.get("commission_rate", 0.0)
                ),
                state_file=state_path,
                adapter=ProductionRakutenRssAdapter(
                    live_trading_enabled=live_enabled,
                    production_transport_enabled=production_transport_enabled,
                    transport=ProductionRakutenRssTransport(
                        live_trading_enabled=live_enabled,
                        production_transport_enabled=production_transport_enabled,
                        armed=production_live_fire_armed,
                        workbook_path=DEFAULT_WORKBOOK_PATH,
                        timeout_seconds=int(
                            broker_config.get("timeout_seconds", 300)
                        ),
                    ),
                ),
                live_enabled=live_enabled,
                timeout_seconds=int(
                    broker_config.get("timeout_seconds", 300)
                ),
            )
        if not live_enabled:
            raise ValueError(
                "broker.type=rakuten_rss requires live_trading_enabled=true"
            )
        return RakutenRssBroker(
            initial_cash_yen=float(
                broker_config.get("initial_cash_yen", 300_000)
            ),
            commission_rate=float(
                broker_config.get("commission_rate", 0.0)
            ),
            state_file=state_path,
            adapter=MockRakutenRssAdapter(
                healthy=True,
                live_trading_enabled=True,
            ),
            live_enabled=True,
            timeout_seconds=int(
                broker_config.get("timeout_seconds", 300)
            ),
        )

    raise ValueError(
        "PHOENIX v7 Step47で利用可能なbroker.typeはpaperまたはrakuten_rssです"
    )
