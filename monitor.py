import argparse
import hashlib
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

import numpy as np
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
BENCHMARK_CSV_PATH = Path("market_benchmarks_daily.csv")
WEB_DATA_DIR = Path("web/public/data")
WEB_JSON_PATH = WEB_DATA_DIR / "nasdaq100.json"
WEB_ANALYSIS_PATH = WEB_DATA_DIR / "analysis.json"
WEB_ANALYSIS_HISTORY_PATH = WEB_DATA_DIR / "analysis_history.json"
WEB_CONTEXT_PATH = WEB_DATA_DIR / "context.json"
WEB_HEALTH_PATH = WEB_DATA_DIR / "health.json"
EMAIL_STATE_PATH = WEB_DATA_DIR / "email_state.json"
WEB_CSV_PATH = WEB_DATA_DIR / CSV_PATH.name
NEW_YORK = ZoneInfo("America/New_York")
TREND_MODEL_VERSION = "2026-08-14.2"
METHODOLOGY_VERSION = "2026-08-17.1"
BENCHMARK_TICKERS = {
    "^GSPC": "SP500",
    "^NDXE": "NDXEqualWeight",
    "^RUT": "Russell2000",
    "QQQ": "QQQ",
    "^IRX": "Treasury3M",
}
CONTEXT_COLUMNS = [
    "VXN", "Treasury10Y", "BreadthEMA200Pct", "BreadthEMA20Pct", "BreadthEMA50Pct",
    "BreadthSampleSize", "NewHigh20Count", "NewLow20Count",
]
BENCHMARK_COLUMNS = list(BENCHMARK_TICKERS.values())


