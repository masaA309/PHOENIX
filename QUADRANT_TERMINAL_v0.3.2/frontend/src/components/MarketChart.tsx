import { useEffect, useRef } from "react";
import {
  CandlestickSeries,
  ColorType,
  HistogramSeries,
  createChart,
  type CandlestickData,
  type HistogramData,
  type IChartApi,
  type ISeriesApi,
  type UTCTimestamp,
} from "lightweight-charts";

const base = 1_788_998_400 as UTCTimestamp;

function buildCandles(anchor: number): CandlestickData<UTCTimestamp>[] {
  const points: CandlestickData<UTCTimestamp>[] = [];
  let prior = anchor - 72;
  for (let i = 0; i < 56; i += 1) {
    const drift = Math.sin(i / 4.2) * 12 + i * 1.25;
    const open = prior;
    const close = anchor - 72 + drift;
    const high = Math.max(open, close) + 5 + (i % 4);
    const low = Math.min(open, close) - 4 - (i % 3);
    points.push({
      time: (base + i * 300) as UTCTimestamp,
      open: Number(open.toFixed(1)),
      high: Number(high.toFixed(1)),
      low: Number(low.toFixed(1)),
      close: Number(close.toFixed(1)),
    });
    prior = close;
  }
  return points;
}

function buildVolume(up: string, down: string): HistogramData<UTCTimestamp>[] {
  return Array.from({ length: 56 }, (_, i) => ({
    time: (base + i * 300) as UTCTimestamp,
    value: 35_000 + ((i * 7919) % 80_000),
    color: i % 3 === 0 ? down : up,
  }));
}

export function MarketChart({
  anchorPrice,
  theme,
  accent,
}: {
  anchorPrice: number;
  theme: "light" | "dark";
  accent: string;
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const volumeSeriesRef = useRef<ISeriesApi<"Histogram"> | null>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const chart = createChart(container, {
      width: Math.max(container.clientWidth, 1),
      height: Math.max(container.clientHeight, 220),
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: theme === "dark" ? "#8b98a5" : "#5f6a75",
        attributionLogo: false,
      },
      grid: {
        vertLines: { color: theme === "dark" ? "rgba(255,255,255,.045)" : "rgba(20,36,50,.075)" },
        horzLines: { color: theme === "dark" ? "rgba(255,255,255,.045)" : "rgba(20,36,50,.075)" },
      },
      rightPriceScale: {
        borderColor: theme === "dark" ? "rgba(255,255,255,.10)" : "rgba(20,36,50,.12)",
      },
      timeScale: {
        borderColor: theme === "dark" ? "rgba(255,255,255,.10)" : "rgba(20,36,50,.12)",
        timeVisible: true,
        secondsVisible: false,
      },
      crosshair: {
        vertLine: { color: accent },
        horzLine: { color: accent },
      },
    });
    chartRef.current = chart;

    const candles = chart.addSeries(CandlestickSeries, {
      upColor: "#22c58b",
      downColor: "#ef5b70",
      borderUpColor: "#22c58b",
      borderDownColor: "#ef5b70",
      wickUpColor: "#22c58b",
      wickDownColor: "#ef5b70",
      priceLineVisible: true,
    });
    candleSeriesRef.current = candles;
    candles.setData(buildCandles(anchorPrice));

    const volume = chart.addSeries(HistogramSeries, {
      priceFormat: { type: "volume" },
      priceScaleId: "",
    });
    volumeSeriesRef.current = volume;
    volume.priceScale().applyOptions({ scaleMargins: { top: 0.78, bottom: 0 } });
    volume.setData(buildVolume("rgba(34,197,139,.34)", "rgba(239,91,112,.34)"));
    chart.timeScale().fitContent();

    const observer = new ResizeObserver((entries) => {
      const rect = entries[0]?.contentRect;
      if (!rect) return;
      const width = Math.max(1, Math.floor(rect.width));
      const height = Math.max(220, Math.floor(rect.height));
      chart.applyOptions({ width, height });
    });
    observer.observe(container);

    return () => {
      observer.disconnect();
      chartRef.current = null;
      candleSeriesRef.current = null;
      volumeSeriesRef.current = null;
      chart.remove();
    };
    // Build the chart only once. Live ticks update the existing series below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    candleSeriesRef.current?.setData(buildCandles(anchorPrice));
  }, [anchorPrice]);

  useEffect(() => {
    chartRef.current?.applyOptions({
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: theme === "dark" ? "#8b98a5" : "#5f6a75",
        attributionLogo: false,
      },
      grid: {
        vertLines: { color: theme === "dark" ? "rgba(255,255,255,.045)" : "rgba(20,36,50,.075)" },
        horzLines: { color: theme === "dark" ? "rgba(255,255,255,.045)" : "rgba(20,36,50,.075)" },
      },
      crosshair: {
        vertLine: { color: accent },
        horzLine: { color: accent },
      },
    });
  }, [accent, theme]);

  return <div className="market-chart" ref={containerRef} aria-label="価格チャート" />;
}
