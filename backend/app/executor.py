from __future__ import annotations

import asyncio
import json
import os
import signal
import sys
import tempfile
from pathlib import Path

from .policy import AcceptedTask
from .registry import build_argv, safe_environment
from .results import read_result, status_for
from .schemas import JobState
from .summarizer import summarize

MAX_STDOUT = 1_000_000
MAX_STDERR = 64_000


def _emit(job: JobState, event: dict) -> None:
    job.events.append(event)


async def _pump_stdout(stream: asyncio.StreamReader, job: JobState) -> None:
    total = 0
    while line := await stream.readline():
        total += len(line)
        if total > MAX_STDOUT:
            _emit(job, {"event": "error", "type": "output_limit", "message": "stdout limit exceeded"})
            if job.process and job.process.returncode is None:
                await _kill_process(job.process)
            return
        try:
            parsed = json.loads(line)
            if isinstance(parsed, dict) and isinstance(parsed.get("event"), str):
                _emit(job, parsed)
            else:
                _emit(job, {"event": "log", "message": "Ignored malformed crawler event"})
        except json.JSONDecodeError:
            _emit(job, {"event": "log", "message": "Ignored malformed crawler event"})


async def _pump_stderr(stream: asyncio.StreamReader, job: JobState) -> None:
    total = 0
    while line := await stream.readline():
        total += len(line)
        if total > MAX_STDERR:
            break
        clean = line.decode("utf-8", "replace").rstrip()
        clean = __import__("re").sub(r"(?i)(api[_-]?key|token|secret)(\s*[:=]\s*)[^\s,;]+", r"\1\2[redacted]", clean)
        job.stderr_tail.append(clean)
        job.stderr_tail = job.stderr_tail[-10:]


async def _kill_process(proc: asyncio.subprocess.Process) -> None:
    if proc.returncode is not None:
        return
    try:
        if os.name == "nt":
            killer = await asyncio.create_subprocess_exec("taskkill", "/PID", str(proc.pid), "/T", "/F",
                                                          stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
            await killer.wait()
        else:
            os.killpg(proc.pid, signal.SIGTERM)
        await asyncio.wait_for(proc.wait(), 3)
    except (ProcessLookupError, asyncio.TimeoutError):
        if proc.returncode is None:
            try:
                if os.name == "nt": proc.kill()
                else: os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            await proc.wait()


async def run_job(job: JobState, task: AcceptedTask, cancel_check=None) -> None:
    with tempfile.TemporaryDirectory(prefix=f"sitecrawl-{job.id}-") as temp_dir:
        job.temp_dir = temp_dir
        home = Path(temp_dir) / "home"; home.mkdir()
        output = Path(temp_dir) / "result.json"
        argv = build_argv(task, output)
        _emit(job, {"event": "execution", "argv": argv})
        kwargs = {"stdout": asyncio.subprocess.PIPE, "stderr": asyncio.subprocess.PIPE,
                  "cwd": temp_dir, "env": safe_environment(home)}
        if os.name == "nt": kwargs["creationflags"] = getattr(__import__("subprocess"), "CREATE_NEW_PROCESS_GROUP", 0)
        else: kwargs["start_new_session"] = True
        started = asyncio.get_running_loop().time()
        killed = None
        try:
            job.process = await asyncio.create_subprocess_exec(*argv, **kwargs)
            _emit(job, {"event": "process_started", "pid": job.process.pid})
            if job.cancelled:
                await _kill_process(job.process)
                killed = "cancelled"
            async def monitor_cancel() -> None:
                while job.process and job.process.returncode is None:
                    try:
                        external_cancel = await cancel_check(job.id) if cancel_check else False
                    except Exception as exc:
                        job.stderr_tail.append(f"Cancellation check unavailable: {exc}")
                        external_cancel = False
                    if job.cancelled or external_cancel:
                        job.cancelled = True
                        await _kill_process(job.process)
                        return
                    await asyncio.sleep(0.75)
            try:
                await asyncio.wait_for(asyncio.gather(_pump_stdout(job.process.stdout, job),
                                                      _pump_stderr(job.process.stderr, job), job.process.wait(), monitor_cancel()), timeout=70)
            except asyncio.TimeoutError:
                killed = "timeout"; job.cancelled = False
                await _kill_process(job.process)
                _emit(job, {"event": "stopped", "reason": "timeout"})
            if job.cancelled:
                killed = "cancelled"
            exit_code = job.process.returncode if job.process.returncode is not None else -15
        except Exception as exc:
            exit_code = 1
            job.stderr_tail.append(str(exc))
        duration = int((asyncio.get_running_loop().time() - started) * 1000)
        result = read_result(output)
        if result:
            result.execution.exit_code = exit_code
            result.execution.duration_ms = duration
        valid = result is not None
        pages_ok = result.execution.pages_ok if result else 0
        status = status_for(exit_code, valid, pages_ok, killed)
        if result:
            result.status = status
            if status != "failed" and task.spec.want_summary and pages_ok:
                result.summary = await summarize(result, task.spec.focus)
            else:
                result.summary = None
            job.result = result
            _emit(job, {"event": "result", "result": result.model_dump(mode="json")})
        job.exit_code = exit_code
        job.duration_ms = duration
        job.killed = killed
        job.argv = argv
        _emit(job, {"event": "execution_complete", "exit_code": exit_code, "duration_ms": duration,
                    "pages_ok": pages_ok, "pages_failed": result.execution.pages_failed if result else 0,
                    "stderr_tail": job.stderr_tail, "killed": killed})
        job.done = True
