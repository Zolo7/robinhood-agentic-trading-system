import pandas as pd
import pytest
from typer.testing import CliRunner

import tradingagents.agentic.cli as cli_module
from tradingagents.agentic.cli import app
from tradingagents.agentic.config import AgenticConfig
from tradingagents.agentic.models import MarketSnapshot, ResearchDecision, TickerResult
from tradingagents.agentic.pipeline import AgenticTradingPipeline, RunSummary
from tradingagents.agentic.storage import SQLiteStore


def _fake_market_loader(ticker: str, analysis_date: str, lookback_days: int):
    history = pd.DataFrame(
        {
            "Close": [100 + i for i in range(60)],
            "Volume": [2_000_000 for _ in range(60)],
        }
    )
    snapshot = MarketSnapshot(
        ticker=ticker,
        as_of=analysis_date,
        price=159.0,
        open=158.0,
        high=160.0,
        low=157.0,
        close=159.0,
        volume=2_000_000,
        avg_volume_20d=2_000_000,
        volatility_20d=0.1,
    )
    return snapshot, history


class FakeResearchAdapter:
    def research(self, ticker: str, analysis_date: str):
        return ResearchDecision(
            ticker=ticker,
            as_of=analysis_date,
            rating="Buy",
            raw_decision="**Rating**: Buy\n\nShadow test.",
        )


@pytest.mark.unit
def test_pipeline_fills_shadow_order_with_mocked_research(tmp_path):
    config = AgenticConfig(
        tickers=("AAPL",),
        db_path=tmp_path / "shadow.sqlite3",
        research_enabled=True,
        min_momentum_score=50,
        max_order_notional=100,
        max_position_weight=0.5,
        min_avg_volume=1,
        shadow_fill_slippage_bps=0,
    )
    store = SQLiteStore(config.db_path)

    summary = AgenticTradingPipeline(
        config,
        store=store,
        market_loader=_fake_market_loader,
        research_adapter=FakeResearchAdapter(),
    ).run(analysis_date="2026-05-29")

    assert summary.filled_count == 1
    assert summary.results[0].status == "filled"
    assert store.count_rows("market_snapshots") == 1
    assert store.count_rows("momentum_scores") == 1
    assert store.count_rows("research_decisions") == 1
    assert store.count_rows("fills") == 1


@pytest.mark.unit
def test_cli_init_db_and_shadow_report(tmp_path):
    runner = CliRunner()
    db_path = tmp_path / "cli.sqlite3"

    init_result = runner.invoke(app, ["init-db", "--db-path", str(db_path)])
    assert init_result.exit_code == 0
    assert db_path.exists()

    report_result = runner.invoke(app, ["shadow-report", "--db-path", str(db_path)])
    assert report_result.exit_code == 0
    assert "Portfolio" in report_result.output


@pytest.mark.unit
def test_cli_run_smoke_uses_pipeline(monkeypatch, tmp_path):
    class FakePipeline:
        def __init__(self, config):
            self.config = config

        def run(self, analysis_date=None):
            return RunSummary(
                analysis_date=analysis_date,
                db_path=self.config.db_path,
                results=[TickerResult(ticker="AAPL", status="held", momentum_score=55.0, reasons=["test"])],
            )

    monkeypatch.setattr(cli_module, "AgenticTradingPipeline", FakePipeline)
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "run",
            "--tickers",
            "AAPL",
            "--date",
            "2026-05-29",
            "--db-path",
            str(tmp_path / "cli.sqlite3"),
            "--skip-research",
        ],
    )

    assert result.exit_code == 0
    assert "AAPL" in result.output
