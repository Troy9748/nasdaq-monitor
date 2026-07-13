import argparse
import io
import json
import math
import os
import smtplib
import urllib.error
import urllib.request
from datetime import datetime
from email.message import EmailMessage
from email.utils import formataddr
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf


TICKER = "^NDX"
MARKET_NAME = "NASDAQ-100"
START_DATE = "1990-01-01"
FRED_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=NASDAQ100&cosd=1990-01-01"
CSV_PATH = Path("nasdaq100_daily_data.csv")
WEB_DATA_DIR = Path("web/public/data")
WEB_JSON_PATH = WEB_DATA_DIR / "nasdaq100.json"
WEB_ANALYSIS_PATH = WEB_DATA_DIR / "analysis.json"
WEB_CSV_PATH = WEB_DATA_DIR / CSV_PATH.name
NEW_YORK = ZoneInfo("America/New_York")


def download_fred_history() -> pd.DataFrame:
    request = urllib.request.Request(FRED_URL, headers={"User-Agent": "nasdaq100-monitor/1.0"})
    with urllib.request.urlopen(request, timeout=45) as response:
        content = response.read()
    data = pd.read_csv(
        io.BytesIO(content),
        parse_dates=["observation_date"],
        na_values=".",
    )
    if data.empty or "NASDAQ100" not in data:
        raise RuntimeError("FRED NASDAQ-100 行情下载为空或缺少 NASDAQ100 列")
    return (
        data.rename(columns={"observation_date": "Date", "NASDAQ100": "Close"})
        .set_index("Date")[["Close"]]
        .dropna()
        .sort_index()
    )


def download_recent_history() -> pd.DataFrame:
    data = yf.download(
        TICKER,
        period="1mo",
        interval="1d",
        auto_adjust=False,
        progress=False,
        multi_level_index=False,
        timeout=30,
    )
    if data.empty or "Close" not in data:
        raise RuntimeError("Yahoo Finance 最新 NASDAQ-100 行情下载为空或缺少 Close 列")
    recent = data[["Close"]].dropna()
    recent.index = pd.to_datetime(recent.index).tz_localize(None).normalize()
    recent.index.name = "Date"
    return recent


def merge_recent_history(fred: pd.DataFrame, recent: pd.DataFrame) -> pd.DataFrame:
    # FRED 保留为权威历史基准；Yahoo 只补 FRED 尚未发布的交易日。
    additions = recent.loc[recent.index > fred.index[-1], ["Close"]]
    return pd.concat([fred, additions]).sort_index()


def load_stored_history(path: Path = CSV_PATH) -> pd.DataFrame:
    if not path.exists():
        raise RuntimeError("FRED 不可用且仓库中没有 NASDAQ-100 历史缓存")
    return pd.read_csv(path, usecols=["Date", "Close"], parse_dates=["Date"]).set_index("Date")


def download_history() -> pd.DataFrame:
    try:
        fred = download_fred_history()
    except Exception as error:
        print(f"⚠️ FRED 暂时不可用，使用仓库中的权威历史缓存: {error}")
        fred = load_stored_history()
    try:
        return merge_recent_history(fred, download_recent_history())
    except Exception as error:
        # ponytail: Yahoo 是时效补充源；不可用时保留 FRED，旧日期检查会阻止重复日报。
        print(f"⚠️ Yahoo 最新行情不可用，仅使用 FRED: {error}")
        return fred


