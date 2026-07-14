import argparse
import io
import json
import math
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf

from monitor import calculate_indicators


START_DATE = "2015-01-01"
SHANGHAI = ZoneInfo("Asia/Shanghai")
CSV_PATH = Path("sector_indices_daily.csv")
WEB_DATA_DIR = Path("web/public/data")
WEB_JSON_PATH = WEB_DATA_DIR / "sectors.json"
WEB_ANALYSIS_PATH = WEB_DATA_DIR / "sector_analysis.json"
WEB_CSV_PATH = WEB_DATA_DIR / CSV_PATH.name

CSI_URL = "https://www.csindex.com.cn/csindex-home/perf/index-perf"
CNI_URL = "https://hq.cnindex.com.cn/market/market/getIndexDailyDataWithDataFormat"
SGE_DAILY_URL = "https://en.sge.com.cn/graph/DayilyJzj"
SGE_LATEST_URL = "https://en.sge.com.cn/data_BenchmarkPrice_Daily"

INDEXES = {
    "931743": {
        "name": "半导体材料设备",
        "category": "国产芯片上游",
        "source": "中证指数",
        "provider": "csi",
        "base_date": "2018-12-28",
        "color": "#22d3ee",
    },
    "931160": {
        "name": "通信设备",
        "category": "CPO · 光模块 · 通信",
        "source": "中证指数",
        "provider": "csi",
        "base_date": "2004-12-31",
        "color": "#a78bfa",
    },
    "930713": {
        "name": "人工智能主题",
        "category": "AI全产业链",
        "source": "中证指数",
        "provider": "csi",
        "base_date": "2012-06-29",
        "color": "#38bdf8",
    },
    "931719": {
        "name": "电池主题",
        "category": "动力电池 · 储能",
        "source": "中证指数",
        "provider": "csi",
        "base_date": "2014-12-31",
        "color": "#34d399",
    },
    "930708": {
        "name": "中证有色金属",
        "category": "稀土 · 工业金属 · 矿业",
        "source": "中证指数",
        "provider": "csi",
        "base_date": "2013-12-31",
        "color": "#f59e0b",
    },
    "980022": {
        "name": "国证机器人产业",
        "category": "机器人 · 自动化",
        "source": "国证指数",
        "provider": "cni",
        "base_date": "2014-12-31",
        "color": "#fb7185",
    },
    "SHAU": {
        "name": "上海金",
        "category": "人民币黄金",
        "source": "上海黄金交易所",
        "provider": "sge",
        "base_date": "2016-04-18",
        "color": "#facc15",
    },
    "SPX": {
        "name": "标普500",
        "category": "美国大盘",
        "source": "Yahoo Finance（S&P 500）",
        "provider": "yahoo",
        "base_date": "1928-01-03",
        "color": "#60a5fa",
    },
}


def request_bytes(url: str, *, data: dict | None = None, timeout: int = 60) -> bytes:
    body = urllib.parse.urlencode(data).encode() if data else None
    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Referer": "https://www.csindex.com.cn/",
            "X-Requested-With": "XMLHttpRequest",
        },
        method="POST" if body else "GET",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def download_csi(code: str, base_date: str) -> pd.DataFrame:
    end = datetime.now(SHANGHAI).strftime("%Y%m%d")
    params = urllib.parse.urlencode(
        {"indexCode": code, "startDate": START_DATE.replace("-", ""), "endDate": end}
    )
    payload = json.loads(request_bytes(f"{CSI_URL}?{params}"))
    rows = payload.get("data") or []
    if not rows:
        raise RuntimeError(f"中证指数 {code} 返回空数据")
    data = pd.DataFrame(rows)
    data["Date"] = pd.to_datetime(data["tradeDate"], format="%Y%m%d")
    for column in ("open", "high", "low", "close", "tradingVol", "tradingValue"):
        data[column] = pd.to_numeric(data[column], errors="coerce")
    # ponytail: API 会夹带基日/查询起点占位值；无开盘价的点不参与连续收益和均线计算。
    base = pd.Timestamp(base_date)
    data = data[data["open"].notna()]
    data = data[data["Date"] >= max(pd.Timestamp(START_DATE), base)]
    data = data.sort_values("Date")
    if (
        len(data) > 1
        and data.iloc[0]["Date"] == pd.Timestamp(START_DATE)
        and data.iloc[0][["open", "high", "low", "close"]].equals(
            data.iloc[1][["open", "high", "low", "close"]]
        )
    ):
        data = data.iloc[1:]
    return (
        data.rename(
            columns={
                "open": "Open",
                "high": "High",
                "low": "Low",
                "close": "Close",
                "tradingVol": "Volume",
                "tradingValue": "Amount",
            }
        )
        .set_index("Date")[["Open", "High", "Low", "Close", "Volume", "Amount"]]
        .assign(Amount=lambda frame: frame["Amount"] * 100_000_000)
        .sort_index()
    )


