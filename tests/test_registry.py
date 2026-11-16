import subprocess
import sys

from backend.app.registry import safe_environment


def test_crawler_module_is_importable_from_job_directory(tmp_path):
    env = safe_environment(tmp_path)
    result = subprocess.run(
        [sys.executable, "-c", "import httpx, trafilatura; import cli.sitecrawl; print('crawler imports ok')"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "crawler imports ok" in result.stdout
