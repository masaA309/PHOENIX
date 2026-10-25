import { useEffect, useMemo, useState, type CSSProperties } from "react";
import { MarketChart } from "./components/MarketChart";
import { mockSnapshot } from "./data/mock";
import type { ChartPayload, ChartTimeframe, PhoenixSnapshot, Position, RankingItem, WatchItem } from "./types";

const PAGE_HOST = window.location.hostname;
const IS_TAURI = PAGE_HOST === "tauri.localhost";
const API_HOST = import.meta.env.VITE_SHISHIN_API_HOST || (IS_TAURI ? "127.0.0.1" : PAGE_HOST) || "127.0.0.1";
const API_PROTOCOL = IS_TAURI ? "http:" : window.location.protocol === "https:" ? "https:" : "http:";
const WS_PROTOCOL = IS_TAURI ? "ws:" : window.location.protocol === "https:" ? "wss:" : "ws:";
const API = `${API_PROTOCOL}//${API_HOST}:8765`;
const WS = `${WS_PROTOCOL}//${API_HOST}:8765/ws/v1/state`;

type BeastId = "phoenix" | "seiryu" | "byakko" | "genbu";
type MainTab = "holdings" | "summary" | "ranking";
type ThemeChoice = "system" | "light" | "dark";
type HoldingsSort = "pnl" | "value" | "ticker";

type Beast = {
  id: BeastId;
  icon: string;
  uiName: string;
  internalEngine: string;
  market: string;
  accent: string;
  accent2: string;
  status: "ACTIVE" | "PLANNED";
};

// UI branding is intentionally separated from the existing engine/project names.
// engine ids, API schema, runtime names and order authority are NOT renamed here.
const beasts: Beast[] = [
  { id: "phoenix", icon: "/assets/guardians/vermilion.png", uiName: "VERMILION", internalEngine: "PHOENIX", market: "JAPAN EQUITIES", accent: "#ff5a36", accent2: "#ffb34d", status: "ACTIVE" },
  { id: "seiryu", icon: "/assets/guardians/azure.png", uiName: "AZURE", internalEngine: "SEIRYU", market: "FX", accent: "#22c7c7", accent2: "#4f8cff", status: "PLANNED" },
  { id: "byakko", icon: "/assets/guardians/white-tiger.png", uiName: "WHITE TIGER", internalEngine: "BYAKKO", market: "GOLD", accent: "#d8b86a", accent2: "#f2f3f5", status: "PLANNED" },
  { id: "genbu", icon: "/assets/guardians/black-warrior.png", uiName: "BLACK WARRIOR", internalEngine: "GENBU", market: "US INDICES", accent: "#7c5ce6", accent2: "#33235f", status: "PLANNED" },
];

const insightByTicker: Record<string, { trend: string; rsi: number; macd: string; volume: string; thesis: string[]; risk: string[] }> = {
  "7203.T": { trend: "STRONG UP", rsi: 61.4, macd: "BUY", volume: "1.42×", thesis: ["中期上昇トレンドを維持", "MA5 > MA25 > MA75", "出来高が平常時より増加"], risk: ["短期過熱が強まれば追随を抑制", "MA25割れを再評価ポイントにする"] },
  "8306.T": { trend: "UP", rsi: 57.8, macd: "POSITIVE", volume: "1.18×", thesis: ["上昇基調を維持", "モメンタムは中立より上", "押し目監視候補"], risk: ["金利材料による急変", "直近安値割れで優先度低下"] },
  "9984.T": { trend: "RANGE", rsi: 48.9, macd: "NEUTRAL", volume: "0.91×", thesis: ["方向感待ち", "スコアは監視圏", "ブレイク確認を優先"], risk: ["ボラティリティ急拡大", "レンジ下限割れ"] },
  "6758.T": { trend: "UP", rsi: 59.2, macd: "BUY", volume: "1.25×", thesis: ["価格と短期MAが上向き", "出来高増加", "モメンタム改善"], risk: ["直近高値での失速", "短期MAデッドクロス"] },
  "6501.T": { trend: "STRONG UP", rsi: 63.1, macd: "BUY", volume: "1.36×", thesis: ["高値圏を維持", "トレンド強度良好", "出来高が追随"], risk: ["過熱圏への接近", "ギャップダウン発生時は再判定"] },
};

function money(value: number) {
  return new Intl.NumberFormat("ja-JP", { style: "currency", currency: "JPY", maximumFractionDigits: 0 }).format(value);
}

