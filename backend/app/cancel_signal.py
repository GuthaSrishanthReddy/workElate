from __future__ import annotations

import os
import re
from urllib.parse import quote

import httpx

JOB_ID_RE = re.compile(r"^[0-9a-f]{12}$")


def upstash_configured() -> bool:
    return bool(os.getenv("UPSTASH_REDIS_REST_URL") and os.getenv("UPSTASH_REDIS_REST_TOKEN"))


def _request_target(job_id: str, operation: str) -> tuple[str, dict[str, str]]:
    if not JOB_ID_RE.fullmatch(job_id):
        raise ValueError("Invalid job id")
    base = os.environ["UPSTASH_REDIS_REST_URL"].rstrip("/")
    token = os.environ["UPSTASH_REDIS_REST_TOKEN"]
    key = quote(f"sitecrawl_cancel_{job_id}", safe="")
    return f"{base}/{operation}/{key}", {"Authorization": f"Bearer {token}"}


async def request_cancel(job_id: str) -> None:
    url, headers = _request_target(job_id, "set")
    async with httpx.AsyncClient(timeout=3) as client:
        response = await client.get(f"{url}/cancelled/EX/180", headers=headers)
        response.raise_for_status()
        if response.json().get("result") != "OK":
            raise RuntimeError("Redis did not record the cancellation request")


async def is_cancelled(job_id: str) -> bool:
    url, headers = _request_target(job_id, "get")
    async with httpx.AsyncClient(timeout=3) as client:
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        return response.json().get("result") == "cancelled"
