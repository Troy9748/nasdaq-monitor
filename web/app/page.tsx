"use client";

import { useEffect, useMemo, useRef, useState } from "react";

type Point = {
  date: string;
  close: number;
  ema50: number | null;
  ema200: number | null;
  rsi14: number | null;
  volatility20_pct: number | null;
  drawdown_pct: number | null;
  robust_trend: number;
  robust_lower: number;
  robust_upper: number;
  robust_deviation_pct: number;
  robust_percentile: number;
  asof_robust_trend: number | null;
  asof_robust_lower: number | null;
  asof_robust_upper: number | null;
  asof_robust_deviation_pct: number | null;
  asof_robust_percentile: number | null;
  source: string;
  is_provisional: boolean;
};

type Summary = {
  market_date: string;
  close: number;
  daily_return_pct: number;
  returns: Record<string, number | null>;
  ema50: number;
  ema200: number;
  distance_ema200_pct: number;
  distance_high252_pct: number;
  rsi14: number;
  volatility20_pct: number;
  drawdown_pct: number;
  max_drawdown_pct: number;
  robust_log_trend: {
    method: string;
    start_date: string;
    end_date: string;
    observations: number;
    annualized_growth_pct: number;
    fitted_close: number;
    lower_band: number;
    upper_band: number;
    deviation_pct: number;
    deviation_percentile: number;
    central_coverage_pct: number;
    above_upper_days: number;
    below_lower_days: number;
    downweighted_pct: number;
    uncertainty: {
      method: string;
      samples: number;
      block_sessions: number;
      annualized_growth_ci95_pct: [number, number];
      fitted_close_ci95: [number, number];
    };
  };
  asof_robust_log_trend: {
    method: string;
    training_end: string;
    fitted_close: number;
    lower_band: number;
    upper_band: number;
    deviation_pct: number;
    deviation_percentile: number;
    annualized_growth_pct: number;
  };
  trend_model_stability: {
    windows: Record<string, { start_date: string; observations: number; annualized_growth_pct: number }>;
    history: Array<{ date: string; annualized_growth_pct: number }>;
  };
  status: string;
  status_detail: string;
  alert: { level: string; code: "normal" | "watch" | "important" | "critical"; reasons: string[]; thresholds: Record<string, number> };
  freshness: { status: string; age_days: number; latest_market_date: string; checked_at: string };
  provenance: {
    latest_source: string;
    latest_is_provisional: boolean;
    authoritative_through: string;
    provisional_rows: number;
    data_fingerprint_sha256: string;
  };
  methodology: { trend_model_version: string; full_history_curve_is_descriptive: boolean; asof_curve_uses_future_data: boolean; asof_refit_cadence: string };
  context: {
    vxn: { value: number; as_of: string; source: string; freshness?: string; age_days?: number } | null;
    treasury10y: { value: number; as_of: string; source: string; freshness?: string; age_days?: number } | null;
    breadth: { above_ema20_pct?: number; above_ema50_pct?: number; above_ema200_pct: number; above_ema200_count: number | null; sample_size: number | null; new_high20_count?: number; new_low20_count?: number; as_of: string; source: string; freshness?: string; age_days?: number } | null;
    calibration?: { checked_at: string; corrected_rows: number; pending_rows: number; max_abs_diff_pct: number | null; max_diff_date: string | null } | null;
  };
};

type RegimeAnalysis = {
  current: string;
  stats: Record<string, { observations: number; forward: Record<string, { samples: number; overlapping_samples: number; median_return_pct: number | null; positive_rate_pct: number | null; median_ci95_low_pct: number | null; median_ci95_high_pct: number | null; excess_vs_baseline_pct: number | null }> }>;
  recent_events: Array<{ date: string; state: string }>;
};

type MarketData = {
  symbol: string;
  name: string;
  start_date: string;
  latest_date: string;
  summary: Summary;
  regime_analysis: RegimeAnalysis;
  series: Point[];
};

type ContextPoint = { date: string; vxn: number | null; treasury10y: number | null; ndx_vxn_corr60: number | null; breadth_ema20_pct: number | null; breadth_ema50_pct: number | null; breadth_ema200_pct: number | null; breadth_divergence: boolean | null };
type ContextData = { series: ContextPoint[] };

type Analysis = {
  market_date: string;
  generated_at: string;
  source: string;
  model: string | null;
  text: string;
  fact_validation?: string;
  disclaimer: string;
};

type Health = { checked_at: string; data?: { status: string; market_date: string }; ai?: { status: string; source: string; model: string | null }; email?: { status: string; market_date: string }; calibration?: { checked_at: string } | null };

const ranges = { "1年": 252, "3年": 756, "5年": 1260, "10年": 2520, 全部: Infinity } as const;
const marketEvents = [
  { date: "2000-03-10", label: "科技泡沫高点" },
  { date: "2008-09-15", label: "金融危机" },
  { date: "2020-03-23", label: "疫情冲击" },
] as const;
const basePath = process.env.NEXT_PUBLIC_BASE_PATH ?? "";
const assetPath = (path: string) => `${basePath}${path}${path.endsWith(".json") ? `?v=${Date.now()}` : ""}`;

function savedRange(key: string, fallback: keyof typeof ranges): keyof typeof ranges {
  if (typeof window === "undefined") return fallback;
  const value = new URLSearchParams(window.location.search).get(key);
  return value && Object.hasOwn(ranges, value) ? value as keyof typeof ranges : fallback;
}

function savedScale(key: string): boolean {
  return typeof window !== "undefined" && new URLSearchParams(window.location.search).get(key) === "log";
}

function signed(value: number | null | undefined, suffix = "%") {
  return value == null ? "—" : `${value >= 0 ? "+" : ""}${value.toFixed(2)}${suffix}`;
}

function number(value: number | null | undefined) {
  return value == null ? "—" : value.toLocaleString("zh-CN", { maximumFractionDigits: 2 });
}

function tone(value: number | null | undefined) {
  if (value == null || value === 0) return "neutral";
  return value > 0 ? "positive" : "negative";
}

type PriceVisibility = { close: boolean; ema50: boolean; ema200: boolean; robust: boolean; band: boolean };
type TrendVisibility = { close: boolean; robust: boolean; asof: boolean; band: boolean };

