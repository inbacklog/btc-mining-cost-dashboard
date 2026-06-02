from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Dict, List

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st
import yfinance as yf
from plotly.subplots import make_subplots
from streamlit_autorefresh import st_autorefresh


BINANCE_BASE_URL = "https://api.binance.com"
BLOCKCHAIN_CHARTS_URL = "https://api.blockchain.info/charts"
COINMETRICS_API_URL = "https://community-api.coinmetrics.io/v4/timeseries/asset-metrics"
COINMETRICS_BTC_CSV_URL = "https://raw.githubusercontent.com/coinmetrics/data/master/csv/btc.csv"

INTERVAL_TO_MS: Dict[str, int] = {
    "1m": 60_000,
    "5m": 5 * 60_000,
    "15m": 15 * 60_000,
    "30m": 30 * 60_000,
    "1h": 60 * 60_000,
    "4h": 4 * 60 * 60_000,
    "1d": 24 * 60 * 60_000,
    "1w": 7 * 24 * 60 * 60_000,
}

TIMEFRAME_OPTIONS: Dict[str, int | None] = {
    "30 days": 30,
    "90 days": 90,
    "180 days": 180,
    "1 year": 365,
    "2 years": 730,
    "4 years": 1460,
    "All available": None,
}

REFRESH_OPTIONS = {
    "Off": 0,
    "Every 1 min": 60,
    "Every 5 min": 5 * 60,
    "Every 15 min": 15 * 60,
    "Every 1 hour": 60 * 60,
    "Every 4 hours": 4 * 60 * 60,
}

# Same margins across all time-series charts keep the plot area aligned. This makes dates
# appear in the same horizontal position when the app-level display window is used.
STANDARD_CHART_MARGIN = dict(l=82, r=82, t=92, b=48)
MAIN_CHART_MARGIN = dict(l=82, r=82, t=132, b=48)
# Force every time-series figure to use the same horizontal plot area.
# This is what makes the same cursor x-position correspond to the same date across separate charts.
STANDARD_X_DOMAIN = [0.055, 0.945]


def make_x_range(df: pd.DataFrame) -> list[str] | None:
    """Return a Plotly-safe x-axis range from a dataframe with a UTC time column."""
    if df is None or df.empty or "time" not in df.columns:
        return None
    t = pd.to_datetime(df["time"], utc=True).dropna()
    if t.empty:
        return None
    start = t.min().isoformat()
    end = t.max().isoformat()
    return [start, end] if start != end else None


def apply_common_time_axis(fig: go.Figure, x_range: list[str] | None = None, title_text: str | None = None) -> go.Figure:
    """Apply consistent x-axis behavior/layout to every date chart in the app.

    Important: separate Streamlit Plotly charts cannot share live hover state with each
    other. What we can control is the visual mapping: every chart uses the same x-axis
    range, margins and x-domain, so the same horizontal cursor position corresponds to
    the same date across charts.
    """
    update = dict(
        showgrid=True,
        fixedrange=False,
        automargin=False,
        domain=STANDARD_X_DOMAIN,
        showspikes=True,
        spikemode="across",
        spikesnap="cursor",
        spikedash="dot",
        spikecolor="rgba(255,255,255,0.55)",
        spikethickness=1,
    )
    if x_range is not None:
        update["range"] = x_range
    if title_text:
        update["title_text"] = title_text
    fig.update_xaxes(**update)
    try:
        fig.update_xaxes(matches="x")
    except Exception:
        pass

    # Keep y-axes from changing the plot area width because of tick-label auto-margins.
    fig.update_yaxes(automargin=False, fixedrange=False)
    fig.update_layout(
        margin=STANDARD_CHART_MARGIN,
        hovermode="x unified",
        spikedistance=-1,
        hoverdistance=80,
    )
    return fig

BINANCE_ALL_START = {
    "BTCUSDT": "2017-08-01",
    "BTCEUR": "2020-01-01",
}

# Rough fleet-efficiency curve for a historical view.
# This is an approximation, not an official data series. It is intentionally editable by switching to constant mode.
EFFICIENCY_CURVE_J_PER_TH = [
    ("2013-01-01", 1200.0),
    ("2014-01-01", 700.0),
    ("2015-01-01", 300.0),
    ("2016-01-01", 150.0),
    ("2017-01-01", 105.0),
    ("2018-01-01", 80.0),
    ("2019-01-01", 60.0),
    ("2020-01-01", 45.0),
    ("2021-01-01", 38.0),
    ("2022-01-01", 32.0),
    ("2023-01-01", 27.0),
    ("2024-01-01", 23.0),
    ("2025-01-01", 20.0),
    ("2026-01-01", 18.0),
]

HALVINGS = [
    (pd.Timestamp("2009-01-03", tz="UTC"), 50.0),
    (pd.Timestamp("2012-11-28", tz="UTC"), 25.0),
    (pd.Timestamp("2016-07-09", tz="UTC"), 12.5),
    (pd.Timestamp("2020-05-11", tz="UTC"), 6.25),
    (pd.Timestamp("2024-04-20", tz="UTC"), 3.125),
]


def http_get_json(url: str, params: dict | None = None, timeout: int = 30):
    headers = {"User-Agent": "btc-cost-dashboard/16.0"}
    response = requests.get(url, params=params, headers=headers, timeout=timeout)
    response.raise_for_status()
    return response.json()


