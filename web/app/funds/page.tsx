"use client";

import { useEffect, useMemo, useState } from "react";
import FundChart, { type FundPoint } from "../components/FundChart";

type Fund = { code:string; name:string; sector_code:string; sector_name:string; path:string; summary:{latest_date:string;nav:number;daily_return_pct:number|null;return_20d_pct:number|null;return_60d_pct:number|null;return_1y_pct:number|null;max_drawdown_pct:number|null}; holdings_report_date:string|null; asset_allocation:Record<string,string|number|null>; analysis:{sections:Record<string,string>;source?:string}; series:FundPoint[] };
type Catalog={generated_at:string;funds:Fund[]};
const basePath=process.env.NEXT_PUBLIC_BASE_PATH??"";
const assetPath=(path:string)=>`${basePath}${path}${path.endsWith(".json")?`?v=${Date.now()}`:""}`;
const fmt=(value:number|null|undefined)=>value==null?"—":value.toLocaleString("zh-CN",{maximumFractionDigits:4});
const pct=(value:number|null|undefined)=>value==null?"—":`${value>=0?"+":""}${value.toFixed(2)}%`;
const tone=(value:number|null|undefined)=>value==null||value===0?"neutral":value>0?"positive":"negative";
const colors=["#22d3ee","#a78bfa","#38bdf8","#34d399","#f59e0b","#fb7185","#facc15"];

export default function FundsPage(){
  const [catalog,setCatalog]=useState<Catalog|null>(null),[sector,setSector]=useState(""),[lockedDate,setLockedDate]=useState<string|null>(null),[openAnalysis,setOpenAnalysis]=useState<string|null>(null),[error,setError]=useState("");
  useEffect(()=>{setSector(new URLSearchParams(location.search).get("sector")??"");fetch(assetPath("/data/funds.json")).then((response)=>{if(!response.ok)throw new Error("基金数据尚未生成");return response.json();}).then(setCatalog).catch((reason)=>setError(reason.message));},[]);
  const funds=useMemo(()=>catalog?.funds.filter((fund)=>!sector||fund.sector_code===sector)??[],[catalog,sector]);
  if(error)return <main className="center-state"><strong>基金数据暂不可用</strong><span>{error}</span></main>;
  if(!catalog)return <main className="center-state"><span className="pulse"/><strong>正在载入基金净值</strong></main>;
  return <main><header className="topbar"><div className="brand"><span className="brand-mark">基</span><div><strong>FUND DRILLDOWN</strong><small>PUBLIC NAV & DISCLOSED HOLDINGS</small></div></div><nav className="top-actions"><a className="download" href={assetPath("/sectors.html")}>返回板块指数</a></nav></header><div className="sector-dashboard fund-dashboard">
    <section className="sector-intro panel"><div><span className="eyebrow">SECTOR → FUND</span><h1>{funds[0]?.sector_name??"全部持仓基金"}</h1><p>基金净值每日更新；持仓仅采用最新公开定期报告，不代表实时仓位。拖动任意曲线并松手可锁定日期。</p></div><div className="sector-leader"><span>本页基金数量</span><strong>{funds.length} 只</strong><b>截至 {funds.map((fund)=>fund.summary.latest_date).sort().at(-1)}</b></div></section>
    {lockedDate&&<div className="date-lock panel"><span>全图已锁定 <strong>{lockedDate}</strong></span><button onClick={()=>setLockedDate(null)}>解除锁定</button></div>}
    <section className="sector-grid">{funds.map((fund,index)=><article className="sector-card panel" key={fund.code}><div className="sector-card-head"><div><span>{fund.code} · {fund.sector_name}</span><h2>{fund.name}</h2></div><b className={tone(fund.summary.daily_return_pct)}>{pct(fund.summary.daily_return_pct)}</b></div><FundChart series={fund.series} color={colors[index%colors.length]} lockedDate={lockedDate} onLockDate={setLockedDate} storageKey={fund.code}/><div className="sector-stats fund-stats"><span>最新净值<strong>{fmt(fund.summary.nav)}</strong></span><span>近20日<strong className={tone(fund.summary.return_20d_pct)}>{pct(fund.summary.return_20d_pct)}</strong></span><span>近1年<strong className={tone(fund.summary.return_1y_pct)}>{pct(fund.summary.return_1y_pct)}</strong></span><span>历史最大回撤<strong className="negative">{pct(fund.summary.max_drawdown_pct)}</strong></span></div><div className="fund-actions"><button onClick={()=>setOpenAnalysis(openAnalysis===fund.code?null:fund.code)}>{fund.analysis.source??"规则分析"} · 基金分析</button><a href={assetPath(`/fund.html?code=${fund.code}`)}>查看持仓分布 →</a></div>{openAnalysis===fund.code&&<div className="analysis-sections compact">{Object.entries(fund.analysis.sections).map(([key,value])=><article key={key}><small>{({performance:"净值表现",relative:"相对板块",holdings:"持仓结构",risks:"风险",watch:"后续观察"} as Record<string,string>)[key]??key}</small><p>{value}</p></article>)}</div>}<small className="sector-source">净值截至 {fund.summary.latest_date} · 持仓报告期 {fund.holdings_report_date??"暂无"}</small></article>)}</section>
  </div><footer>PUBLIC FUND DATA · DISCLOSED HOLDINGS ARE DELAYED · NOT INVESTMENT ADVICE</footer></main>;
}