function downloadCanvas(canvas: HTMLCanvasElement | null, filename: string) {
  if (!canvas) return;
  const link = document.createElement("a");
  link.download = filename;
  link.href = canvas.toDataURL("image/png");
  link.click();
}

function PriceChart({ points, logScale, visibility }: { points: Point[]; logScale: boolean; visibility: PriceVisibility }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [hovered, setHovered] = useState<{ point: Point; x: number } | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || points.length < 2) return;
    const draw = () => {
      const bounds = canvas.getBoundingClientRect();
      const ratio = window.devicePixelRatio || 1;
      canvas.width = Math.max(1, Math.floor(bounds.width * ratio));
      canvas.height = Math.max(1, Math.floor(bounds.height * ratio));
      const context = canvas.getContext("2d");
      if (!context) return;
      context.setTransform(ratio, 0, 0, ratio, 0, 0);
      context.clearRect(0, 0, bounds.width, bounds.height);

      const padding = { top: 24, right: 24, bottom: 34, left: 58 };
      const width = bounds.width - padding.left - padding.right;
      const height = bounds.height - padding.top - padding.bottom;
      const values = points.flatMap((point) => [
        visibility.close ? point.close : null,
        visibility.ema50 ? point.ema50 : null,
        visibility.ema200 ? point.ema200 : null,
        visibility.band ? point.robust_lower : null,
        visibility.band ? point.robust_upper : null,
        visibility.robust ? point.robust_trend : null,
      ]).filter((v): v is number => v != null && v > 0);
      if (!values.length) values.push(...points.map((point) => point.close));
      const transformed = values.map((value) => (logScale ? Math.log(value) : value));
      const rawMin = Math.min(...transformed);
      const rawMax = Math.max(...transformed);
      const margin = (rawMax - rawMin || 1) * 0.06;
      const min = rawMin - margin;
      const max = rawMax + margin;
      const x = (index: number) => padding.left + (index / (points.length - 1)) * width;
      const y = (value: number) => {
        const normalized = ((logScale ? Math.log(value) : value) - min) / (max - min);
        return padding.top + height - normalized * height;
      };

      context.font = "11px ui-monospace, SFMono-Regular, Menlo, monospace";
      context.textAlign = "right";
      context.textBaseline = "middle";
      for (let line = 0; line <= 4; line += 1) {
        const py = padding.top + (height * line) / 4;
        context.strokeStyle = "rgba(148, 163, 184, 0.13)";
        context.lineWidth = 1;
        context.beginPath();
        context.moveTo(padding.left, py);
        context.lineTo(padding.left + width, py);
        context.stroke();
        const transformedValue = max - ((max - min) * line) / 4;
        const label = logScale ? Math.exp(transformedValue) : transformedValue;
        context.fillStyle = "#708099";
        context.fillText(label >= 10000 ? `${(label / 1000).toFixed(1)}k` : label.toFixed(0), padding.left - 9, py);
      }

      context.textAlign = "center";
      context.textBaseline = "top";
      [0, 0.25, 0.5, 0.75, 1].forEach((fraction) => {
        const index = Math.min(points.length - 1, Math.round((points.length - 1) * fraction));
        context.fillStyle = "#708099";
        context.fillText(points[index].date.slice(0, 7), x(index), padding.top + height + 11);
      });

      marketEvents.forEach((event) => {
        const index = points.findIndex((point) => point.date >= event.date);
        if (index < 0 || event.date < points[0].date) return;
        context.save();
        context.setLineDash([3, 5]);
        context.strokeStyle = "rgba(148, 163, 184, 0.24)";
        context.beginPath();
        context.moveTo(x(index), padding.top);
        context.lineTo(x(index), padding.top + height);
        context.stroke();
        context.restore();
        context.fillStyle = "#66778a";
        context.textAlign = "left";
        context.fillText(event.label, Math.min(x(index) + 4, padding.left + width - 64), padding.top + 4);
      });

      if (visibility.band) {
        context.fillStyle = "rgba(167, 139, 250, 0.09)";
        context.beginPath();
        points.forEach((point, index) => index ? context.lineTo(x(index), y(point.robust_upper)) : context.moveTo(x(index), y(point.robust_upper)));
        for (let index = points.length - 1; index >= 0; index -= 1) context.lineTo(x(index), y(points[index].robust_lower));
        context.closePath();
        context.fill();
      }

      const line = (key: "close" | "ema50" | "ema200" | "robust_trend", color: string, widthPx: number) => {
        context.strokeStyle = color;
        context.lineWidth = widthPx;
        context.lineJoin = "round";
        context.beginPath();
        let started = false;
        points.forEach((point, index) => {
          const value = point[key];
          if (value == null || value <= 0) return;
          if (!started) {
            context.moveTo(x(index), y(value));
            started = true;
          } else {
            context.lineTo(x(index), y(value));
          }
        });
        context.stroke();
      };

      if (visibility.ema200) line("ema200", "rgba(245, 158, 11, 0.92)", 1.4);
      if (visibility.ema50) line("ema50", "rgba(167, 139, 250, 0.82)", 1.2);
      if (visibility.robust) line("robust_trend", "rgba(244, 114, 182, 0.95)", 1.8);
      if (visibility.close) line("close", "#22d3ee", 2);
    };

    draw();
    const observer = new ResizeObserver(draw);
    observer.observe(canvas);
    return () => observer.disconnect();
  }, [points, logScale, visibility]);

  return (
    <div className="chart-wrap">
      <canvas
        ref={canvasRef}
        aria-label="NASDAQ-100 价格、EMA50 与 EMA200 历史走势图"
        onMouseLeave={() => setHovered(null)}
        onMouseMove={(event) => {
          const bounds = event.currentTarget.getBoundingClientRect();
          const ratio = Math.min(1, Math.max(0, (event.clientX - bounds.left - 58) / Math.max(1, bounds.width - 82)));
          setHovered({ point: points[Math.round(ratio * (points.length - 1))], x: event.clientX - bounds.left });
        }}
      />
      {hovered && <span className="chart-crosshair" style={{ left: hovered.x }} />}
      <button className="chart-download" onClick={() => downloadCanvas(canvasRef.current, `ndx-price-${points.at(-1)?.date ?? "chart"}.png`)}>下载 PNG</button>
      {hovered && (
        <div className="chart-tooltip" role="status">
          <span>{hovered.point.date}</span>
          <strong>{number(hovered.point.close)}</strong>
          <small>EMA200 {number(hovered.point.ema200)} · 稳健趋势 {number(hovered.point.robust_trend)} · 第 {number(hovered.point.robust_percentile)} 百分位</small>
        </div>
      )}
    </div>
  );
}

