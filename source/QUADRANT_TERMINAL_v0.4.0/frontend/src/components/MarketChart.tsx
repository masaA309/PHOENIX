import { useEffect, useRef } from "react";
import {
  CandlestickSeries,
  ColorType,
  HistogramSeries,
  LineSeries,
  createChart,
  type CandlestickData,
  type HistogramData,
  type IChartApi,
  type IPriceLine,
  type ISeriesApi,
  type LineData,
  type UTCTimestamp,
} from "lightweight-charts";
import type { ChartBar } from "../types";

function t(value: string): UTCTimestamp {
  return Math.floor(new Date(value).getTime() / 1000) as UTCTimestamp;
}

function lineData(bars: ChartBar[], key: "ma5" | "ma25" | "ma75" | "ema12" | "ema26"): LineData<UTCTimestamp>[] {
  return bars.flatMap((bar) => {
    const value = bar[key];
    return typeof value === "number" ? [{ time: t(bar.time), value }] : [];
  });
}

export function MarketChart({
  bars,
  theme,
  accent,
  scenario,
}: {
  bars: ChartBar[];
  theme: "light" | "dark";
  accent: string;
  scenario?: { entry?: number; target?: number; stop?: number };
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const volumeRef = useRef<ISeriesApi<"Histogram"> | null>(null);
  const ma5Ref = useRef<ISeriesApi<"Line"> | null>(null);
  const ma25Ref = useRef<ISeriesApi<"Line"> | null>(null);
  const ma75Ref = useRef<ISeriesApi<"Line"> | null>(null);
  const ema12Ref = useRef<ISeriesApi<"Line"> | null>(null);
  const ema26Ref = useRef<ISeriesApi<"Line"> | null>(null);
  const priceLinesRef = useRef<IPriceLine[]>([]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const chart = createChart(container, {
      width: Math.max(container.clientWidth, 1),
      height: Math.max(container.clientHeight, 240),
      layout: { background: { type: ColorType.Solid, color: "transparent" }, textColor: theme === "dark" ? "#8b98a5" : "#5f6a75", attributionLogo: false },
      grid: {
        vertLines: { color: theme === "dark" ? "rgba(255,255,255,.045)" : "rgba(20,36,50,.075)" },
        horzLines: { color: theme === "dark" ? "rgba(255,255,255,.045)" : "rgba(20,36,50,.075)" },
      },
      rightPriceScale: { borderColor: theme === "dark" ? "rgba(255,255,255,.10)" : "rgba(20,36,50,.12)" },
      timeScale: { borderColor: theme === "dark" ? "rgba(255,255,255,.10)" : "rgba(20,36,50,.12)", timeVisible: true, secondsVisible: false },
      crosshair: { vertLine: { color: accent }, horzLine: { color: accent } },
    });
    chartRef.current = chart;
    candleRef.current = chart.addSeries(CandlestickSeries, { upColor: "#22c58b", downColor: "#ef5b70", borderUpColor: "#22c58b", borderDownColor: "#ef5b70", wickUpColor: "#22c58b", wickDownColor: "#ef5b70" });
    volumeRef.current = chart.addSeries(HistogramSeries, { priceFormat: { type: "volume" }, priceScaleId: "" });
    volumeRef.current.priceScale().applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } });
    ma5Ref.current = chart.addSeries(LineSeries, { color: "#f5c542", lineWidth: 2, priceLineVisible: false, lastValueVisible: false });
    ma25Ref.current = chart.addSeries(LineSeries, { color: "#4f8cff", lineWidth: 2, priceLineVisible: false, lastValueVisible: false });
    ma75Ref.current = chart.addSeries(LineSeries, { color: "#b16cff", lineWidth: 2, priceLineVisible: false, lastValueVisible: false });
    ema12Ref.current = chart.addSeries(LineSeries, { color: "#23c8a5", lineWidth: 1, priceLineVisible: false, lastValueVisible: false });
    ema26Ref.current = chart.addSeries(LineSeries, { color: "#f58b57", lineWidth: 1, priceLineVisible: false, lastValueVisible: false });
    const observer = new ResizeObserver(([entry]) => {
      if (!entry) return;
      chart.applyOptions({ width: Math.max(1, Math.floor(entry.contentRect.width)), height: Math.max(240, Math.floor(entry.contentRect.height)) });
    });
    observer.observe(container);
    return () => { observer.disconnect(); chart.remove(); chartRef.current = null; };
  }, []);

  useEffect(() => {
    const candles: CandlestickData<UTCTimestamp>[] = bars.map((b) => ({ time: t(b.time), open: b.open, high: b.high, low: b.low, close: b.close }));
    const volumes: HistogramData<UTCTimestamp>[] = bars.map((b) => ({ time: t(b.time), value: b.volume, color: b.close >= b.open ? "rgba(34,197,139,.30)" : "rgba(239,91,112,.30)" }));
    candleRef.current?.setData(candles);
    volumeRef.current?.setData(volumes);
    ma5Ref.current?.setData(lineData(bars, "ma5"));
    ma25Ref.current?.setData(lineData(bars, "ma25"));
    ma75Ref.current?.setData(lineData(bars, "ma75"));
    ema12Ref.current?.setData(lineData(bars, "ema12"));
    ema26Ref.current?.setData(lineData(bars, "ema26"));
    chartRef.current?.timeScale().fitContent();
  }, [bars]);

  useEffect(() => {
    const candle = candleRef.current;
    if (!candle) return;
    for (const line of priceLinesRef.current) candle.removePriceLine(line);
    priceLinesRef.current = [];
    const add = (price: number | undefined, title: string, color: string) => {
      if (!price || price <= 0) return;
      priceLinesRef.current.push(candle.createPriceLine({ price, title, color, lineWidth: 1, axisLabelVisible: true }));
    };
    add(scenario?.entry, "ENTRY", accent);
    add(scenario?.target, "TARGET", "#22c58b");
    add(scenario?.stop, "STOP", "#ef5b70");
  }, [scenario?.entry, scenario?.target, scenario?.stop, accent]);

  useEffect(() => {
    chartRef.current?.applyOptions({
      layout: { background: { type: ColorType.Solid, color: "transparent" }, textColor: theme === "dark" ? "#8b98a5" : "#5f6a75", attributionLogo: false },
      crosshair: { vertLine: { color: accent }, horzLine: { color: accent } },
    });
  }, [accent, theme]);

  return <div className="market-chart" ref={containerRef} aria-label="楽天RSS実OHLCVチャート" />;
}