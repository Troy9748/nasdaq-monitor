import argparse
import io
import json
import math
import os
import smtplib
import subprocess
import urllib.error
import urllib.request
import zipfile
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
FRED_CONTEXT_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=VXNCLS,DGS10"
NASDAQ_COMPONENTS_URL = "https://api.nasdaq.com/api/quote/list-type/nasdaq100"
CSV_PATH = Path("nasdaq100_daily_data.csv")
CONTEXT_CSV_PATH = Path("market_context_daily.csv")
WEB_DATA_DIR = Path("web/public/data")
WEB_JSON_PATH = WEB_DATA_DIR / "nasdaq100.json"
WEB_ANALYSIS_PATH = WEB_DATA_DIR / "analysis.json"
WEB_ANALYSIS_HISTORY_PATH = WEB_DATA_DIR / "analysis_history.json"
WEB_CONTEXT_PATH = WEB_DATA_DIR / "context.json"
WEB_HEALTH_PATH = WEB_DATA_DIR / "health.json"
EMAIL_STATE_PATH = WEB_DATA_DIR / "email_state.json"
WEB_CSV_PATH = WEB_DATA_DIR / CSV_PATH.name
NEW_YORK = ZoneInfo("America/New_York")


def fetch_bytes(url: str, timeout: int = 45) -> bytes:
    try:
        return subprocess.run(
            ["curl", "-sS", "--fail", "--max-time", str(timeout), url],
            check=True,
            capture_output=True,
            timeout=timeout + 5,
        ).stdout
    except (OSError, subprocess.SubprocessError) as error:
        raise RuntimeError(f"网络下载失败: {error}") from error


def download_fred_history() -> pd.DataFrame:
    content = fetch_bytes(FRED_URL)
    data = pd.read_csv(
        io.BytesIO(content),
        parse_dates=["observation_date"],
        na_values=".",
    )
    if data.empty or "NASDAQ100" not in data:
        raise RuntimeError("FRED NASDAQ-100 行情下载为空或缺少 NASDAQ100 列")
    result = (
        data.rename(columns={"observation_date": "Date", "NASDAQ100": "Close"})
        .set_index("Date")[["Close"]]
        .dropna()
        .sort_index()
    )
    result["Source"] = "FRED"
    result["Is_Provisional"] = False
    return result


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
    base = fred.copy()
    if "Source" not in base:
        base["Source"] = "FRED"
    if "Is_Provisional" not in base:
        base["Is_Provisional"] = False
    for date, row in recent.iterrows():
        if date not in base.index or bool(base.at[date, "Is_Provisional"]):
            base.loc[date, ["Close", "Source", "Is_Provisional"]] = [
                float(row["Close"]),
                "Yahoo",
                True,
            ]
    base["Is_Provisional"] = base["Is_Provisional"].astype(bool)
    return base.sort_index()


def build_calibration_audit(stored: pd.DataFrame, fred: pd.DataFrame) -> dict:
    flags = (
        stored["Is_Provisional"].astype(bool)
        if "Is_Provisional" in stored
        else pd.Series(False, index=stored.index)
    )
    provisional = stored[flags]
    matched = provisional.index.intersection(fred.index)
    if matched.empty:
        return {
            "checked_at": datetime.now(ZoneInfo("UTC")).isoformat(),
            "corrected_rows": 0,
            "pending_rows": int(len(provisional)),
            "max_abs_diff_pct": None,
            "max_diff_date": None,
        }
    differences = (
        (provisional.loc[matched, "Close"] / fred.loc[matched, "Close"] - 1).abs() * 100
    )
    max_date = differences.idxmax()
    return {
        "checked_at": datetime.now(ZoneInfo("UTC")).isoformat(),
        "corrected_rows": int(len(matched)),
        "pending_rows": int(len(provisional.index.difference(fred.index))),
        "max_abs_diff_pct": round(float(differences.loc[max_date]), 4),
        "max_diff_date": max_date.date().isoformat(),
    }


def load_stored_history(path: Path = CSV_PATH) -> pd.DataFrame:
    if not path.exists():
        raise RuntimeError("FRED 不可用且仓库中没有 NASDAQ-100 历史缓存")
    data = pd.read_csv(path, parse_dates=["Date"]).set_index("Date")
    result = data[["Close"]].copy()
    result["Source"] = data["Source"] if "Source" in data else "FRED"
    result["Is_Provisional"] = data["Is_Provisional"] if "Is_Provisional" in data else False
    result["Is_Provisional"] = result["Is_Provisional"].astype(bool)
    return result