function RobustTrendChart({ points, logScale, visibility }: { points: Point[]; logScale: boolean; visibility: TrendVisibility }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [hovered, setHovered] = useState<{ point: Point; x: number } | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || points.length < 2) return;
    const draw = () => {
      const bounds = canvas.getBoundingClientRect();
      const ratio = window.devicePixelRatio || 1;
      canvas.width = Math.max(1, Math.floor(bounds.width * ratio));
      canvas.height = Math.max(1, Math.floor(bounds.height * ratio));
      const context = canvas.getContext("2d");
      if (!context) return;
      context.setTransform(ratio, 0, 0, ratio, 0, 0);
      context.clearRect(0, 0, bounds.width, bounds.height);

      const padding = { top: 18, right: 24, bottom: 34, left: 58 };
      const width = bounds.width - padding.left - padding.right;
      const height = bounds.height - padding.top - padding.bottom;
      const values = points.flatMap((point) => [
        visibility.close ? point.close : null,
        visibility.band ? point.robust_lower : null,
        visibility.band ? point.robust_upper : null,
        visibility.robust ? point.robust_trend : null,
        visibility.asof ? point.asof_robust_trend : null,
      ]).filter((value): value is number => value != null && value > 0).map((value) => logScale ? Math.log(value) : value);
      if (!values.length) values.push(...points.map((point) => logScale ? Math.log(point.close) : point.close));
      const rawMin = Math.min(...values);
      const rawMax = Math.max(...values);
      const margin = (rawMax - rawMin || 1) * 0.06;
      const min = logScale ? rawMin - margin : Math.max(0, rawMin - margin);
      const max = rawMax + margin;
      const x = (index: number) => padding.left + (index / (points.length - 1)) * width;
      const y = (value: number) => padding.top + height - (((logScale ? Math.log(value) : value) - min) / (max - min)) * height;

      context.font = "11px ui-monospace, SFMono-Regular, Menlo, monospace";
      context.textAlign = "right";
      context.textBaseline = "middle";
      for (let line = 0; line <= 4; line += 1) {
        const py = padding.top + (height * line) / 4;
        context.strokeStyle = "rgba(148, 163, 184, 0.13)";
        context.beginPath();
        context.moveTo(padding.left, py);
        context.lineTo(padding.left + width, py);
        context.stroke();
        const transformedValue = max - ((max - min) * line) / 4;
        const value = logScale ? Math.exp(transformedValue) : transformedValue;
        context.fillStyle = "#708099";
        context.fillText(value >= 10000 ? `${(value / 1000).toFixed(1)}k` : value.toFixed(0), padding.left - 9, py);
      }

      context.textAlign = "center";
      context.textBaseline = "top";
      [0, 0.25, 0.5, 0.75, 1].forEach((fraction) => {
        const index = Math.min(points.length - 1, Math.round((points.length - 1) * fraction));
        context.fillStyle = "#708099";
        context.fillText(points[index].date.slice(0, 7), x(index), padding.top + height + 11);
      });

      marketEvents.forEach((event) => {
        const index = points.findIndex((point) => point.date >= event.date);
        if (index < 0 || event.date < points[0].date) return;
        context.save();
        context.setLineDash([3, 5]);
        context.strokeStyle = "rgba(148, 163, 184, 0.24)";
        context.beginPath();
        context.moveTo(x(index), padding.top);
        context.lineTo(x(index), padding.top + height);
        context.stroke();
        context.restore();
        context.fillStyle = "#66778a";
        context.textAlign = "left";
        context.fillText(event.label, Math.min(x(index) + 4, padding.left + width - 64), padding.top + 4);
      });

      if (visibility.band) {
        context.fillStyle = "rgba(167, 139, 250, 0.11)";
        context.beginPath();
        points.forEach((point, index) => index ? context.lineTo(x(index), y(point.robust_upper)) : context.moveTo(x(index), y(point.robust_upper)));
        for (let index = points.length - 1; index >= 0; index -= 1) context.lineTo(x(index), y(points[index].robust_lower));
        context.closePath();
        context.fill();
      }

      const line = (field: "close" | "robust_trend" | "asof_robust_trend", color: string, widthPx: number, dashed = false) => {
        context.save();
        context.strokeStyle = color;
        context.lineWidth = widthPx;
        context.lineJoin = "round";
        if (dashed) context.setLineDash([7, 5]);
        context.beginPath();
        let started = false;
        points.forEach((point, index) => {
          const value = point[field];
          if (value == null || value <= 0) return;
          if (started) context.lineTo(x(index), y(value));
          else context.moveTo(x(index), y(value));
          started = true;
        });
        context.stroke();
        context.restore();
      };
      if (visibility.close) line("close", "rgba(34, 211, 238, 0.66)", 1.2);
      if (visibility.robust) line("robust_trend", "#a78bfa", 2.2);
      if (visibility.asof) line("asof_robust_trend", "#34d399", 1.8, true);
    };
    draw();
    const observer = new ResizeObserver(draw);
    observer.observe(canvas);
    return () => observer.disconnect();
  }, [points, logScale, visibility]);

  return <div className="robust-chart-wrap"><canvas ref={canvasRef} aria-label="NASDAQ-100 全历史稳健增长趋势与实际收盘点位" onMouseLeave={() => setHovered(null)} onMouseMove={(event) => {
    const bounds = event.currentTarget.getBoundingClientRect();
    const ratio = Math.min(1, Math.max(0, (event.clientX - bounds.left - 58) / Math.max(1, bounds.width - 82)));
    setHovered({ point: points[Math.round(ratio * (points.length - 1))], x: event.clientX - bounds.left });
  }} />{hovered && <span className="chart-crosshair" style={{ left: hovered.x }} />}<button className="chart-download" onClick={() => downloadCanvas(canvasRef.current, `ndx-robust-trend-${points.at(-1)?.date ?? "chart"}.png`)}>下载 PNG</button>{hovered && <div className="chart-tooltip" role="status"><span>{hovered.point.date}</span><strong>{number(hovered.point.close)}</strong><small>全历史 {number(hovered.point.robust_trend)} · 无未来数据 {number(hovered.point.asof_robust_trend)} · 第 {number(hovered.point.robust_percentile)} 百分位</small></div>}</div>;
}

