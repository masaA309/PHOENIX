export type ConnectionStatus = "ONLINE" | "OFFLINE" | "OK" | "SIMULATED" | "NOT_CONNECTED" | "ISOLATED" | string;

export interface SystemState {
  phoenix: ConnectionStatus;
  market_data: ConnectionStatus;
  rakuten_rss: ConnectionStatus;
  live_runtime: ConnectionStatus;
  watchdog: ConnectionStatus;
}

export interface AccountState {
  equity: number;
  buying_power: number;
  day_pnl: number;
  day_pnl_pct: number;
  unrealized_pnl: number;
}

export interface WatchItem {
  ticker: string;
  name: string;
  price: number;
  change_pct: number;
  score: number;
  signal: string;
}

export interface Position {
  ticker: string;
  side: string;
  qty: number;
  avg_price: number;
  last: number;
  pnl: number;
  pnl_pct: number;
}

export interface OrderRow {
  time: string;
  ticker: string;
  side: string;
  qty: number;
  type: string;
  price: number;
  status: string;
}

export interface ExecutionRow {
  time: string;
  ticker: string;
  side: string;
  qty: number;
  price: number;
  status: string;
}

export interface EventRow {
  time: string;
  level: string;
  message: string;
}

export interface PhoenixSnapshot {
  mode: string;
  source: string;
  as_of: string;
  system: SystemState;
  account: AccountState;
  watchlist: WatchItem[];
  positions: Position[];
  orders: OrderRow[];
  executions: ExecutionRow[];
  events: EventRow[];
}
