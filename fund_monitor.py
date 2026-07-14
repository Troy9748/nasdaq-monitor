#!/usr/bin/env python3
"""Daily fund NAV, disclosed holdings, stock history and structured analysis export."""

from __future__ import annotations

import argparse
import html
import json
import math
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf

START_DATE = "2015-01-01"
SHANGHAI = ZoneInfo("Asia/Shanghai")
DATA_DIR = Path("web/public/data")
FUND_DIR = DATA_DIR / "funds"
STOCK_DIR = DATA_DIR / "stocks"
CATALOG_PATH = DATA_DIR / "funds.json"

FUND_SECTORS = {
    "017641": "SPX", "016665": "SPX", "270023": "SPX", "022184": "SPX", "005698": "SPX",
    "018926": "931719", "027495": "931719", "001856": "931719",
    "020640": "931743", "007301": "931743", "006502": "931743", "026623": "931743",
    "021608": "931743", "025687": "931743", "021533": "931743",
    "011036": "930708", "013943": "930708", "019088": "930708", "017192": "930708", "018132": "930708",
    "009504": "SHAU", "007817": "931160",
    "001480": "930713", "017811": "930713", "012734": "930713", "017102": "930713",
    "011370": "980022", "018125": "980022", "018957": "980022",
}

SECTOR_NAMES = {
    "931743": "半导体材料设备", "931160": "通信设备", "930713": "人工智能主题", "931719": "电池主题",
    "930708": "中证有色金属", "980022": "国证机器人产业", "SHAU": "上海金", "SPX": "标普500",
}


def request_bytes(url: str, timeout: int = 30) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://fund.eastmoney.com/"})
    for attempt in range(3):
        try:
            time.sleep(0.12)
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read()
        except (OSError, urllib.error.HTTPError):
            if attempt == 2:
                raise
            time.sleep(0.8 * (attempt + 1))
    raise RuntimeError("unreachable")


def request_json(url: str, timeout: int = 30) -> dict:
    return json.loads(request_bytes(url, timeout).decode("utf-8-sig"))


def js_value(source: str, name: str):
    match = re.search(rf"var\s+{re.escape(name)}\s*=\s*(.*?);(?:/\*|var\s)", source, re.S)
    if not match:
        return None
    value = match.group(1).strip()
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value.strip('"')


def optional_number(value, digits: int = 4):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return round(number, digits) if math.isfinite(number) else None


def enrich_series(rows: list[dict], value_key: str = "value") -> list[dict]:
    if not rows:
        return []
    frame = pd.DataFrame(rows)
    values = pd.to_numeric(frame[value_key], errors="coerce")
    frame["daily_return_pct"] = values.pct_change(fill_method=None) * 100
    for sessions in (20, 60, 120):
        frame[f"ma{sessions}"] = values.rolling(sessions).mean()
    return [
        {key: optional_number(value) if key != "date" else value for key, value in row.items()}
        for row in frame.to_dict("records")
    ]


def period_return(series: list[dict], sessions: int):
    if len(series) <= sessions:
        return None
    base = series[-sessions - 1]["value"]
    return optional_number((series[-1]["value"] / base - 1) * 100, 2) if base else None


def max_drawdown(series: list[dict]):
    values = pd.Series([row["value"] for row in series], dtype=float)
    return optional_number(((values / values.cummax()) - 1).min() * 100, 2)


def parse_fund(code: str) -> dict:
    source = request_bytes(f"https://fund.eastmoney.com/pingzhongdata/{code}.js?v={int(time.time())}").decode("utf-8-sig")
    raw = js_value(source, "Data_netWorthTrend") or []
    series = enrich_series([
        {"date": datetime.fromtimestamp(item["x"] / 1000, SHANGHAI).date().isoformat(), "value": item["y"]}
        for item in raw if item.get("y") is not None
    ])
    allocation = js_value(source, "Data_assetAllocation") or {}
    latest_allocation = {}
    categories = allocation.get("categories") or []
    if categories:
        for item in allocation.get("series") or []:
            latest_allocation[item["name"]] = optional_number((item.get("data") or [None])[-1], 2)
    return {
        "code": code,
        "name": js_value(source, "fS_name") or code,
        "rate_pct": optional_number(js_value(source, "fund_Rate"), 2),
        "series": series,
        "asset_allocation": {"report_date": categories[-1] if categories else None, **latest_allocation},
        "reference_stock_ids": js_value(source, "stockCodesNew") or [],
    }