function StabilityChart({ points }: { points: Array<{ date: string; annualized_growth_pct: number }> }) {
  if (points.length < 2) return null;
  const values = points.map((point) => point.annualized_growth_pct);
  const min = Math.min(...values) - 0.5;
  const max = Math.max(...values) + 0.5;
  const coordinates = points.map((point, index) => {
    const x = 3 + (index / (points.length - 1)) * 94;
    const y = 92 - ((point.annualized_growth_pct - min) / (max - min || 1)) * 84;
    return `${x},${y}`;
  }).join(" ");
  return (
    <div className="stability-chart" aria-label="历年末全历史稳健年化增速稳定性">
      <svg viewBox="0 0 100 100" preserveAspectRatio="none" role="img">
        <line x1="3" x2="97" y1="92" y2="92" />
        <polyline points={coordinates} />
      </svg>
      <span>{points[0].date.slice(0, 4)}</span><strong>{number(points.at(-1)?.annualized_growth_pct)}%</strong><span>{points.at(-1)?.date.slice(0, 4)}</span>
    </div>
  );
}

function IndicatorChart({
  points,
  field,
  color,
  reference,
}: {
  points: Point[];
  field: "drawdown_pct" | "rsi14" | "volatility20_pct";
  color: string;
  reference?: number;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const draw = () => {
      const bounds = canvas.getBoundingClientRect();
      const ratio = window.devicePixelRatio || 1;
      canvas.width = Math.max(1, Math.floor(bounds.width * ratio));
      canvas.height = Math.max(1, Math.floor(bounds.height * ratio));
      const context = canvas.getContext("2d");
      if (!context) return;
      context.setTransform(ratio, 0, 0, ratio, 0, 0);
      context.clearRect(0, 0, bounds.width, bounds.height);
      const values = points.map((point) => point[field]).filter((value): value is number => value != null);
      if (values.length < 2) return;
      const min = Math.min(...values, reference ?? Infinity);
      const max = Math.max(...values, reference ?? -Infinity);
      const spread = max - min || 1;
      const x = (index: number) => (index / Math.max(1, points.length - 1)) * bounds.width;
      const y = (value: number) => 8 + (bounds.height - 16) * (1 - (value - min) / spread);
      if (reference != null) {
        context.setLineDash([4, 4]);
        context.strokeStyle = "rgba(148,163,184,.28)";
        context.beginPath();
        context.moveTo(0, y(reference));
        context.lineTo(bounds.width, y(reference));
        context.stroke();
        context.setLineDash([]);
      }
      context.strokeStyle = color;
      context.lineWidth = 1.6;
      context.beginPath();
      let started = false;
      points.forEach((point, index) => {
        const value = point[field];
        if (value == null) return;
        if (!started) context.moveTo(x(index), y(value));
        else context.lineTo(x(index), y(value));
        started = true;
      });
      context.stroke();
    };
    draw();
    const observer = new ResizeObserver(draw);
    observer.observe(canvas);
    return () => observer.disconnect();
  }, [points, field, color, reference]);
  return <canvas className="indicator-canvas" ref={canvasRef} aria-label={`${field}历史走势图`} />;
}

function ContextIndicatorChart({
  points,
  field,
  color,
  label,
  reference,
}: {
  points: ContextPoint[];
  field: "vxn" | "treasury10y" | "ndx_vxn_corr60" | "breadth_ema20_pct" | "breadth_ema50_pct" | "breadth_ema200_pct";
  color: string;
  label: string;
  reference?: number;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const draw = () => {
      const bounds = canvas.getBoundingClientRect();
      const ratio = window.devicePixelRatio || 1;
      canvas.width = Math.max(1, Math.floor(bounds.width * ratio));
      canvas.height = Math.max(1, Math.floor(bounds.height * ratio));
      const context = canvas.getContext("2d");
      const values = points.map((point) => point[field]).filter((value): value is number => value != null);
      if (!context || values.length < 2) return;
      context.setTransform(ratio, 0, 0, ratio, 0, 0);
      context.clearRect(0, 0, bounds.width, bounds.height);
      const min = Math.min(...values, reference ?? Infinity);
      const max = Math.max(...values, reference ?? -Infinity);
      const spread = max - min || 1;
      const x = (index: number) => (index / Math.max(1, points.length - 1)) * bounds.width;
      const y = (value: number) => 8 + (bounds.height - 16) * (1 - (value - min) / spread);
      if (reference != null) {
        context.setLineDash([4, 4]);
        context.strokeStyle = "rgba(148,163,184,.28)";
        context.beginPath();
        context.moveTo(0, y(reference));
        context.lineTo(bounds.width, y(reference));
        context.stroke();
        context.setLineDash([]);
      }
      context.strokeStyle = color;
      context.lineWidth = 1.6;
      context.beginPath();
      let started = false;
      points.forEach((point, index) => {
        const value = point[field];
        if (value == null) return;
        if (!started) context.moveTo(x(index), y(value));
        else context.lineTo(x(index), y(value));
        started = true;
      });
      context.stroke();
    };
    draw();
    const observer = new ResizeObserver(draw);
    observer.observe(canvas);
    return () => observer.disconnect();
  }, [points, field, color, reference]);
  return <canvas className="indicator-canvas" ref={canvasRef} aria-label={label} />;
}

function RegimeTimeline({ points }: { points: Point[] }) {
  const sampled = points.filter((_, index) => index % Math.max(1, Math.floor(points.length / 180)) === 0);
  return (
    <div className="regime-timeline" aria-label="市场状态时间轴">
      {sampled.map((point) => {
        const state = point.ema200 == null ? "unknown" : point.close < point.ema200 ? "defensive" : point.ema50 != null && point.ema50 > point.ema200 ? "trend" : "repair";
        return <span key={point.date} className={state} title={`${point.date} · ${state}`} />;
      })}
    </div>
  );
}