function num(value: number, digits = 1) {
  return new Intl.NumberFormat("ja-JP", { minimumFractionDigits: digits, maximumFractionDigits: digits }).format(value);
}

function signed(value: number, suffix = "") {
  return `${value > 0 ? "+" : ""}${num(value, 2)}${suffix}`;
}

function tone(value: number) {
  if (value > 0) return "positive";
  if (value < 0) return "negative";
  return "neutral";
}

function useResolvedTheme(choice: ThemeChoice) {
  const [systemDark, setSystemDark] = useState(() => window.matchMedia?.("(prefers-color-scheme: dark)").matches ?? true);
  useEffect(() => {
    const query = window.matchMedia?.("(prefers-color-scheme: dark)");
    if (!query) return;
    const listener = (event: MediaQueryListEvent) => setSystemDark(event.matches);
    query.addEventListener("change", listener);
    return () => query.removeEventListener("change", listener);
  }, []);
  return choice === "system" ? (systemDark ? "dark" : "light") : choice;
}

function StatusDot({ value }: { value: string }) {
  const ok = ["ONLINE", "OK", "CONNECTED", "REAL"].includes(value);
  const muted = ["ISOLATED", "SIMULATED", "NOT_CONNECTED"].includes(value);
  return <span className={`status-dot ${ok ? "ok" : muted ? "muted" : "warn"}`} />;
}

function MetricCard({ label, value, sub, valueClass = "" }: { label: string; value: string; sub?: string; valueClass?: string }) {
  return (
    <div className="metric-card">
      <span>{label}</span>
      <strong className={valueClass}>{value}</strong>
      {sub ? <small>{sub}</small> : null}
    </div>
  );
}

function EmptySystem({ beast }: { beast: Beast }) {
  return (
    <section className="coming-card panel">
      <div className="coming-glyph"><img src={beast.icon} alt="" /></div>
      <span>QUADRANT MODULE</span>
      <h2>{beast.uiName}</h2>
      <p>{beast.market}</p>
      <div className="coming-state">INTERFACE SHELL READY · ENGINE NOT CONNECTED</div>
      <p className="coming-copy">QUADRANTの共通UIだけ先に確認できます。実データ・実注文経路は接続していません。</p>
    </section>
  );
}

