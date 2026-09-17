# PHOENIX TERMINAL v0.1

Read-only desktop trading terminal scaffold for PHOENIX.

## Safety boundary

This version has **no order submission, cancel, replace, broker, Rakuten RSS, or LiveRuntime mutation path**.
It only renders state received from a local read-only API/WebSocket and falls back to bundled mock data if that service is unavailable.

## Layout

- `backend/` — FastAPI read-only mock state API + WebSocket stream
- `frontend/` — React + TypeScript + Vite UI
- `frontend/src-tauri/` — Tauri 2 Windows desktop shell

## Windows prerequisites

Tauri 2 on Windows requires Microsoft C++ Build Tools, WebView2, Rust (MSVC toolchain), and Node.js.

## Run backend

From Git Bash:

```bash
cd PHOENIX_TERMINAL_v0.1/backend
python -m venv .venv
source .venv/Scripts/activate
python -m pip install -r requirements.txt
python -m uvicorn app:app --host 127.0.0.1 --port 8765
```

Health check:

```bash
curl http://127.0.0.1:8765/health
```

## Run web UI first

Open another Git Bash:

```bash
cd PHOENIX_TERMINAL_v0.1/frontend
npm install
npm run dev
```

Then open:

```text
http://localhost:1420
```

## Run as Tauri desktop app

After Rust + Visual Studio C++ Build Tools are installed:

```bash
cd PHOENIX_TERMINAL_v0.1/frontend
npm install
npm run tauri dev
```

## Production build

```bash
cd PHOENIX_TERMINAL_v0.1/frontend
npm run build
npm run tauri build
```

## PHOENIX integration rule

The future integration should expose a read-only snapshot/stream adapter from PHOENIX state authority. Do not let this UI import or call broker mutation, Rakuten RSS order functions, or LiveRuntime mutation methods directly.
