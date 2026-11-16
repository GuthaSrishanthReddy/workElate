from __future__ import annotations

import asyncio
import json
import os
import tempfile
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import httpx

from .events import emit
from .extract import extract_page
from .netguard import BlockedURL, guard_url, same_host


class RobotsDisallowed(ValueError):
    pass

USER_AGENT = "BuildSprintSitecrawl/0.1 (+safe, same-host website crawler)"
BOOST_PATHS = ("about", "contact", "product", "pricing", "services", "team", "docs")
DEPRIORITIZE = ("tag", "page/", "category", "?", "sort=", "filter=")


def rank(url: str) -> tuple[int, str]:
    path = urlsplit(url).path.lower()
    score = sum(2 for term in BOOST_PATHS if term in path) - sum(2 for term in DEPRIORITIZE if term in url.lower())
    return (-score, url)


def atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".part", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


async def fetch_html(client: httpx.AsyncClient, raw_url: str, timeout_s: float, max_bytes: int, redirects: int = 5,
                     robots: RobotFileParser | None = None) -> tuple[str, int, str]:
    url = guard_url(raw_url)
    for _ in range(redirects + 1):
        async with client.stream("GET", url, timeout=timeout_s, follow_redirects=False) as response:
            if response.status_code in {301, 302, 303, 307, 308}:
                location = response.headers.get("location")
                if not location:
                    raise ValueError("redirect without a Location header")
                url = guard_url(urljoin(url, location))
                if not same_host(raw_url, url):
                    raise BlockedURL("Redirect left the starting host")
                if robots and not robots.can_fetch(USER_AGENT, url):
                    raise RobotsDisallowed("robots disallows redirect target")
                continue
            content_type = response.headers.get("content-type", "").lower()
            if not content_type.startswith("text/html") and "application/xhtml+xml" not in content_type:
                raise TypeError(f"non_html:{content_type or 'unknown content type'}")
            chunks, total = [], 0
            async for chunk in response.aiter_bytes():
                remaining = max_bytes - total
                if remaining <= 0:
                    break
                chunk = chunk[:remaining]
                chunks.append(chunk)
                total += len(chunk)
            encoding = response.encoding or "utf-8"
            return b"".join(chunks).decode(encoding, errors="replace"), response.status_code, url
    raise ValueError("too many redirects")


