from __future__ import annotations

from internet_radar.storage.models import SignalRecord


def test_llm_router_uses_online_free_tiers_for_heavy_and_huge_tasks():
    from internet_radar.brain.llm_router import LLMRouter

    router = LLMRouter(available_models=[])

    heavy = router.route("gap_analysis", content_length=2_000)
    huge = router.route("summarize", content_length=60_000)
    overflow = router.route("unmapped_long_analysis", content_length=4_000)

    assert (heavy.provider, heavy.model, heavy.reason) == (
        "groq",
        "llama-3.3-70b-versatile",
        "online free tier for heavy reasoning",
    )
    assert (huge.provider, huge.model) == ("gemini", "gemini-1.5-flash")
    assert (overflow.provider, overflow.model) == (
        "openrouter",
        "meta-llama/llama-3.2-3b-instruct:free",
    )


def test_online_llm_client_builds_provider_requests_without_real_network(monkeypatch):
    from internet_radar.brain.online_llm import GroqClient

    calls: list[dict[str, object]] = []

    def fake_post(url, *, headers, json, timeout):
        calls.append({"url": url, "headers": headers, "json": json, "timeout": timeout})

        class Response:
            def raise_for_status(self):
                return None

            def json(self):
                return {"choices": [{"message": {"content": '{"summary":"ok","confidence":91}'}}]}

        return Response()

    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    client = GroqClient(post=fake_post)

    result = client.generate_json("Summarize this.")

    assert result == {"summary": "ok", "confidence": 91}
    assert calls[0]["url"] == "https://api.groq.com/openai/v1/chat/completions"
    assert calls[0]["headers"]["Authorization"] == "Bearer test-key"
    assert calls[0]["json"]["model"] == "llama-3.3-70b-versatile"


def test_deep_dive_report_summarizes_opportunities_risks_and_actions():
    from internet_radar.brain.deep_dive import build_deep_dive
    from internet_radar.brain.llm_router import LLMRouter

    router = LLMRouter(available_models=[])
    signals = [
        SignalRecord(
            id="gap",
            topic="browser agents",
            title="Users complain browser agents are hard to debug",
            source="Reddit JSON",
            category="social",
            score=84,
            summary="Broken workflows and manual setup pain.",
            metadata={"frustration_score": 88},
        ),
        SignalRecord(
            id="research",
            topic="browser agents",
            title="Browser automation papers increase",
            source="arXiv",
            category="research",
            score=79,
            velocity=22,
        ),
        SignalRecord(
            id="funding",
            topic="browser agents",
            title="Agent devtools startup funded",
            source="YC Companies",
            category="finance",
            score=81,
        ),
    ]

    report = build_deep_dive("browser agents", signals, router=router)

    assert report.query == "browser agents"
    assert report.route.provider == "groq"
    assert "3 signals" in report.executive_summary
    assert "startup gap" in report.opportunities[0].lower()
    assert any("debug" in risk.lower() or "broken" in risk.lower() for risk in report.risks)
    assert report.sources == ["Reddit JSON", "arXiv", "YC Companies"]
    assert report.suggested_actions[0].startswith("Validate")


def test_radar_search_can_include_deep_dive_summary():
    from internet_radar.search.radar_search import analyze_query

    signals = [
        SignalRecord(
            id="a",
            topic="browser agents",
            title="Browser agents exploding",
            source="GitHub Search",
            category="code",
            score=88,
            summary="Local automation projects rising.",
        ),
        SignalRecord(
            id="b",
            topic="browser agents",
            title="Users report broken browser automation setup",
            source="Reddit JSON",
            category="social",
            score=82,
            summary="Manual setup pain.",
        ),
    ]

    analysis = analyze_query(signals, "browser agents", include_deep_dive=True)

    assert analysis["deep_dive"]["query"] == "browser agents"
    assert analysis["deep_dive"]["route"]["provider"] in {"ollama", "groq", "deterministic"}
    assert "suggested_actions" in analysis["deep_dive"]
