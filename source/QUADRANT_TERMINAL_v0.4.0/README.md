# QUADRANT TERMINAL v0.4.0

Unified read-only observation UI for the QUADRANT family.

- VERMILION — JAPAN EQUITIES — internal engine: PHOENIX
- AZURE — FX — internal engine: SEIRYU
- WHITE TIGER — GOLD — internal engine: BYAKKO
- BLACK WARRIOR — US INDICES — internal engine: GENBU

Internal engine names and execution authority are unchanged. QUADRANT remains READ ONLY.

## v0.4.0

### Rakuten account READ ONLY bridge

A dedicated Excel workbook is included at:

`rss/QUADRANT_READONLY_RSS.xlsx`

It uses only `RssPositionList`, `RssCapacityList`, `RssOrderList`, and `RssExecutionList`. The backend attaches to the workbook already open in Excel and reads the current MarketSpeed II RSS session's domestic-stock account data.

In explicit RSS mode, failure to connect returns an empty unavailable state. It never silently replaces a failed REAL account connection with mock holdings.

See `rss/README_RSS.md` for the short setup.

### UI refinement

- REAL RSS / MOCK / RSS OFFLINE is always visible.
- Holdings search by code/name/account type.
- Sort holdings by P/L, market value, or ticker.
- Privacy toggle masks balances and P/L on screen.
- Account type badges (e.g. 特定 / NISA).
- Current RSS buying power is surfaced in the holdings metrics.
- Stale-data warning after 10 seconds without a REAL snapshot update.
- When only account RSS is connected, PHOENIX SCORE/ranking is intentionally hidden rather than fabricated.
- Existing mobile fullscreen chart, responsive layout, dark-first theme, guardian icons, and system switcher remain.

## Start frontend

```bash
cd QUADRANT_TERMINAL_v0.4.0/frontend
npm install
npm run dev -- --host 0.0.0.0
```

## Start backend — mock UI

```bash
cd QUADRANT_TERMINAL_v0.4.0/backend
source .venv/Scripts/activate
python -m pip install -r requirements.txt
python -m uvicorn app:app --host 0.0.0.0 --port 8765
```

## Start backend — REAL Rakuten RSS READ ONLY

Open `rss/QUADRANT_READONLY_RSS.xlsx` in Excel first, then:

```bash
cd QUADRANT_TERMINAL_v0.4.0/backend
source .venv/Scripts/activate
QUADRANT_DATA_SOURCE=rss python -m uvicorn app:app --host 0.0.0.0 --port 8765
```

The backend exposes only GET endpoints plus the state WebSocket. There are no POST/PUT/PATCH/DELETE order routes.
