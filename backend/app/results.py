from __future__ import annotations

from pathlib import Path

from pydantic import ValidationError

from .schemas import Result


def status_for(exit_code: int, valid_result: bool, pages_ok: int, killed: str | None = None) -> str:
    if killed and valid_result:
        return "partial"
    if exit_code == 0 and valid_result and pages_ok >= 1:
        return "success"
    if exit_code == 10 and valid_result:
        return "partial"
    return "failed"


def read_result(path: Path) -> Result | None:
    try:
        return Result.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, ValidationError):
        return None


def status_message(exit_code: int, killed: str | None = None) -> str:
    if killed == "cancelled": return "The crawl was cancelled."
    if killed == "timeout": return "The crawl reached its time limit."
    return {0: "The crawl completed.", 1: "The crawler encountered an internal error.",
            2: "The crawler arguments were invalid.", 3: "The URL or robots policy blocked the crawl.",
            4: "The site could not be reached.", 5: "The start URL had no usable HTML content.",
            10: "The time budget ended or some pages could not be fetched."}.get(exit_code, f"The crawler exited with code {exit_code}.")
