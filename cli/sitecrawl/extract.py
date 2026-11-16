from __future__ import annotations

import re
from urllib.parse import urljoin, urlsplit

import trafilatura
from selectolax.parser import HTMLParser


EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
PHONE_RE = re.compile(r"(?<!\w)\+?\d[\d ().-]{6,}\d(?!\w)")
SOCIAL_HOSTS = ("facebook.com", "instagram.com", "linkedin.com", "twitter.com", "x.com", "youtube.com", "tiktok.com")


def extract_page(html: str, url: str, status_code: int) -> dict:
    tree = HTMLParser(html)
    title_node = tree.css_first("title")
    title = title_node.text(strip=True) if title_node else ""
    desc_node = tree.css_first('meta[name="description" i]')
    description = (desc_node.attributes.get("content", "").strip() if desc_node else "")
    html_node = tree.css_first("html")
    language = html_node.attributes.get("lang", "") if html_node else ""
    headings = [n.text(strip=True) for n in tree.css("h1, h2, h3") if n.text(strip=True)]
    body_text = trafilatura.extract(html, url=url, include_links=False, include_tables=True) or ""
    if not body_text:
        body = tree.css_first("body")
        body_text = body.text(separator=" ", strip=True) if body else ""
    internal, external, social, emails, phones = [], [], [], set(), set()
    for node in tree.css("a[href]"):
        raw = node.attributes.get("href", "").strip()
        if not raw or raw.startswith(("javascript:", "mailto:", "tel:", "#")):
            if raw.lower().startswith("mailto:"):
                emails.add(raw[7:].split("?", 1)[0])
            if raw.lower().startswith("tel:"):
                phones.add(raw[4:].split("?", 1)[0])
            continue
        absolute = urljoin(url, raw).split("#", 1)[0]
        host = (urlsplit(absolute).hostname or "").lower().removeprefix("www.")
        origin = (urlsplit(url).hostname or "").lower().removeprefix("www.")
        if host in {"facebook.com", "instagram.com", "linkedin.com", "twitter.com", "x.com", "youtube.com", "tiktok.com"}:
            social.append(absolute)
        elif host == origin:
            internal.append(absolute)
        elif host:
            external.append(absolute)
    emails.update(EMAIL_RE.findall(body_text))
    phones.update(PHONE_RE.findall(body_text))
    words = body_text.split()
    return {
        "url": url,
        "title": title,
        "status_code": status_code,
        "headings": headings,
        "word_count": len(words),
        "excerpt": " ".join(words[:80]),
        "meta_description": description,
        "language": language,
        "h1_to_h3": headings,
        "main_text": body_text[:20000],
        "internal_links": list(dict.fromkeys(internal)),
        "external_links": list(dict.fromkeys(external)),
        "emails": sorted(emails),
        "phones": sorted(phones),
        "social_links": list(dict.fromkeys(social)),
    }
