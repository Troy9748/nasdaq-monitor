"use client";

import { useEffect, useMemo, useRef, useState } from "react";

type Point = {
  date: string;
  close: number;
  daily_return_pct: number | null;
  ema20: number | null;
  ema50: number | null;
  ema200: number | null;
  amount_billion: number | null;
  amount_ratio20: number | null;
  estimated_inflow_billion: number | null;
  estimated_outflow_billion: number | null;
  estimated_net_flow_billion: number | null;
  money_flow_ratio_pct: number | null;
};
type IndexData = {
  code: string;
  name: string;
  category: string;
  source: string;
  color: string;
  start_date: string;
  latest_date: string;
  summary: {
    close: number;
    daily_return_pct: number | null;
    returns: Record<string, number | null>;
    ema20: number | null;
    ema50: number | null;
    ema200: number | null;
    rsi14: number | null;
    volatility20_pct: number | null;
    amount_billion: number | null;
    amount_ratio20: number | null;
    estimated_inflow_billion: number | null;
    estimated_outflow_billion: number | null;
    estimated_net_flow_billion: number | null;
    money_flow_ratio_pct: number | null;
    trend: string;
  };
  series: Point[];
};
type SectorData = { generated_at: string; latest_a_share_date: string; requested_start_date: string; indices: IndexData[] };
type Analysis = { market_date: string; generated_at: string; source: string; model: string | null; status?: "ok" | "fallback"; error?: string | null; text: string; disclaimer: string };

const chartRanges = { "1月": 22, "3月": 66, "6月": 126, "1年": 252, "3年": 756, "全部": Infinity } as const;
type ChartRange = keyof typeof chartRanges;