def calculate_indicators(prices: pd.DataFrame) -> pd.DataFrame:
    data = prices.copy()
    close = data["Close"]
    daily_return = close.pct_change()
    delta = close.diff()
    gains = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    losses = -delta.clip(upper=0).ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    relative_strength = gains / losses.replace(0, float("nan"))

    data["Daily_Return_Pct"] = daily_return * 100
    data["EMA20"] = close.ewm(span=20, adjust=False).mean()
    data["EMA50"] = close.ewm(span=50, adjust=False).mean()
    data["EMA200"] = close.ewm(span=200, adjust=False).mean()
    data["SMA200"] = close.rolling(200).mean()
    data["RSI14"] = 100 - (100 / (1 + relative_strength))
    data["Volatility20_Pct"] = daily_return.rolling(20).std() * math.sqrt(252) * 100
    data["High252"] = close.rolling(252).max()
    data["Distance_EMA200_Pct"] = (close / data["EMA200"] - 1) * 100
    data["Distance_High252_Pct"] = (close / data["High252"] - 1) * 100
    data["Drawdown_Pct"] = (close / close.cummax() - 1) * 100
    return data.round(4)


def validate_history(data: pd.DataFrame) -> None:
    if len(data) < 200:
        raise RuntimeError(f"NASDAQ-100 数据不足 200 行，仅有 {len(data)} 行")
    if not data.index.is_monotonic_increasing or data.index.has_duplicates:
        raise RuntimeError("NASDAQ-100 日期索引无序或存在重复")
    if not math.isfinite(float(data.iloc[-1]["Close"])) or float(data.iloc[-1]["Close"]) <= 0:
        raise RuntimeError("NASDAQ-100 最新收盘价无效")
    if data.index[-1].date() > datetime.now(NEW_YORK).date():
        raise RuntimeError("NASDAQ-100 最新行情日期晚于纽约当前日期")


def previous_market_date(path: Path = CSV_PATH):
    if not path.exists():
        return None
    dates = pd.read_csv(path, usecols=["Date"], parse_dates=["Date"])["Date"]
    return dates.max().date() if not dates.empty else None


def period_return(close: pd.Series, sessions: int) -> float | None:
    if len(close) <= sessions:
        return None
    return (float(close.iloc[-1]) / float(close.iloc[-sessions - 1]) - 1) * 100


def classify_signal(current: pd.Series, previous: pd.Series) -> tuple[str, str]:
    if previous["Close"] <= previous["EMA200"] and current["Close"] > current["EMA200"]:
        return "转强", "收盘价上穿 EMA200"
    if previous["Close"] >= previous["EMA200"] and current["Close"] < current["EMA200"]:
        return "转弱", "收盘价跌破 EMA200"
    if current["Close"] > current["EMA200"] and current["EMA50"] > current["EMA200"]:
        return "多头趋势", "收盘价与 EMA50 均位于 EMA200 上方"
    if current["Close"] > current["EMA200"]:
        return "修复阶段", "收盘价位于 EMA200 上方，但 EMA50 尚未确认"
    return "防御阶段", "收盘价位于 EMA200 下方"


def build_snapshot(data: pd.DataFrame) -> dict:
    latest = data.iloc[-1]
    previous = data.iloc[-2]
    close = data["Close"]
    market_date = data.index[-1].date()
    year_start = close[close.index.year < market_date.year]
    ytd_base = float(year_start.iloc[-1]) if not year_start.empty else float(close.iloc[0])
    years = max((data.index[-1] - data.index[0]).days / 365.25, 1)
    status, status_detail = classify_signal(latest, previous)

    return {
        "market_date": market_date.isoformat(),
        "close": round(float(latest["Close"]), 2),
        "daily_return_pct": round(float(latest["Daily_Return_Pct"]), 2),
        "returns": {
            "one_month": _round_optional(period_return(close, 21)),
            "three_months": _round_optional(period_return(close, 63)),
            "ytd": round((float(close.iloc[-1]) / ytd_base - 1) * 100, 2),
            "one_year": _round_optional(period_return(close, 252)),
            "since_1990_cagr": round(((float(close.iloc[-1]) / float(close.iloc[0])) ** (1 / years) - 1) * 100, 2),
        },
        "ema50": round(float(latest["EMA50"]), 2),
        "ema200": round(float(latest["EMA200"]), 2),
        "distance_ema200_pct": round(float(latest["Distance_EMA200_Pct"]), 2),
        "distance_high252_pct": _round_optional(float(latest["Distance_High252_Pct"])),
        "rsi14": _round_optional(float(latest["RSI14"])),
        "volatility20_pct": _round_optional(float(latest["Volatility20_Pct"])),
        "drawdown_pct": round(float(latest["Drawdown_Pct"]), 2),
        "max_drawdown_pct": round(float(data["Drawdown_Pct"].min()), 2),
        "status": status,
        "status_detail": status_detail,
    }