@st.cache_data(ttl=60, show_spinner=False)
def fetch_binance_klines(symbol: str, interval: str, start_ms: int, end_ms: int, max_candles: int = 30_000) -> pd.DataFrame:
    all_rows: List[list] = []
    current_start = start_ms
    interval_ms = INTERVAL_TO_MS[interval]

    while current_start < end_ms and len(all_rows) < max_candles:
        params = {
            "symbol": symbol.upper(),
            "interval": interval,
            "startTime": current_start,
            "endTime": end_ms,
            "limit": min(1000, max_candles - len(all_rows)),
        }
        rows = http_get_json(f"{BINANCE_BASE_URL}/api/v3/klines", params=params)
        if not rows:
            break
        all_rows.extend(rows)
        last_open_time = int(rows[-1][0])
        next_start = last_open_time + interval_ms
        if next_start <= current_start:
            break
        current_start = next_start
        if len(rows) < 1000:
            break

    if not all_rows:
        return pd.DataFrame()

    columns = [
        "open_time", "open", "high", "low", "close", "volume", "close_time",
        "quote_asset_volume", "number_of_trades", "taker_buy_base_volume",
        "taker_buy_quote_volume", "ignore",
    ]
    df = pd.DataFrame(all_rows, columns=columns)
    for col in ["open", "high", "low", "close", "volume", "quote_asset_volume", "number_of_trades"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    df = df.drop_duplicates(subset=["time"]).sort_values("time").reset_index(drop=True)
    return df[["time", "open", "high", "low", "close", "volume", "quote_asset_volume", "number_of_trades"]]


@st.cache_data(ttl=10 * 60, show_spinner=False)
def fetch_yahoo_price(ticker: str, interval: str, days: int | None) -> pd.DataFrame:
    period = "max" if days is None else f"{max(days, 1)}d"
    data = yf.download(ticker, period=period, interval=interval, progress=False, auto_adjust=False, threads=False)
    if data.empty:
        return pd.DataFrame()
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = [col[0] for col in data.columns]
    data = data.reset_index()
    date_col = "Datetime" if "Datetime" in data.columns else "Date"
    data["time"] = pd.to_datetime(data[date_col], utc=True)
    data = data.rename(columns={"Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"})
    for col in ["open", "high", "low", "close", "volume"]:
        data[col] = pd.to_numeric(data[col], errors="coerce")
    data["quote_asset_volume"] = data["close"] * data["volume"]
    data["number_of_trades"] = np.nan
    return data[["time", "open", "high", "low", "close", "volume", "quote_asset_volume", "number_of_trades"]].dropna(subset=["close"]).sort_values("time").reset_index(drop=True)


@st.cache_data(ttl=6 * 60 * 60, show_spinner=False)
def fetch_blockchain_chart(chart_name: str, days: int | None, start_date: str = "2013-01-01") -> pd.DataFrame:
    if days is None:
        params = {"start": start_date, "format": "json", "sampled": "false"}
    else:
        params = {"timespan": f"{max(days, 30)}days", "format": "json", "sampled": "false"}
    data = http_get_json(f"{BLOCKCHAIN_CHARTS_URL}/{chart_name}", params=params, timeout=45)
    values = data.get("values", [])
    if not values:
        return pd.DataFrame()
    df = pd.DataFrame(values)
    df["time"] = pd.to_datetime(df["x"], unit="s", utc=True)
    df[chart_name] = pd.to_numeric(df["y"], errors="coerce")
    return df[["time", chart_name]].dropna().sort_values("time").reset_index(drop=True)


def to_ms(ts: pd.Timestamp) -> int:
    return int(ts.timestamp() * 1000)


def get_start_end(days: int | None, symbol: str) -> tuple[pd.Timestamp, pd.Timestamp]:
    end = pd.Timestamp.now(tz="UTC")
    if days is None:
        start = pd.Timestamp(BINANCE_ALL_START.get(symbol, "2017-08-01"), tz="UTC")
    else:
        start = end - pd.Timedelta(days=days)
    return start, end


def add_indicators(df: pd.DataFrame, ma_windows: List[int]) -> pd.DataFrame:
    out = df.copy()
    for w in ma_windows:
        if w > 1:
            out[f"MA{w}"] = out["close"].rolling(w).mean()
    delta = out["close"].diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss.replace(0, np.nan)
    out["RSI14"] = 100 - (100 / (1 + rs))
    out["RSI14_MA"] = out["RSI14"].rolling(14).mean()
    mid = out["close"].rolling(20).mean()
    std = out["close"].rolling(20).std()
    out["BB_upper"] = mid + 2 * std
    out["BB_lower"] = mid - 2 * std
    return out


def add_200w_ma(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy().sort_values("time")
    daily = out[["time", "close"]].dropna().copy()
    if daily.empty:
        out["MA200W"] = np.nan
        return out
    weekly = daily.set_index("time")["close"].resample("W").last().dropna().to_frame("weekly_close")
    weekly["MA200W"] = weekly["weekly_close"].rolling(200).mean()
    weekly = weekly.reset_index()[["time", "MA200W"]].dropna()
    if weekly.empty:
        out["MA200W"] = np.nan
        return out
    return pd.merge_asof(out.sort_values("time"), weekly.sort_values("time"), on="time", direction="backward")


def btc_subsidy_per_block(times: pd.Series) -> pd.Series:
    rewards = pd.Series(index=times.index, dtype=float)
    for i, (start, reward) in enumerate(HALVINGS):
        end = HALVINGS[i + 1][0] if i + 1 < len(HALVINGS) else pd.Timestamp.max.tz_localize("UTC")
        mask = (times >= start) & (times < end)
        rewards.loc[mask] = reward
    return rewards.ffill().bfill()


def historical_efficiency_series(times: pd.Series, constant_efficiency: float | None = None) -> pd.Series:
    if constant_efficiency is not None:
        return pd.Series(float(constant_efficiency), index=times.index)
    curve = pd.DataFrame(EFFICIENCY_CURVE_J_PER_TH, columns=["time", "efficiency_j_per_th"])
    curve["time"] = pd.to_datetime(curve["time"], utc=True)
    daily = pd.DataFrame({"time": times}).sort_values("time")
    merged = pd.merge_asof(daily, curve.sort_values("time"), on="time", direction="backward")
    merged["efficiency_j_per_th"] = merged["efficiency_j_per_th"].ffill().bfill()
    return pd.Series(merged["efficiency_j_per_th"].values, index=times.index)



@st.cache_data(ttl=6 * 60 * 60, show_spinner=False)
def fetch_coinmetrics_api_metrics(start_date: str = "2013-01-01") -> pd.DataFrame:
    """Fetch free daily BTC mining metrics from Coin Metrics Community API.

    HashRate is documented by Coin Metrics in TH/s for BTC. FeeTotNtv and IssTotNtv
    are native BTC units per day. The function follows next_page_url pagination.
    """
    rows: List[dict] = []
    params = {
        "assets": "btc",
        "metrics": "HashRate,FeeTotNtv,IssTotNtv",
        "frequency": "1d",
        "start_time": start_date,
        "page_size": 10000,
    }
    url = COINMETRICS_API_URL
    first = True
    while url:
        payload = http_get_json(url, params=params if first else None, timeout=60)
        rows.extend(payload.get("data", []))
        url = payload.get("next_page_url")
        first = False
        params = None
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["time"] = pd.to_datetime(df["time"], utc=True)
    for c in ["HashRate", "FeeTotNtv", "IssTotNtv"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df.sort_values("time").reset_index(drop=True)


@st.cache_data(ttl=12 * 60 * 60, show_spinner=False)
def fetch_coinmetrics_csv_metrics(start_date: str = "2013-01-01") -> pd.DataFrame:
    """Fallback: read Coin Metrics' free BTC CSV archive from GitHub."""
    wanted = {"time", "HashRate", "FeeTotNtv", "IssTotNtv", "PriceUSD"}
    df = pd.read_csv(COINMETRICS_BTC_CSV_URL, usecols=lambda c: c in wanted)
    if df.empty:
        return pd.DataFrame()
    df["time"] = pd.to_datetime(df["time"], utc=True)
    df = df[df["time"] >= pd.Timestamp(start_date, tz="UTC")].copy()
    for c in ["HashRate", "FeeTotNtv", "IssTotNtv", "PriceUSD"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df.sort_values("time").reset_index(drop=True)


def coinmetrics_to_cost_raw(cm: pd.DataFrame) -> pd.DataFrame:
    if cm.empty:
        return pd.DataFrame()
    out = pd.DataFrame({"time": cm["time"]})
    out["hashrate_reported"] = pd.to_numeric(cm.get("HashRate"), errors="coerce")
    out["hashrate_unit_inferred"] = "Coin Metrics HashRate, TH/s"
    out["hashrate_th_s"] = out["hashrate_reported"]
    out["fees_btc"] = pd.to_numeric(cm.get("FeeTotNtv"), errors="coerce").fillna(0.0)
    issued = pd.to_numeric(cm.get("IssTotNtv"), errors="coerce")
    fallback_issued = btc_subsidy_per_block(out["time"]) * 144.0
    out["btc_issued_per_day"] = issued.where(issued > 0, fallback_issued)
    out["miner_btc_revenue_per_day"] = out["btc_issued_per_day"] + out["fees_btc"]
    return out.dropna(subset=["time", "hashrate_th_s"]).sort_values("time").reset_index(drop=True)

def normalize_hashrate_to_ths(df: pd.DataFrame, col: str = "hash-rate") -> pd.DataFrame:
    out = df.copy()
    out["hashrate_reported"] = pd.to_numeric(out[col], errors="coerce")
    latest = out["hashrate_reported"].dropna().tail(30).median()
    # Blockchain.com has normally reported hash-rate in TH/s. Some chart sources may use EH/s or PH/s.
    # Current BTC network hash rate is hundreds of EH/s, i.e. hundreds of millions of TH/s.
    if pd.isna(latest):
        factor, unit = 1.0, "unknown"
    elif latest < 10_000:  # likely EH/s
        factor, unit = 1_000_000.0, "EH/s -> TH/s"
    elif latest < 10_000_000:  # likely PH/s
        factor, unit = 1_000.0, "PH/s -> TH/s"
    else:
        factor, unit = 1.0, "TH/s"
    out["hashrate_th_s"] = out["hashrate_reported"] * factor
    out["hashrate_unit_inferred"] = unit
    return out


@st.cache_data(ttl=6 * 60 * 60, show_spinner=False)
def build_mining_cost_data(days: int | None) -> pd.DataFrame:
    """Build daily mining raw data.

    v10 uses Coin Metrics Community metrics first because it gives a long daily
    history with HashRate in TH/s plus daily issuance and fees. Blockchain.com is
    retained only as a fallback.
    """
    start_date = "2013-01-01" if days is None else (pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=max(days, 30))).strftime("%Y-%m-%d")

    # Primary: Coin Metrics Community API.
    try:
        cm = fetch_coinmetrics_api_metrics(start_date=start_date)
        raw = coinmetrics_to_cost_raw(cm)
        if not raw.empty and raw["hashrate_th_s"].dropna().tail(30).median() > 10_000_000:
            raw["mining_source"] = "Coin Metrics Community API"
            return raw
    except Exception:
        pass

    # Fallback: Coin Metrics GitHub CSV archive.
    try:
        cm = fetch_coinmetrics_csv_metrics(start_date=start_date)
        raw = coinmetrics_to_cost_raw(cm)
        if not raw.empty and raw["hashrate_th_s"].dropna().tail(30).median() > 10_000_000:
            raw["mining_source"] = "Coin Metrics GitHub CSV"
            return raw
    except Exception:
        pass

    # Last fallback: Blockchain.com hash-rate chart.
    hash_df = fetch_blockchain_chart("hash-rate", days, start_date=start_date)
    if hash_df.empty:
        return pd.DataFrame()
    hash_df = normalize_hashrate_to_ths(hash_df)
    try:
        fees_df = fetch_blockchain_chart("transaction-fees", days, start_date=start_date)
        fees_df = fees_df.rename(columns={"transaction-fees": "fees_btc"})
    except Exception:
        fees_df = pd.DataFrame(columns=["time", "fees_btc"])
    cost = pd.merge_asof(
        hash_df.sort_values("time"),
        fees_df.sort_values("time") if not fees_df.empty else fees_df,
        on="time",
        direction="nearest",
        tolerance=pd.Timedelta(days=2),
    )
    cost["fees_btc"] = pd.to_numeric(cost.get("fees_btc"), errors="coerce").fillna(0.0)
    cost["subsidy_btc_per_block"] = btc_subsidy_per_block(cost["time"])
    cost["estimated_blocks_per_day"] = 144.0
    cost["btc_issued_per_day"] = cost["subsidy_btc_per_block"] * cost["estimated_blocks_per_day"]
    cost["miner_btc_revenue_per_day"] = cost["btc_issued_per_day"] + cost["fees_btc"]
    cost["mining_source"] = "Blockchain.com fallback"
    return cost.sort_values("time").reset_index(drop=True)


def apply_cost_assumptions(
    mining_raw: pd.DataFrame,
    price_daily: pd.DataFrame,
    quote_currency: str,
    efficiency_mode: str,
    constant_efficiency: float,
    electricity_cost: float,
    pue: float,
    electricity_share_of_total_cost: float,
    include_fees_in_denominator: bool,
    calibrate_current_cost: bool,
    target_current_total_cost: float,
) -> pd.DataFrame:
    if mining_raw.empty:
        return mining_raw
    out = mining_raw.copy().sort_values("time")
    if efficiency_mode.startswith("Constant"):
        out["efficiency_j_per_th"] = historical_efficiency_series(out["time"], constant_efficiency=constant_efficiency).values
    else:
        out["efficiency_j_per_th"] = historical_efficiency_series(out["time"], constant_efficiency=None).values

    out["energy_kwh_per_day"] = out["hashrate_th_s"] * out["efficiency_j_per_th"] * 24.0 / 1000.0 * pue
    out["electricity_cost_per_day"] = out["energy_kwh_per_day"] * electricity_cost
    denominator_btc = out["miner_btc_revenue_per_day"] if include_fees_in_denominator else out["btc_issued_per_day"]
    denominator_btc = denominator_btc.replace(0, np.nan)
    out["electricity_cost_per_btc"] = out["electricity_cost_per_day"] / denominator_btc
    share = max(electricity_share_of_total_cost, 1.0) / 100.0
    out["total_production_cost_per_btc"] = out["electricity_cost_per_btc"] / share

    # Merge daily price for miner revenue price and ratios.
    price_daily = price_daily[["time", "close"]].dropna().sort_values("time").copy()
    out = pd.merge_asof(out.sort_values("time"), price_daily, on="time", direction="nearest", tolerance=pd.Timedelta(days=3))
    out = out.rename(columns={"close": "btc_price_for_cost"})
    out["miner_price_per_btc"] = out["btc_price_for_cost"] * (1.0 + out["fees_btc"] / out["btc_issued_per_day"].replace(0, np.nan))
    out["price_to_total_cost"] = out["btc_price_for_cost"] / out["total_production_cost_per_btc"].replace(0, np.nan)
    out["miner_price_to_total_cost"] = out["miner_price_per_btc"] / out["total_production_cost_per_btc"].replace(0, np.nan)

    if calibrate_current_cost:
        latest_model_cost = out["total_production_cost_per_btc"].dropna().iloc[-1] if out["total_production_cost_per_btc"].notna().any() else np.nan
        if pd.notna(latest_model_cost) and latest_model_cost > 0 and target_current_total_cost > 0:
            factor = target_current_total_cost / latest_model_cost
            out["calibration_factor"] = factor
            for c in ["electricity_cost_per_btc", "total_production_cost_per_btc"]:
                out[c] = out[c] * factor
            out["price_to_total_cost"] = out["btc_price_for_cost"] / out["total_production_cost_per_btc"].replace(0, np.nan)
            out["miner_price_to_total_cost"] = out["miner_price_per_btc"] / out["total_production_cost_per_btc"].replace(0, np.nan)
        else:
            out["calibration_factor"] = np.nan
    else:
        out["calibration_factor"] = 1.0

    out["quote_currency"] = quote_currency
    return out


def parse_ma_windows(text: str) -> List[int]:
    windows = []
    for raw in text.split(","):
        raw = raw.strip()
        if not raw:
            continue
        try:
            value = int(raw)
            if 1 < value <= 2000:
                windows.append(value)
        except ValueError:
            pass
    return sorted(set(windows))


def latest_value(df: pd.DataFrame, col: str) -> float | None:
    s = df[col].dropna() if col in df.columns else pd.Series(dtype=float)
    return None if s.empty else float(s.iloc[-1])


def fmt_money(x: float | None, currency_symbol: str = "$") -> str:
    if x is None or not np.isfinite(x):
        return "n/a"
    return f"{currency_symbol}{x:,.0f}"


def fmt_ratio(x: float | None) -> str:
    if x is None or not np.isfinite(x):
        return "n/a"
    return f"{x:.2f}x"




def numeric_visible_range(values, pad: float = 0.08, floor: float | None = None, ceil: float | None = None, include: list[float] | None = None, robust_upper: bool = False) -> list[float] | None:
    """Return a readable y-axis range for already-filtered visible data.

    Plotly/Streamlit does not recalculate subplot axes reliably after mouse zoom,
    and single outliers can make volume/ratio panels unreadable. This helper is
    used only after the app-level visible date filter has already been applied.
    """
    s = pd.to_numeric(pd.Series(values), errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    if s.empty:
        return None
    lo = float(s.min())
    hi = float(s.quantile(0.98) if robust_upper and len(s) >= 20 else s.max())
    # Never crop all values if the high quantile is too low. Allow only mild clipping of extreme spikes.
    if robust_upper and s.max() > hi * 1.8:
        hi = float(hi)
    else:
        hi = float(s.max())
    if include:
        for v in include:
            if v is not None and np.isfinite(v):
                lo = min(lo, float(v))
                hi = max(hi, float(v))
    if not np.isfinite(lo) or not np.isfinite(hi):
        return None
    if hi == lo:
        delta = abs(hi) * 0.1 if hi else 1.0
        lo -= delta
        hi += delta
    span = hi - lo
    lo -= span * pad
    hi += span * pad
    if floor is not None:
        lo = max(float(floor), lo)
    if ceil is not None:
        hi = min(float(ceil), hi)
    if hi <= lo:
        return None
    return [lo, hi]


def robust_nonnegative_range(values, pad: float = 0.12, include: list[float] | None = None) -> list[float] | None:
    """Readable range for non-negative panels like volume and ratio.

    Uses a high percentile if a single spike dominates the visible period, so normal
    bars/lines remain visible. The spike may extend above the axis top, but the chart
    becomes much more useful for analysis.
    """
    s = pd.to_numeric(pd.Series(values), errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    if s.empty:
        return None
    hi_max = float(s.max())
    hi_q = float(s.quantile(0.98)) if len(s) >= 20 else hi_max
    hi = hi_q if hi_max > hi_q * 2 and hi_q > 0 else hi_max
    if include:
        for v in include:
            if v is not None and np.isfinite(v):
                hi = max(hi, float(v))
    if not np.isfinite(hi) or hi <= 0:
        hi = 1.0
    return [0, hi * (1.0 + pad)]


def filter_display_window(
    df: pd.DataFrame,
    display_window_label: str,
    end_time: pd.Timestamp | None = None,
    custom_start: object | None = None,
    custom_end: object | None = None,
) -> pd.DataFrame:
    """Filter the dataframe before plotting so Plotly y-axes autoscale to the selected period.

    Plotly inside Streamlit cannot reliably re-autoscale the y-axis after the user zooms with
    the mouse. Filtering the data before chart creation is the reliable local-app approach.
    """
    if df.empty or "time" not in df.columns:
        return df
    out = df.copy()
    out["time"] = pd.to_datetime(out["time"], utc=True)
    if end_time is None:
        end_time = out["time"].max()
    end_time = pd.Timestamp(end_time).tz_convert("UTC") if pd.Timestamp(end_time).tzinfo else pd.Timestamp(end_time, tz="UTC")

    if display_window_label == "Same as loaded data":
        return out

    if display_window_label == "Custom date range":
        if custom_start is None or custom_end is None:
            return out
        start_ts = pd.Timestamp(custom_start).tz_localize("UTC")
        end_ts = pd.Timestamp(custom_end).tz_localize("UTC") + pd.Timedelta(days=1) - pd.Timedelta(milliseconds=1)
    else:
        days_map = {
            "Last 7 days": 7,
            "Last 30 days": 30,
            "Last 90 days": 90,
            "Last 180 days": 180,
            "Last 1 year": 365,
            "Last 2 years": 730,
            "Last 4 years": 1460,
        }
        days = days_map.get(display_window_label)
        if days is None:
            return out
        start_ts = end_time - pd.Timedelta(days=days)
        end_ts = end_time

    filtered = out[(out["time"] >= start_ts) & (out["time"] <= end_ts)].copy()
    return filtered if not filtered.empty else out




def get_default_display_dates(
    df: pd.DataFrame,
    display_window_label: str,
    custom_start: object | None = None,
    custom_end: object | None = None,
) -> tuple[object, object]:
    """Return default start/end dates for the visible chart window controls."""
    if df.empty or "time" not in df.columns:
        today = pd.Timestamp.today().date()
        return today, today
    t = pd.to_datetime(df["time"], utc=True).dropna()
    min_dt = t.min().date()
    max_dt = t.max().date()

    if display_window_label == "Custom date range" and custom_start is not None and custom_end is not None:
        return max(custom_start, min_dt), min(custom_end, max_dt)

    if display_window_label == "Same as loaded data":
        return min_dt, max_dt

    days_map = {
        "Last 7 days": 7,
        "Last 30 days": 30,
        "Last 90 days": 90,
        "Last 180 days": 180,
        "Last 1 year": 365,
        "Last 2 years": 730,
        "Last 4 years": 1460,
    }
    days = days_map.get(display_window_label)
    if days is None:
        return min_dt, max_dt
    start_dt = (pd.Timestamp(max_dt) - pd.Timedelta(days=days)).date()
    return max(start_dt, min_dt), max_dt


def normalize_date_range_selection(selection, fallback_start, fallback_end):
    """Streamlit date_input can return a date, tuple, or list depending on user state."""
    if isinstance(selection, (tuple, list)) and len(selection) >= 2 and selection[0] is not None and selection[1] is not None:
        start_date, end_date = selection[0], selection[1]
    else:
        start_date, end_date = fallback_start, fallback_end
    if pd.Timestamp(start_date) > pd.Timestamp(end_date):
        start_date, end_date = end_date, start_date
    return start_date, end_date


def filter_by_visible_dates(df: pd.DataFrame, start_date: object, end_date: object) -> pd.DataFrame:
    """Filter data to a date range before plotting, making y-axis autorange truthful for that visible period."""
    if df.empty or "time" not in df.columns:
        return df
    out = df.copy()
    out["time"] = pd.to_datetime(out["time"], utc=True)
    start_ts = pd.Timestamp(start_date).tz_localize("UTC")
    end_ts = pd.Timestamp(end_date).tz_localize("UTC") + pd.Timedelta(days=1) - pd.Timedelta(milliseconds=1)
    filtered = out[(out["time"] >= start_ts) & (out["time"] <= end_ts)].copy()
    return filtered if not filtered.empty else out

def make_main_chart(
    price: pd.DataFrame,
    cost_data: pd.DataFrame,
    ma_windows: List[int],
    symbol_label: str,
    currency_symbol: str,
    show_bbands: bool,
    show_rsi: bool,
    show_volume: bool,
    show_ratio_panel: bool,
    show_costs_on_main: bool,
    x_range: list[str] | None = None,
) -> go.Figure:
    row_specs = [[{"secondary_y": False}]]
    row_heights = [0.58]
    titles = ["BTC price, moving averages and production-cost model"]
    if show_rsi:
        row_specs.append([{"secondary_y": False}])
        row_heights.append(0.14)
        titles.append("RSI 14")
    if show_volume:
        row_specs.append([{"secondary_y": False}])
        row_heights.append(0.14)
        titles.append("Volume")
    if show_ratio_panel:
        row_specs.append([{"secondary_y": False}])
        row_heights.append(0.14)
        titles.append("Price / total production cost")

    fig = make_subplots(
        rows=len(row_specs),
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.045,
        row_heights=row_heights,
        subplot_titles=titles,
    )

    fig.add_trace(go.Candlestick(
        x=price["time"], open=price["open"], high=price["high"], low=price["low"], close=price["close"],
        name=symbol_label, increasing_line_width=1, decreasing_line_width=1,
    ), row=1, col=1)

    for w in ma_windows:
        col = f"MA{w}"
        if col in price.columns:
            fig.add_trace(go.Scatter(x=price["time"], y=price[col], mode="lines", name=col, line=dict(width=1.4)), row=1, col=1)

    if "MA200W" in price.columns and price["MA200W"].notna().any():
        fig.add_trace(go.Scatter(x=price["time"], y=price["MA200W"], mode="lines", name="200W MA", line=dict(width=1.4, dash="dot")), row=1, col=1)

    if show_bbands and {"BB_upper", "BB_lower"}.issubset(price.columns):
        fig.add_trace(go.Scatter(x=price["time"], y=price["BB_upper"], mode="lines", name="Bollinger upper", line=dict(width=1, dash="dot"), opacity=0.55), row=1, col=1)
        fig.add_trace(go.Scatter(x=price["time"], y=price["BB_lower"], mode="lines", name="Bollinger lower", line=dict(width=1, dash="dot"), opacity=0.55), row=1, col=1)

    if show_costs_on_main and not cost_data.empty:
        cost_traces = [
            ("total_production_cost_per_btc", "Total production cost", "dash"),
            ("electricity_cost_per_btc", "Electrical cost floor", "dot"),
            ("miner_price_per_btc", "Miner price/revenue per BTC", "solid"),
        ]
        for col, label, dash in cost_traces:
            if col in cost_data.columns and cost_data[col].notna().any():
                fig.add_trace(go.Scatter(
                    x=cost_data["time"], y=cost_data[col], mode="lines", name=label,
                    line=dict(width=2.2, dash=dash), opacity=0.95,
                ), row=1, col=1)

    current_row = 2
    if show_rsi:
        fig.add_trace(go.Scatter(x=price["time"], y=price["RSI14"], mode="lines", name="RSI14", line=dict(width=1.1, color="#00D5FF")), row=current_row, col=1)
        if "RSI14_MA" in price.columns:
            fig.add_trace(go.Scatter(x=price["time"], y=price["RSI14_MA"], mode="lines", name="RSI14 MA", line=dict(width=1.4, color="#FFFFFF"), opacity=0.75), row=current_row, col=1)
        fig.add_hline(y=70, line_dash="dash", opacity=0.35, row=current_row, col=1)
        fig.add_hline(y=50, line_dash="dot", opacity=0.30, row=current_row, col=1)
        fig.add_hline(y=30, line_dash="dash", opacity=0.35, row=current_row, col=1)
        rsi_values = price[[c for c in ["RSI14", "RSI14_MA"] if c in price.columns]].stack()
        rsi_range = numeric_visible_range(rsi_values, pad=0.12, floor=0, ceil=100, include=[30, 50, 70])
        fig.update_yaxes(title_text="RSI", range=rsi_range, autorange=False if rsi_range else True, row=current_row, col=1)
        current_row += 1
    if show_volume:
        fig.add_trace(go.Bar(x=price["time"], y=price["volume"], name="BTC volume", opacity=0.95, marker_color="#00E5FF"), row=current_row, col=1)
        volume_range = robust_nonnegative_range(price["volume"], pad=0.15)
        fig.update_yaxes(title_text="Volume", range=volume_range, autorange=False if volume_range else True, row=current_row, col=1)
        current_row += 1
    if show_ratio_panel:
        ratio_range = None
        if not cost_data.empty and "price_to_total_cost" in cost_data.columns:
            fig.add_trace(go.Scatter(x=cost_data["time"], y=cost_data["price_to_total_cost"], mode="lines", name="Price / cost", line=dict(width=1.8, color="#7CFC00")), row=current_row, col=1)
            fig.add_hline(y=1, line_dash="dash", opacity=0.55, annotation_text="Breakeven", row=current_row, col=1)
            ratio_range = robust_nonnegative_range(cost_data["price_to_total_cost"], pad=0.15, include=[1])
        fig.update_yaxes(title_text="Ratio", range=ratio_range, autorange=False if ratio_range else True, row=current_row, col=1)

    fig.update_layout(
        height=840 if len(row_specs) > 1 else 640,
        template="plotly_dark",
        hovermode="x unified",
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.075,
            xanchor="left",
            x=0,
            font=dict(size=11),
            itemwidth=36,
        ),
        margin=MAIN_CHART_MARGIN,
        xaxis_rangeslider_visible=False,
        uirevision="synced-display-window",
    )
    fig.update_annotations(font=dict(size=13), yshift=-6)
    fig.update_yaxes(title_text=f"Price and cost ({currency_symbol})", autorange=True, fixedrange=False, row=1, col=1)
    apply_common_time_axis(fig, x_range=x_range)
    fig.update_layout(margin=MAIN_CHART_MARGIN)
    return fig


def make_cost_comparison_chart(cost: pd.DataFrame, symbol_label: str, currency_symbol: str, log_scale: bool, x_range: list[str] | None = None) -> go.Figure:
    fig = go.Figure()
    traces = [
        ("btc_price_for_cost", f"{symbol_label} price", "solid"),
        ("miner_price_per_btc", "Miner price/revenue per BTC", "solid"),
        ("total_production_cost_per_btc", "Total production cost", "dash"),
        ("electricity_cost_per_btc", "Electrical cost floor", "dot"),
    ]
    for col, label, dash in traces:
        if col in cost.columns and cost[col].notna().any():
            fig.add_trace(go.Scatter(x=cost["time"], y=cost[col], mode="lines", name=label, line=dict(width=2.2, dash=dash)))
    fig.update_layout(
        title="BTC price vs mining production cost, direct comparison",
        template="plotly_dark",
        height=560,
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        margin=STANDARD_CHART_MARGIN,
        uirevision="synced-display-window",
    )
    apply_common_time_axis(fig, x_range=x_range, title_text="Date")
    fig.update_yaxes(title_text=f"{currency_symbol} per BTC", type="log" if log_scale else "linear", autorange=True, fixedrange=False)
    return fig



def add_cycle_timing_score(times: pd.Series) -> pd.Series:
    # Historical BTC cycle bottoms often occurred roughly 600-1,100 days after the prior halving.
    # This is deliberately a soft timing feature, not a trading rule.
    halvings = [h[0] for h in HALVINGS] + [pd.Timestamp("2028-04-20", tz="UTC")]
    scores = []
    for t in times:
        prev = max([h for h in halvings if h <= t], default=halvings[0])
        days_since = (t - prev).days
        # Triangular score centered around 850 days after halving, fades to zero before 500 or after 1,250 days.
        score = max(0.0, 1.0 - abs(days_since - 850) / 400.0)
        scores.append(score)
    return pd.Series(scores, index=times.index)


def build_opportunity_data(price: pd.DataFrame, cost: pd.DataFrame) -> pd.DataFrame:
    base = price[["time", "close", "RSI14", "MA200W"]].copy() if "MA200W" in price.columns else price[["time", "close", "RSI14"]].copy()
    if "MA200W" not in base.columns:
        base["MA200W"] = np.nan
    attach = cost[["time", "price_to_total_cost", "total_production_cost_per_btc"]].copy() if not cost.empty else pd.DataFrame(columns=["time", "price_to_total_cost", "total_production_cost_per_btc"])
    out = pd.merge_asof(base.sort_values("time"), attach.sort_values("time"), on="time", direction="nearest", tolerance=pd.Timedelta(days=5))
    out["ath_to_date"] = out["close"].cummax()
    out["drawdown_pct"] = out["close"] / out["ath_to_date"] - 1.0
    out["price_to_200w"] = out["close"] / out["MA200W"].replace(0, np.nan)

    # Components are normalized 0..1. Higher means historically more attractive accumulation context.
    out["score_cost"] = ((1.50 - out["price_to_total_cost"]) / (1.50 - 0.70)).clip(0, 1)
    out["score_drawdown"] = (((-out["drawdown_pct"]) - 0.35) / (0.80 - 0.35)).clip(0, 1)
    out["score_200w"] = ((1.30 - out["price_to_200w"]) / (1.30 - 0.80)).clip(0, 1)
    out["score_rsi"] = ((55.0 - out["RSI14"]) / (55.0 - 25.0)).clip(0, 1)
    out["score_time_cycle"] = add_cycle_timing_score(out["time"])

    weights = {
        "score_cost": 30.0,
        "score_drawdown": 25.0,
        "score_200w": 20.0,
        "score_rsi": 15.0,
        "score_time_cycle": 10.0,
    }
    weighted_sum = 0
    available_weight = 0
    for col, weight in weights.items():
        component = out[col]
        weighted_sum = weighted_sum + component.fillna(0) * weight
        available_weight = available_weight + component.notna().astype(float) * weight
    out["opportunity_score"] = (weighted_sum / available_weight.replace(0, np.nan) * 100.0).clip(0, 100)
    out["opportunity_regime"] = pd.cut(
        out["opportunity_score"],
        bins=[-0.1, 30, 55, 75, 100.1],
        labels=["Low", "Neutral", "Good", "High"],
    )
    return out


def make_opportunity_chart(opp: pd.DataFrame, symbol_label: str, currency_symbol: str, x_range: list[str] | None = None) -> go.Figure:
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Scatter(x=opp["time"], y=opp["close"], mode="lines", name=f"{symbol_label} price", line=dict(width=1.5, color="#9AD8FF")), secondary_y=False)
    fig.add_trace(go.Scatter(x=opp["time"], y=opp["opportunity_score"], mode="lines", name="Opportunity score", line=dict(width=2.0, color="#7CFC00")), secondary_y=True)

    high = opp[opp["opportunity_score"] >= 75].dropna(subset=["opportunity_score", "close"]).copy()
    if not high.empty:
        # Convert to timezone-naive timestamps before monthly grouping to avoid pandas Period warnings.
        high["time_month"] = pd.to_datetime(high["time"], utc=True).dt.tz_convert(None).dt.to_period("M")
        idx = high.groupby("time_month")["opportunity_score"].idxmax()
        high_m = high.loc[idx]
        fig.add_trace(go.Scatter(
            x=high_m["time"], y=high_m["close"], mode="markers", name="High opportunity months",
            marker=dict(size=8, color="#00FF7F", symbol="circle"),
            text=("Score: " + high_m["opportunity_score"].round(0).astype(int).astype(str)),
            hovertemplate="%{x}<br>BTC price: %{y:,.0f}<br>%{text}<extra></extra>",
        ), secondary_y=False)

    for h, _reward in HALVINGS[1:]:
        if opp["time"].min() <= h <= opp["time"].max():
            # Avoid plotly add_vline(annotation_text=...) bug with pandas Timestamp arithmetic.
            h_str = pd.Timestamp(h).strftime("%Y-%m-%d")
            fig.add_shape(
                type="line",
                x0=h_str,
                x1=h_str,
                y0=0,
                y1=1,
                xref="x",
                yref="paper",
                line=dict(width=1, dash="dot", color="rgba(255,255,255,0.45)"),
            )
            fig.add_annotation(
                x=h_str,
                y=1,
                xref="x",
                yref="paper",
                text="Halving",
                showarrow=False,
                yshift=12,
                font=dict(size=10, color="rgba(255,255,255,0.75)"),
            )

    fig.add_hline(y=75, line_dash="dash", opacity=0.45, annotation_text="High", secondary_y=True)
    fig.add_hline(y=55, line_dash="dot", opacity=0.35, annotation_text="Good", secondary_y=True)
    fig.update_layout(
        title="Historical accumulation opportunity score",
        template="plotly_dark",
        height=560,
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        margin=STANDARD_CHART_MARGIN,
        uirevision="synced-display-window",
    )
    fig.update_yaxes(title_text=f"BTC price ({currency_symbol}, log)", type="log", secondary_y=False)
    fig.update_yaxes(title_text="Opportunity score, 0-100", range=[0, 100], secondary_y=True)
    apply_common_time_axis(fig, x_range=x_range, title_text="Date")
    return fig


def describe_latest_rsi(price: pd.DataFrame) -> str:
    rsi = latest_value(price, "RSI14")
    rsi_ma = latest_value(price, "RSI14_MA")
    if rsi is None or not np.isfinite(rsi):
        return "RSI unavailable."
    if rsi >= 70:
        zone = "strong/possibly overheated"
    elif rsi >= 55:
        zone = "bullish momentum"
    elif rsi >= 45:
        zone = "neutral"
    elif rsi >= 30:
        zone = "weak momentum"
    else:
        zone = "oversold/stressed"
    direction = ""
    if rsi_ma is not None and np.isfinite(rsi_ma):
        direction = " RSI is above its short RSI average." if rsi > rsi_ma else " RSI is below its short RSI average."
    return f"Latest RSI is {rsi:.1f}, which is {zone}.{direction}"


def render_manual() -> None:
    st.divider()
    st.header("📘 Dashboard manual: how to use and interpret the app")
    st.caption("This section is a practical guide for reading the dashboard. It is educational, not financial advice.")

    with st.expander("1. Recommended workflow", expanded=False):
        st.markdown(
            """
**Best simple workflow**

1. Select **All available** as the loaded history, especially for BTC cycle context.
2. Use **Chart date range** above the charts to focus on the period you care about.
3. Check **Separate direct price vs mining-cost comparison** first. This answers: is BTC price above or below estimated production cost?
4. Check **Price / total production cost**. Above 1 means BTC is above the estimated cost line. Below 1 means BTC is below it.
5. Use the main price chart, RSI, volume and moving averages for timing.
6. Use the opportunity-score chart only as a context signal, not as an automatic buy/sell trigger.

**Important about date alignment**

The app keeps the time-series charts on the selected visible date range so the panels stay easier to compare.
"""
        )

    with st.expander("2. Main price chart", expanded=False):
        st.markdown(
            """
**Candles / price** show the actual BTC market movement for the selected pair.

**MA20 / MA50 / MA200** are moving averages:
- MA20: short-term trend.
- MA50: medium-term trend.
- MA200: long-term daily trend.

**200W MA** means 200-week moving average, roughly a 4-year trend line. It is often used for BTC cycle context. BTC near or below this line has historically been a deep-stress zone, but it is not guaranteed support.

**Cost lines on the main chart** are useful only if you want to see price and estimated cost together. The cleaner cost view is the separate direct comparison chart.
"""
        )

    with st.expander("3. Separate direct price vs mining-cost comparison", expanded=False):
        st.markdown(
            """
This is the cleanest chart for the mining-cost question.

**BTC price** is the market price.

**Electrical cost floor** estimates the electricity-only production cost per BTC. It is a lower-bound style estimate.

**Total production cost** estimates broader mining production cost by scaling the electrical cost using the selected electricity share assumption.

**Miner revenue price** adjusts BTC price for miner transaction-fee revenue. Miners receive block subsidy plus fees, so this can be slightly higher than spot BTC price during high-fee periods.

Simple interpretation:
- Price above total production cost: miners are generally profitable under the selected assumptions.
- Price near total production cost: neutral/stress area, often more interesting for long-term accumulation.
- Price below total production cost: miner stress/capitulation context, but not a guaranteed bottom.
"""
        )

    with st.expander("4. RSI, volume and ratio panels", expanded=False):
        st.markdown(
            """
**RSI 14** is a momentum indicator:
- Above 70: strong, but possibly overheated.
- 55 to 70: bullish momentum.
- 45 to 55: neutral.
- 30 to 45: weak momentum.
- Below 30: oversold/stressed.

RSI is best used as a regime indicator, not as a standalone buy/sell button. A useful pattern is RSI recovering above 50 after a deep drawdown.

**Volume** confirms participation:
- Price up with strong volume: healthier move.
- Price up with weak volume: less convincing.
- Price down with extreme volume: possible panic/capitulation, especially after a large drawdown.

**Price / total production cost**:
- Ratio above 1: BTC is above estimated production cost.
- Ratio near 1: BTC is close to estimated production cost.
- Ratio below 1: BTC is below estimated production cost.
"""
        )

    with st.expander("5. Historical accumulation opportunity score", expanded=False):
        st.markdown(
            """
The opportunity score is experimental. It combines multiple context indicators:

- Price / total production cost.
- Drawdown from all-time high.
- Distance from 200W MA.
- RSI.
- Approximate halving-cycle timing.

Higher score means the selected period looks more similar to previous BTC accumulation or stress zones. It should help you ask better questions, not make decisions automatically.

A practical reading:
- 0 to 30: weak opportunity context.
- 30 to 55: neutral.
- 55 to 75: good context.
- 75 to 100: historically stronger accumulation/stress context.
"""
        )

    with st.expander("6. Data confidence and limitations", expanded=False):
        st.markdown(
            """
**Higher confidence**
- BTC price from Binance or Yahoo Finance.
- Basic technical indicators like moving averages, RSI, volume and drawdown.

**Medium confidence**
- Network mining data such as hash rate, issuance and fees, because hash rate is estimated from block timing and difficulty.

**Medium / assumption-sensitive confidence**
- Production cost. There is no official BTC production cost. The value depends heavily on electricity price, efficiency, PUE/overhead, and the selected electricity share of total cost.

**Use it like this**
- Production cost gives valuation context.
- RSI, volume and moving averages give timing context.
- Opportunity score summarizes context but should not override your risk management.
"""
        )

def main():
    st.set_page_config(page_title="BTC price vs mining cost", layout="wide")
    st.title("BTC price vs estimated mining production cost")
    st.caption("Research dashboard for BTC price, mining-cost estimates, market structure, and cycle context.")

    with st.sidebar:
        st.header("Price data")
        price_source = st.selectbox("Price source", ["Yahoo Finance longer history", "Binance spot exchange data"], index=0)
        quote_choice = st.selectbox("Quote currency", ["USD / USDT", "EUR"], index=0)
        quote_currency = "USD" if quote_choice == "USD / USDT" else "EUR"
        currency_symbol = "$" if quote_currency == "USD" else "€"
        if price_source.startswith("Binance"):
            symbol = "BTCUSDT" if quote_currency == "USD" else "BTCEUR"
            interval = st.selectbox("Candle interval", list(INTERVAL_TO_MS.keys()), index=5)  # 4h
        else:
            symbol = "BTC-USD" if quote_currency == "USD" else "BTC-EUR"
            interval = st.selectbox("Candle interval", ["1d", "1wk", "1mo"], index=0)
        lookback_label = st.selectbox("Loaded data history", list(TIMEFRAME_OPTIONS.keys()), index=len(TIMEFRAME_OPTIONS) - 1, help="How much data the app downloads/calculates. Keep this broad when you want long moving averages and opportunity-score context.")
        days = TIMEFRAME_OPTIONS[lookback_label]
        display_window_label = st.selectbox(
            "Chart display window (auto y-scale)",
            [
                "Same as loaded data",
                "Last 7 days",
                "Last 30 days",
                "Last 90 days",
                "Last 180 days",
                "Last 1 year",
                "Last 2 years",
                "Last 4 years",
                "Custom date range",
            ],
            index=0,
            help="Filters only what is plotted, so the y-axis rescales to the selected period. Indicators are still calculated using the loaded history.",
        )
        custom_start = custom_end = None
        if display_window_label == "Custom date range":
            custom_start = st.date_input("Chart start date", value=(pd.Timestamp.today() - pd.Timedelta(days=365)).date())
            custom_end = st.date_input("Chart end date", value=pd.Timestamp.today().date())
        refresh_label = st.selectbox("Auto-refresh", list(REFRESH_OPTIONS.keys()), index=0)
        refresh_seconds = REFRESH_OPTIONS[refresh_label]
        if refresh_seconds:
            st_autorefresh(interval=refresh_seconds * 1000, key="btc_cost_refresh")

        st.divider()
        st.header("Chart")
        ma_text = st.text_input("Moving averages", value="20,50,200")
        ma_windows = parse_ma_windows(ma_text)
        show_200w = st.checkbox("Show 200-week MA", value=True)
        show_bbands = st.checkbox("Show Bollinger Bands", value=False)
        show_rsi = st.checkbox("Show RSI panel", value=True)
        show_volume = st.checkbox("Show volume panel", value=True)
        show_ratio_panel = st.checkbox("Show price / total cost panel", value=True)
        show_costs_on_main = st.checkbox("Show cost lines on main price chart", value=True)
        show_separate_cost_chart = st.checkbox("Show separate direct comparison chart", value=True)
        use_log_cost_chart = st.checkbox("Use log scale in separate cost chart", value=False)
        show_opportunity_chart = st.checkbox("Show historical opportunity-score chart", value=True)

        st.divider()
        st.header("Production cost model")
        st.caption("This follows the idea used by public cost charts: network energy cost divided by BTC mined, then scaled to total production cost.")
        efficiency_mode = st.selectbox("Efficiency mode", ["Approx historical fleet efficiency curve", "Constant selected efficiency"], index=0)
        constant_eff = st.number_input("Constant ASIC/fleet efficiency, J/TH", min_value=1.0, max_value=2000.0, value=20.0, step=1.0)
        electricity_cost = st.number_input("Electricity cost, USD/kWh or EUR/kWh", min_value=0.001, max_value=1.0, value=0.050, step=0.005, format="%.3f")
        pue = st.number_input("Facility PUE / overhead multiplier", min_value=1.0, max_value=2.0, value=1.10, step=0.05, format="%.2f")
        electricity_share = st.number_input("Electricity share of total production cost, %", min_value=20.0, max_value=100.0, value=60.0, step=5.0)
        include_fees = st.checkbox("Include transaction fees as miner BTC revenue", value=True)
        calibrate = st.checkbox("Calibrate current total cost to external reference", value=False)
        target_cost = st.number_input("Current reference total production cost", min_value=1000.0, max_value=300000.0, value=85000.0, step=1000.0)

    # Price data
    try:
        if price_source.startswith("Binance"):
            start, end = get_start_end(days, symbol)
            # Avoid downloading millions of intraday candles.
            max_candles = 80_000 if interval in ["1d", "1w"] else 30_000
            price = fetch_binance_klines(symbol, interval, to_ms(start), to_ms(end), max_candles=max_candles)
        else:
            price = fetch_yahoo_price(symbol, interval, days)
    except Exception as exc:
        st.error(f"Could not fetch price data: {exc}")
        st.stop()

    if price.empty:
        st.error("No price data returned. Try another source, interval, or lookback window.")
        st.stop()

    price = add_indicators(price, ma_windows)
    if show_200w:
        price = add_200w_ma(price)

    # Mining cost data, normally daily. Use same days as price lookback.
    try:
        mining_raw = build_mining_cost_data(days)
    except Exception as exc:
        st.warning(f"Could not fetch mining-cost data: {exc}")
        mining_raw = pd.DataFrame()

    if mining_raw.empty:
        cost = pd.DataFrame()
    else:
        # Use daily price for cost model, even when main chart is intraday/weekly.
        daily_price = price[["time", "close"]].copy()
        if interval not in ["1d", "1wk", "1mo"]:
            daily_price = daily_price.set_index("time").resample("D").last().dropna().reset_index()
        cost = apply_cost_assumptions(
            mining_raw=mining_raw,
            price_daily=daily_price,
            quote_currency=quote_currency,
            efficiency_mode=efficiency_mode,
            constant_efficiency=constant_eff,
            electricity_cost=electricity_cost,
            pue=pue,
            electricity_share_of_total_cost=electricity_share,
            include_fees_in_denominator=include_fees,
            calibrate_current_cost=calibrate,
            target_current_total_cost=target_cost,
        )
        # Keep the cost chart aligned to the available BTC price history. This prevents orphan cost-only periods.
        cost = cost[cost["time"] >= price["time"].min() - pd.Timedelta(days=3)].copy()

    # Latest metrics use the full loaded data. Chart y-axis autoscaling is handled separately
    # by filtering the visible date range before each figure is created.
    display_end = price["time"].max()

    latest_price = latest_value(price, "close")
    latest_total_cost = latest_value(cost, "total_production_cost_per_btc") if not cost.empty else None
    latest_electric = latest_value(cost, "electricity_cost_per_btc") if not cost.empty else None
    latest_miner_price = latest_value(cost, "miner_price_per_btc") if not cost.empty else None
    latest_ratio = latest_value(cost, "price_to_total_cost") if not cost.empty else None
    latest_hashrate = latest_value(cost, "hashrate_th_s") if not cost.empty else None

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Latest BTC price", fmt_money(latest_price, currency_symbol))
    c2.metric("Total production cost", fmt_money(latest_total_cost, currency_symbol))
    c3.metric("Electrical cost floor", fmt_money(latest_electric, currency_symbol))
    c4.metric("Miner revenue price", fmt_money(latest_miner_price, currency_symbol))
    c5.metric("Price / total cost", fmt_ratio(latest_ratio))

    if latest_hashrate:
        st.caption(f"Latest inferred network hash rate: {latest_hashrate / 1_000_000:,.0f} EH/s. Cost model is assumption-based, not an official BTC fair value.")

    default_start_date, default_end_date = get_default_display_dates(price, display_window_label, custom_start, custom_end)
    min_chart_date = pd.to_datetime(price["time"], utc=True).min().date()
    max_chart_date = pd.to_datetime(price["time"], utc=True).max().date()

    st.subheader("Chart date range")
    visible_selection = st.date_input(
        "Visible date range for all charts",
        value=(default_start_date, default_end_date),
        min_value=min_chart_date,
        max_value=max_chart_date,
        key=f"visible_date_range_{display_window_label}_{lookback_label}_{symbol}_{interval}",
    )
    visible_start_date, visible_end_date = normalize_date_range_selection(visible_selection, default_start_date, default_end_date)
    price_display = filter_by_visible_dates(price, visible_start_date, visible_end_date)
    cost_display = filter_by_visible_dates(cost, visible_start_date, visible_end_date) if not cost.empty else cost
    synced_x_range = make_x_range(price_display)

    st.caption(
        f"Visible period: {visible_start_date} to {visible_end_date}. "
        f"Visible price rows: {len(price_display):,}."
    )

    fig = make_main_chart(
        price=price_display,
        cost_data=cost_display,
        ma_windows=ma_windows,
        symbol_label=symbol,
        currency_symbol=currency_symbol,
        show_bbands=show_bbands,
        show_rsi=show_rsi,
        show_volume=show_volume,
        show_ratio_panel=show_ratio_panel,
        show_costs_on_main=show_costs_on_main,
        x_range=synced_x_range,
    )
    st.plotly_chart(fig, use_container_width=True)
    st.caption(describe_latest_rsi(price))

    if show_opportunity_chart:
        opp = build_opportunity_data(price, cost)
        opp_display = filter_by_visible_dates(opp, visible_start_date, visible_end_date)
        if not opp_display.empty and opp_display["opportunity_score"].notna().any():
            st.subheader("Historical accumulation opportunity score")
            st.caption("Experimental helper: combines cost ratio, drawdown from ATH, distance to 200W MA, RSI, and halving-cycle timing. Use it for context, not as an automatic buy signal.")
            st.plotly_chart(make_opportunity_chart(opp_display, symbol, currency_symbol, x_range=synced_x_range), use_container_width=True)
            latest_score = latest_value(opp, "opportunity_score")
            if latest_score is not None and np.isfinite(latest_score):
                st.info(f"Latest opportunity score: {latest_score:.0f}/100. Higher means the current area looks more similar to historical accumulation/stress zones under the selected model.")

    if show_separate_cost_chart and not cost_display.empty:
        st.subheader("Separate direct price vs mining-cost comparison")
        st.caption("This is the cleanest chart for your question: are production costs above or below BTC price?")
        fig_cost = make_cost_comparison_chart(cost_display, symbol, currency_symbol, use_log_cost_chart, x_range=synced_x_range)
        st.plotly_chart(fig_cost, use_container_width=True)

    with st.expander("How the cost lines are calculated"):
        st.markdown(
            """
**What other public charts usually do**

Most public BTC production-cost charts do not show many hardware/ops lines on the main price chart. They usually show BTC price versus one or two production-cost lines.

This app follows that simpler structure, using Coin Metrics daily mining metrics when available:

1. **Electrical cost floor**  
   `network hash rate × fleet efficiency × electricity price / BTC miner revenue`

2. **Total production cost**  
   `electrical cost floor / electricity share of total production cost`

3. **Miner revenue price**  
   `BTC spot price × (BTC subsidy + transaction fees) / BTC subsidy`

**Important assumptions**

- There is no single official BTC production cost.
- Coin Metrics HashRate is used in TH/s for BTC; daily fees and issuance are in BTC units.
- The historical fleet-efficiency curve is approximate.
- `Electricity share of total production cost = 60%` means total cost is estimated as `electricity cost / 0.60`.
- The calibration option lets you manually align the latest model value to an external reference, for example a MacroMicro-style current production-cost estimate.
"""
        )
        curve_df = pd.DataFrame(EFFICIENCY_CURVE_J_PER_TH, columns=["date", "efficiency_j_per_th"])
        st.dataframe(curve_df, use_container_width=True, hide_index=True)

    with st.expander("Latest data rows"):
        if not cost.empty:
            display_cols = [
                "time", "mining_source", "hashrate_reported", "hashrate_unit_inferred", "hashrate_th_s", "efficiency_j_per_th",
                "btc_issued_per_day", "fees_btc", "electricity_cost_per_btc", "total_production_cost_per_btc",
                "btc_price_for_cost", "miner_price_per_btc", "price_to_total_cost", "calibration_factor",
            ]
            available_cols = [c for c in display_cols if c in cost.columns]
            st.dataframe(cost[available_cols].tail(20), use_container_width=True, hide_index=True)
        else:
            st.write("No cost data available.")

    with st.expander("Practical interpretation"):
        if latest_ratio is None or not np.isfinite(latest_ratio):
            st.write("Ratio unavailable because mining-cost data did not load.")
        elif latest_ratio > 1:
            st.success(f"BTC price is above estimated total production cost by about {latest_ratio:.2f}x under the selected assumptions.")
        else:
            st.warning(f"BTC price is below estimated total production cost under the selected assumptions. Ratio: {latest_ratio:.2f}x.")

    render_manual()


if __name__ == "__main__":
    main()