export default function Home() {
  const [market, setMarket] = useState<MarketData | null>(null);
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [context, setContext] = useState<ContextData | null>(null);
  const [analysisHistory, setAnalysisHistory] = useState<Analysis[]>([]);
  const [health, setHealth] = useState<Health | null>(null);
  const [range, setRange] = useState<keyof typeof ranges>(() => savedRange("priceRange", "5年"));
  const [logScale, setLogScale] = useState(() => savedScale("priceScale"));
  const [trendRange, setTrendRange] = useState<keyof typeof ranges>(() => savedRange("trendRange", "全部"));
  const [trendLogScale, setTrendLogScale] = useState(() => savedScale("trendScale"));
  const [priceVisibility, setPriceVisibility] = useState<PriceVisibility>({ close: true, ema50: true, ema200: true, robust: true, band: true });
  const [trendVisibility, setTrendVisibility] = useState<TrendVisibility>({ close: true, robust: true, asof: true, band: true });
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const query = new URLSearchParams(window.location.search);
    query.set("priceRange", range);
    query.set("priceScale", logScale ? "log" : "linear");
    query.set("trendRange", trendRange);
    query.set("trendScale", trendLogScale ? "log" : "linear");
    window.history.replaceState(null, "", `${window.location.pathname}?${query}`);
  }, [range, logScale, trendRange, trendLogScale]);

  useEffect(() => {
    Promise.all([
      fetch(assetPath("/data/nasdaq100.json"), { cache: "no-store" }).then((response) => {
        if (!response.ok) throw new Error("市场数据尚未生成");
        return response.json();
      }),
      fetch(assetPath("/data/analysis.json"), { cache: "no-store" }).then((response) => response.json()),
      fetch(assetPath("/data/context.json"), { cache: "no-store" }).then((response) => response.json()),
      fetch(assetPath("/data/analysis_history.json"), { cache: "no-store" }).then((response) => response.json()),
      fetch(assetPath("/data/health.json"), { cache: "no-store" }).then((response) => response.json()),
    ])
      .then(([marketData, analysisData, contextData, historyData, healthData]) => {
        setMarket(marketData);
        setAnalysis(analysisData);
        setContext(contextData);
        setAnalysisHistory(historyData);
        setHealth(healthData);
      })
      .catch((reason) => setError(reason instanceof Error ? reason.message : "数据加载失败"));
  }, []);

  const visiblePoints = useMemo(() => {
    if (!market) return [];
    const sessions = ranges[range];
    return Number.isFinite(sessions) ? market.series.slice(-sessions) : market.series;
  }, [market, range]);

  const visibleTrendPoints = useMemo(() => {
    if (!market) return [];
    const sessions = ranges[trendRange];
    return Number.isFinite(sessions) ? market.series.slice(-sessions) : market.series;
  }, [market, trendRange]);

  const visibleContext = useMemo(() => {
    if (!context || !visiblePoints.length) return [];
    const start = visiblePoints[0].date;
    return context.series.filter((point) => point.date >= start);
  }, [context, visiblePoints]);

  if (error) {
    return <main className="center-state"><strong>数据暂不可用</strong><span>{error}</span></main>;
  }
  if (!market || !analysis || !context) {
    return <main className="center-state"><span className="pulse" /><strong>正在载入 NASDAQ-100 历史数据</strong></main>;
  }

  const summary = market.summary;
  const robustTrend = summary.robust_log_trend;
  const asofTrend = summary.asof_robust_log_trend;
  const stability = summary.trend_model_stability;
  const uncertainty = robustTrend.uncertainty;
  const recent = market.series.slice(-12).reverse();
  const returnCards = [
    ["1个月", summary.returns.one_month],
    ["3个月", summary.returns.three_months],
    ["今年以来", summary.returns.ytd],
    ["1年", summary.returns.one_year],
    ["1990至今年化", summary.returns.since_1990_cagr],
  ] as const;

  return (
    <main>
      <header className="topbar">
        <div className="brand"><span className="brand-mark">N</span><div><strong>NDX SIGNAL DESK</strong><small>NASDAQ-100 MARKET INTELLIGENCE</small></div></div>
        <div className="market-stamp"><span className={`live-dot ${summary.freshness.status !== "正常" ? "warn" : ""}`} />数据截至 {summary.market_date}<span>·</span>{summary.freshness.status}<span className={`alert-chip ${summary.alert.code}`}>{summary.alert.level}</span></div>
        <nav className="top-actions"><a className="download" href={assetPath(`/sectors${basePath ? ".html" : ""}`)}>持仓板块</a><a className="download" href={assetPath("/data/nasdaq100_daily_data.csv")} download>下载完整 CSV</a></nav>
      </header>

      <div className="dashboard">
        <section className="hero panel">
          <div>
            <div className="eyebrow">NASDAQ-100 · ^NDX</div>
            <div className="headline"><h1>{number(summary.close)}</h1><span className={tone(summary.daily_return_pct)}>{signed(summary.daily_return_pct)}</span></div>
            <p>{summary.status_detail}</p>
          </div>
          <div className={`regime ${summary.distance_ema200_pct >= 0 ? "regime-up" : "regime-down"}`}>
            <span>市场状态 · {summary.alert.level}</span><strong>{summary.status}</strong><small>距 EMA200 {signed(summary.distance_ema200_pct)}</small><small>{summary.alert.reasons.join("；")}</small>
          </div>
        </section>

        <section className="metrics">
          <article className="metric panel"><span>EMA 50</span><strong>{number(summary.ema50)}</strong><small>中期趋势</small></article>
          <article className="metric panel"><span>EMA 200</span><strong>{number(summary.ema200)}</strong><small>长期趋势</small></article>
          <article className="metric panel"><span>RSI 14</span><strong>{number(summary.rsi14)}</strong><small>{summary.rsi14 > 70 ? "偏热区间" : summary.rsi14 < 30 ? "偏冷区间" : "中性区间"}</small></article>
          <article className="metric panel"><span>20日波动率</span><strong>{number(summary.volatility20_pct)}%</strong><small>年化历史波动</small></article>
          <article className="metric panel"><span>距52周高点</span><strong className={tone(summary.distance_high252_pct)}>{signed(summary.distance_high252_pct)}</strong><small>价格位置</small></article>
          <article className="metric panel"><span>当前回撤</span><strong className={tone(summary.drawdown_pct)}>{signed(summary.drawdown_pct)}</strong><small>历史最大 {signed(summary.max_drawdown_pct)}</small></article>
        </section>

        <section className="context-strip panel">
          <div><span>数据口径</span><strong>{summary.provenance.latest_source}{summary.provenance.latest_is_provisional ? " · 临时" : " · 权威"}</strong><small>FRED 校准至 {summary.provenance.authoritative_through}</small></div>
          <div><span>VXN</span><strong>{number(summary.context.vxn?.value)}</strong><small>{summary.context.vxn?.as_of ?? "暂无数据"} · {summary.context.vxn?.source ?? "—"} · {summary.context.vxn?.freshness ?? "—"}</small></div>
          <div><span>10年期美债</span><strong>{summary.context.treasury10y ? `${number(summary.context.treasury10y.value)}%` : "—"}</strong><small>{summary.context.treasury10y?.as_of ?? "暂无数据"} · {summary.context.treasury10y?.source ?? "—"} · {summary.context.treasury10y?.freshness ?? "—"}</small></div>
          <div><span>成分股站上 EMA200</span><strong>{summary.context.breadth ? `${number(summary.context.breadth.above_ema200_pct)}%` : "待首次成功计算"}</strong><small>{summary.context.breadth ? `${summary.context.breadth.above_ema200_count == null ? summary.context.breadth.source : `${summary.context.breadth.above_ema200_count}/${summary.context.breadth.sample_size}`} · ${summary.context.breadth.as_of} · ${summary.context.breadth.freshness ?? "—"}` : "Nasdaq 名单 + Yahoo 日线"}</small></div>
        </section>

        <section className="chart-panel panel">
          <div className="section-head">
            <div><span className="eyebrow">PRICE STRUCTURE</span><h2>长期趋势与均线结构</h2></div>
            <div className="chart-controls">
              <div className="segmented" aria-label="时间范围">
                {(Object.keys(ranges) as Array<keyof typeof ranges>).map((label) => <button key={label} aria-pressed={range === label} className={range === label ? "active" : ""} onClick={() => setRange(label)}>{label}</button>)}
              </div>
              <button aria-pressed={logScale} className={`scale-button ${logScale ? "active" : ""}`} onClick={() => setLogScale((value) => !value)}>{logScale ? "对数尺度" : "线性尺度"}</button>
            </div>
          </div>
          <div className="legend interactive-legend">
            <button aria-pressed={priceVisibility.close} onClick={() => setPriceVisibility((value) => ({ ...value, close: !value.close }))}><i className="close-line" />收盘</button>
            <button aria-pressed={priceVisibility.ema50} onClick={() => setPriceVisibility((value) => ({ ...value, ema50: !value.ema50 }))}><i className="ema50-line" />EMA50</button>
            <button aria-pressed={priceVisibility.ema200} onClick={() => setPriceVisibility((value) => ({ ...value, ema200: !value.ema200 }))}><i className="ema200-line" />EMA200</button>
            <button aria-pressed={priceVisibility.robust} onClick={() => setPriceVisibility((value) => ({ ...value, robust: !value.robust }))}><i className="robust-main-line" />稳健拟合</button>
            <button aria-pressed={priceVisibility.band} onClick={() => setPriceVisibility((value) => ({ ...value, band: !value.band }))}><i className="robust-band" />经验区间</button>
          </div>
          <PriceChart points={visiblePoints} logScale={logScale} visibility={priceVisibility} />
          <div className="timeline-label"><span>防御</span><span>修复</span><span>多头</span></div>
          <RegimeTimeline points={visiblePoints} />
        </section>

        <section className="robust-trend-panel panel">
          <div className="section-head">
            <div><span className="eyebrow">ROBUST GROWTH PATH</span><h2>全历史稳健增长趋势</h2></div>
            <div className="chart-controls">
              <div className="segmented" aria-label="稳健趋势时间范围">
                {(Object.keys(ranges) as Array<keyof typeof ranges>).map((label) => <button key={label} aria-pressed={trendRange === label} className={trendRange === label ? "active" : ""} onClick={() => setTrendRange(label)}>{label}</button>)}
              </div>
              <button aria-pressed={trendLogScale} className={`scale-button ${trendLogScale ? "active" : ""}`} onClick={() => setTrendLogScale((value) => !value)}>{trendLogScale ? "对数尺度" : "线性尺度"}</button>
            </div>
          </div>
          <div className="trend-summary">
            <p><span>当前拟合点位</span><strong>{number(robustTrend.fitted_close)}</strong><small>实际 {number(summary.close)}</small></p>
            <p><span>相对趋势偏离</span><strong className={tone(robustTrend.deviation_pct)}>{signed(robustTrend.deviation_pct)}</strong><small>正值高于长期路径</small></p>
            <p><span>历史偏离百分位</span><strong>第 {number(robustTrend.deviation_percentile)}</strong><small>{robustTrend.above_upper_days ? `连续 ${robustTrend.above_upper_days} 日高于上轨` : robustTrend.below_lower_days ? `连续 ${robustTrend.below_lower_days} 日低于下轨` : "位于中央经验区间"}</small></p>
            <p><span>隐含长期年化</span><strong>{number(robustTrend.annualized_growth_pct)}%</strong><small>95%：{number(uncertainty.annualized_growth_ci95_pct[0])}%–{number(uncertainty.annualized_growth_ci95_pct[1])}%</small></p>
            <p><span>经验中枢区间</span><strong>{number(robustTrend.lower_band)}–{number(robustTrend.upper_band)}</strong><small>历史残差 10%–90% · 覆盖 {number(robustTrend.central_coverage_pct)}%</small></p>
            <p><span>无未来数据趋势</span><strong>{number(asofTrend.fitted_close)}</strong><small>偏离 {signed(asofTrend.deviation_pct)} · 训练至 {asofTrend.training_end}</small></p>
          </div>
          <div className="legend robust-legend interactive-legend">
            <button aria-pressed={trendVisibility.close} onClick={() => setTrendVisibility((value) => ({ ...value, close: !value.close }))}><i className="close-line" />实际收盘</button>
            <button aria-pressed={trendVisibility.robust} onClick={() => setTrendVisibility((value) => ({ ...value, robust: !value.robust }))}><i className="robust-line" />全历史拟合</button>
            <button aria-pressed={trendVisibility.asof} onClick={() => setTrendVisibility((value) => ({ ...value, asof: !value.asof }))}><i className="asof-line" />无未来数据拟合</button>
            <button aria-pressed={trendVisibility.band} onClick={() => setTrendVisibility((value) => ({ ...value, band: !value.band }))}><i className="robust-band" />经验区间</button>
          </div>
          <RobustTrendChart points={visibleTrendPoints} logScale={trendLogScale} visibility={trendVisibility} />
          <p className="method-note">紫色全历史拟合用于描述长期结构，会使用当前可得的全部数据；绿色虚线在每月首个交易日仅使用截至上月末的数据重估，可用于无前视偏差的历史观察。经验区间是历史残差中央 80%，不是预测区间。异常偏离会被自动降权（本次 {number(robustTrend.downweighted_pct)}% 样本）。</p>
          <div className="model-validity">
            <div><span className="eyebrow">MODEL VALIDITY</span><h3>长期斜率稳定性与参数不确定性</h3></div>
            <div className="stability-windows">{Object.entries(stability.windows).map(([label, item]) => <p key={label}><span>{label}</span><strong>{number(item.annualized_growth_pct)}%</strong><small>{item.start_date} · {item.observations.toLocaleString("zh-CN")} 日</small></p>)}</div>
            <StabilityChart points={stability.history} />
            <p className="method-note">年末序列每次只使用当时已有数据；斜率 95% 区间采用 {uncertainty.samples} 次、每块 {uncertainty.block_sessions} 个交易日的移动区块残差 Bootstrap。拟合点位参数区间为 {number(uncertainty.fitted_close_ci95[0])}–{number(uncertainty.fitted_close_ci95[1])}。模型版本 {summary.methodology.trend_model_version}，数据指纹 {summary.provenance.data_fingerprint_sha256.slice(0, 12)}。</p>
          </div>
        </section>

        <section className="risk-panel panel">
          <div className="section-head"><div><span className="eyebrow">RISK DIAGNOSTICS</span><h2>回撤、动量与波动结构</h2></div></div>
          <div className="risk-grid">
            <article><div><span>历史回撤</span><strong className="negative">{signed(summary.drawdown_pct)}</strong></div><IndicatorChart points={visiblePoints} field="drawdown_pct" color="#fb7185" reference={0} /></article>
            <article><div><span>RSI 14</span><strong>{number(summary.rsi14)}</strong></div><IndicatorChart points={visiblePoints} field="rsi14" color="#a78bfa" reference={50} /></article>
            <article><div><span>20日年化波动</span><strong>{number(summary.volatility20_pct)}%</strong></div><IndicatorChart points={visiblePoints} field="volatility20_pct" color="#f59e0b" /></article>
          </div>
        </section>

        <section className="context-history panel">
          <div className="section-head"><div><span className="eyebrow">MARKET CONTEXT</span><h2>市场环境历史联动</h2></div><span className="row-count">与所选价格区间同步</span></div>
          <div className="risk-grid">
            <article><div><span>VXN 波动率预期</span><strong>{number(summary.context.vxn?.value)}</strong></div><ContextIndicatorChart points={visibleContext} field="vxn" color="#fb7185" label="VXN 历史走势" /></article>
            <article><div><span>美国10年期收益率</span><strong>{number(summary.context.treasury10y?.value)}%</strong></div><ContextIndicatorChart points={visibleContext} field="treasury10y" color="#f59e0b" label="美国10年期国债收益率历史走势" /></article>
            <article><div><span>NDX/VXN 60日相关性</span><strong>{signed(visibleContext.at(-1)?.ndx_vxn_corr60, "")}</strong></div><ContextIndicatorChart points={visibleContext} field="ndx_vxn_corr60" color="#22d3ee" label="NASDAQ-100 收益与 VXN 变化的60日滚动相关性" reference={0} /></article>
          </div>
          <div className="risk-grid">
            <article><div><span>站上 EMA20</span><strong>{number(summary.context.breadth?.above_ema20_pct)}%</strong></div><ContextIndicatorChart points={visibleContext} field="breadth_ema20_pct" color="#22d3ee" label="成分股站上 EMA20 比例" reference={50} /></article>
            <article><div><span>站上 EMA50</span><strong>{number(summary.context.breadth?.above_ema50_pct)}%</strong></div><ContextIndicatorChart points={visibleContext} field="breadth_ema50_pct" color="#a78bfa" label="成分股站上 EMA50 比例" reference={50} /></article>
            <article><div><span>站上 EMA200</span><strong>{number(summary.context.breadth?.above_ema200_pct)}%</strong></div><ContextIndicatorChart points={visibleContext} field="breadth_ema200_pct" color="#34d399" label="成分股站上 EMA200 比例" reference={50} /></article>
          </div>
          <p className="method-note">市场宽度从本次升级起逐日积累；20 日创新高/新低：{summary.context.breadth?.new_high20_count ?? "—"} / {summary.context.breadth?.new_low20_count ?? "—"}。价格上涨而 EMA200 宽度走弱时标记为背离。</p>
          <p className="method-note">相关性使用日收益与 VXN 日变化的 60 个交易日窗口；仅描述同期关系，不代表因果。</p>
        </section>

        <section className="regime-evidence panel">
          <div className="section-head"><div><span className="eyebrow">SIGNAL EVIDENCE</span><h2>市场状态的历史后续表现</h2></div><span className="source-chip">当前 {market.regime_analysis.current}</span></div>
          <div className="evidence-grid">
            {(Object.entries(market.regime_analysis.stats)).map(([state, stats]) => (
              <article key={state}>
                <div className="evidence-title"><strong>{state}</strong><span>{stats.observations.toLocaleString("zh-CN")} 个交易日</span></div>
                <table><thead><tr><th>观察期</th><th>独立样本</th><th>中位收益</th><th>95%区间</th><th>超额</th></tr></thead><tbody>
                  {Object.entries(stats.forward).map(([horizon, value]) => <tr key={horizon}><td>{horizon}</td><td title={`重叠样本 ${value.overlapping_samples}`}>{value.samples}</td><td className={tone(value.median_return_pct)}>{signed(value.median_return_pct)}</td><td>{signed(value.median_ci95_low_pct)}～{signed(value.median_ci95_high_pct)}</td><td className={tone(value.excess_vs_baseline_pct)}>{signed(value.excess_vs_baseline_pct)}</td></tr>)}
                </tbody></table>
              </article>
            ))}
          </div>
          <div className="event-log"><span>最近状态切换</span>{market.regime_analysis.recent_events.slice(-6).reverse().map((event) => <div key={`${event.date}-${event.state}`}><time>{event.date}</time><strong>{event.state}</strong></div>)}</div>
          <p className="method-note">采用互不重叠样本，95% 为分布无关的中位数区间；“超额”相对同期全市场持有基准。另按高波动/常规波动分组写入数据文件，均不含交易成本。</p>
        </section>

        <section className="audit-panel panel">
          <div><span className="eyebrow">DATA AUDIT</span><h2>权威数据校准</h2></div>
          {summary.context.calibration ? <div className="audit-grid"><p><span>本次校准行数</span><strong>{summary.context.calibration.corrected_rows}</strong></p><p><span>仍待权威发布</span><strong>{summary.context.calibration.pending_rows}</strong></p><p><span>最大临时偏差</span><strong>{summary.context.calibration.max_abs_diff_pct == null ? "—" : `${summary.context.calibration.max_abs_diff_pct.toFixed(4)}%`}</strong></p><p><span>最大偏差日期</span><strong>{summary.context.calibration.max_diff_date ?? "—"}</strong></p></div> : <p className="method-note">等待下一次周度 FRED 权威校准后生成差异审计。</p>}
        </section>

        <section className="returns panel">
          <div className="section-head"><div><span className="eyebrow">RETURN WINDOWS</span><h2>多周期收益</h2></div></div>
          <div className="return-grid">
            {returnCards.map(([label, value]) => <div key={label}><span>{label}</span><strong className={tone(value)}>{signed(value)}</strong></div>)}
          </div>
          <p className="method-note">收益基于日线收盘价；长期年化区间从 {market.start_date} 开始。</p>
        </section>

        <section className="ai-panel panel">
          <div className="section-head"><div><span className="eyebrow">AI RISK BRIEF</span><h2>结构化市场解读</h2></div><span className="source-chip">{analysis.source}{analysis.model ? ` · ${analysis.model}` : ""} · {analysis.fact_validation === "passed" ? "事实已校验 · " : "规则校验 · "}{new Date(analysis.generated_at).toLocaleString("zh-CN", { timeZone: "Asia/Shanghai", hour12: false })}</span></div>
          <div className="ai-copy">{analysis.text}</div>
          <p className="disclaimer">{analysis.disclaimer}</p>
          {analysisHistory.length > 1 && <details className="analysis-history"><summary>查看历史 AI 分析（{analysisHistory.length} 期）</summary>{analysisHistory.slice(0, -1).reverse().slice(0, 8).map((item) => <article key={item.market_date}><strong>{item.market_date} · {item.source}</strong><p>{item.text}</p></article>)}</details>}
        </section>

        <section className="health-panel panel">
          <div className="section-head"><div><span className="eyebrow">SYSTEM HEALTH</span><h2>自动化运行状态</h2></div><span className="source-chip">{health ? new Date(health.checked_at).toLocaleString("zh-CN", { timeZone: "Asia/Shanghai", hour12: false }) : "—"}</span></div>
          <div className="health-grid"><p><span>行情</span><strong>{health?.data?.status ?? "—"}</strong><small>{health?.data?.market_date ?? "—"}</small></p><p><span>AI</span><strong>{health?.ai?.status ?? "—"}</strong><small>{health?.ai?.source ?? "—"}</small></p><p><span>邮件</span><strong>{health?.email?.status ?? "—"}</strong><small>{health?.email?.market_date ?? "—"}</small></p><p><span>告警阈值</span><strong>VXN {summary.alert.thresholds.vxn} · 宽度 {summary.alert.thresholds.breadth}%</strong><small>波动 {summary.alert.thresholds.volatility}% · EMA ±{summary.alert.thresholds.ema_distance}%</small></p></div>
        </section>

        <section className="table-panel panel">
          <div className="section-head"><div><span className="eyebrow">RECENT SESSIONS</span><h2>最近交易日明细</h2></div><span className="row-count">历史 {market.series.length.toLocaleString("zh-CN")} 行</span></div>
          <div className="table-scroll">
            <table>
              <thead><tr><th>日期</th><th>收盘</th><th>EMA50</th><th>EMA200</th><th>RSI14</th><th>波动率</th><th>回撤</th></tr></thead>
              <tbody>{recent.map((row) => <tr key={row.date}><td>{row.date}</td><td>{number(row.close)}</td><td>{number(row.ema50)}</td><td>{number(row.ema200)}</td><td>{number(row.rsi14)}</td><td>{row.volatility20_pct == null ? "—" : `${row.volatility20_pct.toFixed(2)}%`}</td><td className={tone(row.drawdown_pct)}>{signed(row.drawdown_pct)}</td></tr>)}</tbody>
            </table>
          </div>
        </section>

        <section className="methodology panel">
          <div><span className="eyebrow">METHODOLOGY</span><h2>数据与判断口径</h2></div>
          <div className="method-grid">
            <p><strong>趋势</strong><span>收盘价、EMA50 与 EMA200 的相对位置定义市场状态，不预测拐点。</span></p>
            <p><strong>风险</strong><span>20 日年化波动、历史高点回撤和 52 周价格位置共同描述风险环境。</span></p>
            <p><strong>AI 边界</strong><span>只解释已提供的价格、风险与市场环境指标，不抓取新闻，不输出绝对交易指令。</span></p>
          </div>
        </section>
      </div>

      <footer>NASDAQ-100 DAILY MONITOR <span>·</span> 数据研究工具，非投资建议</footer>
    </main>
  );
}