def download_history(*, refresh_fred: bool = False) -> pd.DataFrame:
    stored = load_stored_history() if CSV_PATH.exists() else None
    audit = None
    if refresh_fred or not CSV_PATH.exists():
        try:
            fred = download_fred_history()
            if stored is not None:
                audit = build_calibration_audit(stored, fred)
            print("✅ FRED 权威历史校准完成")
        except Exception as error:
            print(f"⚠️ FRED 暂时不可用，使用仓库中的权威历史缓存: {error}")
            fred = load_stored_history()
    else:
        fred = stored
        print("使用仓库中的 FRED 历史基准；本次不执行全量校准")
    try:
        result = merge_recent_history(fred, download_recent_history())
    except Exception as error:
        # ponytail: Yahoo 是时效补充源；不可用时保留 FRED，旧日期检查会阻止重复日报。
        print(f"⚠️ Yahoo 最新行情不可用，仅使用 FRED: {error}")
        result = fred
    if audit:
        result.attrs["calibration_audit"] = audit
    return result


def download_fred_context() -> pd.DataFrame:
    content = fetch_bytes(FRED_CONTEXT_URL)
    frames = []
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        for name in archive.namelist():
            if not name.endswith(".csv"):
                continue
            frame = pd.read_csv(archive.open(name), parse_dates=["observation_date"], na_values=".")
            frames.append(frame.set_index("observation_date"))
    if not frames:
        raise RuntimeError("FRED VXN/10年期美债数据包中没有 CSV")
    data = pd.concat(frames, axis=1).sort_index()
    if not {"VXNCLS", "DGS10"}.issubset(data.columns):
        raise RuntimeError("FRED 市场环境数据缺少 VXNCLS 或 DGS10")
    return data.rename(columns={"VXNCLS": "VXN", "DGS10": "Treasury10Y"})[
        ["VXN", "Treasury10Y"]
    ]


def load_context_history() -> pd.DataFrame:
    if not CONTEXT_CSV_PATH.exists():
        return pd.DataFrame(columns=["VXN", "Treasury10Y"])
    return pd.read_csv(CONTEXT_CSV_PATH, parse_dates=["Date"]).set_index("Date")


def download_recent_context() -> dict:
    data = yf.download(
        ["^VXN", "^TNX", "^NDXA200R"],
        period="1mo",
        interval="1d",
        auto_adjust=False,
        progress=False,
        group_by="column",
        timeout=30,
    )
    if data.empty or "Close" not in data:
        raise RuntimeError("Yahoo VXN/10年期美债行情下载为空")
    close = data["Close"]
    result = {}
    for ticker, name in (("^VXN", "vxn"), ("^TNX", "treasury10y")):
        series = close[ticker].dropna()
        if not series.empty:
            result[name] = {
                "value": round(float(series.iloc[-1]), 2),
                "as_of": pd.Timestamp(series.index[-1]).date().isoformat(),
                "source": "Yahoo（临时）",
            }
    breadth = close["^NDXA200R"].dropna() if "^NDXA200R" in close else pd.Series(dtype=float)
    if not breadth.empty:
        result["breadth"] = {
            "above_ema200_pct": round(float(breadth.iloc[-1]), 2),
            "above_ema200_count": None,
            "sample_size": None,
            "as_of": pd.Timestamp(breadth.index[-1]).date().isoformat(),
            "source": "NDXA200R（Yahoo）",
        }
    return result


def latest_context_value(data: pd.DataFrame, column: str) -> dict | None:
    series = data[column].dropna() if column in data else pd.Series(dtype=float)
    if series.empty:
        return None
    return {
        "value": round(float(series.iloc[-1]), 2),
        "as_of": pd.Timestamp(series.index[-1]).date().isoformat(),
        "source": "FRED",
    }


def newest_context_value(current: dict | None, cached: dict | None) -> dict | None:
    if not current:
        return cached
    if not cached:
        return current
    return cached if cached.get("as_of", "") > current.get("as_of", "") else current