def download_cni(code: str, base_date: str) -> pd.DataFrame:
    end = datetime.now(SHANGHAI).date().isoformat()
    params = urllib.parse.urlencode(
        {"indexCode": code, "startDate": START_DATE, "endDate": end, "frequency": "Day"}
    )
    payload = json.loads(request_bytes(f"{CNI_URL}?{params}"))
    block = payload.get("data") or {}
    data = pd.DataFrame(block.get("data") or [], columns=block.get("item") or [])
    if data.empty:
        raise RuntimeError(f"国证指数 {code} 返回空数据")
    data["Date"] = pd.to_datetime(data["timestamp"])
    for column in ("open", "high", "low", "close", "volume", "amount"):
        data[column] = pd.to_numeric(data[column], errors="coerce")
    return (
        data[data["Date"] >= max(pd.Timestamp(START_DATE), pd.Timestamp(base_date))]
        .rename(
            columns={
                "open": "Open",
                "high": "High",
                "low": "Low",
                "close": "Close",
                "volume": "Volume",
                "amount": "Amount",
            }
        )
        .set_index("Date")[["Open", "High", "Low", "Close", "Volume", "Amount"]]
        .assign(Amount=lambda frame: frame["Amount"] * 100_000_000)
        .sort_index()
    )


def _sge_points(values: list[list[float]]) -> pd.Series:
    if not values:
        return pd.Series(dtype=float)
    dates = pd.to_datetime([row[0] for row in values], unit="ms", utc=True).tz_convert(SHANGHAI)
    index = dates.tz_localize(None).normalize()
    return pd.Series([float(row[1]) for row in values], index=index)


def download_sge() -> pd.DataFrame:
    payload = json.loads(
        request_bytes(
            SGE_DAILY_URL,
            data={"start": "2016-04-01", "end": datetime.now(SHANGHAI).date().isoformat()},
        )
    )
    am = _sge_points(payload.get("zp") or [])
    pm = _sge_points(payload.get("wp") or [])
    close = pm.combine_first(am).sort_index()

    latest_html = request_bytes(
        SGE_LATEST_URL,
        data={"start": datetime.now(SHANGHAI).date().isoformat(), "end": datetime.now(SHANGHAI).date().isoformat()},
    ).decode("utf-8", errors="ignore")
    for date, morning, afternoon in re.findall(
        r"<td>(\d{8})</td>\s*<td>SHAU</td>\s*<td>([\d./-]+)</td>\s*<td>([\d./-]+)</td>",
        latest_html,
    ):
        value = afternoon if afternoon not in {"/", "-"} else morning
        if value not in {"/", "-"}:
            close.loc[pd.Timestamp(date)] = float(value)
    if close.empty:
        raise RuntimeError("上海金返回空数据")
    return pd.DataFrame({"Close": close[close.index >= pd.Timestamp("2016-04-18")]})


