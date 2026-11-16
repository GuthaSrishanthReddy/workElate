from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlsplit, urlunsplit


class BlockedURL(ValueError):
    pass


def normalize_url(value: str) -> str:
    try:
        parts = urlsplit(value.strip())
        if parts.scheme.lower() not in {"http", "https"}:
            raise BlockedURL("Only http and https URLs are allowed")
        if not parts.hostname or parts.username or parts.password:
            raise BlockedURL("URL must include a host and cannot include credentials")
        host = parts.hostname.encode("idna").decode("ascii").lower().rstrip(".")
        port = parts.port
    except (ValueError, UnicodeError) as exc:
        if isinstance(exc, BlockedURL):
            raise
        raise BlockedURL("Invalid URL") from exc
    netloc = f"{host}:{port}" if port and not ((parts.scheme.lower() == "http" and port == 80) or (parts.scheme.lower() == "https" and port == 443)) else host
    path = parts.path or "/"
    return urlunsplit((parts.scheme.lower(), netloc, path, parts.query, ""))


def _is_public(address: str) -> bool:
    ip = ipaddress.ip_address(address.split("%", 1)[0])
    return ip.is_global and not (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved or ip.is_unspecified)


def resolve_public(host: str, port: int) -> set[str]:
    try:
        literal = ipaddress.ip_address(host)
        addresses = {literal.compressed}
    except ValueError:
        try:
            addresses = {item[4][0] for item in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)}
        except OSError as exc:
            raise OSError(f"DNS resolution failed for {host}: {exc}") from exc
    if not addresses:
        raise OSError(f"DNS returned no addresses for {host}")
    if any(not _is_public(address) for address in addresses):
        raise BlockedURL("Blocked: resolves to a private or reserved address")
    return addresses


def guard_url(value: str) -> str:
    url = normalize_url(value)
    parts = urlsplit(url)
    resolve_public(parts.hostname or "", parts.port or (443 if parts.scheme == "https" else 80))
    return url


def same_host(start_url: str, candidate_url: str) -> bool:
    a = (urlsplit(start_url).hostname or "").lower().removeprefix("www.")
    b = (urlsplit(candidate_url).hostname or "").lower().removeprefix("www.")
    return a == b
