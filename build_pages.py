"""Prepare daily data and the local Plotly runtime for the GitHub Pages artifact."""
from pathlib import Path

import pandas as pd
import requests
from plotly.offline import get_plotlyjs
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from app import (
    COINMETRICS_API_URL, add_200w_ma, add_indicators, apply_cost_assumptions,
    build_opportunity_data, coinmetrics_to_cost_raw,
)

OUTPUT = Path(__file__).resolve().parent / "docs" / "generated"
METRICS = ["PriceUSD", "HashRate", "FeeTotNtv", "IssTotNtv", "volume_reported_spot_usd_1d"]


def fetch_daily():
    today = pd.Timestamp.now(tz="UTC").normalize()
    params = dict(assets="btc", metrics=",".join(METRICS), frequency="1d",
                  start_time="2013-01-01", end_time=(today - pd.Timedelta(days=1)).strftime("%Y-%m-%d"),
                  page_size=10000)
    records = []
    with requests.Session() as session:
        session.mount("https://", HTTPAdapter(max_retries=Retry(
            total=3, backoff_factor=1, status_forcelist=(429, 500, 502, 503, 504))))
        while True:
            response = session.get(COINMETRICS_API_URL, params=params, timeout=(15, 75))
            response.raise_for_status()
            page = response.json()
            records.extend(page["data"])
            if not page.get("next_page_token"):
                break
            params["next_page_token"] = page["next_page_token"]
    df = pd.DataFrame(records)
    df["time"] = pd.to_datetime(df["time"], utc=True)
    df[METRICS] = df[METRICS].apply(pd.to_numeric, errors="coerce")
    complete = (df[["PriceUSD", "HashRate", "IssTotNtv"]] > 0).all(axis=1) & (df["FeeTotNtv"] >= 0)
    df = df.loc[complete].sort_values("time").drop_duplicates("time").reset_index(drop=True)
    if len(df) < 3650 or today - df.time.iloc[-1] > pd.Timedelta(days=7):
        raise ValueError("Incomplete or stale source history. Keeping the previous Pages deployment.")
    return df


def snapshot(df):
    price = df.rename(columns={"PriceUSD": "close", "volume_reported_spot_usd_1d": "volume"})
    price = add_200w_ma(add_indicators(price, [20, 50, 200]))
    cost = apply_cost_assumptions(coinmetrics_to_cost_raw(df), price, "USD", "Historical",
                                  20, .05, 1.10, 60, True, False, 85000)
    # The score is linear in its clipped cost component. Export its endpoints
    # so the browser can change assumptions using the desktop weighting.
    frame = price[["time", "close", "volume", "MA20", "MA50", "MA200", "MA200W",
                   "RSI14", "BB_lower", "BB_upper"]].copy()
    frame = frame.merge(cost[["time", "total_production_cost_per_btc", "efficiency_j_per_th",
                              "fees_btc", "btc_issued_per_day", "hashrate_th_s"]], on="time", validate="one_to_one")
    for name, ratio in [("scoreLow", 1.50), ("scoreHigh", .70)]:
        score = build_opportunity_data(price, cost.assign(price_to_total_cost=ratio))
        frame[name] = frame.time.map(score.set_index("time").opportunity_score)
    frame["time"] = frame.time.dt.strftime("%Y-%m-%d")
    return frame.to_json(orient="split", index=False, double_precision=7)


if __name__ == "__main__":
    daily = fetch_daily()
    payload = snapshot(daily)
    OUTPUT.mkdir(exist_ok=True)
    (OUTPUT / "daily.json").write_text(payload, encoding="utf-8")
    (OUTPUT / "plotly.min.js").write_text(get_plotlyjs(), encoding="utf-8")
    print(f"Built {len(daily)} daily observations through {daily.time.iloc[-1]:%Y-%m-%d}")