def plain_text(value: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", value)).strip()


def parse_holdings(code: str) -> tuple[str | None, list[dict]]:
    year = datetime.now(SHANGHAI).year
    url = f"https://fundf10.eastmoney.com/FundArchivesDatas.aspx?type=jjcc&code={code}&topline=10&year={year}&month=3,6,9,12"
    source = request_bytes(url).decode("utf-8-sig")
    date_match = re.search(r"截止至：.*?([12]\d{3}-\d{2}-\d{2})", source)
    holdings = []
    for row in re.findall(r"<tr>(.*?)</tr>", source, re.S):
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)
        if len(cells) < 7:
            continue
        code_text, name = plain_text(cells[1]), plain_text(cells[2])
        weight_match = re.search(r"(-?[\d.]+)%", plain_text(cells[6]))
        market_match = re.search(r"unify/r/([^'\"?]+)", cells[1])
        if not code_text or not weight_match:
            continue
        holdings.append({
            "stock_id": market_match.group(1) if market_match else code_text,
            "code": code_text,
            "name": name,
            "weight_pct": optional_number(weight_match.group(1), 2),
            "shares_10k": optional_number(plain_text(cells[7]).replace(",", ""), 2) if len(cells) > 7 else None,
            "market_value_10k": optional_number(plain_text(cells[8]).replace(",", ""), 2) if len(cells) > 8 else None,
        })
    return date_match.group(1) if date_match else None, sorted(holdings, key=lambda item: item["weight_pct"] or 0, reverse=True)[:10]


def a_share_stock(stock_id: str) -> bool:
    return stock_id.split(".", 1)[0] in {"0", "1"}


def yahoo_ticker(stock_id: str, code: str) -> str:
    market = stock_id.split(".", 1)[0] if "." in stock_id else ""
    if market in {"105", "106", "107"}:
        return code.replace("_", "-")
    if market in {"116", "128"} or (code.isdigit() and len(code) == 5):
        return f"{code.zfill(4)}.HK"
    return code


