# Agentic Robinhood Shadow Trading System

This repository now contains two related tools:

- `tradingagents`: the original TradingAgents research CLI. Its upstream documentation is preserved in [TradingAgents.md](TradingAgents.md).
- `agentic-trading`: a paper/shadow agentic trading system that uses momentum scoring, TradingAgents research, deterministic risk checks, SQLite audit storage, and simulated fills.

`agentic-trading` does not place live Robinhood orders. The Robinhood MCP gateway is a disabled interface in v1, so all execution is local shadow accounting.

## Setup

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install .
copy .env.example .env
```

Edit `.env` and set at least one LLM provider key if you want TradingAgents research enabled, for example `OPENAI_API_KEY`. The shadow system also reads `AGENTIC_*` settings from `.env`.

Initialize the SQLite database:

```bash
agentic-trading init-db
```

Default database:

```text
~/.tradingagents/agentic/shadow.sqlite3
```

## Run A Shadow Trading Pass

Run with TradingAgents research enabled:

```bash
agentic-trading run --tickers AAPL,MSFT --date 2026-05-29
```

Run a local momentum-only pass without LLM research:

```bash
agentic-trading run --tickers AAPL,MSFT --date 2026-05-29 --skip-research
```

Inspect portfolio state, positions, and recent shadow orders:

```bash
agentic-trading shadow-report
```

Docker:

```bash
docker compose run --rm agentic-trading agentic-trading run --tickers AAPL,MSFT --date 2026-05-29
```

## What To Expect

Each run:

1. Loads daily equity market data.
2. Computes the momentum score from `report.md`:
   `0.40 P + 0.20 T + 0.10 R + 0.10 V + 0.15 S + 0.05 F`, scaled to 0-100.
3. Shortlists tickers above `AGENTIC_MIN_MOMENTUM_SCORE`.
4. Runs TradingAgents research unless `--skip-research` or `AGENTIC_RESEARCH_ENABLED=false` is set.
5. Builds long-only limit-buy shadow orders for bullish candidates.
6. Blocks orders that violate deterministic risk limits.
7. Simulates fills and updates the local SQLite shadow portfolio.
8. Writes audit events for holds, blocks, fills, errors, and run summaries.

SQLite tables include `audit_events`, `market_snapshots`, `momentum_scores`, `research_decisions`, `proposed_orders`, `fills`, `portfolio_positions`, and `portfolio_state`.

## Risk Limits

The default `.env.example` settings create a conservative $10,000 shadow account:

- `AGENTIC_EXECUTION_MODE=shadow`
- `AGENTIC_MAX_ORDER_NOTIONAL=500`
- `AGENTIC_MAX_POSITION_WEIGHT=0.05`
- `AGENTIC_DAILY_LOSS_LIMIT_PCT=0.02`
- `AGENTIC_MIN_AVG_VOLUME=500000`

Only long U.S. equity buy orders are supported. Sell, short, margin, options, crypto, futures, and live Robinhood placement are blocked in v1.

## Robinhood MCP Status

Robinhood Agentic Trading uses dedicated Agentic Accounts and gives users visibility into agent activity. This implementation intentionally stays in paper/shadow mode until live order review and placement can be added with explicit user gating, MCP contract tests, and separate acceptance tests.

## Tests

```bash
python -m pytest tests/test_agentic_*.py
python -m pytest
python -m tradingagents.agentic.cli --help
```
