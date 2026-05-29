"""Portfolio policy for converting signals into candidate shadow orders."""

from __future__ import annotations

from dataclasses import dataclass
from math import floor
from typing import List, Optional

from tradingagents.agentic.config import AgenticConfig
from tradingagents.agentic.models import (
    MarketSnapshot,
    MomentumScore,
    OrderSide,
    PortfolioState,
    ProposedOrder,
    ResearchDecision,
)


BULLISH_RATINGS = {"buy", "overweight"}


@dataclass(frozen=True)
class PolicyDecision:
    order: Optional[ProposedOrder]
    reasons: List[str]


class PortfolioPolicyEngine:
    def __init__(self, config: AgenticConfig):
        self.config = config

    def build_order(
        self,
        snapshot: MarketSnapshot,
        score: MomentumScore,
        portfolio: PortfolioState,
        research: ResearchDecision | None,
    ) -> PolicyDecision:
        reasons: List[str] = []
        if score.score < self.config.min_momentum_score:
            return PolicyDecision(None, [f"Momentum score {score.score:.2f} is below threshold"])

        if self.config.research_enabled:
            rating = (research.rating if research else "Hold").lower()
            if rating not in BULLISH_RATINGS:
                return PolicyDecision(None, [f"Research rating {research.rating if research else 'missing'} is not bullish"])
            reasons.append(f"Research rating {research.rating} passed bullish gate")
        else:
            reasons.append("Research gate skipped; using momentum-only shadow policy")

        score_scale = 1.0 if score.score >= self.config.strong_momentum_score else 0.5
        target_notional = min(self.config.max_order_notional * score_scale, portfolio.cash)
        if target_notional <= 0:
            return PolicyDecision(None, ["No cash available for a shadow buy"])

        limit_price = round(snapshot.price * (1.0 + self.config.limit_order_slippage_bps / 10_000.0), 4)
        quantity = target_notional / limit_price
        if not self.config.allow_fractional_shares:
            quantity = float(floor(quantity))
        quantity = round(quantity, 6)
        if quantity <= 0:
            return PolicyDecision(None, ["Position size rounds to zero shares"])

        notional = round(quantity * limit_price, 2)
        rationale = (
            f"Momentum score {score.score:.2f} ({score.band}); "
            f"limit price includes {self.config.limit_order_slippage_bps:g} bps cushion."
        )
        return PolicyDecision(
            ProposedOrder(
                ticker=snapshot.ticker,
                as_of=snapshot.as_of,
                side=OrderSide.BUY,
                quantity=quantity,
                limit_price=limit_price,
                notional=notional,
                rationale=rationale,
            ),
            reasons,
        )