async def crawl(url: str, out: str, max_pages: int = 10, max_depth: int = 2, timeout_s: int = 60,
                max_bytes: int = 2_000_000, delay_ms: int = 300) -> int:
    start_time = time.monotonic()
    out_path = Path(out).resolve()
    pages: list[dict] = []
    errors: list[dict] = []
    page_events: list[dict] = []
    robots_respected = True
    pages_failed = 0
    from .netguard import normalize_url
    try:
        start_url = normalize_url(url)
    except BlockedURL as exc:
        print(str(exc), file=__import__("sys").stderr)
        emit({"event": "error", "url": url, "type": "blocked"})
        return 3
    parts = urlsplit(start_url)
    port = parts.port or (443 if parts.scheme == "https" else 80)
    base = {"schema_version": "1.0", "status": "partial", "source": {
        "start_url": start_url, "domain": parts.hostname, "crawled_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")},
        "execution": {"tool": "sitecrawl", "tool_version": "0.1.0", "exit_code": 10, "duration_ms": 0, "pages_ok": 0, "pages_failed": 0, "robots_respected": True},
        "summary": None, "extracted": {"site_title": "", "description": "", "language": "", "pages": [],
        "contacts": {"emails": [], "phones": []}, "social_links": [], "external_links": [], "requested_fields": {}}, "errors": []}

    async def checkpoint(exit_code: int = 10, status: str = "partial") -> None:
        base["status"] = status
        base["execution"].update(exit_code=exit_code, duration_ms=int((time.monotonic() - start_time) * 1000),
                                  pages_ok=len(pages), pages_failed=pages_failed, robots_respected=robots_respected)
        base["extracted"]["site_title"] = pages[0]["title"] if pages else ""
        base["extracted"]["description"] = next((p["meta_description"] for p in pages if p["meta_description"]), "")
        base["extracted"]["language"] = next((p["language"] for p in pages if p["language"]), "")
        base["extracted"]["pages"] = pages
        base["extracted"]["contacts"] = {"emails": sorted({e for p in pages for e in p["emails"]}),
                                             "phones": sorted({e for p in pages for e in p["phones"]})}
        base["extracted"]["social_links"] = list(dict.fromkeys(e for p in pages for e in p["social_links"]))
        base["extracted"]["external_links"] = list(dict.fromkeys(e for p in pages for e in p["external_links"]))
        base["errors"] = errors
        atomic_json(out_path, base)

    emit({"event": "start", "url": start_url, "max_pages": max_pages, "max_depth": max_depth})
    try:
        start_url = guard_url(start_url)
        parts = urlsplit(start_url)
        base["source"]["start_url"] = start_url
        base["source"]["domain"] = parts.hostname
        client = httpx.AsyncClient(headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"},
                                   limits=httpx.Limits(max_connections=4, max_keepalive_connections=2))
        async with client:
            robots_url = f"{parts.scheme}://{parts.netloc}/robots.txt"
            try:
                robots_text, _, _ = await fetch_html_robots(client, robots_url, 5)
                robots = RobotFileParser()
                robots.set_url(robots_url)
                robots.parse(robots_text.splitlines())
            except TypeError:
                robots = RobotFileParser(); robots.parse([])
            except (httpx.HTTPError, OSError, ValueError) as exc:
                robots = RobotFileParser(); robots.parse([])
                print(f"robots.txt unavailable: {exc}", file=__import__("sys").stderr)
            start_allowed = robots.can_fetch(USER_AGENT, start_url)
            emit({"event": "robots", "allowed": start_allowed})
            if not start_allowed:
                await checkpoint(3, "failed")
                return 3

            queue = deque([(start_url, 0)])
            seen = {start_url}
            deadline = start_time + timeout_s
            time_exhausted = False
            while queue and len(pages) < max_pages:
                if time.monotonic() >= deadline:
                    time_exhausted = True
                    errors.append({"url": queue[0][0], "type": "timeout", "message": "job time budget exhausted"})
                    pages_failed += 1
                    break
                current, depth = queue.popleft()
                try:
                    current = guard_url(current)
                    if not same_host(start_url, current):
                        continue
                    if not robots.can_fetch(USER_AGENT, current):
                        emit({"event": "skip", "url": current, "reason": "robots"})
                        page_events.append({"event": "skip", "url": current, "reason": "robots"})
                        continue
                    if pages and delay_ms:
                        await asyncio.sleep(delay_ms / 1000)
                    remaining = max(1, min(10, int(deadline - time.monotonic())))
                    html, status_code, final_url = await fetch_html(client, current, remaining, max_bytes, robots=robots)
                    if not same_host(start_url, final_url):
                        raise BlockedURL("Redirect left the starting host")
                    if status_code < 200 or status_code >= 300:
                        raise httpx.HTTPStatusError(f"HTTP {status_code}", request=httpx.Request("GET", final_url), response=httpx.Response(status_code))
                    record = extract_page(html, final_url, status_code)
                    if not record["main_text"].strip():
                        raise ValueError("no text could be extracted")
                    pages.append(record)
                    event = {"event": "page", "url": final_url, "status": status_code,
                             "ms": int((time.monotonic() - start_time) * 1000), "depth": depth, "title": record["title"]}
                    emit(event); page_events.append(event)
                    if depth < max_depth:
                        candidates = [u for u in record["internal_links"] if u not in seen and same_host(start_url, u)]
                        candidates.sort(key=rank)
                        for candidate in candidates:
                            try:
                                candidate = guard_url(candidate)
                            except (BlockedURL, OSError):
                                continue
                            if candidate not in seen:
                                seen.add(candidate)
                                queue.append((candidate, depth + 1))
                    await checkpoint()
                except BlockedURL as exc:
                    emit({"event": "skip", "url": current, "reason": "blocked", "message": str(exc)})
                    page_events.append({"event": "skip", "url": current, "reason": "blocked"})
                    if current == start_url and not pages:
                        errors.append({"url": current, "type": "blocked", "message": str(exc)})
                        await checkpoint(3, "failed"); return 3
                except RobotsDisallowed:
                    event = {"event": "skip", "url": current, "reason": "robots"}
                    emit(event); page_events.append(event)
                    if current == start_url and not pages:
                        errors.append({"url": current, "type": "robots", "message": "robots disallows start page or redirect target"})
                        await checkpoint(3, "failed"); return 3
                except (httpx.TimeoutException, asyncio.TimeoutError) as exc:
                    errors.append({"url": current, "type": "timeout", "message": str(exc) or "read timed out"})
                    pages_failed += 1
                    event = {"event": "error", "url": current, "type": "timeout"}; emit(event); page_events.append(event)
                    await checkpoint()
                except TypeError as exc:
                    kind, message = str(exc).split(":", 1) if ":" in str(exc) else ("no_content", str(exc))
                    errors.append({"url": current, "type": kind, "message": message.strip()})
                    pages_failed += 1
                    event = {"event": "error", "url": current, "type": kind}; emit(event); page_events.append(event)
                    await checkpoint()
                    if current == start_url and not pages:
                        await checkpoint(5, "failed"); return 5
                except (OSError, httpx.HTTPError, ValueError) as exc:
                    err_type = "unreachable" if current == start_url and not pages else "fetch_error"
                    errors.append({"url": current, "type": err_type, "message": str(exc)})
                    pages_failed += 1
                    event = {"event": "error", "url": current, "type": err_type}; emit(event); page_events.append(event)
                    await checkpoint()
                    if current == start_url and not pages:
                        await checkpoint(4, "failed"); return 4
            if not pages and not errors:
                errors.append({"url": start_url, "type": "no_content", "message": "No text could be extracted"})
                await checkpoint(5, "failed"); return 5
            code = 10 if pages_failed or time_exhausted else 0
            status = "partial" if code == 10 else "success"
            await checkpoint(code, status)
            emit({"event": "done", "pages_ok": len(pages), "pages_failed": pages_failed})
            return code
    except BlockedURL as exc:
        print(str(exc), file=__import__("sys").stderr)
        await checkpoint(3, "failed")
        return 3
    except OSError as exc:
        print(str(exc), file=__import__("sys").stderr)
        errors.append({"url": start_url, "type": "unreachable", "message": str(exc)})
        await checkpoint(4, "failed")
        return 4
    except Exception as exc:
        print(f"sitecrawl internal error: {exc}", file=__import__("sys").stderr)
        await checkpoint(1, "failed")
        return 1


async def fetch_html_robots(client: httpx.AsyncClient, raw_url: str, timeout_s: int) -> tuple[str, int, str]:
    """Fetch text/plain robots while still validating the URL and every redirect."""
    start_url = guard_url(raw_url)
    url = start_url
    for _ in range(6):
        async with client.stream("GET", url, timeout=timeout_s, follow_redirects=False) as response:
            if response.status_code in {301, 302, 303, 307, 308}:
                location = response.headers.get("location")
                if not location:
                    raise ValueError("robots redirect missing Location")
                url = guard_url(urljoin(url, location))
                if not same_host(start_url, url):
                    raise BlockedURL("robots redirect left the starting host")
                continue
            if response.status_code == 404:
                return "", response.status_code, url
            response.raise_for_status()
            content = bytearray()
            async for chunk in response.aiter_bytes():
                content.extend(chunk[: max(0, 512_000 - len(content))])
                if len(content) >= 512_000: break
            return bytes(content).decode(response.encoding or "utf-8", errors="replace"), response.status_code, url
    raise ValueError("too many robots redirects")
