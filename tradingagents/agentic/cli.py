"""Command line interface for the paper/shadow agentic trading system."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from tradingagents.agentic.config import AgenticConfig
from tradingagents.agentic.pipeline import AgenticTradingPipeline
from tradingagents.agentic.storage import SQLiteStore

app = typer.Typer(
    name="agentic-trading",
    help="Paper/shadow agentic trading system for TradingAgents.",
    add_completion=True,
)
console = Console()


@app.command("init-db")
def init_db(
    db_path: Optional[Path] = typer.Option(None, "--db-path", help="SQLite database path."),
):
    config = AgenticConfig.from_env().with_overrides(db_path=db_path)
    store = SQLiteStore(config.db_path)
    store.initialize()
    store.ensure_portfolio_state("bootstrap", config.initial_cash)
    console.print(f"Initialized shadow database: {store.db_path}")


@app.command()
def run(
    tickers: Optional[str] = typer.Option(None, "--tickers", help="Comma-separated equity tickers."),
    date: Optional[str] = typer.Option(None, "--date", help="Analysis date in YYYY-MM-DD format."),
    db_path: Optional[Path] = typer.Option(None, "--db-path", help="SQLite database path."),
    skip_research: bool = typer.Option(
        False,
        "--skip-research",
        help="Skip TradingAgents LLM research and use momentum-only shadow policy.",
    ),
):
    config = AgenticConfig.from_env().with_overrides(
        tickers=tickers,
        db_path=db_path,
        research_enabled=False if skip_research else None,
    )
    summary = AgenticTradingPipeline(config).run(analysis_date=date)
    _print_run_summary(summary)


@app.command("shadow-report")
def shadow_report(
    db_path: Optional[Path] = typer.Option(None, "--db-path", help="SQLite database path."),
    limit: int = typer.Option(20, "--limit", help="Number of recent orders/audit events to show."),
):
    config = AgenticConfig.from_env().with_overrides(db_path=db_path)
    store = SQLiteStore(config.db_path)
    store.initialize()

    state = store.get_latest_portfolio_state()
    if state is None:
        console.print("No portfolio state found. Run `agentic-trading init-db` first.")
    else:
        console.print(f"Database: {store.db_path}")
        console.print(
            f"Portfolio as of {state.as_of}: cash=${state.cash:,.2f}, "
            f"equity=${state.equity_value:,.2f}, buying_power=${state.buying_power:,.2f}"
        )

    positions = store.list_positions()
    position_table = Table(title="Positions")
    position_table.add_column("Ticker")
    position_table.add_column("Quantity", justify="right")
    position_table.add_column("Avg Price", justify="right")
    position_table.add_column("Market Price", justify="right")
    position_table.add_column("Market Value", justify="right")
    for position in positions:
        position_table.add_row(
            position.ticker,
            f"{position.quantity:,.6f}",
            f"${position.avg_price:,.2f}",
            f"${position.market_price:,.2f}",
            f"${position.market_value:,.2f}",
        )
    console.print(position_table)

    order_table = Table(title="Recent Orders")
    for column in ("id", "ticker", "as_of", "side", "quantity", "limit_price", "notional", "status"):
        order_table.add_column(column)
    for order in store.list_recent_orders(limit):
        order_table.add_row(
            str(order["id"]),
            order["ticker"],
            order["as_of"],
            order["side"],
            f"{order['quantity']:,.6f}",
            f"${order['limit_price']:,.2f}",
            f"${order['notional']:,.2f}",
            order["status"],
        )
    console.print(order_table)


def _print_run_summary(summary) -> None:
    table = Table(title=f"Shadow Run {summary.analysis_date}")
    table.add_column("Ticker")
    table.add_column("Status")
    table.add_column("Momentum", justify="right")
    table.add_column("Research")
    table.add_column("Order")
    table.add_column("Reasons")
    for result in summary.results:
        table.add_row(
            result.ticker,
            result.status,
            "--" if result.momentum_score is None else f"{result.momentum_score:.2f}",
            result.research_rating or "--",
            "--" if result.order_id is None else str(result.order_id),
            "; ".join(result.reasons),
        )
    console.print(table)
    console.print(
        f"Filled={summary.filled_count} Blocked={summary.blocked_count} "
        f"Held={summary.held_count} DB={summary.db_path}"
    )


if __name__ == "__main__":
    app()
