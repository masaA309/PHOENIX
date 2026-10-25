export type ConnectionStatus = "ONLINE" | "OFFLINE" | "OK" | "SIMULATED" | "NOT_CONNECTED" | "ISOLATED" | "CONNECTED" | "REAL" | "UNAVAILABLE" | "UNKNOWN" | string;

export interface SystemState {
  phoenix: ConnectionStatus;
  market_data: ConnectionStatus;
  rakuten_rss: ConnectionStatus;
  live_runtime: ConnectionStatus;
  watchdog: ConnectionStatus;
  analysis?: ConnectionStatus;
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
  score: number | null;
  signal: string;
}

export interface Position {
  ticker: string;
  name?: string;
  side: string;
  qty: number;
  avg_price: number;
  last: number;
  pnl: number;
  pnl_pct: number;
  market_value?: number;
  account_type?: string;
  pending_qty?: number;
  day_change?: number;
}

export interface OrderRow {
  time: string;
  ticker: string;
  side: string;
  qty: number;
  type: string;
  price: number | string;
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

export interface SnapshotMeta {
  workbook?: string;
  account_scope?: string;
  analysis_available?: boolean;
  equity_basis?: string;
  error?: string;
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
  meta?: SnapshotMeta;
}
