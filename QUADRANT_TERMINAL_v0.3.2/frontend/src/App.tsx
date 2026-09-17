import { useEffect, useMemo, useState, type CSSProperties } from "react";
import { MarketChart } from "./components/MarketChart";
import { mockSnapshot } from "./data/mock";
import type { PhoenixSnapshot, Position, WatchItem } from "./types";

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

type Beast = {
  id: BeastId;
  glyph: string;
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
  { id: "phoenix", glyph: "V", uiName: "VERMILION", internalEngine: "PHOENIX", market: "JAPAN EQUITIES", accent: "#ff5a36", accent2: "#ffb34d", status: "ACTIVE" },
  { id: "seiryu", glyph: "A", uiName: "AZURE", internalEngine: "SEIRYU", market: "FX", accent: "#22c7c7", accent2: "#4f8cff", status: "PLANNED" },
  { id: "byakko", glyph: "WT", uiName: "WHITE TIGER", internalEngine: "BYAKKO", market: "GOLD", accent: "#d8b86a", accent2: "#f2f3f5", status: "PLANNED" },
  { id: "genbu", glyph: "BW", uiName: "BLACK WARRIOR", internalEngine: "GENBU", market: "US INDICES", accent: "#6f78d8", accent2: "#2d4d78", status: "PLANNED" },
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
  const ok = ["ONLINE", "OK"].includes(value);
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
      <div className="coming-glyph">{beast.glyph}</div>
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
  const [themeChoice, setThemeChoice] = useState<ThemeChoice>(() => (localStorage.getItem("shishin-theme") as ThemeChoice) || "dark"); // keep legacy key so existing preference survives branding change
  const resolvedTheme = useResolvedTheme(themeChoice);
  const beast = beasts.find((item) => item.id === activeBeast) ?? beasts[0];

  useEffect(() => {
    localStorage.setItem("shishin-theme", themeChoice);
  }, [themeChoice]);

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
    () => state.watchlist.find((item) => item.ticker === selectedTicker) ?? state.watchlist[0],
    [selectedTicker, state.watchlist],
  );
  const selectedPosition = useMemo(
    () => state.positions.find((item) => item.ticker === selectedItem?.ticker),
    [selectedItem?.ticker, state.positions],
  );
  const ranked = useMemo(() => [...state.watchlist].sort((a, b) => b.score - a.score), [state.watchlist]);
  const insight = insightByTicker[selectedItem?.ticker] ?? insightByTicker["7203.T"];
  const isMock = state.source.includes("MOCK") || state.system.market_data === "SIMULATED";
  const updatedAt = state.as_of ? new Date(state.as_of) : clock;

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
          <div className="shishin-mark quadrant-mark">Q</div>
          <div className="brand-copy">
            <strong>QUADRANT</strong>
            <small>UNIFIED MULTI-MARKET TRADING TERMINAL · READ ONLY</small>
          </div>
        </div>

        <div className="header-actions">
          <div className="beast-switcher-wrap">
            <button className="beast-switcher" type="button" onClick={() => setBeastMenuOpen((v) => !v)} aria-expanded={beastMenuOpen}>
              <span className="beast-mini">{beast.glyph}</span>
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
                    <span className="menu-glyph">{item.glyph}</span>
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
            <section className="overview-strip">
              <MetricCard label="推定資産" value={money(state.account.equity)} sub="ESTIMATED EQUITY" />
              <MetricCard label="本日損益" value={money(state.account.day_pnl)} sub={signed(state.account.day_pnl_pct, "%")} valueClass={tone(state.account.day_pnl)} />
              <MetricCard label="含み損益" value={money(state.account.unrealized_pnl)} sub="UNREALIZED" valueClass={tone(state.account.unrealized_pnl)} />
              <MetricCard label="データ" value={isMock ? "MOCK" : "REAL"} sub={stream === "CONNECTED" ? "STREAM" : "LOCAL"} />
            </section>
          ) : null}

          {tab === "holdings" ? (
            <section className="page-grid holdings-page">
              <div className="panel section-card holdings-list-card">
                <div className="section-heading"><div><small>PORTFOLIO</small><h2>保有株式一覧</h2></div><span>{state.positions.length}銘柄</span></div>
                <div className="holdings-list">
                  {state.positions.map((position) => {
                    const item = state.watchlist.find((candidate) => candidate.ticker === position.ticker);
                    if (!item) return null;
                    return <HoldingCard key={position.ticker} position={position} item={item} onOpen={() => openSummary(position.ticker)} />;
                  })}
                </div>
              </div>

              <div className="panel section-card side-insight">
                <div className="section-heading"><div><small>AT A GLANCE</small><h2>今日の状況</h2></div></div>
                <div className="glance-score"><span>VERMILION TOP SCORE</span><strong>{ranked[0]?.score ?? "--"}</strong><small>{ranked[0]?.ticker.replace(".T", "")} · {ranked[0]?.name}</small></div>
                <button type="button" className="primary-link" onClick={() => setTab("ranking")}>本日の狙い目を見る <span>→</span></button>
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
                  <div className="score-ring"><small>SCORE</small><strong>{selectedItem.score}</strong><span>{selectedItem.signal}</span></div>
                </div>
                <div className="symbol-picker" aria-label="銘柄切替">
                  {state.watchlist.map((item) => <button key={item.ticker} type="button" className={item.ticker === selectedItem.ticker ? "active" : ""} onClick={() => setSelectedTicker(item.ticker)}>{item.ticker.replace(".T", "")}</button>)}
                </div>
              </div>

              <div className="summary-grid">
                <section className={`panel chart-card ${chartFullscreen ? "fullscreen-chart" : ""}`}>
                  <div className="section-heading compact chart-heading"><div><small>PRICE ACTION</small><h2>チャート</h2></div><div className="chart-heading-actions"><span>5m · UI SAMPLE</span><button type="button" className="chart-fullscreen-toggle" onClick={() => setChartFullscreen((v) => !v)} aria-label={chartFullscreen ? "チャート全画面を閉じる" : "チャートを全画面表示"}>{chartFullscreen ? "× 閉じる" : "⤢ 全画面"}</button></div></div>
                  <MarketChart anchorPrice={selectedItem.price} theme={resolvedTheme} accent={beast.accent} />
                </section>

                <aside className="panel analysis-card">
                  <div className="section-heading compact"><div><small>VERMILION ANALYSIS</small><h2>判断サマリー</h2></div></div>
                  <div className="analysis-grid">
                    <MetricCard label="TREND" value={insight.trend} />
                    <MetricCard label="RSI" value={num(insight.rsi, 1)} />
                    <MetricCard label="MACD" value={insight.macd} />
                    <MetricCard label="VOLUME" value={insight.volume} />
                  </div>
                  <div className="decision-blocks">
                    <div className="decision-block thesis-block"><span>判断理由</span>{insight.thesis.slice(0, 2).map((line) => <p key={line}>• {line}</p>)}</div>
                    <div className="decision-block caution-block"><span>注意点</span><p>• {insight.risk[0]}</p></div>
                    <div className="decision-block reevaluate-block"><span>再評価条件</span><p>• {insight.thesis[2] ?? "トレンド・出来高・モメンタムを再確認"}</p></div>
                    <div className="decision-block invalidation-block"><span>無効化条件</span><p>• {insight.risk[1] ?? "主要支持線割れでシナリオ無効"}</p></div>
                  </div>
                </aside>
              </div>

              <div className="detail-strip panel">
                <div><span>保有</span><strong>{selectedPosition ? `${selectedPosition.qty}株` : "なし"}</strong></div>
                <div><span>平均取得</span><strong>{selectedPosition ? `¥${num(selectedPosition.avg_price, 1)}` : "—"}</strong></div>
                <div><span>評価損益</span><strong className={selectedPosition ? tone(selectedPosition.pnl) : ""}>{selectedPosition ? money(selectedPosition.pnl) : "—"}</strong></div>
                <div><span>シグナル</span><strong>{selectedItem.signal}</strong></div>
              </div>
            </section>
          ) : null}

          {tab === "ranking" ? (
            <section className="panel section-card ranking-card">
              <div className="section-heading"><div><small>DAILY OPPORTUNITY</small><h2>本日の狙い目ランキング</h2></div><span>VERMILION SCORE順</span></div>
              <div className="ranking-list">
                {ranked.map((item, index) => (
                  <button type="button" className="ranking-row" key={item.ticker} onClick={() => openSummary(item.ticker)}>
                    <span className="rank-no">{String(index + 1).padStart(2, "0")}</span>
                    <span className="rank-symbol"><b>{item.ticker.replace(".T", "")}</b><small>{item.name}</small><em className="rank-reason">{(insightByTicker[item.ticker]?.thesis ?? ["スコア上位候補"]).slice(0, 2).join(" · ")}</em></span>
                    <span className="rank-price"><b>{num(item.price, 1)}</b><small className={tone(item.change_pct)}>{signed(item.change_pct, "%")}</small></span>
                    <span className="rank-score"><small>SCORE</small><b>{item.score}</b></span>
                    <span className={`signal-chip ${item.signal.toLowerCase()}`}>{item.signal}</span>
                    <span className="open-arrow">›</span>
                  </button>
                ))}
              </div>
              <div className="ranking-footnote">銘柄を選ぶと「個別サマリー」へ移動します。現在はUI確認用のモック値です。</div>
            </section>
          ) : null}
        </div>
      )}

      <footer className="status-footer">
        <div className="footer-status-main"><StatusDot value={activeBeast === "phoenix" ? state.system.phoenix : "ISOLATED"} /><span>{beast.uiName}</span><b>{activeBeast === "phoenix" ? state.system.phoenix : "SHELL"}</b><span className={`status-pill ${isMock ? "mock" : "real"}`}>{isMock ? "MOCK" : "REAL"}</span><span className="status-pill readonly">READ ONLY</span><span className="status-updated">更新 {updatedAt.toLocaleTimeString("ja-JP", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false })}</span></div>
        <div className="footer-desktop"><span>UI AUTHORITY</span><b>NONE</b><span>·</span><span>v0.3.2</span></div>
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
            <p>同じWi-Fi内では、PCのIPアドレスでQUADRANTを開くと同じPCのread-only APIへ接続します。外部公開・ポート開放は不要です。</p>
          </div>
        </section>

        <div className="drawer-safety"><b>READ ONLY / EXECUTION AUTHORITY NONE</b><p>QUADRANT UIからbroker mutationへ直接到達する経路は作りません。</p></div>
      </aside>
    </main>
  );
}

function HoldingCard({ position, item, onOpen }: { position: Position; item: WatchItem; onOpen: () => void }) {
  return (
    <button type="button" className="holding-card" onClick={onOpen}>
      <div className="holding-symbol"><span>{item.ticker.replace(".T", "")}</span><small>{item.name}</small></div>
      <div className="holding-quote"><strong>{num(position.last, 1)}</strong><small className={tone(item.change_pct)}>{signed(item.change_pct, "%")}</small></div>
      <div className="holding-position"><span>{position.qty}株</span><small>平均 ¥{num(position.avg_price, 1)}</small></div>
      <div className="holding-pnl"><strong className={tone(position.pnl)}>{money(position.pnl)}</strong><small className={tone(position.pnl_pct)}>{signed(position.pnl_pct, "%")}</small></div>
      <div className="holding-score"><small>SCORE</small><strong>{item.score}</strong></div>
      <span className="open-arrow">›</span>
    </button>
  );
}

export default App;
