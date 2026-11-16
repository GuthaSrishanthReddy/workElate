from __future__ import annotations

import json
import os
from copy import deepcopy
from typing import Any

import httpx


TASK_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "intent": {"type": "string", "enum": ["crawl_site", "need_input", "unsupported"]},
        "url": {"type": ["string", "null"]},
        "max_pages": {"type": "integer", "minimum": 1, "maximum": 25},
        "max_depth": {"type": "integer", "minimum": 0, "maximum": 3},
        "want_summary": {"type": "boolean"}, "want_json": {"type": "boolean"},
        "focus": {"type": "array", "items": {"type": "string"}, "maxItems": 12},
    }, "required": ["intent", "url", "max_pages", "max_depth", "want_summary", "want_json", "focus"],
}
SUMMARY_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {"text": {"type": "string"}, "key_points": {"type": "array", "items": {
        "type": "object", "additionalProperties": False,
        "properties": {"point": {"type": "string"}, "source_url": {"type": "string"}},
        "required": ["point", "source_url"]}},
    }, "required": ["text", "key_points"],
}


def provider_config() -> tuple[str, str, str] | None:
    provider = os.getenv("LLM_PROVIDER", "").strip().lower()
    settings = {
        "openai": (os.getenv("OPENAI_API_KEY"), os.getenv("LLM_MODEL", "gpt-4o-mini")),
        "anthropic": (os.getenv("ANTHROPIC_API_KEY"), os.getenv("LLM_MODEL", "claude-haiku-5-5")),
        "gemini": (os.getenv("GEMINI_API_KEY"), os.getenv("LLM_MODEL", "gemini-3.8-flash")),
    }
    if provider not in settings:
        return None
    key, model = settings[provider]
    return (provider, key, model) if key else None


async def structured_call(system: str, user: str, schema_name: str, schema: dict[str, Any]) -> dict[str, Any]:
    config = provider_config()
    if not config:
        raise RuntimeError("LLM provider is not configured")
    provider, key, model = config
    async with httpx.AsyncClient(timeout=25) as client:
        if provider == "openai":
            response = await client.post("https://api.openai.com/v1/chat/completions", headers={"Authorization": f"Bearer {key}"}, json={
                "model": model, "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                "response_format": {"type": "json_schema", "json_schema": {"name": schema_name, "strict": True, "schema": schema}}})
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
        elif provider == "anthropic":
            anthropic_schema = deepcopy(schema)
            def remove_unsupported_constraints(node: Any) -> None:
                if isinstance(node, dict):
                    for unsupported in ("minimum", "maximum", "maxItems"):
                        node.pop(unsupported, None)
                    for value in node.values():
                        remove_unsupported_constraints(value)
                elif isinstance(node, list):
                    for value in node:
                        remove_unsupported_constraints(value)
            remove_unsupported_constraints(anthropic_schema)
            response = await client.post("https://api.anthropic.com/v1/messages", headers={"x-api-key": key, "anthropic-version": "2023-06-01"}, json={
                "model": model, "max_tokens": 1200, "system": system,
                "messages": [{"role": "user", "content": user}],
                "output_config": {"format": {"type": "json_schema", "schema": anthropic_schema}}})
            response.raise_for_status()
            content = next(block["text"] for block in response.json()["content"] if block.get("type") == "text")
        else:
            response = await client.post("https://generativelanguage.googleapis.com/v1beta/interactions",
                headers={"x-goog-api-key": key}, json={
                "model": model, "system_instruction": system, "input": user,
                "response_format": {"type": "text", "mime_type": "application/json", "schema": schema}, "store": False})
            response.raise_for_status()
            content = response.json()["output_text"]
    parsed = json.loads(content)
    if not isinstance(parsed, dict):
        raise ValueError("LLM returned a non-object response")
    return parsed
