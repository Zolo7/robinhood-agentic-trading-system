"""TradingAgents adapter used by the agentic shadow pipeline."""

from __future__ import annotations

from typing import Any, Dict

from tradingagents.agentic.config import AgenticConfig
from tradingagents.agentic.models import ResearchDecision
from tradingagents.default_config import DEFAULT_CONFIG


_RATINGS = ("Buy", "Overweight", "Hold", "Underweight", "Sell")


def parse_research_rating(text: str, default: str = "Hold") -> str:
    for line in text.splitlines():
        lower = line.lower()
        if "rating" in lower and (":" in line or "-" in line):
            _, _, tail = line.replace("-", ":", 1).partition(":")
            candidate = tail.strip().strip("*").split()[0] if tail.strip() else ""
            for rating in _RATINGS:
                if candidate.lower().strip("*:.,") == rating.lower():
                    return rating
    for word in text.replace("*", " ").replace(":", " ").replace(",", " ").split():
        for rating in _RATINGS:
            if word.lower().strip(".") == rating.lower():
                return rating
    return default


class TradingAgentsResearchAdapter:
    def __init__(self, config: AgenticConfig):
        self.config = config

    def research(self, ticker: str, analysis_date: str) -> ResearchDecision:
        if not self.config.research_enabled:
            return ResearchDecision(
                ticker=ticker,
                as_of=analysis_date,
                rating="NotRun",
                raw_decision="TradingAgents research skipped by configuration.",
            )

        from tradingagents.graph.trading_graph import TradingAgentsGraph

        graph_config: Dict[str, Any] = DEFAULT_CONFIG.copy()
        graph_config["max_debate_rounds"] = self.config.max_debate_rounds
        graph_config["max_risk_discuss_rounds"] = self.config.max_risk_rounds

        graph = TradingAgentsGraph(
            selected_analysts=list(self.config.selected_analysts),
            config=graph_config,
            debug=False,
        )
        final_state, decision = graph.propagate(ticker, analysis_date, asset_type="stock")
        raw = final_state.get("final_trade_decision", str(decision))
        rating = parse_research_rating(raw, default=str(decision or "Hold"))
        return ResearchDecision(
            ticker=ticker,
            as_of=analysis_date,
            rating=rating,
            raw_decision=raw,
            state={
                "investment_plan": final_state.get("investment_plan"),
                "trader_investment_plan": final_state.get("trader_investment_plan"),
            },
        )