def _round_optional(value: float | None) -> float | None:
    return None if value is None or not math.isfinite(value) else round(value, 2)


def deterministic_analysis(snapshot: dict) -> str:
    return "\n".join(
        [
            f"市场状态：{snapshot['status']}。{snapshot['status_detail']}，当前距 EMA200 {snapshot['distance_ema200_pct']:+.2f}%。",
            f"动量观察：RSI14 为 {snapshot['rsi14']:.2f}，近 20 日年化波动率为 {snapshot['volatility20_pct']:.2f}%。",
            f"风险位置：指数距 52 周高点 {snapshot['distance_high252_pct']:+.2f}%，当前历史高点回撤 {snapshot['drawdown_pct']:.2f}%。",
            "观察建议：下一交易日重点确认价格与 EMA50、EMA200 的相对位置，以及波动率是否继续扩张。仅作数据观察，不构成投资建议。",
        ]
    )


def build_ai_request(snapshot: dict) -> tuple[str, dict, str, str]:
    base_url = (os.getenv("OPENAI_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
    model = os.getenv("OPENAI_MODEL") or "gpt-5.4-mini"
    provider = "DeepSeek" if "api.deepseek.com" in base_url else "OpenAI"
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "你是一名审慎的市场数据分析员。只能使用用户提供的 NASDAQ-100 指标，不得虚构新闻、宏观事件或实时信息。"
                    "用中文输出四个短段落：市场状态、动量与趋势、主要风险、下一交易日观察点。"
                    "区分事实与推断，不给出买入、卖出、重仓或清仓指令，结尾注明不构成投资建议。"
                ),
            },
            {"role": "user", "content": json.dumps(snapshot, ensure_ascii=False)},
        ],
        "max_tokens": 700,
        "stream": False,
    }
    if provider == "DeepSeek":
        payload["thinking"] = {"type": "disabled"}
    return f"{base_url}/chat/completions", payload, model, provider


def request_ai_analysis(snapshot: dict) -> tuple[str, str, str | None]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return deterministic_analysis(snapshot), "规则分析", None

    url, payload, model, provider = build_ai_request(snapshot)
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            result = json.load(response)
        text = result["choices"][0]["message"]["content"].strip()
        if not text:
            raise RuntimeError(f"{provider} 响应中没有文本内容")
        return text, provider, model
    except (OSError, urllib.error.HTTPError, ValueError, KeyError, RuntimeError) as error:
        print(f"⚠️ AI 分析不可用，改用规则分析: {error}")
        return deterministic_analysis(snapshot), "规则分析（AI 回退）", model


