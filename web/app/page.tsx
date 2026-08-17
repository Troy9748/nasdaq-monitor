"use client";

import { useEffect, useMemo, useRef, useState } from "react";

type Point = {
  date: string;
  close: number;
  ema20: number | null;
  ema50: number | null;
  ema200: number | null;
  sma200: number | null;
  bollinger_mid: number | null;
  bollinger_upper: number | null;
  bollinger_lower: number | null;
  macd: number | null;
  macd_signal: number | null;
  macd_histogram: number | null;
  roc20_pct: number | null;
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
  composite_score: { score: number; label: string; components: Record<string, number>; weights: Record<string, number>; interpretation: string };
  risk_dashboard: { window_sessions: number; historical_var95_1d_pct: number; expected_shortfall95_1d_pct: number; downside_volatility_pct: number; sortino_ratio: number; current_drawdown_duration_sessions: number; max_drawdown_duration_sessions: number; median_recovery_sessions: number; method: string };
  walk_forward_validation: { signal: string; transaction_cost_bps: number; uses_future_data: boolean; strategy: Record<string, number>; buy_and_hold: Record<string, number>; annual_turnover_pct: number; position_changes: number; median_mae_pct: number; median_mfe_pct: number; yearly: Array<{ year: number; strategy_return_pct: number; benchmark_return_pct: number }>; limitations: string };
  stress_scenarios: Array<{ name: string; start_date: string; trough_date: string; peak_to_trough_pct: number; worst_day_pct: number; recovery_date: string | null; recovery_sessions: number | null }>;
  data_quality: { score: number; grade: string; components: Record<string, number>; warnings: string[]; methodology_version: string };
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
  methodology: { version: string; trend_model_version: string; full_history_curve_is_descriptive: boolean; asof_curve_uses_future_data: boolean; asof_refit_cadence: string };
  context: {
    vxn: { value: number; as_of: string; source: string; freshness?: string; age_days?: number } | null;
    treasury10y: { value: number; as_of: string; source: string; freshness?: string; age_days?: number } | null;
    breadth: { above_ema20_pct?: number; above_ema50_pct?: number; above_ema200_pct: number; above_ema200_count: number | null; sample_size: number | null; new_high20_count?: number; new_low20_count?: number; acceleration_5d_pct_points?: number | null; price_breadth_divergence_20d?: boolean | null; concentration?: { top10_market_cap_share_pct: number; top10_daily_contribution_proxy_pct: number; members: string[]; method: string }; constituent_history?: string; as_of: string; source: string; freshness?: string; age_days?: number } | null;
    relative_strength: { benchmarks: Record<string, { label: string; excess_return_pct: Record<string, number | null> }>; qqq_cash_excess_1y_pct: number | null; method: string };
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

type ContextPoint = { date: string; vxn: number | null; treasury10y: number | null; ndx_vxn_corr60: number | null; breadth_ema20_pct: number | null; breadth_ema50_pct: number | null; breadth_ema200_pct: number | null; breadth_divergence: boolean | null; sp500: number | null; ndx_equal_weight: number | null; russell2000: number | null; qqq: number | null; treasury3m: number | null };
type ContextData = { series: ContextPoint[] };

type Analysis = {
  market_date: string;
  generated_at: string;
  source: string;
  model: string | null;
  text: string;
  fact_validation?: string;
  disclaimer: string;
  evidence?: Array<{ metric: string; value: number; supports: string }>;
  contradictions?: string[];
  invalidation_conditions?: string[];
  data_quality?: Summary["data_quality"];
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

type PriceVisibility = { close: boolean; ema20: boolean; ema50: boolean; ema200: boolean; sma200: boolean; bollinger: boolean; robust: boolean; band: boolean };
type TrendVisibility = { close: boolean; robust: boolean; asof: boolean; band: boolean };
type RiskIndicator = "rsi" | "macd" | "roc20" | "volatility" | "drawdown" | "trendDeviation";
type RiskVisibility = Record<RiskIndicator, boolean>;

const basicPriceVisibility: PriceVisibility = { close: true, ema20: false, ema50: true, ema200: true, sma200: false, bollinger: false, robust: false, band: false };
const pricePresets: Record<string, PriceVisibility> = {
  基础: basicPriceVisibility,
  短线: { close: true, ema20: true, ema50: true, ema200: false, sma200: false, bollinger: true, robust: false, band: false },
  长期: { close: true, ema20: false, ema50: false, ema200: true, sma200: false, bollinger: false, robust: true, band: true },
  清空: { close: false, ema20: false, ema50: false, ema200: false, sma200: false, bollinger: false, robust: false, band: false },
};
const basicRiskVisibility: RiskVisibility = { rsi: true, macd: true, roc20: false, volatility: false, drawdown: true, trendDeviation: false };
const indicatorGuide = [
  ["EMA20 / EMA50 / EMA200", "指数加权均线", "分别观察约一个月、中期和长期趋势；近期价格权重更高。均线滞后，不能单独预测拐点。"],
  ["SMA200", "长期简单均线", "每个交易日等权，适合与常见长期市场口径对照；与 EMA200 同开通常信息重复。"],
  ["布林带 20, 2", "波动包络", "20日均线加减两倍标准差；带宽扩张表示近期波动放大，触及上下轨不等于反转。"],
  ["RSI14", "动量强弱", "0–100 区间；70以上偏热、30以下偏冷。强趋势中可长时间停留在极端区域。"],
  ["MACD 12, 26, 9", "趋势动量", "EMA12 与 EMA26 的差及其9日信号线；交叉反映动量变化，但震荡市容易反复。"],
  ["20日涨跌幅", "短期动量", "当前收盘相对20个交易日前的变化；零轴用于区分正负动量，不代表未来收益。"],
  ["20日年化波动", "已实现风险", "最近20日收益标准差年化；衡量波动强度，不判断上涨或下跌方向。"],
  ["历史回撤", "资本损伤", "当前点位相对此前历史高点的跌幅；比单日涨跌更适合观察风险恢复过程。"],
  ["稳健趋势偏离", "长期位置", "实际价格相对 Huber 对数趋势的百分比；描述历史位置，不是估值或目标价。"],
] as const;

function savedVisibility<T extends Record<string, boolean>>(key: string, fallback: T): T {
  if (typeof window === "undefined") return fallback;
  const raw = new URLSearchParams(window.location.search).get(key);
  if (raw == null) return fallback;
  const selected = new Set(raw === "none" ? [] : raw.split(","));
  return Object.fromEntries(Object.keys(fallback).map((name) => [name, selected.has(name)])) as T;
}

function visibilityQuery(value: Record<string, boolean>) {
  return Object.entries(value).filter(([, visible]) => visible).map(([name]) => name).join(",") || "none";
}

function downloadCanvas(canvas: HTMLCanvasElement | null, filename: string) {
  if (!canvas) return;
  const link = document.createElement("a");
  link.download = filename;
  link.href = canvas.toDataURL("image/png");
  link.click();
}

function priceDetails(point: Point, visibility: PriceVisibility) {
  const values = [
    visibility.ema20 && `EMA20 ${number(point.ema20)}`,
    visibility.ema50 && `EMA50 ${number(point.ema50)}`,
    visibility.ema200 && `EMA200 ${number(point.ema200)}`,
    visibility.sma200 && `SMA200 ${number(point.sma200)}`,
    visibility.bollinger && `布林带 ${number(point.bollinger_lower)}–${number(point.bollinger_upper)}`,
    visibility.robust && `稳健趋势 ${number(point.robust_trend)}`,
    visibility.band && `经验区间 ${number(point.robust_lower)}–${number(point.robust_upper)}`,
  ].filter(Boolean);
  return values.length ? values.join(" · ") : "未选择价格曲线";
}

function PriceChart({ points, logScale, visibility, sharedDate, onHoverDate }: { points: Point[]; logScale: boolean; visibility: PriceVisibility; sharedDate?: string; onHoverDate?: (date: string) => void }) {
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
        visibility.ema20 ? point.ema20 : null,
        visibility.ema50 ? point.ema50 : null,
        visibility.ema200 ? point.ema200 : null,
        visibility.sma200 ? point.sma200 : null,
        visibility.bollinger ? point.bollinger_lower : null,
        visibility.bollinger ? point.bollinger_upper : null,
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

      if (visibility.bollinger) {
        context.fillStyle = "rgba(34, 211, 238, 0.07)";
        context.beginPath();
        let started = false;
        points.forEach((point, index) => {
          if (point.bollinger_upper == null) return;
          if (started) context.lineTo(x(index), y(point.bollinger_upper));
          else context.moveTo(x(index), y(point.bollinger_upper));
          started = true;
        });
        for (let index = points.length - 1; index >= 0; index -= 1) {
          const value = points[index].bollinger_lower;
          if (value != null) context.lineTo(x(index), y(value));
        }
        context.closePath();
        context.fill();
      }

      const line = (key: "close" | "ema20" | "ema50" | "ema200" | "sma200" | "bollinger_mid" | "bollinger_upper" | "bollinger_lower" | "robust_trend", color: string, widthPx: number, dashed = false) => {
        context.save();
        context.strokeStyle = color;
        context.lineWidth = widthPx;
        context.lineJoin = "round";
        if (dashed) context.setLineDash([5, 4]);
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
        context.restore();
      };

      if (visibility.bollinger) {
        line("bollinger_upper", "rgba(34, 211, 238, 0.48)", 1, true);
        line("bollinger_lower", "rgba(34, 211, 238, 0.48)", 1, true);
        line("bollinger_mid", "rgba(34, 211, 238, 0.34)", 1);
      }
      if (visibility.sma200) line("sma200", "rgba(248, 113, 113, 0.9)", 1.3, true);
      if (visibility.ema200) line("ema200", "rgba(245, 158, 11, 0.92)", 1.4);
      if (visibility.ema50) line("ema50", "rgba(167, 139, 250, 0.82)", 1.2);
      if (visibility.ema20) line("ema20", "rgba(52, 211, 153, 0.85)", 1.15);
      if (visibility.robust) line("robust_trend", "rgba(244, 114, 182, 0.95)", 1.8);
      if (visibility.close) line("close", "#22d3ee", 2);
    };

    draw();
    const observer = new ResizeObserver(draw);
    observer.observe(canvas);
    return () => observer.disconnect();
  }, [points, logScale, visibility]);

  const sharedIndex = sharedDate ? points.findIndex((point) => point.date >= sharedDate) : -1;
  const sharedPoint = sharedIndex >= 0 ? points[sharedIndex] : null;
  const activePoint = hovered?.point ?? sharedPoint;
  const sharedRatio = sharedIndex / Math.max(1, points.length - 1);
  const activeX = hovered?.x ?? (sharedIndex >= 0 ? `calc(${58 - sharedRatio * 82}px + ${sharedRatio * 100}%)` : null);
  return (
    <div className="chart-wrap">
      <canvas
        ref={canvasRef}
        aria-label="NASDAQ-100 价格、EMA50 与 EMA200 历史走势图"
        onMouseLeave={() => setHovered(null)}
        onMouseMove={(event) => {
          const bounds = event.currentTarget.getBoundingClientRect();
          const ratio = Math.min(1, Math.max(0, (event.clientX - bounds.left - 58) / Math.max(1, bounds.width - 82)));
          const point = points[Math.round(ratio * (points.length - 1))];
          setHovered({ point, x: event.clientX - bounds.left });
          onHoverDate?.(point.date);
        }}
      />
      {activeX != null && <span className="chart-crosshair" style={{ left: activeX }} />}
      <button className="chart-download" onClick={() => downloadCanvas(canvasRef.current, `ndx-price-${points.at(-1)?.date ?? "chart"}.png`)}>下载 PNG</button>
      {activePoint && (
        <div className="chart-tooltip" role="status">
          <span>{activePoint.date}</span>
          <strong>{number(activePoint.close)}</strong>
          <small>{priceDetails(activePoint, visibility)}</small>
        </div>
      )}
    </div>
  );
}

