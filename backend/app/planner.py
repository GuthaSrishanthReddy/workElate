from __future__ import annotations

import re

from pydantic import ValidationError

from .llm import TASK_SCHEMA, structured_call
from .schemas import Intent, TaskSpec

URL_RE = re.compile(r"https?://[^\s<>()\[\]{}\"']+", re.I)
DOMAIN_RE = re.compile(r"^(?:www\.)?(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}(?::\d{1,5})?(?:[/?#][^\s]*)?$", re.I)
CRAWL_WORDS = ("crawl", "scrape", "summaris", "summariz", "extract", "website", "site")
FOCUS_RE = re.compile(r"(?:extract|find|show|get)\s+(.{2,100})", re.I)


def regex_plan(message: str) -> TaskSpec:
    cleaned = message.strip().rstrip(".,!?;:")
    match = URL_RE.search(cleaned)
    url = match.group(0).rstrip(".,!?;:") if match else None
    has_crawl_intent = any(word in message.lower() for word in CRAWL_WORDS)
    if not has_crawl_intent and not (url and URL_RE.fullmatch(cleaned)):
        if DOMAIN_RE.fullmatch(cleaned):
            return TaskSpec(intent=Intent.NEED_INPUT)
        return TaskSpec(intent=Intent.UNSUPPORTED)
    focus_match = FOCUS_RE.search(message)
    focus = [focus_match.group(1).strip().rstrip(".!?")] if focus_match else []
    if not url:
        return TaskSpec(intent=Intent.NEED_INPUT, focus=focus)
    return TaskSpec(intent=Intent.CRAWL_SITE, url=url, focus=focus)


async def plan(message: str) -> tuple[TaskSpec, str]:
    # A URL sent by itself is a clear follow-up to the app's request for a URL.
    # Handle it deterministically so the language model cannot classify it as unsupported.
    cleaned = message.strip().rstrip(".,!?;:")
    if URL_RE.fullmatch(cleaned) or DOMAIN_RE.fullmatch(cleaned):
        return regex_plan(message), "regex"
    try:
        raw = await structured_call(
            "Choose one supported intent. Return only the TaskSpec JSON schema. Never write commands, flags, or tool names. A website request needs an explicit http(s) URL; if absent choose need_input. Unsupported tasks must choose unsupported.",
            message, "task_spec", TASK_SCHEMA)
        return TaskSpec.model_validate(raw), "llm"
    except (Exception, ValidationError):
        return regex_plan(message), "regex"
