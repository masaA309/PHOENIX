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
  /** 信用新規建余力（自動振替含む）。信用口座未開設/未取得は null */
  margin_power?: number | null;
  /** 保証金率（新規建） */
  margin_ratio?: number | null;
}

export interface WatchItem {
  ticker: string;
  name: string;
  price: number;
  change_pct: number;
  score: number | null;
  signal: string;
}

export interface RankingItem extends WatchItem {
  rank: number;
  origin?: "MORNING" | "INTRADAY";
  discovered_at?: string;
  discovery_reason?: string;
  promotion_status?: string;
  phoenix_score?: number;
  ai_score?: number;
  rank_label?: string;
  watch_status?: string;
  risk?: string;
  rsi?: number;
  macd?: string;
  volume_ratio?: number;
  expected_win_rate?: number;
  reason?: string;
  technical_reason?: string;
  learning_reason?: string;
  phoenix_reason?: string;
  plus_material?: string;
  caution_material?: string;
  monitor_timing?: string;
  base_price?: number;
  entry_price?: number;
  target_price?: number;
  stop_price?: number;
  trade_decision?: string;
  decision_reason?: string;
  market_risk_score?: number;
  market_risk_level?: string;
  artifact_generated_at?: string;
}

export type ChartTimeframe = "5m" | "15m" | "60m" | "4h" | "1d";

export interface ChartBar {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  ma5?: number | null;
  ma25?: number | null;
  ma75?: number | null;
  ema12?: number | null;
  ema26?: number | null;
  rsi14?: number | null;
  macd?: number | null;
  macd_signal?: number | null;
}

export interface ChartPayload {
  ticker: string;
  timeframe: ChartTimeframe;
  rss_timeframe: string;
  derived: boolean;
  derived_note: string;
  source: string;
  mode: string;
  as_of: string;
  bars: ChartBar[];
  indicators: {
    basis: string;
    ma5?: number | null;
    ma25?: number | null;
    ma75?: number | null;
    ema12?: number | null;
    ema26?: number | null;
    rsi14?: number | null;
    macd?: number | null;
    macd_signal?: number | null;
  };
}

export interface Position {
  ticker: string;
  name?: string;
  side: "LONG" | "SHORT" | "NOT_PROVEN" | string;
  execution?: "CASH" | "MARGIN" | "NOT_PROVEN" | string;
  status?: "HOLDING" | "TRAILING" | "EXIT_PENDING" | "NOT_PROVEN" | string;
  current_stop?: number;
  current_r?: number;
  v_lock_display?: "ACTIVE" | "INACTIVE" | "NOT_PROVEN" | string;
  qty: number;
  avg_price: number;
  last: number;
  pnl: number;
  pnl_pct: number;
  market_value?: number;
  account_type?: string;
  pending_qty?: number;
  day_change?: number;
  /** VERMILION 制度信用LONG（runner state 由来） */
  engine?: "VERMILION" | string;
  source?: "LIVE" | "SHADOW" | string;
  initial_stop?: number;
  pending_stop?: number;
  initial_r?: number;
  locked_r?: number | null;
  held_sessions?: number;
  max_hold_sessions?: number;
  time_exit_due?: boolean;
  open_date?: string;
  price_status?: "NOT_PROVEN" | string;
}

export type GateState = "CLOSED" | "OPEN" | "NOT_PROVEN" | string;

export interface VermilionPlan {
  ticker: string;
  quantity: number;
  limit_price: number;
  signal_date?: string;
  submitted?: boolean;
}

export interface VermilionState {
  available: boolean;
  mode: "LIVE" | "SHADOW" | "NOT_CONNECTED" | "ERROR" | string;
  gates?: { route: GateState; broker_live: GateState; armed: GateState };
  positions: Position[];
  planned: VermilionPlan[];
  events: EventRow[];
  equity_paper?: number;
  last_eod?: string;
  updated_at?: string;
  stale?: boolean;
  latest_report?: string;
  error?: string;
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

export interface ArtifactProvenance {
  name?: string;
  path: string;
  exists?: boolean;
  rows?: number;
  generated_at: string;
  stale?: boolean;
  sha256?: string;
}

export interface SnapshotMeta {
  workbook?: string;
  account_scope?: string;
  analysis_available?: boolean;
  analysis_generated_at?: string;
  analysis_stale?: boolean;
  analysis_source?: string;
  analysis_count?: number;
  analysis_error?: string;
  analysis_consistency?: string;
  analysis_lineage?: string;
  analysis_artifacts?: Record<string, ArtifactProvenance>;
  intraday_available?: boolean;
  intraday_generated_at?: string;
  intraday_stale?: boolean;
  intraday_count?: number;
  intraday_source?: string;
  intraday_artifact?: ArtifactProvenance;
  provenance_mode?: string;
  equity_basis?: string;
  short_runtime?: "CONNECTED" | "NOT_CONNECTED" | string;
  error?: string;
}

export interface PhoenixSnapshot {
  mode: string;
  source: string;
  as_of: string;
  system: SystemState;
  account: AccountState;
  watchlist: WatchItem[];
  ranking?: RankingItem[];
  intraday_candidates?: RankingItem[];
  positions: Position[];
  orders: OrderRow[];
  executions: ExecutionRow[];
  events: EventRow[];
  meta?: SnapshotMeta;
  vermilion?: VermilionState;
}