function RobustTrendChart({ points, logScale, visibility, sharedDate, onHoverDate }: { points: Point[]; logScale: boolean; visibility: TrendVisibility; sharedDate?: string; onHoverDate?: (date: string) => void }) {
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

  const sharedIndex = sharedDate ? points.findIndex((point) => point.date >= sharedDate) : -1;
  const sharedPoint = sharedIndex >= 0 ? points[sharedIndex] : null;
  const activePoint = hovered?.point ?? sharedPoint;
  const sharedRatio = sharedIndex / Math.max(1, points.length - 1);
  const activeX = hovered?.x ?? (sharedIndex >= 0 ? `calc(${58 - sharedRatio * 82}px + ${sharedRatio * 100}%)` : null);
  return <div className="robust-chart-wrap"><canvas ref={canvasRef} aria-label="NASDAQ-100 全历史稳健增长趋势与实际收盘点位" onMouseLeave={() => setHovered(null)} onMouseMove={(event) => {
    const bounds = event.currentTarget.getBoundingClientRect();
    const ratio = Math.min(1, Math.max(0, (event.clientX - bounds.left - 58) / Math.max(1, bounds.width - 82)));
    const point = points[Math.round(ratio * (points.length - 1))];
    setHovered({ point, x: event.clientX - bounds.left }); onHoverDate?.(point.date);
  }} />{activeX != null && <span className="chart-crosshair" style={{ left: activeX }} />}<button className="chart-download" onClick={() => downloadCanvas(canvasRef.current, `ndx-robust-trend-${points.at(-1)?.date ?? "chart"}.png`)}>下载 PNG</button>{activePoint && <div className="chart-tooltip" role="status"><span>{activePoint.date}</span><strong>{number(activePoint.close)}</strong><small>全历史 {number(activePoint.robust_trend)} · 无未来数据 {number(activePoint.asof_robust_trend)} · 第 {number(activePoint.robust_percentile)} 百分位</small></div>}</div>;
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
  field: "drawdown_pct" | "rsi14" | "volatility20_pct" | "roc20_pct" | "robust_deviation_pct";
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

function MacdChart({ points }: { points: Point[] }) {
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
      const values = points.flatMap((point) => [point.macd, point.macd_signal, point.macd_histogram]).filter((value): value is number => value != null);
      if (!context || values.length < 2) return;
      context.setTransform(ratio, 0, 0, ratio, 0, 0);
      context.clearRect(0, 0, bounds.width, bounds.height);
      const limit = Math.max(...values.map(Math.abs), 1);
      const x = (index: number) => (index / Math.max(1, points.length - 1)) * bounds.width;
      const y = (value: number) => 8 + (bounds.height - 16) * (0.5 - value / (2 * limit));
      context.strokeStyle = "rgba(148,163,184,.28)";
      context.setLineDash([4, 4]);
      context.beginPath();
      context.moveTo(0, y(0));
      context.lineTo(bounds.width, y(0));
      context.stroke();
      context.setLineDash([]);
      const barWidth = Math.max(0.7, bounds.width / Math.max(points.length, 1));
      points.forEach((point, index) => {
        if (point.macd_histogram == null) return;
        context.fillStyle = point.macd_histogram >= 0 ? "rgba(52,211,153,.38)" : "rgba(251,113,133,.38)";
        context.fillRect(x(index), Math.min(y(0), y(point.macd_histogram)), barWidth, Math.max(1, Math.abs(y(point.macd_histogram) - y(0))));
      });
      const line = (field: "macd" | "macd_signal", color: string) => {
        context.strokeStyle = color;
        context.lineWidth = 1.5;
        context.beginPath();
        let started = false;
        points.forEach((point, index) => {
          const value = point[field];
          if (value == null) return;
          if (started) context.lineTo(x(index), y(value));
          else context.moveTo(x(index), y(value));
          started = true;
        });
        context.stroke();
      };
      line("macd", "#22d3ee");
      line("macd_signal", "#f59e0b");
    };
    draw();
    const observer = new ResizeObserver(draw);
    observer.observe(canvas);
    return () => observer.disconnect();
  }, [points]);
  return <canvas className="indicator-canvas" ref={canvasRef} aria-label="MACD线、信号线与柱状图历史走势" />;
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

