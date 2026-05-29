import math

import pandas as pd
import pytest

from tradingagents.agentic.momentum import compute_features_from_history, score_band, score_momentum
from tradingagents.agentic.models import MomentumFeatures


@pytest.mark.unit
def test_momentum_formula_matches_report():
    features = MomentumFeatures(
        price_trend=0.5,
        technical_state=0.25,
        risk_penalty=-0.1,
        volume_confirmation=0.75,
        sentiment_attention=0.2,
        fundamental_factor=0.4,
    )

    score = score_momentum("AAPL", "2026-05-29", features)

    expected_z = (0.40 * 0.5) + (0.20 * 0.25) + (0.10 * -0.1) + (0.10 * 0.75) + (0.15 * 0.2) + (0.05 * 0.4)
    expected_score = 100 / (1 + math.exp(-1.6 * expected_z))
    assert score.z_score == pytest.approx(expected_z)
    assert score.score == pytest.approx(expected_score)


@pytest.mark.unit
@pytest.mark.parametrize(
    "score,band",
    [
        (39.99, "bearish"),
        (40.0, "neutral"),
        (60.0, "research_candidate"),
        (75.0, "strong_candidate"),
        (90.0, "high_conviction_high_risk"),
    ],
)
def test_score_bands(score, band):
    assert score_band(score) == band


@pytest.mark.unit
def test_compute_features_from_history_is_bounded():
    history = pd.DataFrame(
        {
            "Close": [100 + i for i in range(40)],
            "Volume": [1_000_000 + (i * 1_000) for i in range(40)],
        }
    )

    features = compute_features_from_history(history, sentiment_attention=5, fundamental_factor=-5)

    assert -1 <= features.price_trend <= 1
    assert -1 <= features.technical_state <= 1
    assert -1 <= features.risk_penalty <= 1
    assert -1 <= features.volume_confirmation <= 1
    assert features.sentiment_attention == 1
    assert features.fundamental_factor == -1
