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
  status: string;
  status_detail: string;
};

type MarketData = {
  symbol: string;
  name: string;
  start_date: string;
  latest_date: string;
  summary: Summary;
  series: Point[];
};

type Analysis = {
  market_date: string;
  generated_at: string;
  source: string;
  model: string | null;
  text: string;
  disclaimer: string;
};

const ranges = { "1年": 252, "3年": 756, "5年": 1260, "10年": 2520, 全部: Infinity } as const;

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

function PriceChart({ points, logScale }: { points: Point[]; logScale: boolean }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [hovered, setHovered] = useState<Point | null>(null);

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
      const values = points.flatMap((point) => [point.close, point.ema50, point.ema200]).filter((v): v is number => v != null && v > 0);
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

      const line = (key: "close" | "ema50" | "ema200", color: string, widthPx: number) => {
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

      line("ema200", "rgba(245, 158, 11, 0.92)", 1.4);
      line("ema50", "rgba(167, 139, 250, 0.82)", 1.2);
      line("close", "#22d3ee", 2);
    };

    draw();
    const observer = new ResizeObserver(draw);
    observer.observe(canvas);
    return () => observer.disconnect();
  }, [points, logScale]);

  return (
    <div className="chart-wrap">
      <canvas
        ref={canvasRef}
        aria-label="NASDAQ-100 价格、EMA50 与 EMA200 历史走势图"
        onMouseLeave={() => setHovered(null)}
        onMouseMove={(event) => {
          const bounds = event.currentTarget.getBoundingClientRect();
          const ratio = Math.min(1, Math.max(0, (event.clientX - bounds.left - 58) / Math.max(1, bounds.width - 82)));
          setHovered(points[Math.round(ratio * (points.length - 1))]);
        }}
      />
      {hovered && (
        <div className="chart-tooltip" role="status">
          <span>{hovered.date}</span>
          <strong>{number(hovered.close)}</strong>
          <small>EMA200 {number(hovered.ema200)}</small>
        </div>
      )}
    </div>
  );
}

export default function Home() {
  const [market, setMarket] = useState<MarketData | null>(null);
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [range, setRange] = useState<keyof typeof ranges>("5年");
  const [logScale, setLogScale] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([
      fetch("/data/nasdaq100.json").then((response) => {
        if (!response.ok) throw new Error("市场数据尚未生成");
        return response.json();
      }),
      fetch("/data/analysis.json").then((response) => response.json()),
    ])
      .then(([marketData, analysisData]) => {
        setMarket(marketData);
        setAnalysis(analysisData);
      })
      .catch((reason) => setError(reason instanceof Error ? reason.message : "数据加载失败"));
  }, []);

  const visiblePoints = useMemo(() => {
    if (!market) return [];
    const sessions = ranges[range];
    return Number.isFinite(sessions) ? market.series.slice(-sessions) : market.series;
  }, [market, range]);

  if (error) {
    return <main className="center-state"><strong>数据暂不可用</strong><span>{error}</span></main>;
  }
  if (!market || !analysis) {
    return <main className="center-state"><span className="pulse" /><strong>正在载入 NASDAQ-100 历史数据</strong></main>;
  }

  const summary = market.summary;
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
        <div className="market-stamp"><span className="live-dot" />数据截至 {summary.market_date}<span>·</span>收盘后日线</div>
        <a className="download" href="/data/nasdaq100_daily_data.csv" download>下载完整 CSV</a>
      </header>

      <div className="dashboard">
        <section className="hero panel">
          <div>
            <div className="eyebrow">NASDAQ-100 · ^NDX</div>
            <div className="headline"><h1>{number(summary.close)}</h1><span className={tone(summary.daily_return_pct)}>{signed(summary.daily_return_pct)}</span></div>
            <p>{summary.status_detail}</p>
          </div>
          <div className={`regime ${summary.distance_ema200_pct >= 0 ? "regime-up" : "regime-down"}`}>
            <span>市场状态</span><strong>{summary.status}</strong><small>距 EMA200 {signed(summary.distance_ema200_pct)}</small>
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

        <section className="chart-panel panel">
          <div className="section-head">
            <div><span className="eyebrow">PRICE STRUCTURE</span><h2>长期趋势与均线结构</h2></div>
            <div className="chart-controls">
              <div className="segmented" aria-label="时间范围">
                {(Object.keys(ranges) as Array<keyof typeof ranges>).map((label) => <button key={label} className={range === label ? "active" : ""} onClick={() => setRange(label)}>{label}</button>)}
              </div>
              <button className={`scale-button ${logScale ? "active" : ""}`} onClick={() => setLogScale((value) => !value)}>对数尺度</button>
            </div>
          </div>
          <div className="legend"><span><i className="close-line" />收盘</span><span><i className="ema50-line" />EMA50</span><span><i className="ema200-line" />EMA200</span></div>
          <PriceChart points={visiblePoints} logScale={logScale} />
        </section>

        <section className="returns panel">
          <div className="section-head"><div><span className="eyebrow">RETURN WINDOWS</span><h2>多周期收益</h2></div></div>
          <div className="return-grid">
            {returnCards.map(([label, value]) => <div key={label}><span>{label}</span><strong className={tone(value)}>{signed(value)}</strong></div>)}
          </div>
          <p className="method-note">收益基于日线收盘价；长期年化区间从 {market.start_date} 开始。</p>
        </section>

        <section className="ai-panel panel">
          <div className="section-head"><div><span className="eyebrow">AI RISK BRIEF</span><h2>结构化市场解读</h2></div><span className="source-chip">{analysis.source}{analysis.model ? ` · ${analysis.model}` : ""}</span></div>
          <div className="ai-copy">{analysis.text}</div>
          <p className="disclaimer">{analysis.disclaimer}</p>
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
            <p><strong>AI 边界</strong><span>只解释表内指标，不抓取新闻、不虚构事件、不输出交易指令。</span></p>
          </div>
        </section>
      </div>

      <footer>NASDAQ-100 DAILY MONITOR <span>·</span> 数据研究工具，非投资建议</footer>
    </main>
  );
}
