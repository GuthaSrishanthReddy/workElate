from __future__ import annotations

import re

from pydantic import ValidationError

from .llm import TASK_SCHEMA, structured_call
from .schemas import Intent, TaskSpec

URL_RE = re.compile(r"https?://[^\s<>()\[\]{}\"']+", re.I)
CRAWL_WORDS = ("crawl", "scrape", "summaris", "summariz", "extract", "website", "site")
FOCUS_RE = re.compile(r"(?:extract|find|show|get)\s+(.{2,100})", re.I)


def regex_plan(message: str) -> TaskSpec:
    match = URL_RE.search(message)
    url = match.group(0).rstrip(".,!?;:") if match else None
    if not any(word in message.lower() for word in CRAWL_WORDS):
        return TaskSpec(intent=Intent.UNSUPPORTED)
    focus_match = FOCUS_RE.search(message)
    focus = [focus_match.group(1).strip().rstrip(".!?")] if focus_match else []
    if not url:
        return TaskSpec(intent=Intent.NEED_INPUT, focus=focus)
    return TaskSpec(intent=Intent.CRAWL_SITE, url=url, focus=focus)


async def plan(message: str) -> tuple[TaskSpec, str]:
    try:
        raw = await structured_call(
            "Choose one supported intent. Return only the TaskSpec JSON schema. Never write commands, flags, or tool names. A website request needs an explicit http(s) URL; if absent choose need_input. Unsupported tasks must choose unsupported.",
            message, "task_spec", TASK_SCHEMA)
        return TaskSpec.model_validate(raw), "llm"
    except (Exception, ValidationError):
        return regex_plan(message), "regex"
