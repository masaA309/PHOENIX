# QUADRANT TERMINAL v0.3.2

QUADRANT is the user-facing unified trading terminal brand. The existing trading engines and repositories are **not renamed** by this UI revision.

## User-facing modules

- **VERMILION** — JAPAN EQUITIES → internal engine: `PHOENIX`
- **AZURE** — FX → internal engine: `SEIRYU`
- **WHITE TIGER** — GOLD → internal engine: `BYAKKO`
- **BLACK WARRIOR** — US INDICES → internal engine: `GENBU`

This separation is deliberate. QUADRANT is a shared read-only observation/switching layer; runtime, state, config, repository and order authority remain isolated per engine.

## v0.3.2 changes

- Replaced the former SHISHIN / Japanese-beast UI branding with **QUADRANT**.
- Replaced user-facing module labels with VERMILION / AZURE / WHITE TIGER / BLACK WARRIOR.
- Kept `phoenix`, `seiryu`, `byakko`, `genbu` engine ids and the PHOENIX API schema unchanged.
- Kept the legacy `shishin-theme` browser storage key so an existing dark/light preference is not lost during the branding change.
- Settings show `VERMILION / PHOENIX ENGINE` for diagnostics so the UI-to-engine mapping remains explicit.
- Dark remains the default appearance; Light and Auto/System remain available.
- Carries forward v0.3.1 behavior: portfolio metrics only on Holdings, mobile chart fullscreen, ranking reasons, decision/caution/re-evaluation/invalidation blocks, and MOCK/REAL/READ ONLY/updated status.

## Frontend

From Git Bash, after extracting under the PHOENIX folder:

```bash
cd "/c/Users/ashtc/OneDrive/デスクトップ/ちちのフォルダ/PHOENIX/QUADRANT_TERMINAL_v0.3.2/frontend"
npm install
npm run dev -- --host 0.0.0.0
```

Open the `Local:` URL on the PC. On an iPhone connected to the same Wi-Fi, open the actual `Network:` URL shown by Vite.

## Read-only backend

The included adapter backend remains read-only. It exposes snapshot/health/WebSocket observation only and contains no order-submit, cancel, replace, broker-mutation or LiveRuntime-authority endpoint.

If the compatible v0.3.x backend is already running on port 8765, the v0.3.2 frontend can be checked against it without changing PHOENIX.

To run the included backend separately:

```bash
cd "/c/Users/ashtc/OneDrive/デスクトップ/ちちのフォルダ/PHOENIX/QUADRANT_TERMINAL_v0.3.2/backend"
"/c/Users/ashtc/AppData/Local/Programs/Python/Python313/python.exe" -m venv .venv
source .venv/Scripts/activate
python -m pip install -r requirements.txt
python -m uvicorn app:app --host 0.0.0.0 --port 8765
```

Do not recreate the PHOENIX root `.venv` as part of this UI setup.

## Safety boundary

`QUADRANT UI → read-only adapter → engine state`

QUADRANT does not receive broker mutation authority. Existing PHOENIX / SEIRYU runtime and policy boundaries are not altered by this package.