def eastmoney_stock_series(stock_id: str) -> list[dict]:
    market, code = stock_id.split(".", 1)
    symbol = f"{'sh' if market == '1' else 'sz'}{code}"
    payload = request_json(f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={symbol},day,,,640,qfq")
    data = (payload.get("data") or {}).get(symbol) or {}
    klines = data.get("qfqday") or data.get("day") or []
    return enrich_series([
        {"date": parts[0], "open": float(parts[1]), "value": float(parts[2]), "high": float(parts[3]), "low": float(parts[4]), "volume": float(parts[5])}
        for parts in klines
    ])


def yahoo_stock_series(stock_id: str, code: str) -> list[dict]:
    ticker = yahoo_ticker(stock_id, code)
    time.sleep(0.8)
    frame = yf.download(ticker, start=START_DATE, auto_adjust=False, progress=False, timeout=30)
    if frame.empty:
        return []
    if isinstance(frame.columns, pd.MultiIndex):
        frame.columns = frame.columns.get_level_values(0)
    return enrich_series([
        {"date": index.date().isoformat(), "open": row.get("Open"), "value": row.get("Close"), "high": row.get("High"), "low": row.get("Low"), "volume": row.get("Volume")}
        for index, row in frame.dropna(subset=["Close"]).iterrows()
    ])


def nasdaq_stock_series(code: str) -> list[dict]:
    params = urllib.parse.urlencode({"assetclass": "stocks", "fromdate": START_DATE, "todate": datetime.now(SHANGHAI).date().isoformat(), "limit": 5000})
    payload = request_json(f"https://api.nasdaq.com/api/quote/{urllib.parse.quote(code.replace('_', '-'))}/historical?{params}", timeout=45)
    rows = ((((payload.get("data") or {}).get("tradesTable") or {}).get("rows")) or [])
    def number(value):
        return float(str(value).replace("$", "").replace(",", ""))
    return enrich_series(list(reversed([
        {"date": datetime.strptime(row["date"], "%m/%d/%Y").date().isoformat(), "open": number(row["open"]), "value": number(row["close"]), "high": number(row["high"]), "low": number(row["low"]), "volume": number(row["volume"])}
        for row in rows if all(row.get(key) not in {None, "N/A"} for key in ("open", "close", "high", "low", "volume"))
    ])))


def hong_kong_stock_series(code: str) -> list[dict]:
    symbol = f"hk{code.zfill(5)}"
    payload = request_json(f"https://web.ifzq.gtimg.cn/appstock/app/hkfqkline/get?param={symbol},day,,,640,qfq")
    data = (payload.get("data") or {}).get(symbol) or {}
    rows = data.get("qfqday") or data.get("day") or []
    return enrich_series([{"date": row[0], "open": float(row[1]), "value": float(row[2]), "high": float(row[3]), "low": float(row[4]), "volume": float(row[5])} for row in rows])


def announcements(code: str, stock_id: str) -> list[dict]:
    if a_share_stock(stock_id):
        params = urllib.parse.urlencode({"sr": -1, "page_size": 8, "page_index": 1, "ann_type": "A", "client_source": "web", "stock_list": code})
        rows = ((request_json(f"https://np-anotice-stock.eastmoney.com/api/security/ann?{params}").get("data") or {}).get("list") or [])
        return [{"date": row["notice_date"][:10], "title": row["title"], "category": "、".join(item["column_name"] for item in row.get("columns") or []), "source": "交易所公告", "url": f"https://data.eastmoney.com/notices/detail/{code}/{row['art_code']}.html"} for row in rows]
    try:
        ticker = yahoo_ticker(stock_id, code)
        rows = request_json(f"https://query1.finance.yahoo.com/v1/finance/search?q={urllib.parse.quote(ticker)}&quotesCount=1&newsCount=8").get("news") or []
        return [{"date": datetime.fromtimestamp(row["providerPublishTime"], SHANGHAI).date().isoformat(), "title": row["title"], "category": "市场新闻", "source": row.get("publisher") or "Yahoo Finance", "url": row.get("link")} for row in rows]
    except Exception:
        return []


def financial_snapshot(code: str, stock_id: str) -> dict | None:
    if not a_share_stock(stock_id):
        return None
    params = urllib.parse.urlencode({
        "reportName": "RPT_LICO_FN_CPD", "columns": "ALL", "filter": f'(SECURITY_CODE="{code}")',
        "pageNumber": 1, "pageSize": 1, "sortColumns": "REPORTDATE", "sortTypes": -1,
    })
    rows = ((request_json(f"https://datacenter-web.eastmoney.com/api/data/v1/get?{params}").get("result") or {}).get("data") or [])
    if not rows:
        return None
    row = rows[0]
    return {
        "report_date": (row.get("REPORTDATE") or "")[:10], "report_type": row.get("DATATYPE"),
        "revenue_billion": optional_number((row.get("TOTAL_OPERATE_INCOME") or 0) / 1e8, 2),
        "revenue_yoy_pct": optional_number(row.get("YSTZ"), 2),
        "net_profit_billion": optional_number((row.get("PARENT_NETPROFIT") or 0) / 1e8, 2),
        "net_profit_yoy_pct": optional_number(row.get("SJLTZ"), 2),
        "roe_pct": optional_number(row.get("WEIGHTAVG_ROE"), 2),
    }


def stock_summary(series: list[dict]) -> dict:
    if not series:
        return {"latest_date": None, "close": None, "daily_return_pct": None, "return_5d_pct": None, "return_20d_pct": None, "volume_ratio20": None}
    volumes = [row.get("volume") for row in series[-20:] if row.get("volume") is not None]
    latest_volume = series[-1].get("volume")
    return {
        "latest_date": series[-1]["date"], "close": series[-1]["value"], "daily_return_pct": series[-1].get("daily_return_pct"),
        "return_5d_pct": period_return(series, 5), "return_20d_pct": period_return(series, 20),
        "volume_ratio20": optional_number(latest_volume / (sum(volumes) / len(volumes)), 2) if latest_volume and volumes else None,
    }


def deterministic_fund_analysis(fund: dict) -> dict:
    names = "、".join(item["name"] for item in fund["holdings"][:3]) or "暂无可核验重仓股"
    return {"sections": {"performance": "近期净值表现与波动需要结合所属板块共同观察。", "relative": f"主要参考{SECTOR_NAMES[fund['sector_code']]}指数判断相对强弱。", "holdings": f"最新公开重仓股包括{names}。", "risks": "公开持仓具有报告期滞后，不代表当前实时仓位。", "watch": "关注净值趋势、板块指数和重仓股表现是否形成一致确认。"}, "evidence": [], "source": "规则分析", "error": None}


def deterministic_stock_analysis(stock: dict) -> dict:
    event = stock["news"][0]["title"] if stock["news"] else "近期没有取得新的可核验公告或新闻。"
    return {"sections": {"event": event, "financial": "结合最近一期公开财务数据观察经营变化。", "reaction": "价格与成交量反应需结合事件发生日期判断。", "risks": "新闻标题不等同于事件最终影响，仍需阅读原始公告。", "watch": "关注后续公告、财报和量价确认。"}, "source_indices": list(range(min(3, len(stock["news"])))), "source": "规则分析", "error": None}


def deepseek_json(system: str, user: dict) -> dict:
    api_key = os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("missing DeepSeek API key")
    base = (os.getenv("DEEPSEEK_BASE_URL") or "https://api.deepseek.com").rstrip("/")
    payload = {"model": os.getenv("DEEPSEEK_MODEL") or "deepseek-v4-pro", "messages": [{"role": "system", "content": system}, {"role": "user", "content": json.dumps(user, ensure_ascii=False)}], "response_format": {"type": "json_object"}, "thinking": {"type": "enabled"}, "reasoning_effort": "high", "max_tokens": 6000, "stream": False}
    body = json.dumps(payload).encode()
    for attempt in range(2):
        try:
            request = urllib.request.Request(f"{base}/chat/completions", data=body, headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(request, timeout=300) as response:
                result = json.load(response)
            content = result["choices"][0]["message"].get("content") or ""
            return json.loads(re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip(), flags=re.I))
        except urllib.error.HTTPError as error:
            detail = error.read().decode(errors="replace")[:1000]
            if attempt:
                raise RuntimeError(f"DeepSeek HTTP {error.code}: {detail}") from error
            time.sleep(3)
        except Exception:
            if attempt:
                raise
            time.sleep(3)
    raise RuntimeError("DeepSeek returned no result")


def analyze_funds(funds: list[dict]) -> dict[str, dict]:
    fallback = {fund["code"]: deterministic_fund_analysis(fund) for fund in funds}
    for start in range(0, len(funds), 8):
        batch = funds[start:start + 8]
        compact = {fund["code"]: {"name": fund["name"], "sector": SECTOR_NAMES[fund["sector_code"]], "summary": fund["summary"], "holdings": fund["holdings"]} for fund in batch}
        try:
            result = deepseek_json("你是基金研究助手。仅依据输入数据，为每只基金返回对象，键为基金代码；每项含sections，固定包含performance、relative、holdings、risks、watch五个简短中文字符串。不得把定期报告持仓称为实时持仓，不给绝对买卖指令，不虚构新闻。", compact)
            for code, item in result.items():
                if code in fallback and all((item.get("sections") or {}).get(key) for key in ("performance", "relative", "holdings", "risks", "watch")):
                    fallback[code] = {"sections": item["sections"], "evidence": [], "source": "DeepSeek", "error": None}
        except Exception as error:
            for fund in batch:
                fallback[fund["code"]]["error"] = f"{type(error).__name__}: {error}"
            print(f"⚠️ 基金 DeepSeek 批次分析回退：{error}")
    return fallback


def analyze_stocks(stocks: list[dict]) -> dict[str, dict]:
    output = {stock["stock_id"]: deterministic_stock_analysis(stock) for stock in stocks}
    system = "你是上市公司事件研究助手。仅依据输入中的行情、公告新闻标题和财务数据总结。返回对象，键为stock_id；每项含sections(event、financial、reaction、risks、watch)及source_indices。不得虚构事实或来源，不给绝对买卖指令。"
    for start in range(0, len(stocks), 8):
        batch = stocks[start:start + 8]
        compact = {stock["stock_id"]: {"name": stock["name"], "summary": stock["summary"], "financial": stock["financial"], "news": stock["news"]} for stock in batch}
        try:
            result = deepseek_json(system, compact)
            for stock_id, item in result.items():
                sections = item.get("sections") or {}
                if stock_id in output and all(sections.get(key) for key in ("event", "financial", "reaction", "risks", "watch")):
                    valid = [index for index in item.get("source_indices") or [] if isinstance(index, int) and 0 <= index < len(compact[stock_id]["news"])]
                    output[stock_id] = {"sections": sections, "source_indices": valid[:5], "source": "DeepSeek", "error": None}
        except Exception as error:
            for stock in batch:
                output[stock["stock_id"]]["error"] = f"{type(error).__name__}: {error}"
            print(f"⚠️ 股票 DeepSeek 批次分析回退：{error}")
    return output


def load_cached_stock(stock_id: str) -> dict | None:
    path = STOCK_DIR / f"{stock_id.replace('.', '_')}.json"
    return json.loads(path.read_text()) if path.exists() else None


def build_stock(holding: dict) -> dict:
    cached = load_cached_stock(holding["stock_id"])
    today = datetime.now(SHANGHAI).date().isoformat()
    if cached and cached.get("generated_date") == today and cached.get("series"):
        series = cached["series"]
    else:
        try:
            market = holding["stock_id"].split(".", 1)[0]
            if a_share_stock(holding["stock_id"]):
                series = eastmoney_stock_series(holding["stock_id"])
            elif market in {"105", "106", "107"}:
                series = nasdaq_stock_series(holding["code"])
            elif market in {"116", "128"}:
                series = hong_kong_stock_series(holding["code"])
            else:
                series = yahoo_stock_series(holding["stock_id"], holding["code"])
            if not series:
                raise RuntimeError("empty stock history")
        except Exception as error:
            if not cached:
                print(f"⚠️ {holding['name']} 行情不可用：{error}")
                series = []
            else:
                print(f"⚠️ {holding['name']} 使用缓存行情：{error}")
                series = cached["series"]
    if cached and cached.get("generated_date") == today:
        news, financial = cached.get("news", []), cached.get("financial")
    else:
        try:
            news = announcements(holding["code"], holding["stock_id"])
        except Exception:
            news = (cached or {}).get("news", [])
        try:
            financial = financial_snapshot(holding["code"], holding["stock_id"])
        except Exception:
            financial = (cached or {}).get("financial")
    return {"stock_id": holding["stock_id"], "code": holding["code"], "name": holding["name"], "generated_date": today, "summary": stock_summary(series), "financial": financial, "news": news, "series": series}


def job() -> None:
    FUND_DIR.mkdir(parents=True, exist_ok=True)
    STOCK_DIR.mkdir(parents=True, exist_ok=True)
    funds = []
    holdings_by_stock = {}
    for code, sector_code in FUND_SECTORS.items():
        path = FUND_DIR / f"{code}.json"
        try:
            fund = parse_fund(code)
            report_date, holdings = parse_holdings(code)
            if not holdings and path.exists():
                cached = json.loads(path.read_text())
                report_date, holdings = cached.get("holdings_report_date"), cached.get("holdings", [])
        except Exception as error:
            if not path.exists():
                raise
            print(f"⚠️ 基金 {code} 使用缓存：{error}")
            cached = json.loads(path.read_text())
            fund, report_date, holdings = cached, cached.get("holdings_report_date"), cached.get("holdings", [])
        fund["sector_code"] = sector_code
        fund["sector_name"] = SECTOR_NAMES[sector_code]
        fund["holdings_report_date"] = report_date
        fund["holdings"] = holdings
        fund["summary"] = {"latest_date": fund["series"][-1]["date"], "nav": fund["series"][-1]["value"], "daily_return_pct": fund["series"][-1].get("daily_return_pct"), "return_20d_pct": period_return(fund["series"], 20), "return_60d_pct": period_return(fund["series"], 60), "return_1y_pct": period_return(fund["series"], 252), "max_drawdown_pct": max_drawdown(fund["series"])}
        funds.append(fund)
        for holding in holdings:
            holdings_by_stock.setdefault(holding["stock_id"], holding)
        print(f"✅ {code} {fund['name']} · {report_date or '无持仓日期'}")
    stocks = [build_stock(holding) for holding in holdings_by_stock.values()]
    stock_analyses = analyze_stocks(stocks)
    for stock in stocks:
        stock["analysis"] = stock_analyses[stock["stock_id"]]
        path = STOCK_DIR / f"{stock['stock_id'].replace('.', '_')}.json"
        path.write_text(json.dumps(stock, ensure_ascii=False, separators=(",", ":"), allow_nan=False))
    fund_analyses = analyze_funds(funds)
    stock_paths = {stock["stock_id"]: f"/data/stocks/{stock['stock_id'].replace('.', '_')}.json" for stock in stocks}
    catalog = []
    for fund in funds:
        fund["analysis"] = fund_analyses[fund["code"]]
        for holding in fund["holdings"]:
            holding["stock_path"] = stock_paths.get(holding["stock_id"])
        (FUND_DIR / f"{fund['code']}.json").write_text(json.dumps(fund, ensure_ascii=False, separators=(",", ":"), allow_nan=False))
        catalog.append({key: fund[key] for key in ("code", "name", "sector_code", "sector_name", "summary", "holdings_report_date", "asset_allocation", "analysis") } | {"path": f"/data/funds/{fund['code']}.json", "series": fund["series"][-252:]})
    CATALOG_PATH.write_text(json.dumps({"generated_at": datetime.now(ZoneInfo("UTC")).isoformat(), "funds": catalog}, ensure_ascii=False, separators=(",", ":"), allow_nan=False))
    print(f"✅ 基金监控完成：{len(funds)} 只基金，{len(stocks)} 只唯一重仓股")


if __name__ == "__main__":
    argparse.ArgumentParser(description="基金与重仓股每日监控").parse_args()
    job()