def download_components() -> list[str]:
    request = urllib.request.Request(
        NASDAQ_COMPONENTS_URL,
        headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json, text/plain, */*"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        result = json.load(response)
    rows = result["data"]["data"]["rows"]
    symbols = sorted({row["symbol"].replace("/", "-") for row in rows if row.get("symbol")})
    if len(symbols) < 90:
        raise RuntimeError(f"Nasdaq 官方成分名单仅返回 {len(symbols)} 个代码")
    return symbols


def calculate_breadth(symbols: list[str]) -> dict:
    data = yf.download(
        symbols,
        period="1y",
        interval="1d",
        auto_adjust=True,
        progress=False,
        group_by="column",
        threads=True,
        timeout=45,
    )
    if data.empty or "Close" not in data:
        raise RuntimeError("NASDAQ-100 成分股日线下载为空")
    close = data["Close"]
    observations = {period: [] for period in (20, 50, 200)}
    new_highs = 0
    new_lows = 0
    dates = []
    for symbol in close.columns:
        series = close[symbol].dropna()
        if len(series) < 200:
            continue
        latest = float(series.iloc[-1])
        for period in observations:
            observations[period].append(
                latest > float(series.ewm(span=period, adjust=False).mean().iloc[-1])
            )
        window = series.iloc[-20:]
        new_highs += latest >= float(window.max())
        new_lows += latest <= float(window.min())
        dates.append(pd.Timestamp(series.index[-1]))
    sample_size = len(observations[200])
    if sample_size < 80:
        raise RuntimeError(f"仅有 {sample_size} 个成分股具备 200 日数据")
    result = {
        "sample_size": sample_size,
        "new_high20_count": new_highs,
        "new_low20_count": new_lows,
        "as_of": max(dates).date().isoformat(),
        "source": "Nasdaq 成分名单 + Yahoo 日线",
    }
    for period, values in observations.items():
        above = sum(values)
        result[f"above_ema{period}_pct"] = round(above / sample_size * 100, 2)
        result[f"above_ema{period}_count"] = above
    return result


def load_previous_context() -> dict:
    if not WEB_CONTEXT_PATH.exists():
        return {}
    return json.loads(WEB_CONTEXT_PATH.read_text(encoding="utf-8"))


def build_market_context(*, refresh_fred: bool = False) -> tuple[pd.DataFrame, dict]:
    history = load_context_history()
    cached_history = history.copy()
    if refresh_fred or history.empty:
        try:
            history = download_fred_context()
            for column in cached_history.columns.difference(history.columns):
                history[column] = cached_history[column]
            print("✅ FRED VXN 与 10年期美债校准完成")
        except Exception as error:
            print(f"⚠️ FRED 市场环境数据不可用，使用缓存: {error}")
    previous = load_previous_context()
    context = {
        "vxn": newest_context_value(latest_context_value(history, "VXN"), previous.get("vxn")),
        "treasury10y": newest_context_value(
            latest_context_value(history, "Treasury10Y"), previous.get("treasury10y")
        ),
        "breadth": previous.get("breadth"),
        "calibration": previous.get("calibration"),
    }
    breadth_updated = False
    try:
        recent = download_recent_context()
        breadth_updated = "breadth" in recent
        context.update(recent)
    except Exception as error:
        print(f"⚠️ Yahoo 市场环境数据不可用，使用缓存: {error}")
    if not breadth_updated or not (context.get("breadth") or {}).get("above_ema50_pct"):
        try:
            context["breadth"] = calculate_breadth(download_components())
        except Exception as error:
            print(f"⚠️ NASDAQ-100 市场广度不可用，使用缓存: {error}")
    return history, context


def record_context_history(history: pd.DataFrame, context: dict) -> pd.DataFrame:
    result = history.copy()
    mappings = {
        "above_ema20_pct": "BreadthEMA20Pct",
        "above_ema50_pct": "BreadthEMA50Pct",
        "above_ema200_pct": "BreadthEMA200Pct",
        "new_high20_count": "NewHigh20Count",
        "new_low20_count": "NewLow20Count",
        "sample_size": "BreadthSampleSize",
    }
    breadth = context.get("breadth") or {}
    if breadth.get("as_of"):
        date = pd.Timestamp(breadth["as_of"])
        for source, column in mappings.items():
            if breadth.get(source) is not None:
                result.at[date, column] = breadth[source]
    return result.sort_index()


def annotate_context_freshness(context: dict, market_date) -> dict:
    result = context.copy()
    for key in ("vxn", "treasury10y", "breadth"):
        item = result.get(key)
        if not item or not item.get("as_of"):
            continue
        age = max(0, (market_date - pd.Timestamp(item["as_of"]).date()).days)
        item = item.copy()
        item["age_days"] = age
        item["freshness"] = "正常" if age <= 3 else "延迟" if age <= 5 else "过期"
        result[key] = item
    return result


def build_freshness(data: pd.DataFrame) -> dict:
    latest_date = data.index[-1].date()
    age_days = (datetime.now(NEW_YORK).date() - latest_date).days
    status = "正常" if age_days <= 3 else "延迟" if age_days <= 5 else "严重过期"
    return {
        "status": status,
        "age_days": age_days,
        "latest_market_date": latest_date.isoformat(),
        "checked_at": datetime.now(ZoneInfo("UTC")).isoformat(),
    }


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
    if (datetime.now(NEW_YORK).date() - data.index[-1].date()).days > 7:
        raise RuntimeError("NASDAQ-100 行情已超过 7 天未更新，请检查 Yahoo 与 FRED 数据源")


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


def regime_series(data: pd.DataFrame) -> pd.Series:
    regimes = pd.Series(
        [
            "未知"
            if pd.isna(row.EMA50) or pd.isna(row.EMA200)
            else "防御"
            if row.Close < row.EMA200
            else "多头"
            if row.EMA50 > row.EMA200
            else "修复"
            for row in data.itertuples()
        ],
        index=data.index,
        name="Regime",
    )
    # ponytail: EMA200 needs 200 sessions before regime statistics are treated as mature.
    regimes.iloc[:199] = "未知"
    return regimes


def build_regime_analysis(data: pd.DataFrame) -> dict:
    regimes = regime_series(data)
    close = data["Close"]
    horizons = {"20日": 20, "60日": 60, "120日": 120}
    baseline = {}
    for label, sessions in horizons.items():
        values = close.shift(-sessions) / close * 100 - 100
        baseline[label] = _forward_statistics(_non_overlapping(values, data.index, sessions))
    stats = {}
    for regime in ("多头", "修复", "防御"):
        mask = regimes == regime
        forward = {
            label: (close.shift(-sessions) / close - 1).where(mask) * 100
            for label, sessions in horizons.items()
        }
        stats[regime] = {
            "observations": int(mask.sum()),
            "forward": {},
        }
        for label, values in forward.items():
            independent = _non_overlapping(values, data.index, horizons[label])
            result = _forward_statistics(independent)
            result["overlapping_samples"] = int(values.count())
            result["excess_vs_baseline_pct"] = _round_optional(
                (result["median_return_pct"] or 0) - (baseline[label]["median_return_pct"] or 0)
            )
            stats[regime]["forward"][label] = result

    high_volatility = data["Volatility20_Pct"] >= data["Volatility20_Pct"].median()
    environment_stats = {}
    for label, mask in (("高波动", high_volatility), ("常规波动", ~high_volatility)):
        environment_stats[label] = {
            horizon: _forward_statistics(
                _non_overlapping(
                    ((close.shift(-sessions) / close - 1) * 100).where(mask),
                    data.index,
                    sessions,
                )
            )
            for horizon, sessions in horizons.items()
        }

    changes = regimes.ne(regimes.shift())
    events = [
        {"date": date.date().isoformat(), "state": state}
        for date, state in regimes[changes].iloc[-12:].items()
        if pd.notna(state) and state != "未知"
    ]
    return {
        "current": str(regimes.iloc[-1]),
        "stats": stats,
        "baseline": baseline,
        "environment_stats": environment_stats,
        "recent_events": events,
    }


def _non_overlapping(values: pd.Series, index: pd.Index, sessions: int) -> pd.Series:
    positions = {date: position for position, date in enumerate(index)}
    selected = []
    next_position = 0
    for date, value in values.dropna().items():
        position = positions[date]
        if position >= next_position:
            selected.append(value)
            next_position = position + sessions
    return pd.Series(selected, dtype=float)


def _forward_statistics(values: pd.Series) -> dict:
    clean = values.dropna().sort_values().reset_index(drop=True)
    samples = len(clean)
    if not samples:
        return {
            "samples": 0,
            "median_return_pct": None,
            "positive_rate_pct": None,
            "median_ci95_low_pct": None,
            "median_ci95_high_pct": None,
        }
    # ponytail: distribution-free median interval; switch to bootstrap only if tail modelling is needed.
    margin = 0.98 * math.sqrt(samples)
    low = max(0, math.floor(samples / 2 - margin))
    high = min(samples - 1, math.ceil(samples / 2 + margin))
    return {
        "samples": samples,
        "median_return_pct": _round_optional(float(clean.median())),
        "positive_rate_pct": _round_optional(float((clean > 0).mean() * 100)),
        "median_ci95_low_pct": _round_optional(float(clean.iloc[low])),
        "median_ci95_high_pct": _round_optional(float(clean.iloc[high])),
    }


def env_float(name: str, default: float, *, minimum: float = 0, maximum: float = 100) -> float:
    raw = os.getenv(name)
    try:
        value = default if not raw else float(raw)
    except ValueError as error:
        raise ValueError(f"{name} 必须是数字") from error
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} 必须在 {minimum} 到 {maximum} 之间")
    return value


def build_alert(snapshot: dict) -> dict:
    thresholds = {
        "vxn": env_float("ALERT_VXN_LEVEL", 30),
        "breadth": env_float("ALERT_BREADTH_LEVEL", 40),
        "volatility": env_float("ALERT_VOLATILITY_LEVEL", 35),
        "ema_distance": env_float("ALERT_EMA_DISTANCE", 1, maximum=20),
    }
    reasons = []
    level = "日常"
    if snapshot["freshness"]["status"] == "严重过期":
        return {"level": "故障", "code": "critical", "reasons": ["指数行情严重过期"], "thresholds": thresholds}
    if snapshot["status"] in {"转强", "转弱"}:
        level = "重要"
        reasons.append(snapshot["status_detail"])
    context = snapshot.get("context", {})
    vxn = (context.get("vxn") or {}).get("value")
    breadth = (context.get("breadth") or {}).get("above_ema200_pct")
    if vxn is not None and vxn >= thresholds["vxn"]:
        reasons.append(f"VXN 升至 {vxn:.2f}")
    if breadth is not None and breadth < thresholds["breadth"]:
        reasons.append(f"市场广度降至 {breadth:.2f}%")
    if snapshot["volatility20_pct"] is not None and snapshot["volatility20_pct"] >= thresholds["volatility"]:
        reasons.append(f"20日年化波动率升至 {snapshot['volatility20_pct']:.2f}%")
    if abs(snapshot.get("distance_ema200_pct", 100)) <= thresholds["ema_distance"]:
        reasons.append(f"距 EMA200 仅 {snapshot['distance_ema200_pct']:+.2f}%")
    if reasons and level == "日常":
        level = "注意"
    return {
        "level": level,
        "code": {"日常": "normal", "注意": "watch", "重要": "important"}[level],
        "reasons": reasons or ["未触发趋势切换或高风险阈值"],
        "thresholds": thresholds,
    }


def build_snapshot(data: pd.DataFrame, context: dict, freshness: dict) -> dict:
    latest = data.iloc[-1]
    previous = data.iloc[-2]
    close = data["Close"]
    market_date = data.index[-1].date()
    year_start = close[close.index.year < market_date.year]
    ytd_base = float(year_start.iloc[-1]) if not year_start.empty else float(close.iloc[0])
    years = max((data.index[-1] - data.index[0]).days / 365.25, 1)
    status, status_detail = classify_signal(latest, previous)

    snapshot = {
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
        "context": context,
        "freshness": freshness,
        "provenance": {
            "latest_source": str(latest["Source"]),
            "latest_is_provisional": bool(latest["Is_Provisional"]),
            "authoritative_through": data.loc[~data["Is_Provisional"].astype(bool)].index[-1].date().isoformat(),
            "provisional_rows": int(data["Is_Provisional"].astype(bool).sum()),
        },
    }
    snapshot["alert"] = build_alert(snapshot)
    return snapshot


def _round_optional(value: float | None) -> float | None:
    return None if value is None or not math.isfinite(value) else round(value, 2)


def deterministic_analysis(snapshot: dict) -> str:
    context = snapshot.get("context", {})
    breadth = context.get("breadth") or {}
    vxn = context.get("vxn") or {}
    treasury = context.get("treasury10y") or {}
    return "\n".join(
        [
            f"市场状态：{snapshot['status']}。{snapshot['status_detail']}，当前距 EMA200 {snapshot['distance_ema200_pct']:+.2f}%。",
            f"动量观察：RSI14 为 {snapshot['rsi14']:.2f}，近 20 日年化波动率为 {snapshot['volatility20_pct']:.2f}%。",
            f"风险位置：指数距 52 周高点 {snapshot['distance_high252_pct']:+.2f}%，当前历史高点回撤 {snapshot['drawdown_pct']:.2f}%。",
            f"环境观察：VXN {vxn.get('value', '—')}，10年期美债 {treasury.get('value', '—')}%，成分股位于 EMA200 上方比例 {breadth.get('above_ema200_pct', '—')}%。",
            "条件框架：若价格维持 EMA200 上方且市场广度改善，趋势确认度提高；若跌破 EMA200 并伴随 VXN 上升，则应优先控制风险。仅作数据观察，不构成投资建议。",
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
                    "区分事实与推断，只提供条件化风险管理框架，不给出绝对买入、卖出、重仓或清仓指令。"
                    "明确指出数据来源与临时数据的局限，结尾注明不构成投资建议。"
                ),
            },
            {"role": "user", "content": json.dumps(snapshot, ensure_ascii=False)},
        ],
        "max_tokens": 2000,
        "stream": False,
    }
    if provider == "DeepSeek":
        payload["thinking"] = {"type": "enabled"}
        payload["reasoning_effort"] = "high"
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
        with urllib.request.urlopen(request, timeout=120) as response:
            result = json.load(response)
        text = result["choices"][0]["message"]["content"].strip()
        if not text:
            raise RuntimeError(f"{provider} 响应中没有文本内容")
        return text, provider, model
    except (OSError, urllib.error.HTTPError, ValueError, KeyError, RuntimeError) as error:
        print(f"⚠️ AI 分析不可用，改用规则分析: {error}")
        return deterministic_analysis(snapshot), "规则分析（AI 回退）", model


def export_data(
    data: pd.DataFrame,
    snapshot: dict,
    analysis: dict,
    context_history: pd.DataFrame,
    context: dict,
    regime_analysis: dict,
) -> None:
    WEB_DATA_DIR.mkdir(parents=True, exist_ok=True)
    export = data.copy()
    export.index.name = "Date"
    export.to_csv(CSV_PATH, encoding="utf-8-sig", float_format="%.4f")
    export.to_csv(WEB_CSV_PATH, encoding="utf-8-sig", float_format="%.4f")
    if not context_history.empty:
        context_history.index.name = "Date"
        context_history.to_csv(CONTEXT_CSV_PATH, encoding="utf-8-sig", float_format="%.4f")

    columns = [
        "Close",
        "EMA50",
        "EMA200",
        "RSI14",
        "Volatility20_Pct",
        "Drawdown_Pct",
        "Source",
        "Is_Provisional",
    ]
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
                "source": str(row["Source"]),
                "is_provisional": bool(row["Is_Provisional"]),
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
                "regime_analysis": regime_analysis,
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
    history = []
    if WEB_ANALYSIS_HISTORY_PATH.exists():
        history = json.loads(WEB_ANALYSIS_HISTORY_PATH.read_text(encoding="utf-8"))
    history = [item for item in history if item.get("market_date") != analysis["market_date"]]
    history.append(analysis)
    WEB_ANALYSIS_HISTORY_PATH.write_text(
        json.dumps(sorted(history, key=lambda item: item["market_date"]), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    aligned = context_history.reindex(data.index).ffill(limit=5) if not context_history.empty else pd.DataFrame(index=data.index)
    for key, column in (("vxn", "VXN"), ("treasury10y", "Treasury10Y")):
        item = context.get(key) or {}
        date = pd.Timestamp(item["as_of"]) if item.get("as_of") else None
        if date is not None and date in aligned.index:
            aligned.at[date, column] = item["value"]
    ndx_returns = data["Close"].pct_change()
    vxn_changes = aligned.get("VXN", pd.Series(index=data.index, dtype=float)).pct_change()
    correlation = ndx_returns.rolling(60).corr(vxn_changes)
    breadth_change20 = aligned.get(
        "BreadthEMA200Pct", pd.Series(index=data.index, dtype=float)
    ).diff(20)
    ndx_return20 = data["Close"].pct_change(20) * 100
    context_series = [
        {
            "date": date.date().isoformat(),
            "vxn": _json_number(aligned.at[date, "VXN"]) if "VXN" in aligned else None,
            "treasury10y": _json_number(aligned.at[date, "Treasury10Y"]) if "Treasury10Y" in aligned else None,
            "ndx_vxn_corr60": _json_number(correlation.loc[date]),
            "breadth_ema20_pct": _json_number(aligned.at[date, "BreadthEMA20Pct"]) if "BreadthEMA20Pct" in aligned else None,
            "breadth_ema50_pct": _json_number(aligned.at[date, "BreadthEMA50Pct"]) if "BreadthEMA50Pct" in aligned else None,
            "breadth_ema200_pct": _json_number(aligned.at[date, "BreadthEMA200Pct"]) if "BreadthEMA200Pct" in aligned else None,
            "breadth_divergence": bool(ndx_return20.loc[date] > 0 and breadth_change20.loc[date] < 0)
            if pd.notna(ndx_return20.loc[date]) and pd.notna(breadth_change20.loc[date])
            else None,
        }
        for date in data.index
    ]
    WEB_CONTEXT_PATH.write_text(
        json.dumps({**context, "series": context_series}, ensure_ascii=False, separators=(",", ":"), allow_nan=False),
        encoding="utf-8",
    )


def write_health(**updates) -> dict:
    health = {}
    if WEB_HEALTH_PATH.exists():
        health = json.loads(WEB_HEALTH_PATH.read_text(encoding="utf-8"))
    health.update(updates)
    health["checked_at"] = datetime.now(ZoneInfo("UTC")).isoformat()
    WEB_DATA_DIR.mkdir(parents=True, exist_ok=True)
    WEB_HEALTH_PATH.write_text(
        json.dumps(health, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8"
    )
    return health


def last_scheduled_email_date() -> str | None:
    if not EMAIL_STATE_PATH.exists():
        return None
    return json.loads(EMAIL_STATE_PATH.read_text(encoding="utf-8")).get("last_sent_market_date")


def record_scheduled_email(market_date: str) -> None:
    EMAIL_STATE_PATH.write_text(
        json.dumps(
            {
                "last_sent_market_date": market_date,
                "sent_at": datetime.now(ZoneInfo("UTC")).isoformat(),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def _json_number(value) -> float | None:
    number = float(value)
    return round(number, 4) if math.isfinite(number) else None


def send_email(snapshot: dict, analysis: dict) -> None:
    sender = os.environ["MAIL_USERNAME"]
    password = os.environ["MAIL_PASSWORD"]
    receiver = os.environ["MAIL_RECEIVER"]
    subject = (
        f"[{snapshot['alert']['level']} · NDX {snapshot['daily_return_pct']:+.2f}%] NASDAQ-100 日报 "
        f"{snapshot['market_date']} · {snapshot['status']}"
    )
    context = snapshot.get("context", {})
    vxn = (context.get("vxn") or {}).get("value", "—")
    treasury = (context.get("treasury10y") or {}).get("value", "—")
    breadth = (context.get("breadth") or {}).get("above_ema200_pct", "—")
    dashboard_url = os.getenv("DASHBOARD_URL")
    content = "\n".join(
        [
            "【NASDAQ-100 每日市场扫描】",
            "",
            f"日期：{snapshot['market_date']}",
            f"收盘：{snapshot['close']:.2f}（{snapshot['daily_return_pct']:+.2f}%）",
            f"状态：{snapshot['status']} · {snapshot['status_detail']}",
            f"提醒：{snapshot['alert']['level']} · {'；'.join(snapshot['alert']['reasons'])}",
            f"EMA50 / EMA200：{snapshot['ema50']:.2f} / {snapshot['ema200']:.2f}",
            f"RSI14 / 20日年化波动率：{snapshot['rsi14']:.2f} / {snapshot['volatility20_pct']:.2f}%",
            f"距52周高点 / 当前回撤：{snapshot['distance_high252_pct']:+.2f}% / {snapshot['drawdown_pct']:.2f}%",
            f"VXN / 10年期美债：{vxn} / {treasury}%",
            f"成分股站上 EMA200：{breadth}%",
            f"数据来源：{snapshot['provenance']['latest_source']}"
            + ("（临时，待 FRED 校准）" if snapshot['provenance']['latest_is_provisional'] else "（权威）"),
            "",
            f"【{analysis['source']}】",
            analysis["text"],
            "",
            *( [f"网页仪表盘：{dashboard_url}", ""] if dashboard_url else [] ),
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


def job(
    *,
    send_mail: bool = True,
    force: bool = False,
    refresh_fred: bool = False,
    scheduled_email: bool = False,
) -> bool:
    old_date = previous_market_date()
    print(f"正在更新 {MARKET_NAME} ({TICKER})：历史基准 + Yahoo 最新交易日...")
    data = calculate_indicators(download_history(refresh_fred=refresh_fred))
    validate_history(data)
    freshness = build_freshness(data)
    latest_date = data.index[-1].date()
    has_new_market_day = old_date is None or latest_date > old_date
    if scheduled_email and last_scheduled_email_date() == latest_date.isoformat():
        write_health(
            data={"status": "正常", "market_date": latest_date.isoformat()},
            email={"status": "已发送", "market_date": latest_date.isoformat()},
        )
        print(f"{latest_date} 的定时日报已经发送，跳过重复邮件")
        return False
    if not force and not scheduled_email and not has_new_market_day:
        print(
            f"没有新的交易日数据（最新 {latest_date}，新鲜度：{freshness['status']}），跳过日报和提交"
        )
        return False

    context_history, context = build_market_context(refresh_fred=refresh_fred)
    context = annotate_context_freshness(context, latest_date)
    context_history = record_context_history(context_history, context)
    if data.attrs.get("calibration_audit"):
        context["calibration"] = data.attrs["calibration_audit"]
    snapshot = build_snapshot(data, context, freshness)
    regime_analysis = build_regime_analysis(data)
    context["freshness"] = freshness
    context["provenance"] = snapshot["provenance"]
    previous_analysis = (
        json.loads(WEB_ANALYSIS_PATH.read_text(encoding="utf-8"))
        if WEB_ANALYSIS_PATH.exists()
        else {}
    )
    reused_analysis = (
        not os.getenv("OPENAI_API_KEY")
        and previous_analysis.get("market_date") == snapshot["market_date"]
        and previous_analysis.get("source") not in {"规则分析", "规则分析（AI 回退）"}
    )
    if reused_analysis:
        text = previous_analysis["text"]
        source = previous_analysis["source"]
        model = previous_analysis.get("model")
    else:
        text, source, model = request_ai_analysis(snapshot)
    analysis = {
        "market_date": snapshot["market_date"],
        "generated_at": previous_analysis["generated_at"]
        if reused_analysis
        else datetime.now(ZoneInfo("UTC")).isoformat(),
        "source": source,
        "model": model,
        "text": text,
        "disclaimer": "仅供数据研究与市场观察，不构成投资建议。",
    }
    print(f"✅ 分析来源: {source}" + (f" ({model})" if model else ""))
    export_data(data, snapshot, analysis, context_history, context, regime_analysis)
    write_health(
        data={"status": freshness["status"], "market_date": snapshot["market_date"]},
        ai={"status": "正常" if source not in {"规则分析", "规则分析（AI 回退）"} else "回退", "source": source, "model": model},
        calibration=context.get("calibration"),
        email={"status": "待发送" if send_mail else "本次禁用", "market_date": snapshot["market_date"]},
    )
    print(f"✅ 已更新至 {latest_date}，共 {len(data)} 个交易日")
    if send_mail:
        try:
            send_email(snapshot, analysis)
            if scheduled_email:
                record_scheduled_email(snapshot["market_date"])
            write_health(email={"status": "已发送", "market_date": snapshot["market_date"]})
        except Exception as error:
            write_health(email={"status": "失败", "market_date": snapshot["market_date"], "error_type": type(error).__name__})
            raise
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NASDAQ-100 每日监控")
    parser.add_argument("--no-email", action="store_true", help="生成数据但不发送邮件")
    parser.add_argument("--force", action="store_true", help="即使没有新交易日也重新生成")
    parser.add_argument("--refresh-fred", action="store_true", help="执行每周 FRED 权威历史校准")
    parser.add_argument("--scheduled-email", action="store_true", help="定时日报：每个行情日期最多发送一次")
    arguments = parser.parse_args()
    job(
        send_mail=not arguments.no_email,
        force=arguments.force,
        refresh_fred=arguments.refresh_fred,
        scheduled_email=arguments.scheduled_email,
    )
