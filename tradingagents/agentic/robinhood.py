"""Disabled Robinhood MCP gateway placeholder for v1 shadow mode."""

from __future__ import annotations

from typing import Any

from tradingagents.agentic.models import ProposedOrder


class LiveTradingDisabledError(RuntimeError):
    pass


class RobinhoodMCPGateway:
    """Interface placeholder for future Robinhood MCP integration.

    v1 deliberately refuses live review or placement calls. The shadow pipeline
    can be extended behind this interface once live trading is explicitly gated.
    """

    def review_equity_order(self, order: ProposedOrder) -> Any:
        raise LiveTradingDisabledError("Robinhood MCP review is disabled in paper/shadow v1")

    def place_equity_order(self, order: ProposedOrder) -> Any:
        raise LiveTradingDisabledError("Robinhood MCP live order placement is disabled in paper/shadow v1")
