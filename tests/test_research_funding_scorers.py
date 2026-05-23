from __future__ import annotations

from internet_radar.storage.models import SignalRecord


def test_research_signal_scorer_exposes_components_and_timing_window():
    from internet_radar.scoring.research_signal_scorer import ResearchSignalScorer

    result = ResearchSignalScorer().score(
        {
            "topic": "browser agents",
            "papers_per_week": 20,
            "citation_velocity": 10,
            "top_institution_count": 5,
            "has_code_repos": True,
            "industry_mentions": 3,
        }
    )

    assert result.score == 95
    assert result.recommended_skill == "browser agents"
    assert result.industry_lag_months == "12-18"
    assert result.components == {
        "paper_velocity": 30,
        "citation_growth": 20,
        "institution_quality": 10,
        "github_code": 20,
        "industry_adoption": 15,
    }


def test_funding_scorer_scores_market_validation_without_keys():
    from internet_radar.scoring.funding_scorer import FundingScorer

    result = FundingScorer().score(
        {
            "company": "Agent Tools",
            "amount": 12_000_000,
            "investors": ["a16z", "Sequoia", "YC"],
            "sector": "developer tools",
            "days_ago": 4,
            "related_jobs": 8,
        }
    )

    assert result.score >= 85
    assert result.market_validation == "high"
    assert result.components["amount_signal"] > 30
    assert result.components["investor_quality"] == 20
    assert result.components["freshness"] == 20


def test_dashboard_payload_enriches_research_and_funding_domain_scores():
    from internet_radar.dashboard_data import build_dashboard_payload

    payload = build_dashboard_payload(
        [
            SignalRecord(
                id="paper",
                topic="agent benchmarks",
                title="Agent benchmark papers spike",
                source="arXiv",
                category="research",
                score=70,
                metadata={
                    "papers_per_week": 12,
                    "citation_velocity": 8,
                    "top_institution_count": 4,
                    "has_code_repos": True,
                    "industry_mentions": 2,
                },
            ),
            SignalRecord(
                id="funding",
                topic="ai devtools",
                title="AI devtools startup raises seed",
                source="YC",
                category="finance",
                score=72,
                metadata={"amount": 7_500_000, "investors": ["YC", "Accel"], "days_ago": 12, "related_jobs": 5},
            ),
        ]
    )

    research_signal = payload["research_radar"]["signals"][0]
    funding_signal = payload["funding_radar"]["signals"][0]

    assert research_signal.metadata["research_score"] >= 75
    assert research_signal.metadata["industry_lag_months"] == "12-18"
    assert funding_signal.metadata["funding_score"] >= 80
    assert funding_signal.metadata["market_validation"] in {"medium", "high"}