function App() {
  const [state, setState] = useState<PhoenixSnapshot>(mockSnapshot);
  const [stream, setStream] = useState<"CONNECTED" | "FALLBACK">("FALLBACK");
  const [clock, setClock] = useState(new Date());
  const [activeBeast, setActiveBeast] = useState<BeastId>("phoenix");
  const [tab, setTab] = useState<MainTab>("holdings");
  const [selectedTicker, setSelectedTicker] = useState("7203.T");
  const [beastMenuOpen, setBeastMenuOpen] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [chartFullscreen, setChartFullscreen] = useState(false);
  const [chartTimeframe, setChartTimeframe] = useState<ChartTimeframe>("5m");
  const [chartData, setChartData] = useState<ChartPayload | null>(null);
  const [chartError, setChartError] = useState("");
  const [chartLoading, setChartLoading] = useState(false);
  const [holdingsQuery, setHoldingsQuery] = useState("");
  const [holdingsSort, setHoldingsSort] = useState<HoldingsSort>("pnl");
  const [balancesHidden, setBalancesHidden] = useState(() => localStorage.getItem("quadrant-hide-balances") === "1");
  const [themeChoice, setThemeChoice] = useState<ThemeChoice>(() => (localStorage.getItem("shishin-theme") as ThemeChoice) || "dark"); // keep legacy key so existing preference survives branding change
  const resolvedTheme = useResolvedTheme(themeChoice);
  const beast = beasts.find((item) => item.id === activeBeast) ?? beasts[0];

  useEffect(() => {
    localStorage.setItem("shishin-theme", themeChoice);
  }, [themeChoice]);

  useEffect(() => {
    localStorage.setItem("quadrant-hide-balances", balancesHidden ? "1" : "0");
  }, [balancesHidden]);

  useEffect(() => {
    document.body.classList.toggle("chart-fullscreen-open", chartFullscreen);
    const onKey = (event: KeyboardEvent) => { if (event.key === "Escape") setChartFullscreen(false); };
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.classList.remove("chart-fullscreen-open");
      window.removeEventListener("keydown", onKey);
    };
  }, [chartFullscreen]);

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
      .then((snapshot) => !closed && setState(snapshot))
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
    () => state.watchlist.find((item) => item.ticker === selectedTicker)
      ?? state.ranking?.find((item) => item.ticker === selectedTicker)
      ?? state.watchlist[0]
      ?? state.ranking?.[0],
    [selectedTicker, state.watchlist, state.ranking],
  );
  const selectedPosition = useMemo(() => {
    const lots = state.positions.filter((item) => item.ticker === selectedItem?.ticker);
    if (!lots.length) return undefined;
    const qty = lots.reduce((sum, item) => sum + item.qty, 0);
    const cost = lots.reduce((sum, item) => sum + item.avg_price * item.qty, 0);
    const pnl = lots.reduce((sum, item) => sum + item.pnl, 0);
    const last = lots[0]?.last ?? 0;
    const avgPrice = qty ? cost / qty : 0;
    return { ...lots[0], qty, avg_price: avgPrice, last, pnl, pnl_pct: avgPrice ? (last / avgPrice - 1) * 100 : 0 };
  }, [selectedItem?.ticker, state.positions]);
  const ranked = useMemo(
    () => state.ranking?.length
      ? [...state.ranking].sort((a, b) => a.rank - b.rank)
      : state.watchlist.filter((item) => item.score !== null).sort((a, b) => (b.score ?? -1) - (a.score ?? -1)),
    [state.ranking, state.watchlist],
  );
  const selectedAnalysis = useMemo<RankingItem | undefined>(
    () => state.ranking?.find((item) => item.ticker === selectedItem?.ticker),
    [selectedItem?.ticker, state.ranking],
  );
  const selectableItems = useMemo(() => {
    const byTicker = new Map<string, WatchItem>();
    for (const item of state.ranking ?? []) byTicker.set(item.ticker, item);
    for (const item of state.watchlist) byTicker.set(item.ticker, { ...byTicker.get(item.ticker), ...item, score: byTicker.get(item.ticker)?.score ?? item.score });
    return [...byTicker.values()];
  }, [state.ranking, state.watchlist]);
  const insight = selectedItem ? insightByTicker[selectedItem.ticker] : undefined;
  const isMock = state.source.includes("MOCK") || state.system.market_data === "SIMULATED";
  const isRealRss = state.source === "RAKUTEN_RSS_EXCEL";
  const rssUnavailable = state.source === "RAKUTEN_RSS_UNAVAILABLE";
  const analysisAvailable = state.meta?.analysis_available ?? state.system.analysis === "MOCK";
  const analysisStale = state.meta?.analysis_stale ?? false;
  const analysisGeneratedAt = state.meta?.analysis_generated_at ?? "";
  const updatedAt = state.as_of ? new Date(state.as_of) : clock;
  const stale = isRealRss && clock.getTime() - updatedAt.getTime() > 10_000;

  useEffect(() => {
    let cancelled = false;
    if (!isRealRss || tab !== "summary" || !selectedItem?.ticker) {
      setChartData(null);
      setChartError("");
      return () => { cancelled = true; };
    }
    setChartLoading(true);
    setChartError("");
    fetch(`${API}/api/v1/chart/${encodeURIComponent(selectedItem.ticker)}?timeframe=${chartTimeframe}&bars=240`)
      .then(async (response) => {
        if (!response.ok) {
          const detail = await response.json().catch(() => ({})) as { detail?: string };
          throw new Error(detail.detail || `HTTP ${response.status}`);
        }
        return response.json() as Promise<ChartPayload>;
      })
      .then((payload) => { if (!cancelled) setChartData(payload); })
      .catch((error: Error) => { if (!cancelled) { setChartData(null); setChartError(error.message); } })
      .finally(() => { if (!cancelled) setChartLoading(false); });
    return () => { cancelled = true; };
  }, [chartTimeframe, isRealRss, selectedItem?.ticker, tab]);

  const moneyView = (value: number) => balancesHidden ? "••••••" : money(value);
  const filteredPositions = useMemo(() => {
    const query = holdingsQuery.trim().toLowerCase();
    const rows = state.positions.filter((position) => {
      const item = state.watchlist.find((candidate) => candidate.ticker === position.ticker);
      const haystack = `${position.ticker} ${position.name ?? ""} ${item?.name ?? ""} ${position.account_type ?? ""}`.toLowerCase();
      return !query || haystack.includes(query);
    });
    return rows.sort((a, b) => {
      if (holdingsSort === "value") return (b.market_value ?? b.last * b.qty) - (a.market_value ?? a.last * a.qty);
      if (holdingsSort === "ticker") return a.ticker.localeCompare(b.ticker, "ja");
      return b.pnl - a.pnl;
    });
  }, [holdingsQuery, holdingsSort, state.positions, state.watchlist]);

  const openSummary = (ticker: string) => {
    setSelectedTicker(ticker);
    setTab("summary");
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  return (
    <main
      className="app-shell"
      data-theme={resolvedTheme}
      data-beast={beast.id}
      style={{ "--accent": beast.accent, "--accent-2": beast.accent2 } as CSSProperties}
    >
      <header className="app-header">
        <div className="brand-lockup">
          <div className="shishin-mark quadrant-mark"><img src="/quadrant-home-1024.png" alt="QUADRANT" /></div>
          <div className="brand-copy">
            <strong>QUADRANT</strong>
            <small>UNIFIED MULTI-MARKET TRADING TERMINAL · READ ONLY</small>
          </div>
        </div>

        <div className="header-actions">
          <div className="beast-switcher-wrap">
            <button className="beast-switcher" type="button" onClick={() => setBeastMenuOpen((v) => !v)} aria-expanded={beastMenuOpen}>
              <span className="beast-mini"><img src={beast.icon} alt="" /></span>
              <span className="beast-switch-text"><b>{beast.uiName}</b><small>{beast.market}</small></span>
              <span className="chevron">⌄</span>
            </button>
            {beastMenuOpen ? (
              <div className="beast-menu panel">
                {beasts.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    className={item.id === activeBeast ? "selected" : ""}
                    onClick={() => { setActiveBeast(item.id); setBeastMenuOpen(false); }}
                    style={{ "--item-accent": item.accent } as CSSProperties}
                  >
                    <span className="menu-glyph"><img src={item.icon} alt="" /></span>
                    <span><b>{item.uiName}</b><small>{item.market}</small></span>
                    <em>{item.status}</em>
                  </button>
                ))}
              </div>
            ) : null}
          </div>
          <div className="clock-block"><span>{stream === "CONNECTED" ? "● STREAM" : "○ MOCK"}</span><time>{clock.toLocaleTimeString("ja-JP", { hour12: false })}</time></div>
          <button className="menu-button" type="button" onClick={() => setDrawerOpen(true)} aria-label="設定メニュー">☰</button>
        </div>
      </header>

      <nav className="main-tabs" aria-label="メインナビゲーション">
        <button type="button" className={tab === "holdings" ? "active" : ""} onClick={() => setTab("holdings")}><span>保有株式一覧</span><small>POSITIONS</small></button>
        <button type="button" className={tab === "summary" ? "active" : ""} onClick={() => setTab("summary")}><span>個別サマリー</span><small>SUMMARY</small></button>
        <button type="button" className={tab === "ranking" ? "active" : ""} onClick={() => setTab("ranking")}><span>本日の狙い目</span><small>RANKING</small></button>
      </nav>

      {activeBeast !== "phoenix" ? (
        <div className="content-wrap"><EmptySystem beast={beast} /></div>
      ) : (
        <div className="content-wrap">
          {tab === "holdings" ? (
            <>
              <section className={`source-banner ${isRealRss ? "real" : rssUnavailable ? "error" : "mock"}`}>
                <div><StatusDot value={isRealRss ? "CONNECTED" : rssUnavailable ? "OFFLINE" : "SIMULATED"} /><b>{isRealRss ? "RAKUTEN RSS · LIVE ACCOUNT" : rssUnavailable ? "RAKUTEN RSS · NOT AVAILABLE" : "MOCK DATA"}</b></div>
                <span>{isRealRss ? `${state.positions.length} holdings · ${state.orders.length} orders today · ${state.executions.length} fills today` : rssUnavailable ? (state.meta?.error ?? "Excel RSS bridge is not ready") : "UI preview data"}</span>
                <em className={stale ? "stale" : ""}>{stale ? "STALE" : `更新 ${updatedAt.toLocaleTimeString("ja-JP", { hour12: false })}`}</em>
              </section>
              <section className="overview-strip">
                <MetricCard label="推定資産" value={moneyView(state.account.equity)} sub="ESTIMATED EQUITY" />
                <MetricCard label="現物買付可能額" value={moneyView(state.account.buying_power)} sub="BUYING POWER" />
                <MetricCard label="保有株本日差" value={moneyView(state.account.day_pnl)} sub={balancesHidden ? "••••" : signed(state.account.day_pnl_pct, "%")} valueClass={tone(state.account.day_pnl)} />
                <MetricCard label="含み損益" value={moneyView(state.account.unrealized_pnl)} sub="UNREALIZED" valueClass={tone(state.account.unrealized_pnl)} />
              </section>
            </>
          ) : null}

          {tab === "holdings" ? (
            <section className="page-grid holdings-page">
              <div className="panel section-card holdings-list-card">
                <div className="section-heading holdings-heading"><div><small>PORTFOLIO</small><h2>保有株式一覧</h2></div><div className="heading-actions"><span>{state.positions.length}銘柄</span><button type="button" className="privacy-toggle" onClick={() => setBalancesHidden((value) => !value)} aria-label={balancesHidden ? "金額を表示" : "金額を隠す"}>{balancesHidden ? "◉" : "◎"}</button></div></div>
                <div className="portfolio-tools">
                  <input value={holdingsQuery} onChange={(event) => setHoldingsQuery(event.target.value)} placeholder="銘柄コード・名称・口座区分で検索" aria-label="保有銘柄を検索" />
                  <div className="sort-chips" aria-label="並び順">
                    <button type="button" className={holdingsSort === "pnl" ? "active" : ""} onClick={() => setHoldingsSort("pnl")}>損益</button>
                    <button type="button" className={holdingsSort === "value" ? "active" : ""} onClick={() => setHoldingsSort("value")}>評価額</button>
                    <button type="button" className={holdingsSort === "ticker" ? "active" : ""} onClick={() => setHoldingsSort("ticker")}>コード</button>
                  </div>
                </div>
                <div className="holdings-list">
                  {filteredPositions.length ? filteredPositions.map((position) => {
                    const item = state.watchlist.find((candidate) => candidate.ticker === position.ticker);
                    if (!item) return null;
                    return <HoldingCard key={`${position.ticker}-${position.account_type ?? "all"}`} position={position} item={item} masked={balancesHidden} onOpen={() => openSummary(position.ticker)} />;
                  }) : <div className="empty-list">{rssUnavailable ? "RSS接続後に保有銘柄を表示します。" : "条件に一致する保有銘柄はありません。"}</div>}
                </div>
              </div>

              <div className="panel section-card side-insight">
                <div className="section-heading"><div><small>AT A GLANCE</small><h2>今日の状況</h2></div></div>
                {analysisAvailable && ranked.length ? <div className="glance-score"><span>VERMILION TOP SCORE</span><strong>{ranked[0]?.score ?? "--"}</strong><small>{ranked[0]?.ticker.replace(".T", "")} · {ranked[0]?.name}</small></div> : <div className="analysis-offline-card"><b>PHOENIX ANALYSIS</b><strong>NOT CONNECTED</strong><p>口座情報はREALでも、ランキング/スコアは偽装せず非表示にします。</p></div>}
                <button type="button" className="primary-link" onClick={() => setTab("ranking")} disabled={!analysisAvailable}>本日の狙い目を見る <span>→</span></button>
                <div className="read-only-note"><b>READ ONLY</b><p>このUIには発注・訂正・取消の権限を持たせていません。</p></div>
              </div>
            </section>
          ) : null}

          {tab === "summary" && selectedItem ? (
            <section className="summary-page">
              <div className="instrument-hero panel">
                <div className="instrument-main">
                  <div className="symbol-block"><small>SELECTED SYMBOL</small><div><strong>{selectedItem.ticker.replace(".T", "")}</strong><span>{selectedItem.name}</span></div></div>
                  <div className="quote-block"><strong>{num(selectedItem.price, 1)}</strong><span className={tone(selectedItem.change_pct)}>{signed(selectedItem.change_pct, "%")}</span></div>
                  <div className="score-ring"><small>PHOENIX</small><strong>{selectedAnalysis?.score ?? selectedItem.score ?? "—"}</strong><span>{selectedAnalysis?.trade_decision || selectedAnalysis?.signal || selectedItem.signal || "—"}</span></div>
                </div>
                <div className="symbol-picker" aria-label="銘柄切替">
                  {selectableItems.map((item) => <button key={item.ticker} type="button" className={item.ticker === selectedItem.ticker ? "active" : ""} onClick={() => setSelectedTicker(item.ticker)}>{item.ticker.replace(".T", "")}</button>)}
                </div>
              </div>

              <div className="summary-grid">
                <section className={`panel chart-card ${chartFullscreen ? "fullscreen-chart" : ""}`}>
                  <div className="section-heading compact chart-heading">
                    <div><small>RAKUTEN RSS · REAL OHLCV</small><h2>チャート</h2></div>
                    <div className="chart-heading-actions"><span>{chartLoading ? "LOADING" : chartData ? `${chartTimeframe.toUpperCase()} · REAL` : "WAITING"}</span><button type="button" className="chart-fullscreen-toggle" onClick={() => setChartFullscreen((v) => !v)}>{chartFullscreen ? "× 閉じる" : "⤢ 全画面"}</button></div>
                  </div>
                  <div className="timeframe-chips">
                    {(["5m", "15m", "60m", "4h", "1d"] as ChartTimeframe[]).map((value) => <button key={value} type="button" className={chartTimeframe === value ? "active" : ""} onClick={() => setChartTimeframe(value)}>{value === "1d" ? "日足" : value === "4h" ? "4時間*" : value.replace("m", "分")}</button>)}
                  </div>
                  {chartData?.derived ? <div className="derived-chart-note">* {chartData.derived_note}</div> : null}
                  {chartData?.bars.length ? <MarketChart bars={chartData.bars} theme={resolvedTheme} accent={beast.accent} scenario={{ entry: selectedAnalysis?.entry_price, target: selectedAnalysis?.target_price, stop: selectedAnalysis?.stop_price }} /> : <div className="chart-waiting">{chartError || (isMock ? "REAL RSSモードで実チャートを表示します。" : "RssChartデータ待機中")}</div>}
                  {chartData ? <div className="rss-indicator-strip"><span>RSS VIEW</span><b>MA5 {typeof chartData.indicators.ma5 === "number" ? num(chartData.indicators.ma5, 2) : "—"}</b><b>MA25 {typeof chartData.indicators.ma25 === "number" ? num(chartData.indicators.ma25, 2) : "—"}</b><b>MA75 {typeof chartData.indicators.ma75 === "number" ? num(chartData.indicators.ma75, 2) : "—"}</b><b>EMA12 {typeof chartData.indicators.ema12 === "number" ? num(chartData.indicators.ema12, 2) : "—"}</b><b>EMA26 {typeof chartData.indicators.ema26 === "number" ? num(chartData.indicators.ema26, 2) : "—"}</b><b>RSI14 {typeof chartData.indicators.rsi14 === "number" ? num(chartData.indicators.rsi14, 1) : "—"}</b><b>MACD {typeof chartData.indicators.macd === "number" ? num(chartData.indicators.macd, 3) : "—"}</b><b>SIG {typeof chartData.indicators.macd_signal === "number" ? num(chartData.indicators.macd_signal, 3) : "—"}</b></div> : null}
                </section>

                <aside className="panel analysis-card">
                  <div className="section-heading compact"><div><small>PHOENIX LOGIC · DAILY ARTIFACT</small><h2>判断と条件付きシナリオ</h2></div>{analysisStale ? <span className="stale-badge">STALE</span> : null}</div>
                  {analysisAvailable && selectedAnalysis ? <>
                    <div className="analysis-grid">
                      <MetricCard label="PHOENIX SCORE" value={num(selectedAnalysis.phoenix_score ?? 0, 0)} />
                      <MetricCard label="RSI14" value={num(selectedAnalysis.rsi ?? 0, 1)} />
                      <MetricCard label="MACD" value={selectedAnalysis.macd || "—"} />
                      <MetricCard label="VOLUME" value={`${num(selectedAnalysis.volume_ratio ?? 0, 2)}×`} />
                    </div>
                    <div className="scenario-ladder">
                      <div><span>現在判断</span><strong>{selectedAnalysis.trade_decision || selectedAnalysis.signal || "—"}</strong></div>
                      <div><span>基準</span><strong>{selectedAnalysis.base_price ? `¥${num(selectedAnalysis.base_price, 1)}` : "—"}</strong></div>
                      <div className="entry"><span>押し目 / ENTRY</span><strong>{selectedAnalysis.entry_price ? `¥${num(selectedAnalysis.entry_price, 1)}` : "—"}</strong></div>
                      <div className="target"><span>TARGET</span><strong>{selectedAnalysis.target_price ? `¥${num(selectedAnalysis.target_price, 1)}` : "—"}</strong></div>
                      <div className="stop"><span>STOP / INVALIDATION</span><strong>{selectedAnalysis.stop_price ? `¥${num(selectedAnalysis.stop_price, 1)}` : "—"}</strong></div>
                    </div>
                    <div className="decision-blocks">
                      <div className="decision-block thesis-block"><span>PHOENIXが見ている条件</span><p>{selectedAnalysis.phoenix_reason || selectedAnalysis.technical_reason || "判断条件の記録なし"}</p></div>
                      <div className="decision-block reevaluate-block"><span>条件付きシナリオ</span><p>{selectedAnalysis.monitor_timing || "押し目・モメンタム・出来高条件を再確認"}。ENTRY付近で条件維持なら候補、STOP割れで無効化。</p></div>
                      <div className="decision-block caution-block"><span>注意材料</span><p>{selectedAnalysis.caution_material || `市場リスク: ${selectedAnalysis.market_risk_level || "—"}`}</p></div>
                      <div className="decision-block invalidation-block"><span>判定理由</span><p>{selectedAnalysis.decision_reason || selectedAnalysis.reason || "—"}</p></div>
                    </div>
                    <div className="artifact-note">GENERATED {analysisGeneratedAt || selectedAnalysis.artifact_generated_at || "—"} · {analysisStale ? "STALE / 過去分析" : "CURRENT"} · Qは表示のみ</div>
                  </> : isMock && insight ? <div className="analysis-placeholder"><b>MOCK ANALYSIS</b><p>{insight.thesis.join(" / ")}</p></div> : <div className="analysis-placeholder"><b>THIS TICKER IS NOT IN CURRENT PHOENIX ARTIFACT</b><p>保有口座には存在しますが、現在読み込んでいるPHOENIXランキング/シグナルには含まれていません。推測値は表示しません。</p></div>}
                </aside>
              </div>

              <div className="detail-strip panel">
                <div><span>保有</span><strong>{selectedPosition ? `${selectedPosition.qty}株` : "なし"}</strong></div>
                <div><span>平均取得</span><strong>{selectedPosition ? (balancesHidden ? "••••" : `¥${num(selectedPosition.avg_price, 1)}`) : "—"}</strong></div>
                <div><span>評価損益</span><strong className={selectedPosition ? tone(selectedPosition.pnl) : ""}>{selectedPosition ? moneyView(selectedPosition.pnl) : "—"}</strong></div>
                <div><span>シグナル</span><strong>{selectedAnalysis?.trade_decision || selectedAnalysis?.signal || selectedItem.signal}</strong></div>
              </div>
            </section>
          ) : null}

          {tab === "ranking" ? (
            <section className="panel section-card ranking-card">
              <div className="section-heading"><div><small>DAILY OPPORTUNITY</small><h2>本日の狙い目ランキング</h2></div><span>VERMILION SCORE順</span></div>
              {analysisAvailable ? <>
                <div className="ranking-list">
                  {ranked.map((item, index) => (
                    <button type="button" className="ranking-row" key={item.ticker} onClick={() => openSummary(item.ticker)}>
                      <span className="rank-no">{String(index + 1).padStart(2, "0")}</span>
                      <span className="rank-symbol"><b>{item.ticker.replace(".T", "")}</b><small>{item.name}</small><em className="rank-reason">{(insightByTicker[item.ticker]?.thesis ?? ["スコア上位候補"]).slice(0, 2).join(" · ")}</em></span>
                      <span className="rank-price"><b>{num(item.price, 1)}</b><small className={tone(item.change_pct)}>{signed(item.change_pct, "%")}</small></span>
                      <span className="rank-score"><small>SCORE</small><b>{item.score ?? "—"}</b></span>
                      <span className={`signal-chip ${item.signal.toLowerCase()}`}>{item.signal}</span>
                      <span className="open-arrow">›</span>
                    </button>
                  ))}
                </div>
                <div className="ranking-footnote">銘柄を選ぶと「個別サマリー」へ移動します。{isMock ? "現在はUI確認用のモック分析です。" : "PHOENIX分析stateから表示します。"}</div>
              </> : <div className="ranking-unavailable"><b>PHOENIX ANALYSIS NOT CONNECTED</b><p>楽天RSSの実ポートフォリオは表示中ですが、狙い目ランキングを口座データから推測して生成することはしません。</p></div>}
            </section>
          ) : null}
        </div>
      )}

      <footer className="status-footer">
        <div className="footer-status-main"><StatusDot value={activeBeast === "phoenix" ? state.system.phoenix : "ISOLATED"} /><span>{beast.uiName}</span><b>{activeBeast === "phoenix" ? state.system.phoenix : "SHELL"}</b><span className={`status-pill ${isMock ? "mock" : isRealRss ? "real" : "warn"}`}>{isMock ? "MOCK" : isRealRss ? "REAL RSS" : "RSS OFFLINE"}</span><span className="status-pill readonly">READ ONLY</span><span className="status-updated">更新 {updatedAt.toLocaleTimeString("ja-JP", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false })}</span></div>
        <div className="footer-desktop"><span>UI AUTHORITY</span><b>NONE</b><span>·</span><span>v0.4.0</span></div>
      </footer>

      {drawerOpen ? <div className="drawer-backdrop" onClick={() => setDrawerOpen(false)} /> : null}
      <aside className={`settings-drawer ${drawerOpen ? "open" : ""}`} aria-hidden={!drawerOpen}>
        <div className="drawer-head"><div><small>QUADRANT TERMINAL</small><h2>設定</h2></div><button type="button" onClick={() => setDrawerOpen(false)} aria-label="閉じる">×</button></div>

        <section className="drawer-section">
          <span className="drawer-label">外観</span>
          <div className="segmented">
            {(["system", "light", "dark"] as ThemeChoice[]).map((choice) => (
              <button type="button" key={choice} className={themeChoice === choice ? "active" : ""} onClick={() => setThemeChoice(choice)}>{choice === "system" ? "自動" : choice === "light" ? "ライト" : "ダーク"}</button>
            ))}
          </div>
          <p className="drawer-help">「自動」はiPhone / Windowsの外観設定に追従します。</p>
        </section>

        <section className="drawer-section">
          <span className="drawer-label">モジュール</span>
          <div className="module-map-card">
            <span><b>{beast.uiName}</b><small>{beast.market}</small></span>
            <span className="module-map-arrow">→</span>
            <span><b>{beast.internalEngine}</b><small>INTERNAL ENGINE</small></span>
          </div>
          <p className="drawer-help">表示名だけをQUADRANT側で切り替えます。内部エンジン名・runtime・state・order authorityは変更しません。</p>
        </section>

        <section className="drawer-section">
          <span className="drawer-label">システム状態</span>
          <div className="system-list">
            {[
              ["VERMILION / PHOENIX ENGINE", state.system.phoenix],
              ["MARKET", state.system.market_data],
              ["RAKUTEN RSS", state.system.rakuten_rss],
              ["LIVE RUNTIME", state.system.live_runtime],
              ["WATCHDOG", state.system.watchdog],
              ["PHOENIX ANALYSIS", state.system.analysis ?? "UNKNOWN"],
            ].map(([label, value]) => <div key={label}><span><StatusDot value={value} />{label}</span><b>{value}</b></div>)}
          </div>
        </section>

        <section className="drawer-section">
          <span className="drawer-label">操作ガイド</span>
          <ol className="quick-guide">
            <li><b>マーケット切替</b><span>上部の「VERMILION」をタップ</span></li>
            <li><b>画面切替</b><span>上の3タブから選択</span></li>
            <li><b>銘柄詳細</b><span>保有一覧・ランキングの銘柄をタップ</span></li>
            <li><b>iPhoneホーム画面</b><span>Safariの共有 →「ホーム画面に追加」でアプリ風に起動</span></li>
          </ol>
        </section>

        <section className="drawer-section mobile-connection-help">
          <span className="drawer-label">スマホ接続</span>
          <div className="connection-card">
            <b>API HOST</b>
            <code>{API_HOST}:8765</code>
            <p>PCのread-only APIへ接続します。現在の楽天RSS連携はExcelブリッジ経由で、注文関数は使用しません。外部アクセスは将来VPN経由にします。</p>
          </div>
        </section>

        <div className="drawer-safety"><b>READ ONLY / EXECUTION AUTHORITY NONE</b><p>QUADRANT UIからbroker mutationへ直接到達する経路は作りません。</p></div>
      </aside>
    </main>
  );
}

function HoldingCard({ position, item, masked, onOpen }: { position: Position; item: WatchItem; masked: boolean; onOpen: () => void }) {
  return (
    <button type="button" className="holding-card" onClick={onOpen}>
      <div className="holding-symbol"><span>{item.ticker.replace(".T", "")}</span><small>{item.name}</small>{position.account_type ? <em>{position.account_type}</em> : null}</div>
      <div className="holding-quote"><strong>{num(position.last, 1)}</strong><small className={tone(item.change_pct)}>{signed(item.change_pct, "%")}</small></div>
      <div className="holding-position"><span>{position.qty}株</span><small>平均 {masked ? "••••" : `¥${num(position.avg_price, 1)}`}</small></div>
      <div className="holding-pnl"><strong className={tone(position.pnl)}>{masked ? "••••••" : money(position.pnl)}</strong><small className={tone(position.pnl_pct)}>{masked ? "••••" : signed(position.pnl_pct, "%")}</small></div>
      <div className="holding-score"><small>SCORE</small><strong>{item.score ?? "—"}</strong></div>
      <span className="open-arrow">›</span>
    </button>
  );
}

export default App;
