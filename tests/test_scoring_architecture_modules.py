from __future__ import annotations

from internet_radar.storage.models import SignalRecord


def test_split_scorers_match_architecture_components():
    from internet_radar.scoring.hackathon_scorer import HackathonScorer
    from internet_radar.scoring.internship_scorer import InternshipScorer
    from internet_radar.scoring.startup_gap_scorer import StartupGapScorer
    from internet_radar.scoring.trend_scorer import TrendScorer

    hackathon = HackathonScorer().score(
        {
            "prize_pool": 50_000,
            "crowd_ratio": 0.2,
            "days_left": 6,
            "sponsors": ["NVIDIA", "AWS"],
            "is_remote": True,
            "theme": "python ai agents",
        },
        {"skills": ["python", "ai"]},
    )
    internship = InternshipScorer().score(
        {
            "posted_hours_ago": 4,
            "applicant_ratio": 0.1,
            "description": "python ai streamlit internship",
            "company_growth": 0.8,
        },
        {"skills": ["python", "ai"]},
    )
    startup_gap = StartupGapScorer().score(
        {
            "complaint_count": 80,
            "market_score": 0.8,
            "competition_score": 0.25,
            "feasibility_score": 0.8,
            "trend_phase": "EMERGING",
        }
    )
    trend = TrendScorer().score(
        {
            "velocity_score": 40,
            "confirming_sources": 6,
            "phase": "EMERGING",
            "funding_detected": True,
        }
    )

    assert hackathon.score >= 85
    assert hackathon.components["remote_score"] == 10
    assert internship.score > 70
    assert internship.components["freshness"] == 30
    assert startup_gap.score >= 65
    assert startup_gap.components["competition_gap"] == 15
    assert trend.score == 100
    assert trend.components["funding_bonus"] == 20


def test_master_scorer_delegates_to_split_scorers():
    from internet_radar.scoring.hackathon_scorer import HackathonScorer
    from internet_radar.scoring.internship_scorer import InternshipScorer
    from internet_radar.scoring.master_scorer import MasterScorer
    from internet_radar.scoring.startup_gap_scorer import StartupGapScorer
    from internet_radar.scoring.trend_scorer import TrendScorer

    profile = {"skills": ["python", "ai"]}
    hackathon = {"prize_pool": 10_000, "crowd_ratio": 0.3, "days_left": 8, "sponsors": ["OpenAI"], "theme": "ai"}
    internship = {"posted_hours_ago": 8, "applicant_ratio": 0.25, "description": "python ai", "company_growth": 0.7}
    gap = {"complaint_count": 40, "market_score": 0.7, "competition_score": 0.3, "feasibility_score": 0.75, "trend_phase": "EMERGING"}
    trend = {"velocity_score": 28, "confirming_sources": 4, "phase": "ACCELERATING", "funding_detected": True}
    master = MasterScorer()

    assert master.score_hackathon(hackathon, profile) == HackathonScorer().score(hackathon, profile).score
    assert master.score_internship(internship, profile) == InternshipScorer().score(internship, profile).score
    assert master.score_startup_gap(gap) == StartupGapScorer().score(gap).score
    assert master.score_trend(trend) == TrendScorer().score(trend).score


def test_scoring_cross_source_multiplier_module_matches_architecture():
    from internet_radar.scoring.cross_source_multiplier import apply_cross_source_multiplier, cross_source_multiplier

    assert cross_source_multiplier(1) == 1.0
    assert cross_source_multiplier(3) == 1.15
    assert cross_source_multiplier(5) == 1.3
    assert apply_cross_source_multiplier(90, 5) == 100


def test_dashboard_payload_enriches_split_scoring_metadata():
    from internet_radar.dashboard_data import build_dashboard_payload

    payload = build_dashboard_payload(
        [
            SignalRecord(
                id="hack",
                topic="ai challenge",
                title="NVIDIA AI Challenge",
                source="Devpost",
                category="hackathons",
                score=70,
                metadata={"prize_pool": 50_000, "crowd_ratio": 0.2, "days_left": 6, "sponsors": ["NVIDIA"], "theme": "python ai"},
            ),
            SignalRecord(
                id="job",
                topic="ai intern",
                title="AI Platform Intern",
                source="RemoteOK",
                category="jobs",
                score=68,
                metadata={"posted_hours_ago": 4, "applicant_ratio": 0.1, "description": "python ai streamlit", "company_growth": 0.8},
            ),
            SignalRecord(
                id="social",
                topic="browser agents",
                title="Users complain browser agents are hard to debug",
                source="Reddit JSON",
                category="social",
                score=86,
                metadata={"complaint_count": 80, "market_score": 0.8, "competition_score": 0.25, "feasibility_score": 0.8, "trend_phase": "EMERGING"},
            ),
            SignalRecord(
                id="trend",
                topic="browser agents",
                title="Browser agents confirmed",
                source="GitHub Search",
                category="code",
                score=82,
                velocity=40,
                metadata={"confirming_sources": 4, "phase": "EMERGING", "funding_detected": True},
            ),
        ],
        profile=None,
    )

    assert payload["hackathon_radar"]["signals"][0].metadata["hackathon_score"] >= 85
    job_signal = next(signal for signal in payload["skill_radar"]["signals"] if signal.category == "jobs")
    assert job_signal.metadata["internship_score"] > 70
    assert payload["startup_gaps"]["signals"][0].metadata["startup_gap_score"] >= 65
    assert payload["github_radar"]["signals"][0].metadata["trend_score"] >= 85
