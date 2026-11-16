from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit

from cli.sitecrawl.netguard import BlockedURL, normalize_url, resolve_public
from .schemas import Intent, TaskSpec


@dataclass
class AcceptedTask:
    spec: TaskSpec
    url: str


def validate_task(spec: TaskSpec) -> AcceptedTask:
    if spec.intent != Intent.CRAWL_SITE or not spec.url:
        raise ValueError("Only a crawl_site task with a URL can start a process")
    try:
        url = normalize_url(spec.url)
        parts = urlsplit(url)
        resolve_public(parts.hostname or "", parts.port or (443 if parts.scheme == "https" else 80))
    except BlockedURL as exc:
        raise ValueError(str(exc)) from exc
    except OSError:
        # Let sitecrawl produce the documented exit 4 and stderr for an unreachable host.
        pass
    spec.max_pages = min(max(spec.max_pages, 1), 10)
    spec.max_depth = min(max(spec.max_depth, 0), 2)
    return AcceptedTask(spec=spec, url=url)