const basePath = process.env.NEXT_PUBLIC_BASE_PATH ?? "";
const assetPath = (path: string) => `${basePath}${path}`;
const fmt = (value: number | null | undefined, digits = 2) => value == null ? "—" : value.toLocaleString("zh-CN", { maximumFractionDigits: digits });
const pct = (value: number | null | undefined) => value == null ? "—" : `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;
const tone = (value: number | null | undefined) => value == null || value === 0 ? "neutral" : value > 0 ? "positive" : "negative";
const flowText = (value: number | null | undefined) => value == null ? "暂无成交额口径" : `${value >= 0 ? "净流入估算" : "净流出估算"} ${fmt(Math.abs(value))}亿元`;

function setupCanvas(canvas: HTMLCanvasElement) {
  const bounds = canvas.getBoundingClientRect();
  const ratio = window.devicePixelRatio || 1;
  canvas.width = Math.max(1, Math.floor(bounds.width * ratio));
  canvas.height = Math.max(1, Math.floor(bounds.height * ratio));
  const context = canvas.getContext("2d");
  context?.setTransform(ratio, 0, 0, ratio, 0, 0);
  return { context, width: bounds.width, height: bounds.height };
}

function IndexChartCanvas({ index, points, logScale, large = false, onTap }: { index: IndexData; points: Point[]; logScale: boolean; large?: boolean; onTap?: () => void }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [hover, setHover] = useState<Point | null>(null);
  const pointerStart = useRef<{ x: number; y: number } | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || points.length < 2) return;
    const draw = () => {
      const { context: ctx, width, height } = setupCanvas(canvas);
      if (!ctx) return;
      ctx.clearRect(0, 0, width, height);
      const top = 12, bottom = 24, volumeHeight = 38;
      const priceHeight = height - top - bottom - volumeHeight;
      const values = points.flatMap((p) => [p.close, p.ema20, p.ema50, p.ema200]).filter((v): v is number => v != null && (!logScale || v > 0));
      const transformed = values.map((value) => logScale ? Math.log(value) : value);
      const min = Math.min(...transformed), max = Math.max(...transformed), spread = max - min || 1;
      const x = (i: number) => (i / (points.length - 1)) * width;
      const y = (v: number) => top + priceHeight * (1 - ((logScale ? Math.log(v) : v) - min) / spread);
      const amounts = points.map((p) => p.amount_billion ?? 0);
      const amountMax = Math.max(...amounts, 1);
      points.forEach((point, i) => {
        if (!point.amount_billion) return;
        ctx.fillStyle = point.money_flow_ratio_pct != null && point.money_flow_ratio_pct < 0 ? "rgba(251,113,133,.25)" : "rgba(52,211,153,.25)";
        const bar = (point.amount_billion / amountMax) * (volumeHeight - 7);
        ctx.fillRect(x(i), height - bottom - bar, Math.max(1, width / points.length), bar);
      });
      const line = (key: "close" | "ema20" | "ema50" | "ema200", color: string, lineWidth: number) => {
        ctx.beginPath(); ctx.strokeStyle = color; ctx.lineWidth = lineWidth;
        let started = false;
        points.forEach((point, i) => {
          const value = point[key]; if (value == null) return;
          if (!started) { ctx.moveTo(x(i), y(value)); started = true; } else ctx.lineTo(x(i), y(value));
        });
        ctx.stroke();
      };
      line("ema200", "rgba(245,158,11,.7)", 1);
      line("ema50", "rgba(167,139,250,.7)", 1);
      line("ema20", "rgba(148,163,184,.55)", 1);
      line("close", index.color, 2);
      ctx.fillStyle = "#66798c"; ctx.font = "9px ui-monospace";
      ctx.fillText(points[0].date.slice(0, 7), 0, height - 5);
      ctx.textAlign = "right"; ctx.fillText(points.at(-1)!.date.slice(0, 7), width, height - 5);
      if (hover) {
        const hoverIndex = points.indexOf(hover);
        if (hoverIndex >= 0) {
          ctx.strokeStyle = "rgba(226,232,240,.55)"; ctx.setLineDash([3, 3]);
          ctx.beginPath(); ctx.moveTo(x(hoverIndex), top); ctx.lineTo(x(hoverIndex), height - bottom); ctx.stroke(); ctx.setLineDash([]);
        }
      }
    };
    draw(); const observer = new ResizeObserver(draw); observer.observe(canvas); return () => observer.disconnect();
  }, [hover, index.color, logScale, points]);

  const updateHover = (event: React.PointerEvent<HTMLCanvasElement>) => {
    const box = event.currentTarget.getBoundingClientRect();
    const ratio = Math.max(0, Math.min(1, (event.clientX - box.left) / box.width));
    setHover(points[Math.round(ratio * (points.length - 1))]);
  };

  return <div className={`sector-mini-chart ${large ? "large" : ""}`}>
    <canvas ref={canvasRef} aria-label={`${index.name}价格、均线、成交额与资金方向估算图`} onPointerLeave={() => { if (!pointerStart.current) setHover(null); }} onPointerDown={(event) => {
      pointerStart.current = { x: event.clientX, y: event.clientY }; event.currentTarget.setPointerCapture(event.pointerId); updateHover(event);
    }} onPointerMove={updateHover} onPointerUp={(event) => {
      updateHover(event); const start = pointerStart.current; pointerStart.current = null;
      if (start && Math.hypot(event.clientX - start.x, event.clientY - start.y) < 6) onTap?.();
    }} />
    {hover && <div className="sector-tooltip"><strong>{hover.date}</strong><span>收盘 {fmt(hover.close)}</span><span className={tone(hover.daily_return_pct)}>涨跌 {pct(hover.daily_return_pct)}</span><span>成交额 {hover.amount_billion == null ? "—" : `${fmt(hover.amount_billion)}亿元`}</span><span className={tone(hover.estimated_net_flow_billion)}>{flowText(hover.estimated_net_flow_billion)} · {pct(hover.money_flow_ratio_pct)}</span><span>估算流入 / 流出<br />{fmt(hover.estimated_inflow_billion)} / {fmt(hover.estimated_outflow_billion)} 亿元</span><span>EMA20 / 50 / 200<br />{fmt(hover.ema20)} / {fmt(hover.ema50)} / {fmt(hover.ema200)}</span></div>}
  </div>;
}

function ChartLegend({ color }: { color: string }) {
  return <div className="sector-legend"><span><i style={{ background: color }} />指数收盘</span><span><i className="line20" />EMA20</span><span><i className="line50" />EMA50</span><span><i className="line200" />EMA200</span><span><i className="volume" />成交额（红/绿按方向估算）</span></div>;
}

function MiniChart({ index }: { index: IndexData }) {
  const [range, setRange] = useState<ChartRange>("1年");
  const [logScale, setLogScale] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const points = useMemo(() => Number.isFinite(chartRanges[range]) ? index.series.slice(-chartRanges[range]) : index.series, [index.series, range]);
  return <>
    <div className="mini-controls"><div className="range-buttons">{(Object.keys(chartRanges) as ChartRange[]).map((label) => <button className={range === label ? "active" : ""} key={label} onClick={() => setRange(label)}>{label}</button>)}</div><button className={logScale ? "active" : ""} onClick={() => setLogScale((value) => !value)}>对数</button><button onClick={() => setExpanded(true)}>放大</button></div>
    <IndexChartCanvas index={index} points={points} logScale={logScale} onTap={() => setExpanded(true)} />
    <ChartLegend color={index.color} />
    {expanded && <div className="chart-modal" role="dialog" aria-modal="true" aria-label={`${index.name}放大图表`} onClick={() => setExpanded(false)}><div className="chart-modal-card panel" onClick={(event) => event.stopPropagation()}><div className="modal-head"><div><span>{index.code} · {index.category}</span><h2>{index.name}</h2></div><button onClick={() => setExpanded(false)} aria-label="关闭放大图">关闭</button></div><div className="mini-controls"><div className="range-buttons">{(Object.keys(chartRanges) as ChartRange[]).map((label) => <button className={range === label ? "active" : ""} key={label} onClick={() => setRange(label)}>{label}</button>)}</div><button className={logScale ? "active" : ""} onClick={() => setLogScale((value) => !value)}>对数坐标</button></div><IndexChartCanvas index={index} points={points} logScale={logScale} large /><ChartLegend color={index.color} /><p className="method-note">拖动或移动指针可连续查看每个交易日；成交额方向为区间位置估算，不是交易所披露的真实净流入。</p></div></div>}
  </>;
}

function ComparisonChart({ indices, selected, requestedStart, logScale }: { indices: IndexData[]; selected: string[]; requestedStart: string; logScale: boolean }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [hoverRatio, setHoverRatio] = useState<number | null>(null);
  const prepared = useMemo(() => {
    const chosen = indices.filter((item) => selected.includes(item.code));
    const starts = chosen.map((item) => item.series.find((point) => point.date >= requestedStart)?.date).filter(Boolean) as string[];
    const commonStart = chosen.length > 0 && starts.length === chosen.length ? starts.sort().at(-1)! : requestedStart;
    return { commonStart, lines: chosen.map((item) => {
      const points = item.series.filter((point) => point.date >= commonStart);
      const base = points[0]?.close;
      return { ...item, normalized: base ? points.map((point) => ({ ...point, value: (logScale ? Math.log(point.close / base) : point.close / base - 1) * 100 })) : [] };
    }).filter((item) => item.normalized.length > 1) };
  }, [indices, logScale, selected, requestedStart]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !prepared.lines.length) return;
    const draw = () => {
      const { context: ctx, width, height } = setupCanvas(canvas); if (!ctx) return;
      ctx.clearRect(0, 0, width, height);
      const pad = { top: 20, right: 22, bottom: 32, left: 52 };
      const plotW = width - pad.left - pad.right, plotH = height - pad.top - pad.bottom;
      const all = prepared.lines.flatMap((line) => line.normalized.map((point) => point.value));
      const min = Math.min(...all, 0), max = Math.max(...all, 0), margin = (max - min || 1) * .08;
      const lo = min - margin, hi = max + margin;
      const first = new Date(prepared.commonStart).getTime();
      const last = Math.max(...prepared.lines.flatMap((line) => line.normalized.map((point) => new Date(point.date).getTime())));
      const x = (date: string) => pad.left + ((new Date(date).getTime() - first) / Math.max(1, last - first)) * plotW;
      const y = (value: number) => pad.top + (1 - (value - lo) / (hi - lo)) * plotH;
      ctx.font = "10px ui-monospace"; ctx.textAlign = "right"; ctx.textBaseline = "middle";
      for (let i = 0; i <= 4; i++) {
        const value = hi - (hi - lo) * i / 4, py = y(value);
        ctx.strokeStyle = "rgba(148,163,184,.13)"; ctx.beginPath(); ctx.moveTo(pad.left, py); ctx.lineTo(width - pad.right, py); ctx.stroke();
        ctx.fillStyle = "#66798c"; ctx.fillText(`${value.toFixed(0)}%`, pad.left - 8, py);
      }
      prepared.lines.forEach((line) => {
        ctx.strokeStyle = line.color; ctx.lineWidth = 1.8; ctx.beginPath();
        line.normalized.forEach((point, i) => i ? ctx.lineTo(x(point.date), y(point.value)) : ctx.moveTo(x(point.date), y(point.value)));
        ctx.stroke();
      });
      ctx.textAlign = "center"; ctx.textBaseline = "top";
      [0, .25, .5, .75, 1].forEach((fraction) => {
        const date = new Date(first + (last - first) * fraction).toISOString().slice(0, 7);
        ctx.fillStyle = "#66798c"; ctx.fillText(date, pad.left + plotW * fraction, height - 19);
      });
      if (hoverRatio != null) {
        const px = pad.left + plotW * hoverRatio; ctx.strokeStyle = "rgba(226,232,240,.5)"; ctx.setLineDash([3, 3]);
        ctx.beginPath(); ctx.moveTo(px, pad.top); ctx.lineTo(px, height - pad.bottom); ctx.stroke(); ctx.setLineDash([]);
      }
    };
    draw(); const observer = new ResizeObserver(draw); observer.observe(canvas); return () => observer.disconnect();
  }, [prepared, hoverRatio]);

  const hovered = useMemo(() => {
    if (hoverRatio == null || !prepared.lines.length) return null;
    const first = new Date(prepared.commonStart).getTime();
    const last = Math.max(...prepared.lines.flatMap((line) => line.normalized.map((point) => new Date(point.date).getTime())));
    const target = first + (last - first) * hoverRatio;
    return prepared.lines.map((line) => ({ line, point: line.normalized.reduce((best, point) => Math.abs(new Date(point.date).getTime() - target) < Math.abs(new Date(best.date).getTime() - target) ? point : best) }));
  }, [hoverRatio, prepared]);

  const updateHover = (event: React.PointerEvent<HTMLCanvasElement>) => {
    const box = event.currentTarget.getBoundingClientRect();
    setHoverRatio(Math.max(0, Math.min(1, (event.clientX - box.left - 52) / Math.max(1, box.width - 74))));
  };

  return <>
    <div className="comparison-chart">
      <canvas ref={canvasRef} aria-label="所选指数从共同起点归一化后的涨跌幅比较图" onPointerLeave={() => setHoverRatio(null)} onPointerDown={(event) => { event.currentTarget.setPointerCapture(event.pointerId); updateHover(event); }} onPointerMove={updateHover} onPointerUp={updateHover} />
      {hovered && <div className="comparison-tooltip"><strong>{hovered[0].point.date}</strong>{hovered.map(({ line, point }) => <span key={line.code}><i style={{ background: line.color }} />{line.name}<b className={tone(point.value)}>{pct(point.value)}</b></span>)}</div>}
    </div>
    <p className="method-note">参考线：每种颜色对应上方勾选的指数，水平 0% 线代表共同起点。当前为{logScale ? "对数收益率（适合跨长周期比较）" : "普通累计涨跌幅"}。实际共同归一化起点：{prepared.commonStart}；较晚成立的指数会自动推迟共同起点。拖动可逐日查看。</p>
  </>;
}

export default function SectorsPage() {
  const [data, setData] = useState<SectorData | null>(null);
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState<string[]>([]);
  const [start, setStart] = useState("2015-01-01");
  const [comparisonLog, setComparisonLog] = useState(false);
  useEffect(() => { Promise.all([
    fetch(assetPath("/data/sectors.json")).then((response) => response.json()),
    fetch(assetPath("/data/sector_analysis.json")).then((response) => response.json()),
  ]).then(([sectorData, analysisData]) => { setData(sectorData); setAnalysis(analysisData); setSelected(sectorData.indices.map((item: IndexData) => item.code)); }).catch((reason) => setError(reason instanceof Error ? reason.message : "数据加载失败")); }, []);
  if (error) return <main className="center-state"><strong>板块数据暂不可用</strong><span>{error}</span></main>;
  if (!data || !analysis) return <main className="center-state"><span className="pulse" /><strong>正在载入持仓板块指数</strong></main>;
  const ranked = [...data.indices].sort((a, b) => (b.summary.daily_return_pct ?? -999) - (a.summary.daily_return_pct ?? -999));
  const chooseComparisonRange = (range: "今年" | "1年" | "3年" | "5年" | "全部") => {
    if (range === "全部") return setStart(data.requested_start_date);
    const date = new Date(`${data.latest_a_share_date}T00:00:00`);
    if (range === "今年") date.setMonth(0, 1); else date.setFullYear(date.getFullYear() - Number(range[0]));
    setStart(date.toISOString().slice(0, 10));
  };
  return <main>
    <header className="topbar">
      <div className="brand"><span className="brand-mark">板</span><div><strong>SECTOR SIGNAL DESK</strong><small>HOLDINGS EXPOSURE MONITOR</small></div></div>
      <div className="market-stamp"><span className="live-dot" />A股指数截至 {data.latest_a_share_date}<span>·</span>每日收盘后更新</div>
      <nav className="top-actions"><a className="download" href={assetPath("/")}>NASDAQ 监控</a><a className="download" href={assetPath("/data/sector_indices_daily.csv")} download>下载 CSV</a></nav>
    </header>
    <div className="sector-dashboard">
      <section className="sector-intro panel"><div><span className="eyebrow">PORTFOLIO SECTOR MAP · 8 CORE BENCHMARKS</span><h1>持仓板块指数</h1><p>芯片上游、通信、AI、电池、有色、机器人、黄金与美国大盘。NASDAQ 已在独立页面监控，本页不重复。</p></div><div className="sector-leader"><span>今日领涨</span><strong>{ranked[0].name}</strong><b className={tone(ranked[0].summary.daily_return_pct)}>{pct(ranked[0].summary.daily_return_pct)}</b></div></section>
      <section className="sector-grid">{data.indices.map((item) => <article className="sector-card panel" key={item.code}>
        <div className="sector-card-head"><div><span>{item.code} · {item.category}</span><h2>{item.name}</h2></div><b className={tone(item.summary.daily_return_pct)}>{pct(item.summary.daily_return_pct)}</b></div>
        <MiniChart index={item} />
        <div className="sector-stats"><span>收盘<strong>{fmt(item.summary.close)}</strong></span><span>20日<strong className={tone(item.summary.returns.twenty_days)}>{pct(item.summary.returns.twenty_days)}</strong></span><span>成交活跃度<strong>{item.summary.amount_ratio20 == null ? "—" : `${item.summary.amount_ratio20.toFixed(2)}×`}</strong></span><span>资金方向估算<strong className={tone(item.summary.estimated_net_flow_billion)}>{flowText(item.summary.estimated_net_flow_billion)}</strong><small>{item.summary.money_flow_ratio_pct == null ? "无成交额数据" : `净占比 ${pct(item.summary.money_flow_ratio_pct)}`}</small></span></div>
        <small className="sector-source">{item.source} · 数据 {item.start_date}—{item.latest_date}</small>
      </article>)}</section>
      <section className="comparison-panel panel">
        <div className="section-head"><div><span className="eyebrow">NORMALIZED COMPARISON</span><h2>多指数归一化比较</h2></div><div className="comparison-controls"><div className="range-buttons">{(["今年", "1年", "3年", "5年", "全部"] as const).map((label) => <button key={label} onClick={() => chooseComparisonRange(label)}>{label}</button>)}</div><button className={comparisonLog ? "active" : ""} onClick={() => setComparisonLog((value) => !value)}>对数收益</button><label className="date-control">起点<input type="date" min="2015-01-01" max={data.latest_a_share_date} value={start} onChange={(event) => setStart(event.target.value)} /></label></div></div>
        <div className="index-picker">{data.indices.map((item) => <label key={item.code}><input type="checkbox" checked={selected.includes(item.code)} onChange={() => setSelected((current) => current.includes(item.code) ? current.filter((code) => code !== item.code) : [...current, item.code])} /><i style={{ background: item.color }} />{item.name}</label>)}</div>
        <ComparisonChart indices={data.indices} selected={selected} requestedStart={start} logScale={comparisonLog} />
      </section>
      <section className="ai-panel panel sector-ai"><div className="section-head"><div><span className="eyebrow">DAILY SYNTHESIS · THINK MODE</span><h2>当日跨板块分析</h2></div><span className={`source-chip ${analysis.status === "fallback" ? "fallback" : ""}`}>{analysis.source}{analysis.model ? ` · ${analysis.model}` : ""}</span></div>{analysis.error && <p className="ai-error">DeepSeek 暂未生效：{analysis.error}</p>}<div className="ai-copy">{analysis.text}</div><p className="disclaimer">{analysis.disclaimer} “资金方向”根据收盘在当日高低区间的位置和成交额估算，不是交易所披露的真实资金净流入。</p></section>
      <section className="table-panel panel"><div className="section-head"><div><span className="eyebrow">DAILY RANKING</span><h2>当日强弱、资金方向估算与趋势</h2></div><span className="row-count">{data.indices.length} 个核心指数</span></div><div className="table-scroll"><table><thead><tr><th>指数</th><th>当日</th><th>5日</th><th>20日</th><th>60日</th><th>今年以来</th><th>EMA200距离</th><th>估算流入</th><th>估算流出</th><th>估算净额 / 占比</th><th>趋势</th></tr></thead><tbody>{ranked.map((item) => <tr key={item.code}><td>{item.name}<small>{item.code}</small></td><td className={tone(item.summary.daily_return_pct)}>{pct(item.summary.daily_return_pct)}</td><td className={tone(item.summary.returns.five_days)}>{pct(item.summary.returns.five_days)}</td><td className={tone(item.summary.returns.twenty_days)}>{pct(item.summary.returns.twenty_days)}</td><td className={tone(item.summary.returns.sixty_days)}>{pct(item.summary.returns.sixty_days)}</td><td className={tone(item.summary.returns.ytd)}>{pct(item.summary.returns.ytd)}</td><td>{item.summary.ema200 ? pct((item.summary.close / item.summary.ema200 - 1) * 100) : "—"}</td><td>{item.summary.estimated_inflow_billion == null ? "—" : `${fmt(item.summary.estimated_inflow_billion)}亿`}</td><td>{item.summary.estimated_outflow_billion == null ? "—" : `${fmt(item.summary.estimated_outflow_billion)}亿`}</td><td className={tone(item.summary.estimated_net_flow_billion)}>{item.summary.estimated_net_flow_billion == null ? "—" : `${item.summary.estimated_net_flow_billion >= 0 ? "+" : ""}${fmt(item.summary.estimated_net_flow_billion)}亿 / ${pct(item.summary.money_flow_ratio_pct)}`}</td><td>{item.summary.trend}</td></tr>)}</tbody></table></div><p className="method-note">估算公式：资金方向占比 = (2×收盘−最高−最低) ÷ (最高−最低)；估算净额 = 成交额 × 方向占比，流入与流出为成交额按该比例拆分。上海金与标普500没有同口径成交额时显示“—”。</p></section>
    </div>
    <footer>SECTOR SIGNAL DESK <span>·</span> OFFICIAL INDEX DATA <span>·</span> NOT INVESTMENT ADVICE</footer>
  </main>;
}
