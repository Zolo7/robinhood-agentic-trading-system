"""Shared domain models for the paper/shadow agentic trading system."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderStatus(str, Enum):
    PROPOSED = "proposed"
    BLOCKED = "blocked"
    HELD = "held"
    FILLED = "filled"
    NOT_FILLED = "not_filled"


@dataclass(frozen=True)
class MarketSnapshot:
    ticker: str
    as_of: str
    price: float
    open: float
    high: float
    low: float
    close: float
    volume: float
    avg_volume_20d: float
    volatility_20d: float
    asset_type: str = "equity"
    tradable: bool = True
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MomentumFeatures:
    price_trend: float
    technical_state: float
    risk_penalty: float
    volume_confirmation: float
    sentiment_attention: float = 0.0
    fundamental_factor: float = 0.0


@dataclass(frozen=True)
class MomentumScore:
    ticker: str
    as_of: str
    features: MomentumFeatures
    z_score: float
    score: float
    band: str


@dataclass(frozen=True)
class ResearchDecision:
    ticker: str
    as_of: str
    rating: str
    raw_decision: str
    state: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PortfolioState:
    as_of: str
    cash: float
    equity_value: float
    buying_power: float
    daily_pnl: float = 0.0


@dataclass(frozen=True)
class Position:
    ticker: str
    quantity: float
    avg_price: float
    market_price: float

    @property
    def market_value(self) -> float:
        return self.quantity * self.market_price


@dataclass(frozen=True)
class ProposedOrder:
    ticker: str
    as_of: str
    side: OrderSide
    quantity: float
    limit_price: float
    notional: float
    rationale: str
    status: OrderStatus = OrderStatus.PROPOSED


@dataclass(frozen=True)
class RiskResult:
    approved: bool
    reasons: List[str]
    checks: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Fill:
    order_id: int
    ticker: str
    as_of: str
    side: OrderSide
    quantity: float
    fill_price: float
    notional: float
    slippage_bps: float


@dataclass(frozen=True)
class TickerResult:
    ticker: str
    status: str
    momentum_score: Optional[float] = None
    research_rating: Optional[str] = None
    order_id: Optional[int] = None
    fill_id: Optional[int] = None
    reasons: List[str] = field(default_factory=list)
