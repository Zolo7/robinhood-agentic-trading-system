"""Shadow execution gateway and portfolio accounting."""

from __future__ import annotations

from tradingagents.agentic.config import AgenticConfig
from tradingagents.agentic.models import Fill, MarketSnapshot, OrderSide, PortfolioState, Position, ProposedOrder
from tradingagents.agentic.storage import SQLiteStore


class ShadowExecutionError(RuntimeError):
    pass


class ShadowExecutionGateway:
    def __init__(self, config: AgenticConfig):
        self.config = config

    def execute(self, order_id: int, order: ProposedOrder, snapshot: MarketSnapshot) -> Fill:
        if order.side is not OrderSide.BUY:
            raise ShadowExecutionError("Shadow gateway only supports buy orders in v1")

        simulated_price = round(snapshot.price * (1.0 + self.config.shadow_fill_slippage_bps / 10_000.0), 4)
        if simulated_price > order.limit_price:
            raise ShadowExecutionError("Limit order did not fill in shadow simulation")

        notional = round(order.quantity * simulated_price, 2)
        return Fill(
            order_id=order_id,
            ticker=order.ticker,
            as_of=order.as_of,
            side=order.side,
            quantity=order.quantity,
            fill_price=simulated_price,
            notional=notional,
            slippage_bps=self.config.shadow_fill_slippage_bps,
        )


def apply_fill_to_portfolio(store: SQLiteStore, fill: Fill) -> PortfolioState:
    current = store.get_latest_portfolio_state()
    if current is None:
        raise ShadowExecutionError("Portfolio state is not initialized")

    existing = store.get_position(fill.ticker)
    if existing is None:
        new_position = Position(
            ticker=fill.ticker,
            quantity=fill.quantity,
            avg_price=fill.fill_price,
            market_price=fill.fill_price,
        )
    else:
        total_qty = existing.quantity + fill.quantity
        if total_qty <= 0:
            raise ShadowExecutionError("Shadow position quantity cannot be non-positive after buy")
        avg_price = ((existing.quantity * existing.avg_price) + fill.notional) / total_qty
        new_position = Position(
            ticker=fill.ticker,
            quantity=round(total_qty, 6),
            avg_price=round(avg_price, 6),
            market_price=fill.fill_price,
        )

    store.upsert_position(new_position)
    positions_value = sum(position.market_value for position in store.list_positions())
    new_cash = round(current.cash - fill.notional, 2)
    state = PortfolioState(
        as_of=fill.as_of,
        cash=new_cash,
        equity_value=round(new_cash + positions_value, 2),
        buying_power=new_cash,
        daily_pnl=current.daily_pnl,
    )
    store.set_portfolio_state(state)
    return state