def export_data(data: pd.DataFrame, snapshot: dict, analysis: dict) -> None:
    WEB_DATA_DIR.mkdir(parents=True, exist_ok=True)
    export = data.copy()
    export.index.name = "Date"
    export.to_csv(CSV_PATH, encoding="utf-8-sig", float_format="%.4f")
    export.to_csv(WEB_CSV_PATH, encoding="utf-8-sig", float_format="%.4f")

    columns = ["Close", "EMA50", "EMA200", "RSI14", "Volatility20_Pct", "Drawdown_Pct"]
    records = []
    for date, row in data[columns].iterrows():
        records.append(
            {
                "date": date.date().isoformat(),
                "close": _json_number(row["Close"]),
                "ema50": _json_number(row["EMA50"]),
                "ema200": _json_number(row["EMA200"]),
                "rsi14": _json_number(row["RSI14"]),
                "volatility20_pct": _json_number(row["Volatility20_Pct"]),
                "drawdown_pct": _json_number(row["Drawdown_Pct"]),
            }
        )
    WEB_JSON_PATH.write_text(
        json.dumps(
            {
                "symbol": TICKER,
                "name": MARKET_NAME,
                "start_date": data.index[0].date().isoformat(),
                "latest_date": data.index[-1].date().isoformat(),
                "summary": snapshot,
                "series": records,
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


def _json_number(value) -> float | None:
    number = float(value)
    return round(number, 4) if math.isfinite(number) else None


def send_email(snapshot: dict, analysis: dict) -> None:
    sender = os.environ["MAIL_USERNAME"]
    password = os.environ["MAIL_PASSWORD"]
    receiver = os.environ["MAIL_RECEIVER"]
    subject = (
        f"[NDX {snapshot['daily_return_pct']:+.2f}%] NASDAQ-100 日报 "
        f"{snapshot['market_date']} · {snapshot['status']}"
    )
    content = "\n".join(
        [
            "【NASDAQ-100 每日市场扫描】",
            "",
            f"日期：{snapshot['market_date']}",
            f"收盘：{snapshot['close']:.2f}（{snapshot['daily_return_pct']:+.2f}%）",
            f"状态：{snapshot['status']} · {snapshot['status_detail']}",
            f"EMA50 / EMA200：{snapshot['ema50']:.2f} / {snapshot['ema200']:.2f}",
            f"RSI14 / 20日年化波动率：{snapshot['rsi14']:.2f} / {snapshot['volatility20_pct']:.2f}%",
            f"距52周高点 / 当前回撤：{snapshot['distance_high252_pct']:+.2f}% / {snapshot['drawdown_pct']:.2f}%",
            "",
            f"【{analysis['source']}】",
            analysis["text"],
            "",
            "详细历史数据见附件。",
        ]
    )

    message = EmailMessage()
    message["From"] = formataddr(("NASDAQ-100 市场监控", sender))
    message["To"] = receiver
    message["Subject"] = subject
    message.set_content(content)
    message.add_attachment(
        CSV_PATH.read_bytes(),
        maintype="text",
        subtype="csv",
        filename=CSV_PATH.name,
    )
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as server:
        server.login(sender, password)
        server.send_message(message)
    print(f"✅ 邮件已发送至 {receiver}")


def job(*, send_mail: bool = True, force: bool = False) -> bool:
    old_date = previous_market_date()
    print(f"正在下载 {MARKET_NAME} ({TICKER})：FRED 历史 + Yahoo 最新交易日...")
    data = calculate_indicators(download_history())
    validate_history(data)
    latest_date = data.index[-1].date()
    if not force and old_date is not None and latest_date <= old_date:
        print(f"没有新的交易日数据（最新 {latest_date}），跳过日报和提交")
        return False

    snapshot = build_snapshot(data)
    text, source, model = request_ai_analysis(snapshot)
    analysis = {
        "market_date": snapshot["market_date"],
        "generated_at": datetime.now(ZoneInfo("UTC")).isoformat(),
        "source": source,
        "model": model,
        "text": text,
        "disclaimer": "仅供数据研究与市场观察，不构成投资建议。",
    }
    export_data(data, snapshot, analysis)
    print(f"✅ 已更新至 {latest_date}，共 {len(data)} 个交易日")
    if send_mail:
        send_email(snapshot, analysis)
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NASDAQ-100 每日监控")
    parser.add_argument("--no-email", action="store_true", help="生成数据但不发送邮件")
    parser.add_argument("--force", action="store_true", help="即使没有新交易日也重新生成")
    arguments = parser.parse_args()
    job(send_mail=not arguments.no_email, force=arguments.force)
