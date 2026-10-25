import { useEffect, useRef } from "react";
import {
  CandlestickSeries,
  ColorType,
  HistogramSeries,
  createChart,
  type CandlestickData,
  type HistogramData,
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

function buildVolume(): HistogramData<UTCTimestamp>[] {
  return Array.from({ length: 56 }, (_, i) => ({
    time: (base + i * 300) as UTCTimestamp,
    value: 35_000 + ((i * 7919) % 80_000),
    color: i % 3 === 0 ? "rgba(255, 91, 113, 0.45)" : "rgba(32, 211, 161, 0.38)",
  }));
}

export function MarketChart({ anchorPrice }: { anchorPrice: number }) {
  const ref = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!ref.current) return;

    const chart = createChart(ref.current, {
      autoSize: true,
      layout: {
        background: { type: ColorType.Solid, color: "#0a141b" },
        textColor: "#8194a4",
        attributionLogo: false,
      },
      grid: {
        vertLines: { color: "#13232e" },
        horzLines: { color: "#13232e" },
      },
      rightPriceScale: {
        borderColor: "#1d3340",
      },
      timeScale: {
        borderColor: "#1d3340",
        timeVisible: true,
        secondsVisible: false,
      },
      crosshair: {
        vertLine: { color: "#526b7a" },
        horzLine: { color: "#526b7a" },
      },
    });

    const candles = chart.addSeries(CandlestickSeries, {
      upColor: "#20d3a1",
      downColor: "#ff5b71",
      borderUpColor: "#20d3a1",
      borderDownColor: "#ff5b71",
      wickUpColor: "#20d3a1",
      wickDownColor: "#ff5b71",
      priceLineVisible: true,
    });
    candles.setData(buildCandles(anchorPrice));

    const volume = chart.addSeries(HistogramSeries, {
      priceFormat: { type: "volume" },
      priceScaleId: "",
    });
    volume.priceScale().applyOptions({
      scaleMargins: { top: 0.78, bottom: 0 },
    });
    volume.setData(buildVolume());

    chart.timeScale().fitContent();
    return () => chart.remove();
  }, [anchorPrice]);

  return <div className="market-chart" ref={ref} />;
}