const benchmarkMeta = {
  ndx: { label: "NASDAQ-100", color: "#22d3ee" },
  sp500: { label: "标普500", color: "#a78bfa" },
  ndx_equal_weight: { label: "纳指100等权", color: "#34d399" },
  russell2000: { label: "罗素2000", color: "#f59e0b" },
  qqq: { label: "QQQ", color: "#f472b6" },
} as const;
type BenchmarkKey = keyof typeof benchmarkMeta;

function BenchmarkChart({ points, ndx, visibility }: { points: ContextPoint[]; ndx: Point[]; visibility: Record<BenchmarkKey, boolean> }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || points.length < 2) return;
    const ndxByDate = new Map(ndx.map((point) => [point.date, point.close]));
    const series = (Object.keys(benchmarkMeta) as BenchmarkKey[]).filter((key) => visibility[key]).map((key) => {
      const values = points.map((point) => key === "ndx" ? ndxByDate.get(point.date) ?? null : point[key]);
      const base = values.find((value): value is number => value != null && value > 0);
      return { key, values: values.map((value) => value != null && base ? value / base * 100 : null) };
    });
    const draw = () => {
      const bounds = canvas.getBoundingClientRect();
      const ratio = window.devicePixelRatio || 1;
      canvas.width = Math.max(1, Math.floor(bounds.width * ratio));
      canvas.height = Math.max(1, Math.floor(bounds.height * ratio));
      const context = canvas.getContext("2d");
      if (!context) return;
      context.setTransform(ratio, 0, 0, ratio, 0, 0);
      context.clearRect(0, 0, bounds.width, bounds.height);
      const values = series.flatMap((item) => item.values).filter((value): value is number => value != null);
      if (!values.length) return;
      const min = Math.min(...values), max = Math.max(...values), spread = max - min || 1;
      const x = (index: number) => 44 + index / Math.max(1, points.length - 1) * (bounds.width - 56);
      const y = (value: number) => 10 + (bounds.height - 34) * (1 - (value - min) / spread);
      context.font = "10px ui-monospace, monospace";
      context.strokeStyle = "rgba(148,163,184,.18)";
      context.fillStyle = "#708099";
      context.textAlign = "right";
      for (let line = 0; line <= 3; line += 1) {
        const value = min + spread * line / 3, py = y(value);
        context.beginPath(); context.moveTo(44, py); context.lineTo(bounds.width - 12, py); context.stroke();
        context.fillText(value.toFixed(0), 39, py + 3);
      }
      series.forEach(({ key, values: normalized }) => {
        context.strokeStyle = benchmarkMeta[key].color; context.lineWidth = key === "ndx" ? 2 : 1.4; context.beginPath();
        let started = false;
        normalized.forEach((value, index) => { if (value == null) return; if (started) context.lineTo(x(index), y(value)); else context.moveTo(x(index), y(value)); started = true; });
        context.stroke();
      });
    };
    draw(); const observer = new ResizeObserver(draw); observer.observe(canvas); return () => observer.disconnect();
  }, [points, ndx, visibility]);
  return <canvas className="benchmark-canvas" ref={canvasRef} aria-label="NASDAQ-100 与主要基准按区间起点归一为100的相对强弱图" />;
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
  const [priceVisibility, setPriceVisibility] = useState<PriceVisibility>(() => savedVisibility("priceLines", basicPriceVisibility));
  const [trendVisibility, setTrendVisibility] = useState<TrendVisibility>(() => savedVisibility("trendLines", { close: true, robust: true, asof: true, band: false }));
  const [riskVisibility, setRiskVisibility] = useState<RiskVisibility>(() => savedVisibility("riskIndicators", basicRiskVisibility));
  const [benchmarkVisibility, setBenchmarkVisibility] = useState<Record<BenchmarkKey, boolean>>(() => savedVisibility("benchmarks", { ndx: true, sp500: true, ndx_equal_weight: true, russell2000: true, qqq: false }));
  const [compareStart, setCompareStart] = useState("");
  const [compareEnd, setCompareEnd] = useState("");
  const [linkCopied, setLinkCopied] = useState(false);
  const [sharedDate, setSharedDate] = useState<string>();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const query = new URLSearchParams(window.location.search);
    query.set("priceRange", range);
    query.set("priceScale", logScale ? "log" : "linear");
    query.set("trendRange", trendRange);
    query.set("trendScale", trendLogScale ? "log" : "linear");
    query.set("priceLines", visibilityQuery(priceVisibility));
    query.set("trendLines", visibilityQuery(trendVisibility));
    query.set("riskIndicators", visibilityQuery(riskVisibility));
    query.set("benchmarks", visibilityQuery(benchmarkVisibility));
    window.history.replaceState(null, "", `${window.location.pathname}?${query}`);
  }, [range, logScale, trendRange, trendLogScale, priceVisibility, trendVisibility, riskVisibility, benchmarkVisibility]);

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
  const latestPoint = market.series.at(-1)!;
  const comparisonStartDate = compareStart || market.series.at(-253)?.date || market.start_date;
  const comparisonEndDate = compareEnd || market.latest_date;
  const pointAt = (date: string) => market.series.findLast((point) => point.date <= date);
  const comparisonStart = pointAt(comparisonStartDate);
  const comparisonEnd = pointAt(comparisonEndDate);
  const comparisonReturn = comparisonStart && comparisonEnd ? (comparisonEnd.close / comparisonStart.close - 1) * 100 : null;

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

        <section className="professional-overview panel">
          <div className="score-ring"><span>综合市场健康度</span><strong>{number(summary.composite_score.score)}</strong><small>{summary.composite_score.label} · 0–100</small></div>
          <div className="score-components">{Object.entries(summary.composite_score.components).map(([label, value]) => <p key={label}><span>{label}</span><i><b style={{ width: `${value}%` }} /></i><strong>{number(value)}</strong></p>)}</div>
          <div className="quality-card"><span>数据质量</span><strong>{summary.data_quality.grade} · {number(summary.data_quality.score)}</strong><small>{summary.data_quality.warnings.length ? `注意：${summary.data_quality.warnings.join("、")}` : "全部质量维度正常"}</small><button onClick={() => { navigator.clipboard.writeText(window.location.href); setLinkCopied(true); window.setTimeout(() => setLinkCopied(false), 1600); }}>{linkCopied ? "已复制" : "复制当前视图链接"}</button></div>
          <p className="method-note">{summary.composite_score.interpretation}。权重：趋势30%、动量20%、宽度20%、风险20%、长期位置10%，每项明示、可复核。</p>
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
          <div className="preset-row" aria-label="价格指标预设">
            <span>显示预设</span>
            {Object.entries(pricePresets).map(([label, preset]) => <button key={label} onClick={() => setPriceVisibility(preset)}>{label}</button>)}
            <small>默认“基础”只显示收盘、EMA50、EMA200；下方每项仍可单独开关。</small>
          </div>
          <div className="legend interactive-legend">
            <button aria-pressed={priceVisibility.close} onClick={() => setPriceVisibility((value) => ({ ...value, close: !value.close }))}><i className="close-line" />收盘</button>
            <button aria-pressed={priceVisibility.ema20} onClick={() => setPriceVisibility((value) => ({ ...value, ema20: !value.ema20 }))}><i className="ema20-line" />EMA20</button>
            <button aria-pressed={priceVisibility.ema50} onClick={() => setPriceVisibility((value) => ({ ...value, ema50: !value.ema50 }))}><i className="ema50-line" />EMA50</button>
            <button aria-pressed={priceVisibility.ema200} onClick={() => setPriceVisibility((value) => ({ ...value, ema200: !value.ema200 }))}><i className="ema200-line" />EMA200</button>
            <button aria-pressed={priceVisibility.sma200} onClick={() => setPriceVisibility((value) => ({ ...value, sma200: !value.sma200 }))}><i className="sma200-line" />SMA200</button>
            <button aria-pressed={priceVisibility.bollinger} onClick={() => setPriceVisibility((value) => ({ ...value, bollinger: !value.bollinger }))}><i className="bollinger-band" />布林带20,2</button>
            <button aria-pressed={priceVisibility.robust} onClick={() => setPriceVisibility((value) => ({ ...value, robust: !value.robust }))}><i className="robust-main-line" />稳健拟合</button>
            <button aria-pressed={priceVisibility.band} onClick={() => setPriceVisibility((value) => ({ ...value, band: !value.band }))}><i className="robust-band" />经验区间</button>
          </div>
          <PriceChart points={visiblePoints} logScale={logScale} visibility={priceVisibility} sharedDate={sharedDate} onHoverDate={setSharedDate} />
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
          <RobustTrendChart points={visibleTrendPoints} logScale={trendLogScale} visibility={trendVisibility} sharedDate={sharedDate} onHoverDate={setSharedDate} />
          <p className="method-note">紫色全历史拟合用于描述长期结构，会使用当前可得的全部数据；绿色虚线在每月首个交易日仅使用截至上月末的数据重估，可用于无前视偏差的历史观察。经验区间是历史残差中央 80%，不是预测区间。异常偏离会被自动降权（本次 {number(robustTrend.downweighted_pct)}% 样本）。</p>
          <div className="model-validity">
            <div><span className="eyebrow">MODEL VALIDITY</span><h3>长期斜率稳定性与参数不确定性</h3></div>
            <div className="stability-windows">{Object.entries(stability.windows).map(([label, item]) => <p key={label}><span>{label}</span><strong>{number(item.annualized_growth_pct)}%</strong><small>{item.start_date} · {item.observations.toLocaleString("zh-CN")} 日</small></p>)}</div>
            <StabilityChart points={stability.history} />
            <p className="method-note">年末序列每次只使用当时已有数据；斜率 95% 区间采用 {uncertainty.samples} 次、每块 {uncertainty.block_sessions} 个交易日的移动区块残差 Bootstrap。拟合点位参数区间为 {number(uncertainty.fitted_close_ci95[0])}–{number(uncertainty.fitted_close_ci95[1])}。模型版本 {summary.methodology.trend_model_version}，数据指纹 {summary.provenance.data_fingerprint_sha256.slice(0, 12)}。</p>
          </div>
        </section>

        <section className="risk-panel panel">
          <div className="section-head"><div><span className="eyebrow">TECHNICAL INDICATORS</span><h2>动量、波动与风险指标</h2></div><button className="reset-indicators" onClick={() => setRiskVisibility(basicRiskVisibility)}>恢复基础版</button></div>
          <div className="indicator-picker" aria-label="选择副图指标">
            {([
              ["rsi", "RSI14"], ["macd", "MACD"], ["roc20", "20日涨跌幅"],
              ["volatility", "20日年化波动"], ["drawdown", "历史回撤"], ["trendDeviation", "稳健趋势偏离"],
            ] as Array<[RiskIndicator, string]>).map(([key, label]) => <button key={key} aria-pressed={riskVisibility[key]} onClick={() => setRiskVisibility((value) => ({ ...value, [key]: !value[key] }))}>{label}</button>)}
          </div>
          <div className="risk-grid">
            {riskVisibility.rsi && <article><div><span>RSI 14</span><strong>{number(summary.rsi14)}</strong></div><IndicatorChart points={visiblePoints} field="rsi14" color="#a78bfa" reference={50} /><small className="chart-caption">50 为强弱中轴；70/30 常作偏热/偏冷参考。</small></article>}
            {riskVisibility.macd && <article><div><span>MACD 12,26,9</span><strong className={tone(latestPoint.macd_histogram)}>{signed(latestPoint.macd_histogram, "")}</strong></div><MacdChart points={visiblePoints} /><small className="chart-caption">青色 MACD · 橙色信号线 · 柱体为两者差值。</small></article>}
            {riskVisibility.roc20 && <article><div><span>20日涨跌幅</span><strong className={tone(latestPoint.roc20_pct)}>{signed(latestPoint.roc20_pct)}</strong></div><IndicatorChart points={visiblePoints} field="roc20_pct" color="#22d3ee" reference={0} /><small className="chart-caption">零轴上方为正动量，下方为负动量。</small></article>}
            {riskVisibility.volatility && <article><div><span>20日年化波动</span><strong>{number(summary.volatility20_pct)}%</strong></div><IndicatorChart points={visiblePoints} field="volatility20_pct" color="#f59e0b" /><small className="chart-caption">只衡量波动强度，不区分涨跌方向。</small></article>}
            {riskVisibility.drawdown && <article><div><span>历史回撤</span><strong className="negative">{signed(summary.drawdown_pct)}</strong></div><IndicatorChart points={visiblePoints} field="drawdown_pct" color="#fb7185" reference={0} /><small className="chart-caption">相对此前历史高点的跌幅，越负代表损伤越深。</small></article>}
            {riskVisibility.trendDeviation && <article><div><span>稳健趋势偏离</span><strong className={tone(latestPoint.robust_deviation_pct)}>{signed(latestPoint.robust_deviation_pct)}</strong></div><IndicatorChart points={visiblePoints} field="robust_deviation_pct" color="#f472b6" reference={0} /><small className="chart-caption">零轴代表全历史稳健增长中枢，不是估值目标。</small></article>}
            {!Object.values(riskVisibility).some(Boolean) && <p className="empty-indicators">当前未选择副图指标，可在上方开启任意项目。</p>}
          </div>
          <div className="indicator-guide">
            <div><span className="eyebrow">INDICATOR GUIDE</span><h3>指标意义与使用边界</h3><p>优先组合不同维度，不建议同时开启所有相似指标。</p></div>
            <div className="indicator-guide-grid">{indicatorGuide.map(([name, category, description]) => <article key={name}><span>{category}</span><strong>{name}</strong><p>{description}</p></article>)}</div>
          </div>
        </section>

        <section className="professional-risk panel">
          <div className="section-head"><div><span className="eyebrow">PROFESSIONAL RISK</span><h2>尾部风险与恢复能力</h2></div><span className="source-chip">近 {summary.risk_dashboard.window_sessions} 交易日</span></div>
          <div className="risk-stat-grid">
            <p><span>1日历史 VaR 95%</span><strong>{number(summary.risk_dashboard.historical_var95_1d_pct)}%</strong><small>约5%交易日损失可能更差</small></p>
            <p><span>预期损失 ES 95%</span><strong>{number(summary.risk_dashboard.expected_shortfall95_1d_pct)}%</strong><small>最差5%交易日平均损失</small></p>
            <p><span>下行波动率</span><strong>{number(summary.risk_dashboard.downside_volatility_pct)}%</strong><small>只计负收益的年化波动</small></p>
            <p><span>Sortino</span><strong>{number(summary.risk_dashboard.sortino_ratio)}</strong><small>年化收益 / 下行波动</small></p>
            <p><span>当前水下期</span><strong>{summary.risk_dashboard.current_drawdown_duration_sessions} 日</strong><small>从最近历史高点起</small></p>
            <p><span>历史最长水下期</span><strong>{summary.risk_dashboard.max_drawdown_duration_sessions} 日</strong><small>中位恢复 {number(summary.risk_dashboard.median_recovery_sessions)} 日</small></p>
          </div>
          <p className="method-note">{summary.risk_dashboard.method}。VaR 不是最大可能损失，ES 用于补充观察尾部严重度。</p>
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
          <div className="breadth-detail"><p><span>20日新高 / 新低</span><strong>{summary.context.breadth?.new_high20_count ?? "—"} / {summary.context.breadth?.new_low20_count ?? "—"}</strong></p><p><span>EMA200宽度五日加速度</span><strong className={tone(summary.context.breadth?.acceleration_5d_pct_points)}>{signed(summary.context.breadth?.acceleration_5d_pct_points, "点")}</strong></p><p><span>价格/宽度20日背离</span><strong>{summary.context.breadth?.price_breadth_divergence_20d ? "是" : "否"}</strong></p><p><span>前十大市值占比代理</span><strong>{number(summary.context.breadth?.concentration?.top10_market_cap_share_pct)}%</strong><small>当日贡献代理 {signed(summary.context.breadth?.concentration?.top10_daily_contribution_proxy_pct)}</small></p></div>
          <p className="method-note">市场宽度从功能启用日起按当时成分名单逐日积累，不用今天的成分股回填过去。前十大数据是当前普通市值权重代理，并非 Nasdaq 官方修正指数权重；因此只用于集中度观察。</p>
          <p className="method-note">相关性使用日收益与 VXN 日变化的 60 个交易日窗口；仅描述同期关系，不代表因果。</p>
        </section>

        <section className="relative-panel panel">
          <div className="section-head"><div><span className="eyebrow">RELATIVE STRENGTH</span><h2>跨市场相对强弱</h2></div><span className="source-chip">区间起点 = 100</span></div>
          <div className="indicator-picker">{(Object.keys(benchmarkMeta) as BenchmarkKey[]).map((key) => <button key={key} aria-pressed={benchmarkVisibility[key]} onClick={() => setBenchmarkVisibility((value) => ({ ...value, [key]: !value[key] }))}><i style={{ background: benchmarkMeta[key].color }} />{benchmarkMeta[key].label}</button>)}</div>
          <BenchmarkChart points={visibleContext} ndx={visiblePoints} visibility={benchmarkVisibility} />
          <div className="relative-cards">{Object.entries(summary.context.relative_strength.benchmarks).map(([key, item]) => <p key={key}><span>{item.label} · NDX超额</span><strong className={tone(item.excess_return_pct["1年"])}>{signed(item.excess_return_pct["1年"])}</strong><small>3个月 {signed(item.excess_return_pct["3个月"])} · 3年 {signed(item.excess_return_pct["3年"])}</small></p>)}<p><span>QQQ 相对现金</span><strong className={tone(summary.context.relative_strength.qqq_cash_excess_1y_pct)}>{signed(summary.context.relative_strength.qqq_cash_excess_1y_pct)}</strong><small>近1年 · 现金以13周国库券近似</small></p></div>
          <p className="method-note">{summary.context.relative_strength.method}。等权指数相对市值加权指数可辅助观察上涨是否过度集中。</p>
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

        <section className="validation-panel panel">
          <div className="section-head"><div><span className="eyebrow">WALK-FORWARD VALIDATION</span><h2>无前视偏差的规则验证</h2></div><span className="source-chip">单边换仓成本 {summary.walk_forward_validation.transaction_cost_bps} bp</span></div>
          <div className="validation-grid"><article><h3>状态规则</h3><p>{summary.walk_forward_validation.signal}</p><small>{summary.walk_forward_validation.limitations}</small></article><article><h3>策略</h3><strong>{signed(summary.walk_forward_validation.strategy.cagr_pct)} CAGR</strong><p>波动 {number(summary.walk_forward_validation.strategy.annualized_volatility_pct)}% · 最大回撤 {signed(summary.walk_forward_validation.strategy.max_drawdown_pct)}</p></article><article><h3>买入持有</h3><strong>{signed(summary.walk_forward_validation.buy_and_hold.cagr_pct)} CAGR</strong><p>波动 {number(summary.walk_forward_validation.buy_and_hold.annualized_volatility_pct)}% · 最大回撤 {signed(summary.walk_forward_validation.buy_and_hold.max_drawdown_pct)}</p></article><article><h3>执行特征</h3><strong>{summary.walk_forward_validation.position_changes} 次切换</strong><p>年化换手 {number(summary.walk_forward_validation.annual_turnover_pct)}% · MAE/MFE {signed(summary.walk_forward_validation.median_mae_pct)} / {signed(summary.walk_forward_validation.median_mfe_pct)}</p></article></div>
          <div className="yearly-strip">{summary.walk_forward_validation.yearly.slice(-10).map((item) => <span key={item.year}><small>{item.year}</small><b className={tone(item.strategy_return_pct)}>{signed(item.strategy_return_pct)}</b><i>{signed(item.benchmark_return_pct)}</i></span>)}</div>
          <p className="method-note">每根K线只使用前一交易日已经知道的状态，避免同日收盘信号偷看未来。年度条形中粗体为规则策略，细体为买入持有。</p>
        </section>

        <section className="stress-panel panel">
          <div className="section-head"><div><span className="eyebrow">STRESS LAB</span><h2>历史压力场景</h2></div><span className="source-chip">实际历史路径 · 非预测</span></div>
          <div className="stress-grid">{summary.stress_scenarios.map((scenario) => <article key={scenario.name}><span>{scenario.name}</span><strong className="negative">{signed(scenario.peak_to_trough_pct)}</strong><p>{scenario.start_date} → {scenario.trough_date}</p><small>最差单日 {signed(scenario.worst_day_pct)} · {scenario.recovery_date ? `${scenario.recovery_sessions}个交易日恢复` : "尚未恢复"}</small></article>)}</div>
          <p className="method-note">峰谷损失从场景起点收盘计算，恢复指重新达到场景起点收盘；历史情景不能覆盖未来所有风险。</p>
        </section>

        <section className="compare-panel panel">
          <div className="section-head"><div><span className="eyebrow">DATE COMPARE</span><h2>两日期状态对照</h2></div><span className="source-chip">与图表使用同一历史序列</span></div>
          <div className="compare-controls"><label>起点<input type="date" min={market.start_date} max={market.latest_date} value={comparisonStartDate} onChange={(event) => setCompareStart(event.target.value)} /></label><label>终点<input type="date" min={market.start_date} max={market.latest_date} value={comparisonEndDate} onChange={(event) => setCompareEnd(event.target.value)} /></label></div>
          <div className="compare-grid"><p><span>区间收益</span><strong className={tone(comparisonReturn)}>{signed(comparisonReturn)}</strong></p><p><span>收盘</span><strong>{number(comparisonStart?.close)} → {number(comparisonEnd?.close)}</strong></p><p><span>距 EMA200</span><strong>{comparisonStart?.ema200 ? signed((comparisonStart.close / comparisonStart.ema200 - 1) * 100) : "—"} → {comparisonEnd?.ema200 ? signed((comparisonEnd.close / comparisonEnd.ema200 - 1) * 100) : "—"}</strong></p><p><span>回撤</span><strong>{signed(comparisonStart?.drawdown_pct)} → {signed(comparisonEnd?.drawdown_pct)}</strong></p><p><span>稳健趋势偏离</span><strong>{signed(comparisonStart?.robust_deviation_pct)} → {signed(comparisonEnd?.robust_deviation_pct)}</strong></p></div>
        </section>

        <section className="audit-panel panel">
          <div><span className="eyebrow">DATA AUDIT</span><h2>权威数据校准</h2></div>
          {summary.context.calibration ? <div className="audit-grid"><p><span>本次校准行数</span><strong>{summary.context.calibration.corrected_rows}</strong></p><p><span>仍待权威发布</span><strong>{summary.context.calibration.pending_rows}</strong></p><p><span>最大临时偏差</span><strong>{summary.context.calibration.max_abs_diff_pct == null ? "—" : `${summary.context.calibration.max_abs_diff_pct.toFixed(4)}%`}</strong></p><p><span>最大偏差日期</span><strong>{summary.context.calibration.max_diff_date ?? "—"}</strong></p></div> : <p className="method-note">等待下一次周度 FRED 权威校准后生成差异审计。</p>}
          <div className="quality-components">{Object.entries(summary.data_quality.components).map(([label, value]) => <p key={label}><span>{label}</span><strong>{number(value)} / 20</strong></p>)}</div>
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
          <div className="ai-framework"><article><span>可核验证据</span>{analysis.evidence?.map((item) => <p key={item.metric}><strong>{item.supports}</strong>{item.metric} = {number(item.value)}</p>)}</article><article><span>矛盾证据</span>{analysis.contradictions?.map((item) => <p key={item}>{item}</p>)}</article><article><span>结论失效条件</span>{analysis.invalidation_conditions?.map((item) => <p key={item}>{item}</p>)}</article></div>
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
            <p><strong>版本</strong><span>方法 {summary.methodology.version} · 长期模型 {summary.methodology.trend_model_version}；口径变化随代码提交保留，可由数据指纹复核。</span></p>
            <p><strong>无前视验证</strong><span>月度扩展趋势及状态策略只使用当时可得数据；全历史拟合仅描述当前结构。</span></p>
            <p><strong>已知边界</strong><span>历史成分股不回填；前十大贡献为当前市值代理；Yahoo 最新行待 FRED 权威校准。</span></p>
          </div>
        </section>
      </div>

      <footer>NASDAQ-100 DAILY MONITOR <span>·</span> 数据研究工具，非投资建议</footer>
    </main>
  );
}
