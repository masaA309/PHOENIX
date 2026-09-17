# QUADRANT — Rakuten RSS READ ONLY bridge

This bridge is observation-only. The workbook contains only these MarketSpeed II RSS functions:

- `RssPositionList()` — domestic cash equity holdings
- `RssCapacityList()` — cash buying power / capacity
- `RssOrderList()` — today's domestic stock order list
- `RssExecutionList()` — today's domestic stock executions

No order, modify, cancel, margin-open/close, or futures-order function is present.

## Windows use

1. Start MarketSpeed II and make MarketSpeed II RSS available.
2. Open `QUADRANT_READONLY_RSS.xlsx` in **Excel** and leave it open.
3. Confirm the Positions/Capacity sheets are populated by RSS.
4. Start the QUADRANT backend in explicit RSS mode:

```bash
cd QUADRANT_TERMINAL_v0.4.0/backend
source .venv/Scripts/activate
QUADRANT_DATA_SOURCE=rss python -m uvicorn app:app --host 0.0.0.0 --port 8765
```

5. Start the frontend as usual and open QUADRANT.

If Excel/RSS/the workbook is unavailable, RSS mode returns an empty `RAKUTEN_RSS_UNAVAILABLE` state. It deliberately does **not** substitute fake portfolio data.

## Boundary

QUADRANT reads cells only. It does not press an order trigger, call a VBA order function, submit/cancel/modify an order, or hold broker mutation authority.
