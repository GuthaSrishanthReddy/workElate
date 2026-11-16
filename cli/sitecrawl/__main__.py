from __future__ import annotations

import argparse
import asyncio
import sys

from .crawler import crawl


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sitecrawl", description="Safe, same-host HTML crawler with NDJSON progress")
    parser.add_argument("--url", required=True, help="HTTP(S) start URL")
    parser.add_argument("--out", required=True, help="Result JSON path")
    parser.add_argument("--max-pages", type=int, default=10, help="Maximum pages (1-25)")
    parser.add_argument("--max-depth", type=int, default=2, help="Maximum link depth (0-3)")
    parser.add_argument("--timeout-s", type=int, default=60, help="Total crawl budget in seconds (1-90)")
    parser.add_argument("--max-bytes", type=int, default=2_000_000, help="Maximum bytes read per page")
    parser.add_argument("--delay-ms", type=int, default=300, help="Delay between page requests")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if not (1 <= args.max_pages <= 25 and 0 <= args.max_depth <= 3 and 1 <= args.timeout_s <= 90 and
            1 <= args.max_bytes <= 2_000_000 and 0 <= args.delay_ms <= 10_000):
        parser.error("limits out of range (pages 1-25, depth 0-3, timeout 1-90, bytes 1-2000000, delay 0-10000)")
    try:
        code = asyncio.run(crawl(args.url, args.out, args.max_pages, args.max_depth, args.timeout_s, args.max_bytes, args.delay_ms))
    except KeyboardInterrupt:
        code = 10
    sys.exit(code)


if __name__ == "__main__":
    main()