def download_spx() -> pd.DataFrame:
    try:
        data = yf.download(
            "^GSPC",
            start=START_DATE,
            end=(datetime.now(SHANGHAI).date() + timedelta(days=1)).isoformat(),
            auto_adjust=False,
            progress=False,
            multi_level_index=False,
            timeout=45,
        )
    except Exception:
        data = pd.DataFrame()

    if data.empty or "Close" not in data:
        start = int(pd.Timestamp(START_DATE, tz="UTC").timestamp())
        end = int((pd.Timestamp.now(tz="UTC") + pd.Timedelta(days=1)).timestamp())
        url = (
            "https://query1.finance.yahoo.com/v8/finance/chart/%5EGSPC"
            f"?period1={start}&period2={end}&interval=1d&events=history"
        )
        try:
            result = json.loads(request_bytes(url))["chart"]["result"][0]
            quote = result["indicators"]["quote"][0]
            data = pd.DataFrame(
                {
                    "Open": quote["open"],
                    "High": quote["high"],
                    "Low": quote["low"],
                    "Close": quote["close"],
                    "Volume": quote["volume"],
                },
                index=pd.to_datetime(result["timestamp"], unit="s", utc=True).tz_localize(None),
            )
        except Exception as yahoo_error:
            # ponytail: FRED is a close-only fallback; remove it if Yahoo becomes reliably available.
            fred = pd.read_csv(
                io.BytesIO(
                    request_bytes(
                        f"https://fred.stlouisfed.org/graph/fredgraph.csv?id=SP500&cosd={START_DATE}"
                    )
                ),
                parse_dates=["observation_date"],
                na_values=".",
            ).dropna(subset=["SP500"])
            if fred.empty:
                raise RuntimeError(f"标普500返回空数据：{yahoo_error}") from yahoo_error
            data = fred.set_index("observation_date")[["SP500"]].rename(columns={"SP500": "Close"})

    data.index = pd.to_datetime(data.index).tz_localize(None).normalize()
    return data[[column for column in ("Open", "High", "Low", "Close", "Volume") if column in data]].dropna(
        subset=["Close"]
    )


def load_cached() -> dict[str, pd.DataFrame]:
    if not CSV_PATH.exists():
        return {}
    data = pd.read_csv(CSV_PATH, parse_dates=["Date"])
    frames = {}
    for code, rows in data.groupby("Code"):
        frame = rows.set_index("Date").drop(columns=["Code", "Name"], errors="ignore")
        frames[str(code)] = frame
    return frames


def download_all() -> dict[str, pd.DataFrame]:
    cached = load_cached()
    result = {}
    for code, config in INDEXES.items():
        try:
            if config["provider"] == "csi":
                frame = download_csi(code, config["base_date"])
            elif config["provider"] == "cni":
                frame = download_cni(code, config["base_date"])
            elif config["provider"] == "sge":
                frame = download_sge()
            else:
                frame = download_spx()
            print(f"✅ {config['name']}：{frame.index[0].date()} 至 {frame.index[-1].date()}")
        except Exception as error:
            if code not in cached:
                raise
            print(f"⚠️ {config['name']} 下载失败，保留历史缓存：{error}")
            frame = cached[code]
        result[code] = frame
    return result


def prepare_frame(frame: pd.DataFrame) -> pd.DataFrame:
    data = calculate_indicators(frame)
    data["EMA20"] = data["Close"].ewm(span=20, adjust=False).mean()
    if "Amount" in data:
        data["Amount_Ratio20"] = data["Amount"] / data["Amount"].rolling(20).mean()
    else:
        data["Amount"] = float("nan")
        data["Amount_Ratio20"] = float("nan")
    return data.round(4)


def validate_frame(code: str, data: pd.DataFrame) -> None:
    if len(data) < 500:
        raise RuntimeError(f"{code} 历史数据不足，仅有 {len(data)} 行")
    if data.index.has_duplicates or not data.index.is_monotonic_increasing:
        raise RuntimeError(f"{code} 日期无序或重复")
    if not math.isfinite(float(data.iloc[-1]["Close"])) or data.iloc[-1]["Close"] <= 0:
        raise RuntimeError(f"{code} 最新收盘无效")
    age = (datetime.now(SHANGHAI).date() - data.index[-1].date()).days
    if age > 10:
        raise RuntimeError(f"{code} 数据已过期 {age} 天")


def period_return(close: pd.Series, sessions: int) -> float | None:
    if len(close) <= sessions:
        return None
    return round((float(close.iloc[-1]) / float(close.iloc[-sessions - 1]) - 1) * 100, 2)


def optional_number(value, digits: int = 2) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return round(number, digits) if math.isfinite(number) else None


