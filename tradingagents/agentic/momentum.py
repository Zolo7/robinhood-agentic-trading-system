"""Momentum feature engineering and scoring."""

from __future__ import annotations

import math

import pandas as pd

from tradingagents.agentic.models import MomentumFeatures, MomentumScore


def clamp(value: float, lower: float = -1.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, float(value)))


def score_band(score: float) -> str:
    if score < 40:
        return "bearish"
    if score < 60:
        return "neutral"
    if score < 75:
        return "research_candidate"
    if score < 90:
        return "strong_candidate"
    return "high_conviction_high_risk"


def score_momentum(ticker: str, as_of: str, features: MomentumFeatures) -> MomentumScore:
    z_score = (
        0.40 * features.price_trend
        + 0.20 * features.technical_state
        + 0.10 * features.risk_penalty
        + 0.10 * features.volume_confirmation
        + 0.15 * features.sentiment_attention
        + 0.05 * features.fundamental_factor
    )
    score = 100.0 / (1.0 + math.exp(-1.6 * z_score))
    return MomentumScore(
        ticker=ticker,
        as_of=as_of,
        features=features,
        z_score=z_score,
        score=score,
        band=score_band(score),
    )


def _latest_rsi(close: pd.Series, window: int = 14) -> float:
    if len(close) < 2:
        return 50.0
    delta = close.diff().dropna()
    gains = delta.clip(lower=0).tail(window).mean()
    losses = (-delta.clip(upper=0)).tail(window).mean()
    if losses == 0 and gains == 0:
        return 50.0
    if losses == 0:
        return 100.0
    rs = gains / losses
    return 100.0 - (100.0 / (1.0 + rs))


def compute_features_from_history(
    history: pd.DataFrame,
    sentiment_attention: float = 0.0,
    fundamental_factor: float = 0.0,
) -> MomentumFeatures:
    if "Close" not in history or "Volume" not in history:
        raise ValueError("history must include Close and Volume columns")

    close = history["Close"].astype(float).dropna()
    volume = history["Volume"].astype(float).dropna()
    if len(close) < 2:
        raise ValueError("at least two close prices are required")

    lookback_index = max(0, len(close) - 21)
    price_return = (close.iloc[-1] / close.iloc[lookback_index]) - 1.0
    price_trend = clamp(price_return / 0.20)

    short_ma = close.tail(min(10, len(close))).mean()
    long_ma = close.tail(min(30, len(close))).mean()
    ma_component = 0.0 if long_ma == 0 else clamp(((short_ma - long_ma) / long_ma) / 0.05)
    rsi_component = clamp((_latest_rsi(close) - 50.0) / 50.0)
    technical_state = clamp((ma_component + rsi_component) / 2.0)

    returns = close.pct_change().dropna()
    annualized_vol = float(returns.tail(20).std() * math.sqrt(252)) if len(returns) else 0.0
    rolling_high = close.tail(min(30, len(close))).max()
    drawdown = 0.0 if rolling_high == 0 else (close.iloc[-1] / rolling_high) - 1.0
    risk_penalty = clamp(1.0 - (annualized_vol / 0.60) + drawdown)

    avg_volume = volume.tail(min(20, len(volume))).mean() if len(volume) else 0.0
    latest_volume = volume.iloc[-1] if len(volume) else 0.0
    volume_confirmation = 0.0 if avg_volume == 0 else clamp(((latest_volume / avg_volume) - 1.0) / 1.5)

    return MomentumFeatures(
        price_trend=price_trend,
        technical_state=technical_state,
        risk_penalty=risk_penalty,
        volume_confirmation=volume_confirmation,
        sentiment_attention=clamp(sentiment_attention),
        fundamental_factor=clamp(fundamental_factor),
    )
