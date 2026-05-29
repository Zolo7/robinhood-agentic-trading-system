"""End-to-end paper/shadow agentic trading pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Optional, Sequence, Tuple

import pandas as pd

from tradingagents.agentic.config import AgenticConfig, parse_tickers
from tradingagents.agentic.execution import ShadowExecutionError, ShadowExecutionGateway, apply_fill_to_portfolio
from tradingagents.agentic.market_data import fetch_market_data
from tradingagents.agentic.models import (
    MarketSnapshot,
    MomentumScore,
    OrderStatus,
    ResearchDecision,
    TickerResult,
)
from tradingagents.agentic.momentum import compute_features_from_history, score_momentum
from tradingagents.agentic.policy import PortfolioPolicyEngine
from tradingagents.agentic.research import TradingAgentsResearchAdapter
from tradingagents.agentic.risk import RiskEngine
from tradingagents.agentic.storage import SQLiteStore

MarketLoader = Callable[[str, str, int], Tuple[MarketSnapshot, pd.DataFrame]]


@dataclass(frozen=True)
class RunSummary:
    analysis_date: str
    db_path: Path
    results: List[TickerResult]

    @property
    def filled_count(self) -> int:
        return sum(1 for result in self.results if result.status == "filled")

    @property
    def blocked_count(self) -> int:
        return sum(1 for result in self.results if result.status == "blocked")

    @property
    def held_count(self) -> int:
        return sum(1 for result in self.results if result.status == "held")


class AgenticTradingPipeline:
    def __init__(
        self,
        config: AgenticConfig,
        store: SQLiteStore | None = None,
        market_loader: MarketLoader | None = None,
        research_adapter: TradingAgentsResearchAdapter | None = None,
    ):
        self.config = config.validated()
        self.store = store or SQLiteStore(self.config.db_path)
        self.market_loader = market_loader or fetch_market_data
        self.research_adapter = research_adapter or TradingAgentsResearchAdapter(self.config)
        self.policy = PortfolioPolicyEngine(self.config)
        self.risk = RiskEngine(self.config)
        self.execution = ShadowExecutionGateway(self.config)

    def initialize(self, analysis_date: str | None = None) -> None:
        self.store.initialize()
        self.store.ensure_portfolio_state(analysis_date or _today(), self.config.initial_cash)

    def run(self, tickers: Sequence[str] | None = None, analysis_date: str | None = None) -> RunSummary:
        run_date = analysis_date or _today()
        ticker_list = parse_tickers(tickers or self.config.tickers)
        self.initialize(run_date)
        self.store.record_audit(
            "run_started",
            {
                "analysis_date": run_date,
                "tickers": ticker_list,
                "execution_mode": self.config.execution_mode,
                "research_enabled": self.config.research_enabled,
            },
        )

        scored: List[Tuple[MarketSnapshot, pd.DataFrame, MomentumScore]] = []
        results: List[TickerResult] = []
        for ticker in ticker_list:
            try:
                snapshot, history = self.market_loader(ticker, run_date, self.config.lookback_days)
                self.store.record_market_snapshot(snapshot)
                features = compute_features_from_history(history)
                score = score_momentum(ticker=snapshot.ticker, as_of=snapshot.as_of, features=features)
                self.store.record_momentum_score(score)
                scored.append((snapshot, history, score))
            except Exception as exc:
                self.store.record_audit("ticker_error", {"error": str(exc)}, ticker=ticker)
                results.append(TickerResult(ticker=ticker, status="error", reasons=[str(exc)]))

        eligible = [item for item in scored if item[2].score >= self.config.min_momentum_score]
        eligible.sort(key=lambda item: item[2].score, reverse=True)
        selected = eligible[: self.config.max_candidates]
        selected_tickers = {snapshot.ticker for snapshot, _, _ in selected}

        for snapshot, _, score in scored:
            if score.score < self.config.min_momentum_score:
                reason = f"Momentum score {score.score:.2f} below threshold {self.config.min_momentum_score:.2f}"
                self.store.record_audit("ticker_held", {"reason": reason, "score": score}, ticker=snapshot.ticker)
                results.append(TickerResult(ticker=snapshot.ticker, status="held", momentum_score=score.score, reasons=[reason]))
            elif snapshot.ticker not in selected_tickers:
                reason = f"Excluded by max_candidates={self.config.max_candidates}"
                self.store.record_audit("ticker_held", {"reason": reason, "score": score}, ticker=snapshot.ticker)
                results.append(TickerResult(ticker=snapshot.ticker, status="held", momentum_score=score.score, reasons=[reason]))

        for snapshot, _, score in selected:
            results.append(self._process_candidate(snapshot, score, run_date))

        self.store.record_audit(
            "run_completed",
            {
                "analysis_date": run_date,
                "filled": sum(1 for result in results if result.status == "filled"),
                "blocked": sum(1 for result in results if result.status == "blocked"),
                "held": sum(1 for result in results if result.status == "held"),
                "errors": sum(1 for result in results if result.status == "error"),
            },
        )
        return RunSummary(analysis_date=run_date, db_path=self.store.db_path, results=results)

    def _process_candidate(self, snapshot: MarketSnapshot, score: MomentumScore, run_date: str) -> TickerResult:
        research: Optional[ResearchDecision] = None
        try:
            if self.config.research_enabled:
                research = self.research_adapter.research(snapshot.ticker, run_date)
                self.store.record_research_decision(research)
            else:
                research = ResearchDecision(
                    ticker=snapshot.ticker,
                    as_of=run_date,
                    rating="NotRun",
                    raw_decision="TradingAgents research skipped; momentum-only shadow policy active.",
                )
                self.store.record_research_decision(research)

            portfolio = self.store.get_latest_portfolio_state()
            if portfolio is None:
                raise ValueError("portfolio state has not been initialized")
            policy_decision = self.policy.build_order(snapshot, score, portfolio, research)
            if policy_decision.order is None:
                self.store.record_audit(
                    "ticker_held",
                    {"reasons": policy_decision.reasons, "score": score, "research": research},
                    ticker=snapshot.ticker,
                )
                return TickerResult(
                    ticker=snapshot.ticker,
                    status="held",
                    momentum_score=score.score,
                    research_rating=research.rating,
                    reasons=policy_decision.reasons,
                )

            positions = {position.ticker: position for position in self.store.list_positions()}
            risk_result = self.risk.evaluate(policy_decision.order, snapshot, portfolio, positions)
            order_id = self.store.record_order(policy_decision.order, risk_result)
            if not risk_result.approved:
                self.store.update_order_status(order_id, OrderStatus.BLOCKED, risk_result)
                self.store.record_audit(
                    "order_blocked",
                    {"order_id": order_id, "order": policy_decision.order, "risk": risk_result},
                    ticker=snapshot.ticker,
                )
                return TickerResult(
                    ticker=snapshot.ticker,
                    status="blocked",
                    momentum_score=score.score,
                    research_rating=research.rating,
                    order_id=order_id,
                    reasons=risk_result.reasons,
                )

            try:
                fill = self.execution.execute(order_id, policy_decision.order, snapshot)
            except ShadowExecutionError as exc:
                self.store.update_order_status(order_id, OrderStatus.NOT_FILLED, risk_result)
                self.store.record_audit("order_not_filled", {"order_id": order_id, "error": str(exc)}, ticker=snapshot.ticker)
                return TickerResult(
                    ticker=snapshot.ticker,
                    status="not_filled",
                    momentum_score=score.score,
                    research_rating=research.rating,
                    order_id=order_id,
                    reasons=[str(exc)],
                )

            fill_id = self.store.record_fill(fill)
            apply_fill_to_portfolio(self.store, fill)
            self.store.update_order_status(order_id, OrderStatus.FILLED, risk_result)
            self.store.record_audit(
                "order_filled",
                {"order_id": order_id, "fill_id": fill_id, "fill": fill},
                ticker=snapshot.ticker,
            )
            return TickerResult(
                ticker=snapshot.ticker,
                status="filled",
                momentum_score=score.score,
                research_rating=research.rating,
                order_id=order_id,
                fill_id=fill_id,
            )
        except Exception as exc:
            self.store.record_audit("ticker_error", {"error": str(exc)}, ticker=snapshot.ticker)
            return TickerResult(
                ticker=snapshot.ticker,
                status="error",
                momentum_score=score.score,
                research_rating=research.rating if research else None,
                reasons=[str(exc)],
            )


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")