def build_summary(data: pd.DataFrame) -> dict:
    latest = data.iloc[-1]
    close = data["Close"]
    market_date = data.index[-1]
    prior_year = close[close.index.year < market_date.year]
    ytd_base = float(prior_year.iloc[-1]) if not prior_year.empty else float(close.iloc[0])
    if latest["Close"] > latest["EMA50"] > latest["EMA200"]:
        trend = "多头排列"
    elif latest["Close"] < latest["EMA50"] < latest["EMA200"]:
        trend = "空头排列"
    elif latest["Close"] >= latest["EMA200"]:
        trend = "震荡偏强"
    else:
        trend = "震荡偏弱"
    return {
        "market_date": market_date.date().isoformat(),
        "close": round(float(latest["Close"]), 2),
        "daily_return_pct": optional_number(latest["Daily_Return_Pct"]),
        "returns": {
            "five_days": period_return(close, 5),
            "twenty_days": period_return(close, 20),
            "sixty_days": period_return(close, 60),
            "ytd": round((float(close.iloc[-1]) / ytd_base - 1) * 100, 2),
        },
        "ema20": optional_number(latest["EMA20"]),
        "ema50": optional_number(latest["EMA50"]),
        "ema200": optional_number(latest["EMA200"]),
        "distance_ema200_pct": optional_number((latest["Close"] / latest["EMA200"] - 1) * 100),
        "rsi14": optional_number(latest["RSI14"]),
        "volatility20_pct": optional_number(latest["Volatility20_Pct"]),
        "amount_billion": optional_number(latest["Amount"] / 1_000_000_000),
        "amount_ratio20": optional_number(latest["Amount_Ratio20"]),
        "trend": trend,
    }


def deterministic_analysis(summaries: dict[str, dict]) -> str:
    ranked = sorted(
        summaries.items(), key=lambda item: item[1].get("daily_return_pct") or -999, reverse=True
    )
    leader, laggard = ranked[0], ranked[-1]
    strong = [INDEXES[code]["name"] for code, value in summaries.items() if value["trend"] == "多头排列"]
    return "\n\n".join(
        [
            f"今日强弱：{INDEXES[leader[0]]['name']}领涨 {leader[1]['daily_return_pct']:+.2f}%，"
            f"{INDEXES[laggard[0]]['name']}相对落后 {laggard[1]['daily_return_pct']:+.2f}%。",
            f"趋势结构：当前多头排列板块为{'、'.join(strong) if strong else '暂无'}。",
            "观察建议：优先观察领涨板块能否在成交活跃度提升时维持均线结构；若仅价格上涨而成交额低于20日均值，避免把单日反弹直接视为趋势确认。仅作数据观察，不构成投资建议。",
        ]
    )


def build_ai_request(summaries: dict[str, dict]) -> tuple[str, dict, str, str]:
    base_url = (os.getenv("OPENAI_BASE_URL") or "https://api.deepseek.com").rstrip("/")
    model = os.getenv("OPENAI_MODEL") or "deepseek-v4-pro"
    provider = "DeepSeek" if "api.deepseek.com" in base_url else "OpenAI"
    compact = {
        code: {"name": INDEXES[code]["name"], **summary} for code, summary in summaries.items()
    }
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "你是审慎的跨板块市场数据分析员，只能使用给定指数数据，不得虚构新闻或资金流向。"
                    "用中文输出五个短段落：今日强弱、主线与轮动、趋势与成交验证、主要风险、下一交易日条件式观察建议。"
                    "明确区分成交活跃度与资金净流入，不给绝对买卖指令，结尾注明不构成投资建议。"
                ),
            },
            {"role": "user", "content": json.dumps(compact, ensure_ascii=False)},
        ],
        "max_tokens": 2200,
        "stream": False,
    }
    if provider == "DeepSeek":
        payload["thinking"] = {"type": "enabled"}
        payload["reasoning_effort"] = "high"
    return f"{base_url}/chat/completions", payload, model, provider


def request_ai_analysis(summaries: dict[str, dict]) -> tuple[str, str, str | None]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return deterministic_analysis(summaries), "规则分析", None
    url, payload, model, provider = build_ai_request(summaries)
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=150) as response:
            result = json.load(response)
        text = result["choices"][0]["message"]["content"].strip()
        if not text:
            raise RuntimeError("AI响应为空")
        return text, provider, model
    except (OSError, urllib.error.HTTPError, ValueError, KeyError, RuntimeError) as error:
        print(f"⚠️ 板块AI分析不可用，使用规则分析：{error}")
        return deterministic_analysis(summaries), "规则分析（AI回退）", model


