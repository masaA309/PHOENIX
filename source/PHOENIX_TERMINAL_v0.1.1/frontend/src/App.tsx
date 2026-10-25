import { useEffect, useMemo, useState } from "react";
import { MarketChart } from "./components/MarketChart";
import { mockSnapshot } from "./data/mock";
import type { PhoenixSnapshot, WatchItem } from "./types";

const API = "http://127.0.0.1:8765";
const WS = "ws://127.0.0.1:8765/ws/v1/state";

function money(value: number) {
  return new Intl.NumberFormat("ja-JP", {
    style: "currency",
    currency: "JPY",
    maximumFractionDigits: 0,
  }).format(value);
}

function num(value: number, digits = 1) {
  return new Intl.NumberFormat("ja-JP", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(value);
}

function signed(value: number, suffix = "") {
  const prefix = value > 0 ? "+" : "";
  return `${prefix}${num(value, 2)}${suffix}`;
}

function tone(value: number) {
  if (value > 0) return "positive";
  if (value < 0) return "negative";
  return "neutral";
}

function StatusPill({ label, value }: { label: string; value: string }) {
  const ok = ["ONLINE", "OK"].includes(value);
  const muted = ["ISOLATED", "SIMULATED", "NOT_CONNECTED"].includes(value);
  return (
    <div className="status-pill">
      <span className={`dot ${ok ? "ok" : muted ? "muted" : "warn"}`} />
      <span className="status-label">{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function WatchRow({ item, active, onClick }: { item: WatchItem; active: boolean; onClick: () => void }) {
  return (
    <button className={`watch-row ${active ? "active" : ""}`} onClick={onClick} type="button">
      <span>
        <strong>{item.ticker.replace(".T", "")}</strong>
        <small>{item.name}</small>
      </span>
      <span className="watch-price">{num(item.price, 1)}</span>
      <span className={tone(item.change_pct)}>{signed(item.change_pct, "%")}</span>
      <span className="score">{item.score}</span>
      <span className={`signal ${item.signal.toLowerCase()}`}>{item.signal}</span>
    </button>
  );
}

export default function App() {
  const [state, setState] = useState<PhoenixSnapshot>(mockSnapshot);
  const [selected, setSelected] = useState("7203.T");
  const [stream, setStream] = useState<"CONNECTED" | "FALLBACK">("FALLBACK");
  const [clock, setClock] = useState(new Date());

  useEffect(() => {
    const t = window.setInterval(() => setClock(new Date()), 1000);
    return () => window.clearInterval(t);
  }, []);

  useEffect(() => {
    let socket: WebSocket | undefined;
    let closed = false;

    fetch(`${API}/api/v1/snapshot`)
      .then((response) => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return response.json() as Promise<PhoenixSnapshot>;
      })
      .then((snapshot) => {
        if (!closed) setState(snapshot);
      })
      .catch(() => undefined);

    try {
      socket = new WebSocket(WS);
      socket.onopen = () => !closed && setStream("CONNECTED");
      socket.onmessage = (event) => {
        if (closed) return;
        try {
          setState(JSON.parse(event.data) as PhoenixSnapshot);
        } catch {
          setStream("FALLBACK");
        }
      };
      socket.onerror = () => !closed && setStream("FALLBACK");
      socket.onclose = () => !closed && setStream("FALLBACK");
    } catch {
      setStream("FALLBACK");
    }

    return () => {
      closed = true;
      socket?.close();
    };
  }, []);

  const selectedItem = useMemo(
    () => state.watchlist.find((item) => item.ticker === selected) ?? state.watchlist[0],
    [selected, state.watchlist],
  );

  return (
    <main className="terminal-shell">
      <header className="topbar">
        <div className="brand">
          <div className="phoenix-mark">P</div>
          <div>
            <h1>PHOENIX TERMINAL</h1>
            <span>READ-ONLY OBSERVATION CONSOLE · v0.1.1</span>
          </div>
        </div>
        <div className="top-status">
          <span className={`stream ${stream === "CONNECTED" ? "connected" : "fallback"}`}>
            {stream === "CONNECTED" ? "● STREAM" : "○ LOCAL MOCK"}
          </span>
          <span>{state.mode}</span>
          <time>{clock.toLocaleTimeString("ja-JP", { hour12: false })}</time>
        </div>
      </header>

      <section className="status-strip">
        <StatusPill label="PHOENIX" value={state.system.phoenix} />
        <StatusPill label="MARKET" value={state.system.market_data} />
        <StatusPill label="RAKUTEN RSS" value={state.system.rakuten_rss} />
        <StatusPill label="LIVE RUNTIME" value={state.system.live_runtime} />
        <StatusPill label="WATCHDOG" value={state.system.watchdog} />
      </section>

      <div className="dashboard-grid">
        <aside className="panel watch-panel">
          <div className="panel-title">
            <span>WATCHLIST</span>
            <small>PHOENIX SCORE</small>
          </div>
          <div className="watch-head"><span>SYMBOL</span><span>LAST</span><span>CHG</span><span>SCORE</span><span>SIGNAL</span></div>
          <div className="watch-list">
            {state.watchlist.map((item) => (
              <WatchRow key={item.ticker} item={item} active={item.ticker === selectedItem.ticker} onClick={() => setSelected(item.ticker)} />
            ))}
          </div>
        </aside>

        <section className="panel chart-panel">
          <div className="instrument-head">
            <div>
              <span className="instrument-symbol">{selectedItem.ticker.replace(".T", "")}</span>
              <strong>{selectedItem.name}</strong>
              <span className={`instrument-change ${tone(selectedItem.change_pct)}`}>{signed(selectedItem.change_pct, "%")}</span>
            </div>
            <div className="instrument-price">{num(selectedItem.price, 1)}</div>
          </div>
          <MarketChart anchorPrice={selectedItem.price} />
          <div className="chart-footer">
            <span>5m · MOCK OHLCV</span>
            <span>TradingView Lightweight Charts™</span>
          </div>
        </section>

        <aside className="panel account-panel">
          <div className="panel-title"><span>ACCOUNT</span><small>DISPLAY ONLY</small></div>
          <div className="account-equity">
            <small>ESTIMATED EQUITY</small>
            <strong>{money(state.account.equity)}</strong>
          </div>
          <div className="metric-grid">
            <div><small>DAY P/L</small><strong className={tone(state.account.day_pnl)}>{money(state.account.day_pnl)}</strong><span className={tone(state.account.day_pnl_pct)}>{signed(state.account.day_pnl_pct, "%")}</span></div>
            <div><small>UNREALIZED</small><strong className={tone(state.account.unrealized_pnl)}>{money(state.account.unrealized_pnl)}</strong></div>
            <div><small>BUYING POWER</small><strong>{money(state.account.buying_power)}</strong></div>
            <div><small>AUTHORITY</small><strong className="authority">NONE</strong><span>UI cannot trade</span></div>
          </div>
          <div className="safety-card">
            <span>EXECUTION BOUNDARY</span>
            <strong>SEALED</strong>
            <p>No broker mutation path exists in TERMINAL v0.1.</p>
          </div>
        </aside>
      </div>

      <div className="lower-grid">
        <section className="panel table-panel wide">
          <div className="panel-title"><span>POSITIONS</span><small>{state.positions.length} OPEN</small></div>
          <table>
            <thead><tr><th>SYMBOL</th><th>SIDE</th><th>QTY</th><th>AVG</th><th>LAST</th><th>P/L</th><th>P/L %</th></tr></thead>
            <tbody>{state.positions.map((row) => <tr key={row.ticker}><td className="symbol-cell">{row.ticker}</td><td>{row.side}</td><td>{row.qty}</td><td>{num(row.avg_price, 1)}</td><td>{num(row.last, 1)}</td><td className={tone(row.pnl)}>{money(row.pnl)}</td><td className={tone(row.pnl_pct)}>{signed(row.pnl_pct, "%")}</td></tr>)}</tbody>
          </table>
        </section>

        <section className="panel table-panel">
          <div className="panel-title"><span>ACTIVE ORDERS</span><small>OBSERVATION</small></div>
          <table>
            <thead><tr><th>TIME</th><th>SYMBOL</th><th>SIDE</th><th>QTY</th><th>TYPE</th><th>PRICE</th><th>STATUS</th></tr></thead>
            <tbody>{state.orders.map((row, index) => <tr key={`${row.ticker}-${index}`}><td>{row.time}</td><td className="symbol-cell">{row.ticker}</td><td className={row.side === "BUY" ? "positive" : "negative"}>{row.side}</td><td>{row.qty}</td><td>{row.type}</td><td>{num(row.price, 1)}</td><td><span className="status-tag">{row.status}</span></td></tr>)}</tbody>
          </table>
        </section>

        <section className="panel table-panel">
          <div className="panel-title"><span>EXECUTIONS</span><small>FILLS</small></div>
          <table>
            <thead><tr><th>TIME</th><th>SYMBOL</th><th>SIDE</th><th>QTY</th><th>PRICE</th><th>STATUS</th></tr></thead>
            <tbody>{state.executions.map((row, index) => <tr key={`${row.ticker}-${index}`}><td>{row.time}</td><td className="symbol-cell">{row.ticker}</td><td className={row.side === "BUY" ? "positive" : "negative"}>{row.side}</td><td>{row.qty}</td><td>{num(row.price, 1)}</td><td><span className="status-tag filled">{row.status}</span></td></tr>)}</tbody>
          </table>
        </section>

        <section className="panel activity-panel wide">
          <div className="panel-title"><span>ACTIVITY / STATE EVENTS</span><small>SOURCE: {state.source}</small></div>
          <div className="event-list">
            {state.events.map((event, index) => <div className="event-row" key={`${event.time}-${index}`}><time>{event.time}</time><span className={`event-level ${event.level.toLowerCase()}`}>{event.level}</span><p>{event.message}</p></div>)}
          </div>
        </section>
      </div>

      <footer>
        <span>PHOENIX TERMINAL v0.1.1 · READ ONLY · NO EXECUTION AUTHORITY</span>
        <span>State UI lane is isolated from AUTO LIVE mutation authority.</span>
      </footer>
    </main>
  );
}