def fetch_bytes(url: str, timeout: int = 45) -> bytes:
    try:
        return subprocess.run(
            ["curl", "--http1.1", "-sS", "--fail", "--max-time", str(timeout), "-H", "User-Agent: Mozilla/5.0", url],
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
    history = (
        pd.read_csv(CONTEXT_CSV_PATH, parse_dates=["Date"]).set_index("Date")
        if CONTEXT_CSV_PATH.exists()
        else pd.DataFrame(columns=["VXN", "Treasury10Y"])
    )
    if BENCHMARK_CSV_PATH.exists():
        benchmark = pd.read_csv(BENCHMARK_CSV_PATH, parse_dates=["Date"]).set_index("Date")
        history = history.combine_first(benchmark)
    return history


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


def download_component_rows() -> list[dict]:
    request = urllib.request.Request(
        NASDAQ_COMPONENTS_URL,
        headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json, text/plain, */*"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        result = json.load(response)
    rows = result["data"]["data"]["rows"]
    symbols = {row["symbol"].replace("/", "-") for row in rows if row.get("symbol")}
    if len(symbols) < 90:
        raise RuntimeError(f"Nasdaq 官方成分名单仅返回 {len(symbols)} 个代码")
    return rows


def download_components() -> list[str]:
    return sorted(
        {row["symbol"].replace("/", "-") for row in download_component_rows() if row.get("symbol")}
    )


def calculate_top10_proxy(rows: list[dict]) -> dict:
    parsed = []
    for row in rows:
        try:
            market_cap = float(str(row.get("marketCap", "")).replace(",", ""))
            change = float(str(row.get("percentageChange", "")).replace("%", "").replace("+", ""))
        except ValueError:
            continue
        if market_cap > 0:
            parsed.append((row["symbol"], market_cap, change))
    if len(parsed) < 90:
        raise RuntimeError("Nasdaq 成分接口缺少足够的市值或涨跌幅字段")
    total_cap = sum(item[1] for item in parsed)
    top10 = sorted(parsed, key=lambda item: item[1], reverse=True)[:10]
    return {
        "top10_market_cap_share_pct": round(sum(item[1] for item in top10) / total_cap * 100, 2),
        "top10_daily_contribution_proxy_pct": round(sum(item[1] / total_cap * item[2] for item in top10), 3),
        "members": [item[0] for item in top10],
        "method": "当前成分股市值占比 × 当日涨跌幅代理；非 Nasdaq 官方修正权重贡献",
    }


def download_benchmark_history(*, full: bool = False) -> pd.DataFrame:
    try:
        data = yf.download(
            list(BENCHMARK_TICKERS),
            period="max" if full else "1mo",
            interval="1d",
            auto_adjust=True,
            progress=False,
            group_by="column",
            threads=True,
            timeout=45,
        )
        if data.empty or "Close" not in data:
            raise RuntimeError("Yahoo 基准行情下载为空")
        close = data["Close"] if isinstance(data.columns, pd.MultiIndex) else data[["Close"]]
        if not isinstance(close, pd.DataFrame):
            close = close.to_frame()
        result = pd.DataFrame(index=pd.to_datetime(close.index).tz_localize(None).normalize())
        for ticker, column in BENCHMARK_TICKERS.items():
            source = close[ticker] if ticker in close else pd.Series(dtype=float)
            if not source.empty:
                result[column] = source.to_numpy(dtype=float)
        result.index.name = "Date"
        return result.dropna(how="all").sort_index()
    except Exception as error:
        print(f"⚠️ Yahoo 基准限流，切换 Nasdaq/FRED 备用源: {error}")
        return download_benchmark_fallback(full=full)


def download_benchmark_fallback(*, full: bool = False) -> pd.DataFrame:
    end = datetime.now(NEW_YORK).date()
    start = (pd.Timestamp(end) - pd.DateOffset(years=10 if full else 1)).date()
    frames = []
    for symbol, asset_class, column in (
        ("SPY", "etf", "SP500"),
        ("NDXE", "index", "NDXEqualWeight"),
        ("IWM", "etf", "Russell2000"),
        ("QQQ", "etf", "QQQ"),
    ):
        url = (
            f"https://api.nasdaq.com/api/quote/{symbol}/historical?assetclass={asset_class}"
            f"&fromdate={start.isoformat()}&todate={end.isoformat()}&limit=5000"
        )
        payload = json.loads(fetch_bytes(url))
        rows = (((payload.get("data") or {}).get("tradesTable") or {}).get("rows") or [])
        if not rows:
            continue
        frame = pd.DataFrame(
            {
                "Date": pd.to_datetime([row["date"] for row in rows]),
                column: [float(str(row["close"]).replace(",", "").replace("$", "")) for row in rows],
            }
        ).set_index("Date")
        frames.append(frame)
    try:
        treasury = pd.read_csv(
            io.BytesIO(fetch_bytes("https://fred.stlouisfed.org/graph/fredgraph.csv?id=DTB3", timeout=15)),
            parse_dates=["observation_date"],
            na_values=".",
        ).rename(columns={"observation_date": "Date", "DTB3": "Treasury3M"}).set_index("Date")
        frames.append(treasury)
    except Exception as error:
        print(f"⚠️ FRED 3个月国库券备用序列不可用: {error}")
    if len(frames) < 4:
        raise RuntimeError("Nasdaq/FRED 备用基准返回不完整")
    result = pd.concat(frames, axis=1).sort_index()
    result.index.name = "Date"
    result.attrs["benchmark_source"] = "Nasdaq NDXE + SPY/IWM/QQQ ETF proxies; FRED DTB3"
    return result


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
            rows = download_component_rows()
            try:
                context["breadth"] = calculate_breadth(
                    sorted({row["symbol"].replace("/", "-") for row in rows if row.get("symbol")})
                )
            except Exception as error:
                print(f"⚠️ 成分股日线宽度不可用，保留缓存: {error}")
            if context.get("breadth"):
                context["breadth"] = {
                    **context["breadth"],
                    "concentration": calculate_top10_proxy(rows),
                    "constituent_history": "仅从功能启用日起逐日保存当时名单；不以当前名单回填历史",
                }
        except Exception as error:
            print(f"⚠️ NASDAQ-100 市场广度不可用，使用缓存: {error}")
    try:
        benchmark = download_benchmark_history(
            full=refresh_fred or not {"SP500", "NDXEqualWeight", "Russell2000", "QQQ"}.issubset(history.columns)
        )
        history = history.combine_first(benchmark)
        history.update(benchmark)
    except Exception as error:
        print(f"⚠️ 相对强弱基准不可用，使用缓存: {error}")
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


def _huber_fit(x: np.ndarray, y: np.ndarray) -> tuple[float, float, np.ndarray, int]:
    slope, intercept = np.polyfit(x, y, 1)
    weights = np.ones(len(y))
    iterations = 0
    for iterations in range(1, 31):
        residuals = y - (intercept + slope * x)
        median = np.median(residuals)
        scale = 1.4826 * np.median(np.abs(residuals - median))
        if scale <= 1e-12:
            break
        distance = np.abs(residuals - median)
        cutoff = 1.345 * scale
        weights = np.minimum(1.0, cutoff / np.maximum(distance, 1e-12))
        new_slope, new_intercept = np.polyfit(x, y, 1, w=np.sqrt(weights))
        if max(abs(new_slope - slope), abs(new_intercept - intercept)) < 1e-10:
            slope, intercept = new_slope, new_intercept
            break
        slope, intercept = new_slope, new_intercept
    return float(slope), float(intercept), weights, iterations


def _fit_robust_log_model(close: pd.Series) -> dict:
    if len(close) < 200 or (close <= 0).any():
        raise ValueError("稳健长期趋势至少需要 200 个有效正数收盘价")
    years = (close.index - close.index[0]).days.to_numpy(dtype=float) / 365.25
    center_years = float(years.mean())
    centered_years = years - center_years
    log_close = np.log(close.to_numpy(dtype=float))
    slope, intercept, weights, iterations = _huber_fit(centered_years, log_close)
    fitted_log = intercept + slope * centered_years
    residuals = log_close - fitted_log
    lower_residual, upper_residual = np.quantile(residuals, [0.1, 0.9])
    return {
        "origin": close.index[0],
        "center_years": center_years,
        "slope": slope,
        "intercept": intercept,
        "weights": weights,
        "iterations": iterations,
        "fitted_log": fitted_log,
        "residuals": residuals,
        "lower_residual": float(lower_residual),
        "upper_residual": float(upper_residual),
    }


def _predict_robust_log(model: dict, index: pd.Index) -> np.ndarray:
    years = (index - model["origin"]).days.to_numpy(dtype=float) / 365.25
    return model["intercept"] + model["slope"] * (years - model["center_years"])


def _percentile(values: np.ndarray, reference: np.ndarray) -> np.ndarray:
    ordered = np.sort(reference)
    return np.searchsorted(ordered, values, side="right") / len(ordered) * 100


def _consecutive_true(values: np.ndarray) -> int:
    count = 0
    for value in values[::-1]:
        if not value:
            break
        count += 1
    return count


def calculate_robust_log_trend(close: pd.Series) -> tuple[pd.DataFrame, dict]:
    model = _fit_robust_log_model(close)
    fitted_log = model["fitted_log"]
    residuals = model["residuals"]
    fitted = np.exp(fitted_log)
    lower = np.exp(fitted_log + model["lower_residual"])
    upper = np.exp(fitted_log + model["upper_residual"])
    trend = pd.DataFrame(
        {
            "Robust_Log_Trend": fitted,
            "Robust_Log_Lower": lower,
            "Robust_Log_Upper": upper,
            "Robust_Log_Deviation_Pct": (close.to_numpy(dtype=float) / fitted - 1) * 100,
            "Robust_Log_Percentile": _percentile(residuals, residuals),
        },
        index=close.index,
    )
    summary = {
        "method": "Huber IRLS 对数线性回归",
        "model_version": TREND_MODEL_VERSION,
        "start_date": close.index[0].date().isoformat(),
        "end_date": close.index[-1].date().isoformat(),
        "observations": len(close),
        "annualized_growth_pct": round((math.exp(model["slope"]) - 1) * 100, 2),
        "fitted_close": round(float(fitted[-1]), 2),
        "lower_band": round(float(trend.iloc[-1]["Robust_Log_Lower"]), 2),
        "upper_band": round(float(trend.iloc[-1]["Robust_Log_Upper"]), 2),
        "deviation_pct": round(float(trend.iloc[-1]["Robust_Log_Deviation_Pct"]), 2),
        "deviation_percentile": round(float(trend.iloc[-1]["Robust_Log_Percentile"]), 2),
        "central_coverage_pct": round(float(((close >= lower) & (close <= upper)).mean() * 100), 2),
        "above_upper_days": _consecutive_true((close.to_numpy(dtype=float) > upper)),
        "below_lower_days": _consecutive_true((close.to_numpy(dtype=float) < lower)),
        "lower_multiplier": round(math.exp(model["lower_residual"]), 4),
        "upper_multiplier": round(math.exp(model["upper_residual"]), 4),
        "downweighted_pct": round(float((model["weights"] < 0.999).mean() * 100), 2),
        "iterations": model["iterations"],
    }
    return trend, summary


def calculate_asof_robust_log_trend(
    close: pd.Series, min_observations: int = 1260
) -> tuple[pd.DataFrame, dict]:
    columns = [
        "AsOf_Robust_Log_Trend",
        "AsOf_Robust_Log_Lower",
        "AsOf_Robust_Log_Upper",
        "AsOf_Robust_Log_Deviation_Pct",
        "AsOf_Robust_Log_Percentile",
    ]
    result = pd.DataFrame(np.nan, index=close.index, columns=columns)
    months = close.index.to_period("M")
    latest_model = None
    latest_training_end = None
    for month in months.unique():
        positions = np.flatnonzero(months == month)
        start = int(positions[0])
        if start < min_observations:
            continue
        training = close.iloc[:start]
        model = _fit_robust_log_model(training)
        target_index = close.index[positions]
        fitted_log = _predict_robust_log(model, target_index)
        actual_log = np.log(close.iloc[positions].to_numpy(dtype=float))
        fitted = np.exp(fitted_log)
        result.iloc[positions] = np.column_stack(
            [
                fitted,
                np.exp(fitted_log + model["lower_residual"]),
                np.exp(fitted_log + model["upper_residual"]),
                (close.iloc[positions].to_numpy(dtype=float) / fitted - 1) * 100,
                _percentile(actual_log - fitted_log, model["residuals"]),
            ]
        )
        latest_model = model
        latest_training_end = training.index[-1]
    latest = result.iloc[-1]
    summary = {
        "method": "月度扩展窗口 Huber 对数线性回归",
        "model_version": TREND_MODEL_VERSION,
        "minimum_observations": min_observations,
        "training_end": latest_training_end.date().isoformat() if latest_training_end is not None else None,
        "fitted_close": _round_optional(float(latest["AsOf_Robust_Log_Trend"])),
        "lower_band": _round_optional(float(latest["AsOf_Robust_Log_Lower"])),
        "upper_band": _round_optional(float(latest["AsOf_Robust_Log_Upper"])),
        "deviation_pct": _round_optional(float(latest["AsOf_Robust_Log_Deviation_Pct"])),
        "deviation_percentile": _round_optional(float(latest["AsOf_Robust_Log_Percentile"])),
        "annualized_growth_pct": _round_optional(
            (math.exp(latest_model["slope"]) - 1) * 100 if latest_model else None
        ),
    }
    return result, summary


def calculate_model_stability(close: pd.Series) -> dict:
    latest = close.index[-1]
    windows = {}
    for label, years in (("10年", 10), ("15年", 15), ("20年", 20), ("全历史", None)):
        sample = close if years is None else close[close.index >= latest - pd.DateOffset(years=years)]
        model = _fit_robust_log_model(sample)
        windows[label] = {
            "start_date": sample.index[0].date().isoformat(),
            "observations": len(sample),
            "annualized_growth_pct": round((math.exp(model["slope"]) - 1) * 100, 2),
        }
    history = []
    for _, yearly in close.groupby(close.index.year):
        end = yearly.index[-1]
        sample = close.loc[:end]
        if len(sample) < 1260:
            continue
        model = _fit_robust_log_model(sample)
        history.append(
            {
                "date": end.date().isoformat(),
                "annualized_growth_pct": round((math.exp(model["slope"]) - 1) * 100, 4),
            }
        )
    return {"windows": windows, "history": history}


def calculate_trend_uncertainty(close: pd.Series, samples: int = 200, block_sessions: int = 20) -> dict:
    model = _fit_robust_log_model(close)
    residuals = model["residuals"]
    x = (close.index - close.index[0]).days.to_numpy(dtype=float) / 365.25
    x -= x.mean()
    rng = np.random.default_rng(9748)
    slopes = np.empty(samples)
    latest_fits = np.empty(samples)
    blocks = math.ceil(len(close) / block_sessions)
    offsets = np.arange(block_sessions)
    for iteration in range(samples):
        starts = rng.integers(0, len(close), size=blocks)
        indices = ((starts[:, None] + offsets) % len(close)).ravel()[: len(close)]
        boot_y = model["fitted_log"] + residuals[indices]
        slope, intercept, _, _ = _huber_fit(x, boot_y)
        slopes[iteration] = (math.exp(slope) - 1) * 100
        latest_fits[iteration] = math.exp(intercept + slope * x[-1])
    growth_low, growth_high = np.quantile(slopes, [0.025, 0.975])
    fit_low, fit_high = np.quantile(latest_fits, [0.025, 0.975])
    return {
        "method": "20交易日移动区块残差 Bootstrap",
        "samples": samples,
        "block_sessions": block_sessions,
        "annualized_growth_ci95_pct": [round(float(growth_low), 2), round(float(growth_high), 2)],
        "fitted_close_ci95": [round(float(fit_low), 2), round(float(fit_high), 2)],
    }


def calculate_indicators(prices: pd.DataFrame, *, advanced: bool = False) -> pd.DataFrame:
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
    bollinger_mid = close.rolling(20).mean()
    bollinger_std = close.rolling(20).std(ddof=0)
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    data["Bollinger_Mid"] = bollinger_mid
    data["Bollinger_Upper"] = bollinger_mid + 2 * bollinger_std
    data["Bollinger_Lower"] = bollinger_mid - 2 * bollinger_std
    data["MACD"] = ema12 - ema26
    data["MACD_Signal"] = data["MACD"].ewm(span=9, adjust=False).mean()
    data["MACD_Histogram"] = data["MACD"] - data["MACD_Signal"]
    data["ROC20_Pct"] = close.pct_change(20) * 100
    data["RSI14"] = 100 - (100 / (1 + relative_strength))
    data["Volatility20_Pct"] = daily_return.rolling(20).std() * math.sqrt(252) * 100
    data["High252"] = close.rolling(252).max()
    data["Distance_EMA200_Pct"] = (close / data["EMA200"] - 1) * 100
    data["Distance_High252_Pct"] = (close / data["High252"] - 1) * 100
    data["Drawdown_Pct"] = (close / close.cummax() - 1) * 100
    trend, trend_summary = calculate_robust_log_trend(close)
    data = data.join(trend)
    if advanced:
        asof_trend, asof_summary = calculate_asof_robust_log_trend(close)
        data = data.join(asof_trend)
        trend_summary["uncertainty"] = calculate_trend_uncertainty(close)
    result = data.round(4)
    result.attrs.update(prices.attrs)
    result.attrs["robust_log_trend"] = trend_summary
    if advanced:
        result.attrs["asof_robust_log_trend"] = asof_summary
        result.attrs["trend_model_stability"] = calculate_model_stability(close)
    return result


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


def _bounded(value: float, low: float = 0, high: float = 100) -> float:
    return max(low, min(high, value))


def build_relative_strength(data: pd.DataFrame, context_history: pd.DataFrame) -> dict:
    aligned = context_history.reindex(data.index).ffill(limit=5)
    windows = {"3个月": 63, "1年": 252, "3年": 756}
    labels = {
        "SP500": "标普500",
        "NDXEqualWeight": "纳指100等权",
        "Russell2000": "罗素2000",
        "QQQ": "QQQ",
    }
    result = {"benchmarks": {}, "qqq_cash_excess_1y_pct": None}
    ndx = data["Close"]
    for column, label in labels.items():
        benchmark = aligned.get(column, pd.Series(index=data.index, dtype=float))
        common = pd.concat([ndx.rename("ndx"), benchmark.rename("benchmark")], axis=1).dropna()
        values = {}
        for window, sessions in windows.items():
            sample = common.iloc[-sessions - 1 :]
            values[window] = _round_optional(
                ((sample.ndx.iloc[-1] / sample.ndx.iloc[0]) - (sample.benchmark.iloc[-1] / sample.benchmark.iloc[0])) * 100
            ) if len(sample) > sessions else None
        result["benchmarks"][column] = {"label": label, "excess_return_pct": values}
    qqq = aligned.get("QQQ", pd.Series(index=data.index, dtype=float)).dropna()
    bill = aligned.get("Treasury3M", pd.Series(index=data.index, dtype=float)).reindex(qqq.index).ffill()
    if len(qqq) > 252 and bill.iloc[-252:].notna().any():
        qqq_return = qqq.iloc[-1] / qqq.iloc[-253] - 1
        cash_return = (1 + bill.iloc[-252:].ffill().mean() / 100) ** (252 / 252) - 1
        result["qqq_cash_excess_1y_pct"] = _round_optional((qqq_return - cash_return) * 100)
    result["method"] = (
        "各资产同日收盘、同窗口总收益之差；QQQ/现金以13周国库券年化收益率近似；"
        "Yahoo指数不可用时，标普500与罗素2000分别使用SPY、IWM价格型ETF代理"
    )
    return result


def enrich_breadth_context(data: pd.DataFrame, history: pd.DataFrame, context: dict) -> None:
    breadth = context.get("breadth")
    if not breadth:
        return
    series = history.get("BreadthEMA200Pct", pd.Series(dtype=float)).dropna()
    breadth["acceleration_5d_pct_points"] = _round_optional(
        float(series.iloc[-1] - series.iloc[-6]) if len(series) >= 6 else None
    )
    breadth["price_breadth_divergence_20d"] = None
    if len(series) >= 21 and len(data) >= 21:
        breadth["price_breadth_divergence_20d"] = bool(
            data["Close"].pct_change(20).iloc[-1] > 0 and series.diff(20).iloc[-1] < 0
        )


def calculate_risk_dashboard(data: pd.DataFrame) -> dict:
    returns = data["Close"].pct_change().dropna()
    sample = returns.iloc[-252:]
    tail = sample[sample <= sample.quantile(0.05)]
    downside = sample.clip(upper=0)
    annual_return = sample.mean() * 252
    downside_vol = downside.pow(2).mean() ** 0.5 * math.sqrt(252)
    drawdown = data["Close"] / data["Close"].cummax() - 1
    underwater = drawdown < 0
    durations, current = [], 0
    for value in underwater:
        current = current + 1 if value else 0
        durations.append(current)
    recovery_lengths = []
    start = None
    for position, value in enumerate(underwater.to_numpy()):
        if value and start is None:
            start = position
        elif not value and start is not None:
            recovery_lengths.append(position - start)
            start = None
    return {
        "window_sessions": len(sample),
        "historical_var95_1d_pct": _round_optional(max(0, -float(sample.quantile(0.05)) * 100)),
        "expected_shortfall95_1d_pct": _round_optional(max(0, -float(tail.mean()) * 100)),
        "downside_volatility_pct": _round_optional(float(downside_vol * 100)),
        "sortino_ratio": _round_optional(float(annual_return / downside_vol) if downside_vol > 0 else None),
        "current_drawdown_duration_sessions": int(durations[-1]),
        "max_drawdown_duration_sessions": int(max(durations)),
        "median_recovery_sessions": _round_optional(float(np.median(recovery_lengths)) if recovery_lengths else None),
        "method": "近252个交易日历史模拟 VaR/ES；无风险利率取0；回撤周期按收盘创新高重置",
    }


def calculate_walk_forward_validation(data: pd.DataFrame, cost_bps: float = 10) -> dict:
    returns = data["Close"].pct_change().fillna(0)
    regimes = regime_series(data)
    exposure = regimes.map({"多头": 1.0, "修复": 0.5, "防御": 0.0}).fillna(0).shift(1).fillna(0)
    turnover = exposure.diff().abs().fillna(exposure.abs())
    strategy = exposure * returns - turnover * cost_bps / 10000
    valid = regimes.ne("未知").shift(1, fill_value=False)
    strategy, benchmark = strategy[valid], returns[valid]

    def metrics(values: pd.Series) -> dict:
        wealth = (1 + values).cumprod()
        years = max(len(values) / 252, 1 / 252)
        downside = values.clip(upper=0).pow(2).mean() ** 0.5 * math.sqrt(252)
        annual = wealth.iloc[-1] ** (1 / years) - 1
        return {
            "cagr_pct": _round_optional(float(annual * 100)),
            "annualized_volatility_pct": _round_optional(float(values.std() * math.sqrt(252) * 100)),
            "sortino_ratio": _round_optional(float(annual / downside) if downside > 0 else None),
            "max_drawdown_pct": _round_optional(float((wealth / wealth.cummax() - 1).min() * 100)),
        }

    episodes = []
    active = exposure[valid] > 0
    group = active.ne(active.shift()).cumsum()
    for _, values in strategy[active].groupby(group[active]):
        path = (1 + values).cumprod() - 1
        episodes.append((float(path.min() * 100), float(path.max() * 100)))
    yearly = []
    for year, values in strategy.groupby(strategy.index.year):
        yearly.append({
            "year": int(year),
            "strategy_return_pct": _round_optional(float(((1 + values).prod() - 1) * 100)),
            "benchmark_return_pct": _round_optional(float(((1 + benchmark.loc[values.index]).prod() - 1) * 100)),
        })
    return {
        "signal": "前一交易日多头/修复/防御对应下一日 100%/50%/0% 风险暴露",
        "transaction_cost_bps": cost_bps,
        "uses_future_data": False,
        "strategy": metrics(strategy),
        "buy_and_hold": metrics(benchmark),
        "annual_turnover_pct": _round_optional(float(turnover[valid].mean() * 252 * 100)),
        "position_changes": int((turnover[valid] > 0).sum()),
        "median_mae_pct": _round_optional(float(np.median([item[0] for item in episodes])) if episodes else None),
        "median_mfe_pct": _round_optional(float(np.median([item[1] for item in episodes])) if episodes else None),
        "yearly": yearly,
        "limitations": "收盘信号下一交易日生效；不含税费、滑点冲击和现金利息；用于验证规则稳定性而非业绩承诺",
    }


def calculate_stress_scenarios(close: pd.Series) -> list[dict]:
    definitions = [
        ("科技泡沫", "2000-03-10", "2002-10-09"),
        ("全球金融危机", "2007-10-31", "2009-03-09"),
        ("疫情冲击", "2020-02-19", "2020-03-23"),
        ("2022加息周期", "2021-11-19", "2022-12-28"),
    ]
    scenarios = []
    for name, start, trough_end in definitions:
        sample = close.loc[start:trough_end]
        if sample.empty:
            continue
        start_value = float(close.loc[:start].iloc[-1])
        trough_date = sample.idxmin()
        trough_value = float(sample.loc[trough_date])
        future = close.loc[trough_date:]
        recovered = future[future >= start_value]
        recovery_date = recovered.index[0] if not recovered.empty else None
        scenarios.append({
            "name": name,
            "start_date": pd.Timestamp(start).date().isoformat(),
            "trough_date": trough_date.date().isoformat(),
            "peak_to_trough_pct": _round_optional((trough_value / start_value - 1) * 100),
            "worst_day_pct": _round_optional(float(sample.pct_change().min() * 100)),
            "recovery_date": recovery_date.date().isoformat() if recovery_date is not None else None,
            "recovery_sessions": int(close.loc[trough_date:recovery_date].size - 1) if recovery_date is not None else None,
        })
    return scenarios


def build_data_quality(data: pd.DataFrame, context: dict) -> dict:
    freshness_points = {"正常": 20, "延迟": 10, "严重过期": 0}.get(
        build_freshness(data)["status"], 0
    )
    provisional_share = data["Is_Provisional"].astype(bool).mean()
    authority_points = 20 * (1 - min(1, provisional_share * 20))
    critical = ["Close", "EMA50", "EMA200", "RSI14", "Volatility20_Pct"]
    completeness_points = float(data[critical].tail(252).notna().mean().mean() * 20)
    context_items = [context.get(key) for key in ("vxn", "treasury10y", "breadth")]
    context_points = sum(1 for item in context_items if item and item.get("freshness") != "过期") / 3 * 20
    difference = (context.get("calibration") or {}).get("max_abs_diff_pct")
    consistency_points = 20 if difference is None else 20 * (1 - min(1, difference / 1.0))
    components = {
        "行情新鲜度": freshness_points,
        "权威来源": authority_points,
        "关键字段完整性": completeness_points,
        "环境数据覆盖": context_points,
        "跨源一致性": consistency_points,
    }
    score = round(sum(components.values()), 1)
    return {
        "score": score,
        "grade": "A" if score >= 90 else "B" if score >= 80 else "C" if score >= 70 else "D",
        "components": {key: round(value, 1) for key, value in components.items()},
        "warnings": [key for key, value in components.items() if value < 16],
        "methodology_version": METHODOLOGY_VERSION,
    }


def build_composite_score(data: pd.DataFrame, context: dict, risk: dict) -> dict:
    latest = data.iloc[-1]
    breadth = context.get("breadth") or {}
    vxn = (context.get("vxn") or {}).get("value")
    trend = _bounded(50 + (25 if latest.Close > latest.EMA200 else -25) + (15 if latest.EMA50 > latest.EMA200 else -15) + latest.Distance_EMA200_Pct)
    momentum = _bounded(50 + (latest.RSI14 - 50) * 0.6 + latest.ROC20_Pct * 1.5 + np.sign(latest.MACD_Histogram) * 10)
    breadth_values = [breadth.get(key) for key in ("above_ema20_pct", "above_ema50_pct", "above_ema200_pct")]
    breadth_score = float(np.mean([value for value in breadth_values if value is not None])) if any(value is not None for value in breadth_values) else 50
    risk_score = _bounded(100 - latest.Volatility20_Pct * 1.5 + latest.Drawdown_Pct * 1.2 - max(0, (vxn or 20) - 20) * 1.5)
    position = _bounded(100 - abs(latest.Robust_Log_Percentile - 50) * 2)
    components = {"趋势": trend, "动量": momentum, "宽度": breadth_score, "风险": risk_score, "长期位置": position}
    weights = {"趋势": 0.30, "动量": 0.20, "宽度": 0.20, "风险": 0.20, "长期位置": 0.10}
    score = round(sum(components[key] * weights[key] for key in components), 1)
    return {
        "score": score,
        "label": "强" if score >= 70 else "中性" if score >= 45 else "弱",
        "components": {key: round(float(value), 1) for key, value in components.items()},
        "weights": weights,
        "interpretation": "市场健康度合成，不是买卖信号；高分表示趋势、动量、宽度与风险环境更一致",
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
        "calibration_diff": env_float("ALERT_CALIBRATION_DIFF_PCT", 0.5, maximum=20),
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
    calibration_diff = (context.get("calibration") or {}).get("max_abs_diff_pct")
    if vxn is not None and vxn >= thresholds["vxn"]:
        reasons.append(f"VXN 升至 {vxn:.2f}")
    if breadth is not None and breadth < thresholds["breadth"]:
        reasons.append(f"市场广度降至 {breadth:.2f}%")
    if snapshot["volatility20_pct"] is not None and snapshot["volatility20_pct"] >= thresholds["volatility"]:
        reasons.append(f"20日年化波动率升至 {snapshot['volatility20_pct']:.2f}%")
    if abs(snapshot.get("distance_ema200_pct", 100)) <= thresholds["ema_distance"]:
        reasons.append(f"距 EMA200 仅 {snapshot['distance_ema200_pct']:+.2f}%")
    if calibration_diff is not None and calibration_diff > thresholds["calibration_diff"]:
        reasons.append(f"Yahoo/FRED 校准差异升至 {calibration_diff:.4f}%")
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
    fingerprint = hashlib.sha256(
        data[["Close", "Source", "Is_Provisional"]].to_csv(float_format="%.4f").encode()
    ).hexdigest()

    risk_dashboard = calculate_risk_dashboard(data)
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
        "ema20": round(float(latest["EMA20"]), 2),
        "ema50": round(float(latest["EMA50"]), 2),
        "ema200": round(float(latest["EMA200"]), 2),
        "sma200": _round_optional(float(latest["SMA200"])),
        "bollinger_upper": _round_optional(float(latest["Bollinger_Upper"])),
        "bollinger_lower": _round_optional(float(latest["Bollinger_Lower"])),
        "macd": _round_optional(float(latest["MACD"])),
        "macd_signal": _round_optional(float(latest["MACD_Signal"])),
        "macd_histogram": _round_optional(float(latest["MACD_Histogram"])),
        "roc20_pct": _round_optional(float(latest["ROC20_Pct"])),
        "distance_ema200_pct": round(float(latest["Distance_EMA200_Pct"]), 2),
        "distance_high252_pct": _round_optional(float(latest["Distance_High252_Pct"])),
        "rsi14": _round_optional(float(latest["RSI14"])),
        "volatility20_pct": _round_optional(float(latest["Volatility20_Pct"])),
        "drawdown_pct": round(float(latest["Drawdown_Pct"]), 2),
        "max_drawdown_pct": round(float(data["Drawdown_Pct"].min()), 2),
        "risk_dashboard": risk_dashboard,
        "walk_forward_validation": calculate_walk_forward_validation(data),
        "stress_scenarios": calculate_stress_scenarios(close),
        "robust_log_trend": data.attrs["robust_log_trend"],
        "asof_robust_log_trend": data.attrs.get("asof_robust_log_trend"),
        "trend_model_stability": data.attrs.get("trend_model_stability"),
        "status": status,
        "status_detail": status_detail,
        "context": context,
        "freshness": freshness,
        "provenance": {
            "latest_source": str(latest["Source"]),
            "latest_is_provisional": bool(latest["Is_Provisional"]),
            "authoritative_through": data.loc[~data["Is_Provisional"].astype(bool)].index[-1].date().isoformat(),
            "provisional_rows": int(data["Is_Provisional"].astype(bool).sum()),
            "data_fingerprint_sha256": fingerprint,
        },
        "methodology": {
            "version": METHODOLOGY_VERSION,
            "trend_model_version": TREND_MODEL_VERSION,
            "full_history_curve_is_descriptive": True,
            "asof_curve_uses_future_data": False,
            "asof_refit_cadence": "每月首个交易日使用截至上月末的数据重估",
        },
    }
    snapshot["composite_score"] = build_composite_score(data, context, risk_dashboard)
    snapshot["data_quality"] = build_data_quality(data, context)
    snapshot["alert"] = build_alert(snapshot)
    return snapshot


def _round_optional(value: float | None) -> float | None:
    return None if value is None or not math.isfinite(value) else round(value, 2)


def deterministic_analysis(snapshot: dict) -> str:
    context = snapshot.get("context", {})
    breadth = context.get("breadth") or {}
    vxn = context.get("vxn") or {}
    treasury = context.get("treasury10y") or {}
    trend = snapshot["robust_log_trend"]
    asof = snapshot.get("asof_robust_log_trend") or {}
    return "\n".join(
        [
            f"市场状态：{snapshot['status']}。{snapshot['status_detail']}，当前距 EMA200 {snapshot['distance_ema200_pct']:+.2f}%。",
            f"动量观察：RSI14 为 {snapshot['rsi14']:.2f}，MACD 柱值 {snapshot['macd_histogram']:+.2f}，20 日涨跌幅 {snapshot['roc20_pct']:+.2f}%，近 20 日年化波动率 {snapshot['volatility20_pct']:.2f}%。",
            f"风险位置：指数距 52 周高点 {snapshot['distance_high252_pct']:+.2f}%，当前历史高点回撤 {snapshot['drawdown_pct']:.2f}%。",
            f"长期位置：全历史稳健趋势偏离 {trend['deviation_pct']:+.2f}%、处于历史第 {trend['deviation_percentile']:.2f} 百分位；无未来数据月度趋势偏离 {asof.get('deviation_pct', float('nan')):+.2f}%。",
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
                    "只返回 JSON 对象，字段必须是 market_state、momentum_trend、risks、next_session_watch、"
                    "contradictions、invalidation_conditions、data_quality 和 facts。"
                    "前四项与 data_quality 是中文短段落；contradictions 与 invalidation_conditions 各为1至3条中文短句数组；"
                    "facts 是3至6项数组，每项仅含 metric 和 value。"
                    "JSON 格式示例：{\"market_state\":\"文字\",\"momentum_trend\":\"文字\",\"risks\":\"文字\","
                    "\"next_session_watch\":\"文字\",\"facts\":[{\"metric\":\"close\",\"value\":0}]}；"
                    "示例中的0必须替换为输入里的精确值，且 facts 必须扩展到3至6项。"
                    "metric 只能选 close、daily_return_pct、ema20、ema50、ema200、sma200、macd、macd_signal、"
                    "macd_histogram、roc20_pct、rsi14、volatility20_pct、drawdown_pct、"
                    "robust_log_trend.deviation_pct、robust_log_trend.deviation_percentile、"
                    "asof_robust_log_trend.deviation_pct、context.vxn.value、context.treasury10y.value、"
                    "context.breadth.above_ema200_pct；value 必须与输入完全一致。"
                    "区分事实与推断，只提供条件化风险管理框架，不给出绝对买入、卖出、重仓或清仓指令。"
                    "不得在文字段落中增加输入以外的数字、日期或阈值；明确指出临时数据局限。"
                ),
            },
            {"role": "user", "content": json.dumps(snapshot, ensure_ascii=False)},
        ],
        "max_tokens": 8000,
        "stream": False,
        "response_format": {"type": "json_object"},
    }
    if provider == "DeepSeek":
        payload["thinking"] = {"type": "enabled"}
        payload["reasoning_effort"] = "high"
    return f"{base_url}/chat/completions", payload, model, provider


AI_SECTION_LABELS = {
    "market_state": "市场状态",
    "momentum_trend": "动量与趋势",
    "risks": "主要风险",
    "next_session_watch": "下一交易日观察点",
}


def _snapshot_fact_values(snapshot: dict) -> dict[str, float]:
    def nested(path: str):
        value = snapshot
        for key in path.split("."):
            value = (value or {}).get(key)
        return value

    paths = [
        "close",
        "daily_return_pct",
        "ema20",
        "ema50",
        "ema200",
        "sma200",
        "macd",
        "macd_signal",
        "macd_histogram",
        "roc20_pct",
        "rsi14",
        "volatility20_pct",
        "drawdown_pct",
        "robust_log_trend.deviation_pct",
        "robust_log_trend.deviation_percentile",
        "asof_robust_log_trend.deviation_pct",
        "context.vxn.value",
        "context.treasury10y.value",
        "context.breadth.above_ema200_pct",
    ]
    return {path: float(value) for path in paths if (value := nested(path)) is not None}


def parse_and_validate_ai_analysis(raw: str, snapshot: dict) -> str:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    result = json.loads(cleaned)
    if not isinstance(result, dict) or any(not str(result.get(key, "")).strip() for key in AI_SECTION_LABELS):
        raise ValueError("AI JSON 缺少分析段落")
    combined = " ".join(str(result[key]) for key in AI_SECTION_LABELS)
    forbidden = ("立即买入", "立即卖出", "满仓", "清仓", "保证上涨", "保证下跌")
    if any(term in combined for term in forbidden):
        raise ValueError("AI 输出包含绝对交易指令")
    allowed = _snapshot_fact_values(snapshot)
    facts = result.get("facts")
    if not isinstance(facts, list) or not 3 <= len(facts) <= 6:
        raise ValueError("AI facts 数量无效")
    checked = []
    for fact in facts:
        metric = fact.get("metric") if isinstance(fact, dict) else None
        if metric not in allowed:
            raise ValueError(f"AI 使用了未授权指标: {metric}")
        value = float(fact.get("value"))
        if not math.isclose(value, allowed[metric], rel_tol=0, abs_tol=0.011):
            raise ValueError(f"AI 指标数值不一致: {metric}")
        checked.append(metric)
    contradictions = result.get("contradictions") or ["未提供额外矛盾证据"]
    invalidations = result.get("invalidation_conditions") or ["价格、宽度与风险指标出现反向变化时重新评估"]
    if not isinstance(contradictions, list) or not isinstance(invalidations, list):
        raise ValueError("AI 矛盾证据或失效条件格式无效")
    return "\n".join(
        [f"{label}：{str(result[key]).strip()}" for key, label in AI_SECTION_LABELS.items()]
        + [
            f"矛盾证据：{'；'.join(map(str, contradictions[:3]))}",
            f"失效条件：{'；'.join(map(str, invalidations[:3]))}",
            f"数据质量：{str(result.get('data_quality') or snapshot.get('data_quality', {}).get('grade', '待评估')).strip()}",
            f"事实校验：已核对 {len(checked)} 项结构化指标；仅供数据研究，不构成投资建议。",
        ]
    )


def build_analysis_framework(snapshot: dict) -> dict:
    breadth = snapshot.get("context", {}).get("breadth") or {}
    evidence = [
        {"metric": "close_vs_ema200_pct", "value": snapshot.get("distance_ema200_pct"), "supports": "趋势"},
        {"metric": "breadth_above_ema200_pct", "value": breadth.get("above_ema200_pct"), "supports": "宽度"},
        {"metric": "volatility20_pct", "value": snapshot.get("volatility20_pct"), "supports": "风险"},
        {"metric": "robust_deviation_pct", "value": snapshot.get("robust_log_trend", {}).get("deviation_pct"), "supports": "长期位置"},
    ]
    evidence = [item for item in evidence if item["value"] is not None]
    contradictions = []
    if snapshot.get("daily_return_pct", 0) > 0 and breadth.get("acceleration_5d_pct_points", 0) < 0:
        contradictions.append("指数上涨但 EMA200 市场宽度五日变化转弱")
    if snapshot.get("status") == "多头趋势" and snapshot.get("drawdown_pct", 0) < -10:
        contradictions.append("长期均线仍偏多，但价格尚处于较深历史回撤")
    if not contradictions:
        contradictions.append("当前主要指标未出现显著方向冲突，仍需观察下一交易日确认")
    return {
        "evidence": evidence,
        "contradictions": contradictions,
        "invalidation_conditions": [
            "收盘跌破 EMA200 且市场宽度同步恶化",
            "VXN 与已实现波动同时显著上升",
            "临时行情经 FRED 校准后改变关键阈值判断",
        ],
        "data_quality": snapshot.get("data_quality"),
    }


def request_ai_analysis(snapshot: dict) -> tuple[str, str, str | None, str | None]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return deterministic_analysis(snapshot), "规则分析", None, None

    url, payload, model, provider = build_ai_request(snapshot)
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        empty_detail = ""
        for attempt in range(2):
            with urllib.request.urlopen(request, timeout=120) as response:
                result = json.load(response)
            choice = result["choices"][0]
            message = choice["message"]
            raw = (message.get("content") or "").strip()
            if raw:
                text = parse_and_validate_ai_analysis(raw, snapshot)
                return text, provider, model, None
            usage = result.get("usage") or {}
            empty_detail = (
                f"finish_reason={choice.get('finish_reason') or 'unknown'}, "
                f"reasoning_chars={len(message.get('reasoning_content') or '')}, "
                f"completion_tokens={usage.get('completion_tokens', 'unknown')}"
            )
            print(f"⚠️ {provider} 第 {attempt + 1} 次响应正文为空（{empty_detail}）")
        raise RuntimeError(f"{provider} 连续两次响应正文为空（{empty_detail}）")
    except (OSError, urllib.error.HTTPError, ValueError, KeyError, RuntimeError) as error:
        print(f"⚠️ AI 分析不可用，改用规则分析: {error}")
        return deterministic_analysis(snapshot), "规则分析（AI 回退）", model, str(error)[:300]


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
        context_columns = [column for column in CONTEXT_COLUMNS if column in context_history]
        benchmark_columns = [column for column in BENCHMARK_COLUMNS if column in context_history]
        context_history[context_columns].dropna(how="all").to_csv(
            CONTEXT_CSV_PATH, encoding="utf-8-sig", float_format="%.4f"
        )
        context_history[benchmark_columns].dropna(how="all").to_csv(
            BENCHMARK_CSV_PATH, encoding="utf-8-sig", float_format="%.4f"
        )

    columns = [
        "Close",
        "EMA20",
        "EMA50",
        "EMA200",
        "SMA200",
        "Bollinger_Mid",
        "Bollinger_Upper",
        "Bollinger_Lower",
        "MACD",
        "MACD_Signal",
        "MACD_Histogram",
        "ROC20_Pct",
        "RSI14",
        "Volatility20_Pct",
        "Drawdown_Pct",
        "Robust_Log_Trend",
        "Robust_Log_Lower",
        "Robust_Log_Upper",
        "Robust_Log_Deviation_Pct",
        "Robust_Log_Percentile",
        "AsOf_Robust_Log_Trend",
        "AsOf_Robust_Log_Lower",
        "AsOf_Robust_Log_Upper",
        "AsOf_Robust_Log_Deviation_Pct",
        "AsOf_Robust_Log_Percentile",
        "Source",
        "Is_Provisional",
    ]
    records = []
    for date, row in data[columns].iterrows():
        records.append(
            {
                "date": date.date().isoformat(),
                "close": _json_number(row["Close"]),
                "ema20": _json_number(row["EMA20"]),
                "ema50": _json_number(row["EMA50"]),
                "ema200": _json_number(row["EMA200"]),
                "sma200": _json_number(row["SMA200"]),
                "bollinger_mid": _json_number(row["Bollinger_Mid"]),
                "bollinger_upper": _json_number(row["Bollinger_Upper"]),
                "bollinger_lower": _json_number(row["Bollinger_Lower"]),
                "macd": _json_number(row["MACD"]),
                "macd_signal": _json_number(row["MACD_Signal"]),
                "macd_histogram": _json_number(row["MACD_Histogram"]),
                "roc20_pct": _json_number(row["ROC20_Pct"]),
                "rsi14": _json_number(row["RSI14"]),
                "volatility20_pct": _json_number(row["Volatility20_Pct"]),
                "drawdown_pct": _json_number(row["Drawdown_Pct"]),
                "robust_trend": _json_number(row["Robust_Log_Trend"]),
                "robust_lower": _json_number(row["Robust_Log_Lower"]),
                "robust_upper": _json_number(row["Robust_Log_Upper"]),
                "robust_deviation_pct": _json_number(row["Robust_Log_Deviation_Pct"]),
                "robust_percentile": _json_number(row["Robust_Log_Percentile"]),
                "asof_robust_trend": _json_number(row["AsOf_Robust_Log_Trend"]),
                "asof_robust_lower": _json_number(row["AsOf_Robust_Log_Lower"]),
                "asof_robust_upper": _json_number(row["AsOf_Robust_Log_Upper"]),
                "asof_robust_deviation_pct": _json_number(row["AsOf_Robust_Log_Deviation_Pct"]),
                "asof_robust_percentile": _json_number(row["AsOf_Robust_Log_Percentile"]),
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
            "sp500": _json_number(aligned.at[date, "SP500"]) if "SP500" in aligned else None,
            "ndx_equal_weight": _json_number(aligned.at[date, "NDXEqualWeight"]) if "NDXEqualWeight" in aligned else None,
            "russell2000": _json_number(aligned.at[date, "Russell2000"]) if "Russell2000" in aligned else None,
            "qqq": _json_number(aligned.at[date, "QQQ"]) if "QQQ" in aligned else None,
            "treasury3m": _json_number(aligned.at[date, "Treasury3M"]) if "Treasury3M" in aligned else None,
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
    trend = snapshot["robust_log_trend"]
    asof = snapshot.get("asof_robust_log_trend") or {}
    uncertainty = trend.get("uncertainty") or {}
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
            f"全历史稳健趋势：{trend['fitted_close']:.2f}（偏离 {trend['deviation_pct']:+.2f}%，历史第 {trend['deviation_percentile']:.2f} 百分位）",
            f"无未来数据趋势：{asof.get('fitted_close', '—')}（偏离 {asof.get('deviation_pct', '—')}%，训练截至 {asof.get('training_end', '—')}）",
            f"长期年化：{trend['annualized_growth_pct']:.2f}%（Bootstrap 95% 区间 {uncertainty.get('annualized_growth_ci95_pct', ['—', '—'])[0]}%–{uncertainty.get('annualized_growth_ci95_pct', ['—', '—'])[1]}%）",
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
    data = calculate_indicators(download_history(refresh_fred=refresh_fred), advanced=True)
    validate_history(data)
    freshness = build_freshness(data)
    latest_date = data.index[-1].date()
    has_new_market_day = old_date is None or latest_date > old_date
    if scheduled_email and last_scheduled_email_date() == latest_date.isoformat():
        if freshness["status"] == "严重过期":
            raise RuntimeError(f"定时任务连续未取得新行情，最新仍为 {latest_date}")
        write_health(
            data={"status": freshness["status"], "market_date": latest_date.isoformat()},
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
    enrich_breadth_context(data, context_history, context)
    context["relative_strength"] = build_relative_strength(data, context_history)
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
        and bool(previous_analysis.get("text"))
        and previous_analysis.get("fact_validation") in {"passed", "deterministic"}
    )
    if reused_analysis:
        text = previous_analysis["text"]
        source = previous_analysis["source"]
        model = previous_analysis.get("model")
        analysis_error = previous_analysis.get("error")
    else:
        text, source, model, analysis_error = request_ai_analysis(snapshot)
    analysis = {
        "market_date": snapshot["market_date"],
        "generated_at": previous_analysis["generated_at"]
        if reused_analysis
        else datetime.now(ZoneInfo("UTC")).isoformat(),
        "source": source,
        "model": model,
        "error": analysis_error,
        "text": text,
        "fact_validation": "passed" if source not in {"规则分析", "规则分析（AI 回退）"} else "deterministic",
        "disclaimer": "仅供数据研究与市场观察，不构成投资建议。",
        **build_analysis_framework(snapshot),
    }
    print(f"✅ 分析来源: {source}" + (f" ({model})" if model else ""))
    export_data(data, snapshot, analysis, context_history, context, regime_analysis)
    health_updates = {
        "data": {"status": freshness["status"], "market_date": snapshot["market_date"]},
        "ai": {"status": "正常" if source not in {"规则分析", "规则分析（AI 回退）"} else "回退", "source": source, "model": model, "error": analysis_error},
        "calibration": context.get("calibration"),
    }
    if send_mail:
        health_updates["email"] = {"status": "待发送", "market_date": snapshot["market_date"]}
    write_health(**health_updates)
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