def export_data(frames: dict[str, pd.DataFrame], summaries: dict[str, dict], analysis: dict) -> None:
    WEB_DATA_DIR.mkdir(parents=True, exist_ok=True)
    csv_frames = []
    indices = []
    fields = [
        "Close",
        "Daily_Return_Pct",
        "EMA20",
        "EMA50",
        "EMA200",
        "RSI14",
        "Volatility20_Pct",
        "Amount",
        "Amount_Ratio20",
    ]
    for code, data in frames.items():
        csv = data.copy()
        csv.insert(0, "Name", INDEXES[code]["name"])
        csv.insert(0, "Code", code)
        csv.index.name = "Date"
        csv_frames.append(csv.reset_index())
        series = [
            {
                "date": date.date().isoformat(),
                "close": optional_number(row["Close"], 4),
                "daily_return_pct": optional_number(row["Daily_Return_Pct"], 4),
                "ema20": optional_number(row["EMA20"], 4),
                "ema50": optional_number(row["EMA50"], 4),
                "ema200": optional_number(row["EMA200"], 4),
                "rsi14": optional_number(row["RSI14"], 4),
                "volatility20_pct": optional_number(row["Volatility20_Pct"], 4),
                "amount_billion": optional_number(row["Amount"] / 1_000_000_000, 4),
                "amount_ratio20": optional_number(row["Amount_Ratio20"], 4),
            }
            for date, row in data[fields].iterrows()
        ]
        indices.append(
            {
                "code": code,
                **{key: INDEXES[code][key] for key in ("name", "category", "source", "color")},
                "start_date": data.index[0].date().isoformat(),
                "latest_date": data.index[-1].date().isoformat(),
                "summary": summaries[code],
                "series": series,
            }
        )
    combined = pd.concat(csv_frames, ignore_index=True)
    combined.to_csv(CSV_PATH, index=False, encoding="utf-8-sig", float_format="%.4f")
    combined.to_csv(WEB_CSV_PATH, index=False, encoding="utf-8-sig", float_format="%.4f")
    a_share_dates = [summaries[code]["market_date"] for code in INDEXES if INDEXES[code]["provider"] in {"csi", "cni"}]
    WEB_JSON_PATH.write_text(
        json.dumps(
            {
                "generated_at": datetime.now(ZoneInfo("UTC")).isoformat(),
                "latest_a_share_date": max(a_share_dates),
                "requested_start_date": START_DATE,
                "indices": indices,
            },
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        ),
        encoding="utf-8",
    )
    WEB_ANALYSIS_PATH.write_text(
        json.dumps(analysis, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8"
    )


def previous_a_share_date() -> str | None:
    if not WEB_JSON_PATH.exists():
        return None
    return json.loads(WEB_JSON_PATH.read_text(encoding="utf-8")).get("latest_a_share_date")


def job(*, force: bool = False) -> bool:
    previous_date = previous_a_share_date()
    raw_frames = download_all()
    frames = {code: prepare_frame(frame) for code, frame in raw_frames.items()}
    for code, frame in frames.items():
        validate_frame(code, frame)
    summaries = {code: build_summary(frame) for code, frame in frames.items()}
    latest_a_share_date = max(
        summary["market_date"]
        for code, summary in summaries.items()
        if INDEXES[code]["provider"] in {"csi", "cni"}
    )
    if not force and previous_date and latest_a_share_date <= previous_date:
        print(f"没有新的A股交易日（最新 {latest_a_share_date}），跳过分析和提交")
        return False
    text, source, model = request_ai_analysis(summaries)
    analysis = {
        "market_date": latest_a_share_date,
        "generated_at": datetime.now(ZoneInfo("UTC")).isoformat(),
        "source": source,
        "model": model,
        "text": text,
        "disclaimer": "仅供数据研究与板块观察，不构成投资建议。",
    }
    export_data(frames, summaries, analysis)
    print(f"✅ 持仓板块监控已更新至 {latest_a_share_date}，分析来源：{source}")
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="持仓板块指数每日监控")
    parser.add_argument("--force", action="store_true", help="即使没有新交易日也重新生成")
    arguments = parser.parse_args()
    job(force=arguments.force)
