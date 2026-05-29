"""SQLite storage for the paper/shadow trading system."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from tradingagents.agentic.models import (
    Fill,
    MarketSnapshot,
    MomentumScore,
    OrderStatus,
    PortfolioState,
    Position,
    ProposedOrder,
    ResearchDecision,
    RiskResult,
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _json_default(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if is_dataclass(value):
        return asdict(value)
    return str(value)


def _json_dumps(payload: Any) -> str:
    return json.dumps(payload, default=_json_default, sort_keys=True)


class SQLiteStore:
    def __init__(self, db_path: Path | str):
        self.db_path = Path(db_path).expanduser()

    def connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def initialize(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS audit_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    ticker TEXT,
                    payload_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS market_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticker TEXT NOT NULL,
                    as_of TEXT NOT NULL,
                    price REAL NOT NULL,
                    open REAL NOT NULL,
                    high REAL NOT NULL,
                    low REAL NOT NULL,
                    close REAL NOT NULL,
                    volume REAL NOT NULL,
                    avg_volume_20d REAL NOT NULL,
                    volatility_20d REAL NOT NULL,
                    asset_type TEXT NOT NULL,
                    tradable INTEGER NOT NULL,
                    raw_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS momentum_scores (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticker TEXT NOT NULL,
                    as_of TEXT NOT NULL,
                    price_trend REAL NOT NULL,
                    technical_state REAL NOT NULL,
                    risk_penalty REAL NOT NULL,
                    volume_confirmation REAL NOT NULL,
                    sentiment_attention REAL NOT NULL,
                    fundamental_factor REAL NOT NULL,
                    z_score REAL NOT NULL,
                    score REAL NOT NULL,
                    band TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS research_decisions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticker TEXT NOT NULL,
                    as_of TEXT NOT NULL,
                    rating TEXT NOT NULL,
                    raw_decision TEXT NOT NULL,
                    state_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS proposed_orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticker TEXT NOT NULL,
                    as_of TEXT NOT NULL,
                    side TEXT NOT NULL,
                    quantity REAL NOT NULL,
                    limit_price REAL NOT NULL,
                    notional REAL NOT NULL,
                    status TEXT NOT NULL,
                    rationale TEXT NOT NULL,
                    risk_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS fills (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_id INTEGER NOT NULL,
                    ticker TEXT NOT NULL,
                    as_of TEXT NOT NULL,
                    side TEXT NOT NULL,
                    quantity REAL NOT NULL,
                    fill_price REAL NOT NULL,
                    notional REAL NOT NULL,
                    slippage_bps REAL NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(order_id) REFERENCES proposed_orders(id)
                );

                CREATE TABLE IF NOT EXISTS portfolio_positions (
                    ticker TEXT PRIMARY KEY,
                    quantity REAL NOT NULL,
                    avg_price REAL NOT NULL,
                    market_price REAL NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS portfolio_state (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    as_of TEXT NOT NULL,
                    cash REAL NOT NULL,
                    equity_value REAL NOT NULL,
                    buying_power REAL NOT NULL,
                    daily_pnl REAL NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )

    def record_audit(self, event_type: str, payload: Any, ticker: str | None = None) -> int:
        with self.connect() as conn:
            cursor = conn.execute(
                "INSERT INTO audit_events (ts, event_type, ticker, payload_json) VALUES (?, ?, ?, ?)",
                (utc_now(), event_type, ticker, _json_dumps(payload)),
            )
            return int(cursor.lastrowid)

    def record_market_snapshot(self, snapshot: MarketSnapshot) -> int:
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO market_snapshots (
                    ticker, as_of, price, open, high, low, close, volume,
                    avg_volume_20d, volatility_20d, asset_type, tradable,
                    raw_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot.ticker,
                    snapshot.as_of,
                    snapshot.price,
                    snapshot.open,
                    snapshot.high,
                    snapshot.low,
                    snapshot.close,
                    snapshot.volume,
                    snapshot.avg_volume_20d,
                    snapshot.volatility_20d,
                    snapshot.asset_type,
                    int(snapshot.tradable),
                    _json_dumps(snapshot.raw),
                    utc_now(),
                ),
            )
            return int(cursor.lastrowid)

    def record_momentum_score(self, score: MomentumScore) -> int:
        f = score.features
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO momentum_scores (
                    ticker, as_of, price_trend, technical_state, risk_penalty,
                    volume_confirmation, sentiment_attention, fundamental_factor,
                    z_score, score, band, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    score.ticker,
                    score.as_of,
                    f.price_trend,
                    f.technical_state,
                    f.risk_penalty,
                    f.volume_confirmation,
                    f.sentiment_attention,
                    f.fundamental_factor,
                    score.z_score,
                    score.score,
                    score.band,
                    utc_now(),
                ),
            )
            return int(cursor.lastrowid)

    def record_research_decision(self, decision: ResearchDecision) -> int:
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO research_decisions (
                    ticker, as_of, rating, raw_decision, state_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    decision.ticker,
                    decision.as_of,
                    decision.rating,
                    decision.raw_decision,
                    _json_dumps(decision.state),
                    utc_now(),
                ),
            )
            return int(cursor.lastrowid)

    def record_order(self, order: ProposedOrder, risk: RiskResult | None = None) -> int:
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO proposed_orders (
                    ticker, as_of, side, quantity, limit_price, notional,
                    status, rationale, risk_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    order.ticker,
                    order.as_of,
                    order.side.value,
                    order.quantity,
                    order.limit_price,
                    order.notional,
                    order.status.value,
                    order.rationale,
                    _json_dumps(risk or {}),
                    utc_now(),
                ),
            )
            return int(cursor.lastrowid)

    def update_order_status(self, order_id: int, status: OrderStatus, risk: RiskResult | None = None) -> None:
        with self.connect() as conn:
            if risk is None:
                conn.execute("UPDATE proposed_orders SET status = ? WHERE id = ?", (status.value, order_id))
            else:
                conn.execute(
                    "UPDATE proposed_orders SET status = ?, risk_json = ? WHERE id = ?",
                    (status.value, _json_dumps(risk), order_id),
                )

    def record_fill(self, fill: Fill) -> int:
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO fills (
                    order_id, ticker, as_of, side, quantity, fill_price,
                    notional, slippage_bps, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    fill.order_id,
                    fill.ticker,
                    fill.as_of,
                    fill.side.value,
                    fill.quantity,
                    fill.fill_price,
                    fill.notional,
                    fill.slippage_bps,
                    utc_now(),
                ),
            )
            return int(cursor.lastrowid)

    def ensure_portfolio_state(self, as_of: str, initial_cash: float) -> PortfolioState:
        current = self.get_latest_portfolio_state()
        if current is not None:
            return current
        state = PortfolioState(as_of=as_of, cash=initial_cash, equity_value=initial_cash, buying_power=initial_cash)
        self.set_portfolio_state(state)
        return state

    def set_portfolio_state(self, state: PortfolioState) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO portfolio_state (
                    as_of, cash, equity_value, buying_power, daily_pnl, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (state.as_of, state.cash, state.equity_value, state.buying_power, state.daily_pnl, utc_now()),
            )

    def get_latest_portfolio_state(self) -> Optional[PortfolioState]:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM portfolio_state ORDER BY id DESC LIMIT 1").fetchone()
        if row is None:
            return None
        return PortfolioState(
            as_of=row["as_of"],
            cash=float(row["cash"]),
            equity_value=float(row["equity_value"]),
            buying_power=float(row["buying_power"]),
            daily_pnl=float(row["daily_pnl"]),
        )

    def upsert_position(self, position: Position) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO portfolio_positions (ticker, quantity, avg_price, market_price, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(ticker) DO UPDATE SET
                    quantity = excluded.quantity,
                    avg_price = excluded.avg_price,
                    market_price = excluded.market_price,
                    updated_at = excluded.updated_at
                """,
                (position.ticker, position.quantity, position.avg_price, position.market_price, utc_now()),
            )

    def get_position(self, ticker: str) -> Optional[Position]:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM portfolio_positions WHERE ticker = ?", (ticker,)).fetchone()
        if row is None:
            return None
        return Position(
            ticker=row["ticker"],
            quantity=float(row["quantity"]),
            avg_price=float(row["avg_price"]),
            market_price=float(row["market_price"]),
        )

    def list_positions(self) -> List[Position]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM portfolio_positions ORDER BY ticker").fetchall()
        return [
            Position(
                ticker=row["ticker"],
                quantity=float(row["quantity"]),
                avg_price=float(row["avg_price"]),
                market_price=float(row["market_price"]),
            )
            for row in rows
        ]

    def list_recent_orders(self, limit: int = 20) -> List[Dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM proposed_orders ORDER BY id DESC LIMIT ?",
                (int(limit),),
            ).fetchall()
        return [dict(row) for row in rows]

    def count_rows(self, table: str) -> int:
        allowed = {
            "audit_events",
            "market_snapshots",
            "momentum_scores",
            "research_decisions",
            "proposed_orders",
            "fills",
            "portfolio_positions",
            "portfolio_state",
        }
        if table not in allowed:
            raise ValueError(f"Unsupported table: {table}")
        with self.connect() as conn:
            row = conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()
        return int(row["n"])

    def latest_audit_events(self, limit: int = 20) -> List[Dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM audit_events ORDER BY id DESC LIMIT ?",
                (int(limit),),
            ).fetchall()
        return [dict(row) for row in rows]

    def refresh_equity_value(self, as_of: str) -> PortfolioState:
        current = self.get_latest_portfolio_state()
        if current is None:
            raise ValueError("portfolio state has not been initialized")
        positions_value = sum(position.market_value for position in self.list_positions())
        state = PortfolioState(
            as_of=as_of,
            cash=current.cash,
            equity_value=current.cash + positions_value,
            buying_power=current.cash,
            daily_pnl=current.daily_pnl,
        )
        self.set_portfolio_state(state)
        return state

    def replace_positions(self, positions: Iterable[Position]) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM portfolio_positions")
        for position in positions:
            self.upsert_position(position)
