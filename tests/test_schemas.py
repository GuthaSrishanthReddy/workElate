from backend.app.schemas import Result


def test_result_schema_accepts_cli_checkpoint():
    result = Result.model_validate({
        "schema_version": "1.0", "status": "success",
        "source": {"start_url": "https://example.com", "domain": "example.com", "crawled_at": "2026-11-16T14:05:11Z"},
        "execution": {"tool": "sitecrawl", "tool_version": "0.1.0", "exit_code": 0, "duration_ms": 12,
                      "pages_ok": 1, "pages_failed": 0, "robots_respected": True},
        "summary": None,
        "extracted": {"site_title": "Example", "description": "Example site", "language": "en",
                      "pages": [{"url": "https://example.com/", "title": "Example", "status_code": 200,
                                 "headings": ["Example"], "word_count": 3, "excerpt": "Example text here"}],
                      "contacts": {"emails": [], "phones": []}, "social_links": [], "external_links": [], "requested_fields": {}},
        "errors": [],
    })
    assert result.execution.pages_ok == 1
