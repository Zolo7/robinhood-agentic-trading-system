"""Deterministic risk controls for paper/shadow orders."""

from __future__ import annotations

from typing import Dict

from tradingagents.agentic.config import AgenticConfig
from tradingagents.agentic.models import (
    MarketSnapshot,
    OrderSide,
    PortfolioState,
    Position,
    ProposedOrder,
    RiskResult,
)


class RiskEngine:
    def __init__(self, config: AgenticConfig):
        self.config = config

    def evaluate(
        self,
        order: ProposedOrder,
        snapshot: MarketSnapshot,
        portfolio: PortfolioState,
        positions: Dict[str, Position],
    ) -> RiskResult:
        reasons = []
        checks = {
            "execution_mode": self.config.execution_mode,
            "asset_type": snapshot.asset_type,
            "tradable": snapshot.tradable,
            "side": order.side.value,
            "order_notional": order.notional,
            "buying_power": portfolio.buying_power,
            "avg_volume_20d": snapshot.avg_volume_20d,
            "daily_pnl": portfolio.daily_pnl,
        }

        if self.config.execution_mode != "shadow":
            reasons.append("Only shadow execution is supported in v1")
        if snapshot.asset_type != "equity":
            reasons.append("Only equities are allowed")
        if not snapshot.tradable:
            reasons.append("Security is marked non-tradable")
        if order.side is not OrderSide.BUY:
            reasons.append("Sell, short, margin, options, and derivatives orders are blocked in v1")
        if order.quantity <= 0:
            reasons.append("Quantity must be positive")
        if order.notional > self.config.max_order_notional + 0.01:
            reasons.append("Order exceeds max_order_notional")
        if order.notional > portfolio.buying_power + 0.01:
            reasons.append("Insufficient shadow buying power")
        if snapshot.avg_volume_20d < self.config.min_avg_volume:
            reasons.append("Average 20-day volume is below liquidity threshold")

        loss_limit = portfolio.equity_value * self.config.daily_loss_limit_pct
        checks["daily_loss_limit"] = loss_limit
        if portfolio.daily_pnl <= -loss_limit:
            reasons.append("Daily loss limit reached")

        current_position = positions.get(order.ticker)
        current_value = current_position.market_value if current_position else 0.0
        projected_value = current_value + order.notional
        equity_base = max(portfolio.equity_value, portfolio.cash, 1.0)
        max_position_value = equity_base * self.config.max_position_weight
        checks["current_position_value"] = current_value
        checks["projected_position_value"] = projected_value
        checks["max_position_value"] = max_position_value
        if projected_value > max_position_value + 0.01:
            reasons.append("Projected position exceeds max_position_weight")

        return RiskResult(approved=not reasons, reasons=reasons, checks=checks)
