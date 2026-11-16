import pytest

from backend.app.planner import plan, regex_plan
from backend.app.schemas import Intent


@pytest.mark.parametrize("message", ["https://www.amazon.com/", "https://example.com/about"])
def test_url_alone_starts_a_crawl(message):
    spec = regex_plan(message)

    assert spec.intent == Intent.CRAWL_SITE
    assert spec.url == message


@pytest.mark.parametrize("message", ["amazon.com", "www.amazon.com"])
def test_bare_domain_requests_a_full_url(message):
    assert regex_plan(message).intent == Intent.NEED_INPUT


@pytest.mark.asyncio
async def test_url_only_followup_bypasses_language_model(monkeypatch):
    async def unexpected_llm_call(*args, **kwargs):
        raise AssertionError("URL-only follow-ups should be handled deterministically")

    monkeypatch.setattr("backend.app.planner.structured_call", unexpected_llm_call)

    spec, planner_name = await plan("https://www.amazon.com/")

    assert spec.intent == Intent.CRAWL_SITE
    assert spec.url == "https://www.amazon.com/"
    assert planner_name == "regex"
