"""Environment-backed configuration for the agentic shadow system."""

from __future__ import annotations

import os
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Iterable, Tuple


def parse_csv(raw: str | Iterable[str] | None, *, uppercase: bool = False) -> Tuple[str, ...]:
    if raw is None:
        return ()
    if isinstance(raw, str):
        parts = raw.replace(";", ",").split(",")
    else:
        parts = list(raw)
    values = []
    for part in parts:
        value = str(part).strip()
        if not value:
            continue
        if uppercase:
            value = value.upper()
        if len(value) > 32 or not all(ch.isalnum() or ch in ".-_^" for ch in value):
            raise ValueError(f"Invalid comma-separated value: {value}")
        values.append(value)
    return tuple(dict.fromkeys(values))


def parse_tickers(raw: str | Iterable[str] | None) -> Tuple[str, ...]:
    return parse_csv(raw, uppercase=True)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return float(raw)


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return int(raw)


@dataclass(frozen=True)
class AgenticConfig:
    tickers: Tuple[str, ...] = ("SPY", "QQQ")
    db_path: Path = Path("~/.tradingagents/agentic/shadow.sqlite3")
    initial_cash: float = 10_000.0
    execution_mode: str = "shadow"
    research_enabled: bool = True
    selected_analysts: Tuple[str, ...] = ("market", "social", "news", "fundamentals")
    max_debate_rounds: int = 1
    max_risk_rounds: int = 1
    max_candidates: int = 5
    min_momentum_score: float = 60.0
    strong_momentum_score: float = 75.0
    max_order_notional: float = 500.0
    max_position_weight: float = 0.05
    daily_loss_limit_pct: float = 0.02
    min_avg_volume: float = 500_000.0
    limit_order_slippage_bps: float = 10.0
    shadow_fill_slippage_bps: float = 5.0
    allow_fractional_shares: bool = True
    lookback_days: int = 120

    @classmethod
    def from_env(cls) -> "AgenticConfig":
        default = cls()
        return cls(
            tickers=parse_tickers(os.getenv("AGENTIC_TICKERS", ",".join(default.tickers))),
            db_path=Path(os.getenv("AGENTIC_DB_PATH", str(default.db_path))).expanduser(),
            initial_cash=_env_float("AGENTIC_INITIAL_CASH", default.initial_cash),
            execution_mode=os.getenv("AGENTIC_EXECUTION_MODE", default.execution_mode).strip().lower(),
            research_enabled=_env_bool("AGENTIC_RESEARCH_ENABLED", default.research_enabled),
            selected_analysts=parse_csv(os.getenv("AGENTIC_SELECTED_ANALYSTS", ",".join(default.selected_analysts))),
            max_debate_rounds=_env_int("AGENTIC_MAX_DEBATE_ROUNDS", default.max_debate_rounds),
            max_risk_rounds=_env_int("AGENTIC_MAX_RISK_ROUNDS", default.max_risk_rounds),
            max_candidates=_env_int("AGENTIC_MAX_CANDIDATES", default.max_candidates),
            min_momentum_score=_env_float("AGENTIC_MIN_MOMENTUM_SCORE", default.min_momentum_score),
            strong_momentum_score=_env_float("AGENTIC_STRONG_MOMENTUM_SCORE", default.strong_momentum_score),
            max_order_notional=_env_float("AGENTIC_MAX_ORDER_NOTIONAL", default.max_order_notional),
            max_position_weight=_env_float("AGENTIC_MAX_POSITION_WEIGHT", default.max_position_weight),
            daily_loss_limit_pct=_env_float("AGENTIC_DAILY_LOSS_LIMIT_PCT", default.daily_loss_limit_pct),
            min_avg_volume=_env_float("AGENTIC_MIN_AVG_VOLUME", default.min_avg_volume),
            limit_order_slippage_bps=_env_float(
                "AGENTIC_LIMIT_ORDER_SLIPPAGE_BPS", default.limit_order_slippage_bps
            ),
            shadow_fill_slippage_bps=_env_float(
                "AGENTIC_SHADOW_FILL_SLIPPAGE_BPS", default.shadow_fill_slippage_bps
            ),
            allow_fractional_shares=_env_bool("AGENTIC_ALLOW_FRACTIONAL_SHARES", default.allow_fractional_shares),
            lookback_days=_env_int("AGENTIC_LOOKBACK_DAYS", default.lookback_days),
        ).validated()

    def with_overrides(self, **overrides) -> "AgenticConfig":
        clean = {key: value for key, value in overrides.items() if value is not None}
        if "tickers" in clean:
            clean["tickers"] = parse_tickers(clean["tickers"])
        if "db_path" in clean:
            clean["db_path"] = Path(clean["db_path"]).expanduser()
        return replace(self, **clean).validated()

    def validated(self) -> "AgenticConfig":
        if self.execution_mode != "shadow":
            raise ValueError("v1 only supports AGENTIC_EXECUTION_MODE=shadow")
        if not self.tickers:
            raise ValueError("At least one ticker is required")
        if self.initial_cash <= 0:
            raise ValueError("initial_cash must be positive")
        if self.max_order_notional <= 0:
            raise ValueError("max_order_notional must be positive")
        if not 0 < self.max_position_weight <= 1:
            raise ValueError("max_position_weight must be between 0 and 1")
        if self.daily_loss_limit_pct <= 0:
            raise ValueError("daily_loss_limit_pct must be positive")
        if self.max_candidates <= 0:
            raise ValueError("max_candidates must be positive")
        return self
