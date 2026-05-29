"""Market data loading for the shadow system."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Tuple

import pandas as pd

from tradingagents.agentic.models import MarketSnapshot


def fetch_market_data(ticker: str, analysis_date: str, lookback_days: int = 120) -> Tuple[MarketSnapshot, pd.DataFrame]:
    try:
        import yfinance as yf
    except ImportError as exc:
        raise RuntimeError("yfinance is required for live market data loading; install the project dependencies") from exc

    end_date = datetime.strptime(analysis_date, "%Y-%m-%d") + timedelta(days=1)
    start_date = end_date - timedelta(days=max(lookback_days * 2, 45))

    history = yf.Ticker(ticker).history(
        start=start_date.strftime("%Y-%m-%d"),
        end=end_date.strftime("%Y-%m-%d"),
        auto_adjust=False,
    )
    if history.empty:
        raise ValueError(f"No market data returned for {ticker} through {analysis_date}")

    history = history.dropna(subset=["Close"])
    if history.empty:
        raise ValueError(f"No close prices returned for {ticker} through {analysis_date}")

    latest = history.iloc[-1]
    latest_index = history.index[-1]
    as_of = latest_index.date().isoformat() if hasattr(latest_index, "date") else analysis_date
    close = history["Close"].astype(float)
    returns = close.pct_change().dropna()
    volatility = float(returns.tail(20).std() * (252 ** 0.5)) if len(returns) else 0.0
    avg_volume = float(history["Volume"].astype(float).tail(min(20, len(history))).mean())

    snapshot = MarketSnapshot(
        ticker=ticker,
        as_of=as_of,
        price=float(latest["Close"]),
        open=float(latest.get("Open", latest["Close"])),
        high=float(latest.get("High", latest["Close"])),
        low=float(latest.get("Low", latest["Close"])),
        close=float(latest["Close"]),
        volume=float(latest.get("Volume", 0.0)),
        avg_volume_20d=avg_volume,
        volatility_20d=volatility,
        raw={
            "source": "yfinance",
            "requested_as_of": analysis_date,
            "rows": int(len(history)),
        },
    )
    return snapshot, history
