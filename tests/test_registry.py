import subprocess
import sys

from backend.app.registry import safe_environment


def test_crawler_module_is_importable_from_job_directory(tmp_path):
    env = safe_environment(tmp_path)
    result = subprocess.run(
        [sys.executable, "-m", "cli.sitecrawl", "--help"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "Safe, same-host HTML crawler" in result.stdout
