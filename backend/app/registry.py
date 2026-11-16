from __future__ import annotations

import os
import sys
from pathlib import Path

from .policy import AcceptedTask


def build_argv(task: AcceptedTask, result_path: Path) -> list[str]:
    return [sys.executable, "-m", "cli.sitecrawl", "--url", task.url, "--max-pages", str(task.spec.max_pages),
            "--max-depth", str(task.spec.max_depth), "--timeout-s", "60", "--max-bytes", "2000000",
            "--delay-ms", "300", "--out", str(result_path)]


def safe_environment(job_home: Path) -> dict[str, str]:
    allowed = {key: os.environ[key] for key in ("PATH", "LANG", "SYSTEMROOT", "WINDIR", "PATHEXT") if key in os.environ}
    package_root = Path(__file__).resolve().parents[2]
    allowed.update({"HOME": str(job_home), "USERPROFILE": str(job_home), "PYTHONIOENCODING": "utf-8",
                    "PYTHONUNBUFFERED": "1", "PYTHONPATH": str(package_root)})
    return allowed
