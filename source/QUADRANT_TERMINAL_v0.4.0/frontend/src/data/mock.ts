import type { PhoenixSnapshot } from "../types";

export const mockSnapshot: PhoenixSnapshot = {
  mode: "READ_ONLY",
  source: "BUNDLED_MOCK",
  as_of: new Date().toISOString(),
  system: {
    phoenix: "ONLINE",
    market_data: "SIMULATED",
    rakuten_rss: "NOT_CONNECTED",
    live_runtime: "ISOLATED",
    watchdog: "OK",
    analysis: "MOCK",
  },
  account: {
    equity: 4_862_430,
    buying_power: 1_725_000,
    day_pnl: 28_460,
    day_pnl_pct: 0.59,
    unrealized_pnl: 41_700,
  },
  watchlist: [
    { ticker: "7203.T", name: "Toyota", price: 3018.0, change_pct: 1.24, score: 92, signal: "BUY" },
    { ticker: "8306.T", name: "MUFG", price: 2365.5, change_pct: 0.82, score: 87, signal: "WATCH" },
    { ticker: "9984.T", name: "SoftBank G", price: 17120.0, change_pct: -0.31, score: 78, signal: "HOLD" },
    { ticker: "6758.T", name: "Sony G", price: 3248.0, change_pct: 0.46, score: 84, signal: "BUY" },
    { ticker: "6501.T", name: "Hitachi", price: 4483.0, change_pct: 1.03, score: 89, signal: "WATCH" },
  ],
  positions: [
    { ticker: "7203.T", name: "Toyota", side: "LONG", qty: 100, avg_price: 2945.0, last: 3018.0, pnl: 7300, pnl_pct: 2.48, market_value: 301800, account_type: "特定", pending_qty: 0 },
    { ticker: "8306.T", name: "MUFG", side: "LONG", qty: 200, avg_price: 2310.0, last: 2365.5, pnl: 11100, pnl_pct: 2.4, market_value: 473100, account_type: "NISA", pending_qty: 0 },
  ],
  orders: [
    { time: "14:31:52", ticker: "6758.T", side: "BUY", qty: 100, type: "LIMIT", price: 3240.0, status: "SUBMITTED" },
    { time: "14:29:18", ticker: "7203.T", side: "SELL", qty: 100, type: "STOP", price: 2970.0, status: "WORKING" },
  ],
  executions: [
    { time: "13:42:05", ticker: "8306.T", side: "BUY", qty: 200, price: 2310.0, status: "FILLED" },
    { time: "09:14:33", ticker: "7203.T", side: "BUY", qty: 100, price: 2945.0, status: "FILLED" },
  ],
  meta: { analysis_available: true, account_scope: "mock", equity_basis: "mock" },
  events: [
    { time: "14:31:53", level: "INFO", message: "6758.T BUY request accepted by mock adapter" },
    { time: "14:30:21", level: "INFO", message: "7203.T quote update received" },
    { time: "14:29:04", level: "PASS", message: "Risk policy observation: PASS (display only)" },
    { time: "09:00:00", level: "INFO", message: "QUADRANT / VERMILION read-only session started (PHOENIX engine)" },
  ],
};
