from __future__ import annotations

import asyncio
import json
import os
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .cancel_signal import is_cancelled, request_cancel, upstash_configured
from .executor import _kill_process, run_job
from .planner import plan
from .policy import validate_task
from .schemas import ChatRequest, Intent, JobState

load_dotenv()
jobs: dict[str, JobState] = {}
running_job: str | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    for job in jobs.values():
        if job.process and job.process.returncode is None:
            await _kill_process(job.process)


app = FastAPI(title="BuildSprint Chat + sitecrawl", version="0.1.0", lifespan=lifespan)


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.post("/api/chat")
async def chat(body: ChatRequest, request: Request):
    global running_job
    async def stream():
        global running_job
        yield f"data: {json.dumps({'event': 'planning'})}\n\n"
        planning = asyncio.create_task(plan(body.message))
        while not planning.done():
            if await request.is_disconnected():
                planning.cancel()
                return
            try:
                await asyncio.wait_for(asyncio.shield(planning), timeout=5)
            except asyncio.TimeoutError:
                yield ": keepalive\n\n"
        spec, planner_name = await planning
        if spec.intent == Intent.NEED_INPUT:
            reply = "Which website should I crawl? Please include its full http or https URL."
            yield f"data: {json.dumps({'event': 'reply', 'text': reply, 'planner': planner_name})}\n\n"
            yield 'data: {"event":"complete"}\n\n'
            return
        if spec.intent == Intent.UNSUPPORTED:
            reply = "I can crawl a public website over HTTP or HTTPS, extract page and contact details, and summarize the pages I fetched. Include the site's URL to start."
            yield f"data: {json.dumps({'event': 'reply', 'text': reply, 'planner': planner_name})}\n\n"
            yield 'data: {"event":"complete"}\n\n'
            return
        try:
            accepted = validate_task(spec)
        except ValueError as exc:
            yield f"data: {json.dumps({'event': 'reply', 'text': str(exc), 'planner': planner_name})}\n\n"
            yield 'data: {"event":"complete"}\n\n'
            return
        if os.getenv("VERCEL") and not upstash_configured():
            reply = "This Vercel deployment needs UPSTASH_REDIS_REST_URL and UPSTASH_REDIS_REST_TOKEN so Cancel works across function instances."
            yield f"data: {json.dumps({'event': 'reply', 'text': reply, 'planner': planner_name})}\n\n"
            yield 'data: {"event":"complete"}\n\n'
            return
        if running_job and running_job in jobs and not jobs[running_job].done:
            reply = "A crawl is already running. Cancel it or wait for it to finish before starting another."
            yield f"data: {json.dumps({'event': 'reply', 'text': reply, 'planner': planner_name})}\n\n"
            yield 'data: {"event":"complete"}\n\n'
            return
        if await request.is_disconnected():
            return

        job_id = uuid.uuid4().hex[:12]
        job = JobState(job_id)
        jobs[job_id] = job
        running_job = job_id
        job.events.append({"event": "task", "job_id": job_id, "url": accepted.url, "focus": spec.focus, "planner": planner_name})
        runner = asyncio.create_task(run_job(job, accepted, cancel_check=is_cancelled if upstash_configured() else None))
        cursor = 0
        last_heartbeat = asyncio.get_running_loop().time()
        try:
            while not job.done or cursor < len(job.events):
                while cursor < len(job.events):
                    payload = json.dumps(job.events[cursor], ensure_ascii=False, separators=(",", ":"))
                    yield f"data: {payload}\n\n"
                    cursor += 1
                    last_heartbeat = asyncio.get_running_loop().time()
                if job.done:
                    break
                if await request.is_disconnected():
                    job.cancelled = True
                    if job.process and job.process.returncode is None:
                        await _kill_process(job.process)
                    break
                now = asyncio.get_running_loop().time()
                if now - last_heartbeat >= 5:
                    yield ": keepalive\n\n"
                    last_heartbeat = now
                await asyncio.sleep(0.15)
            if not job.done:
                try:
                    await asyncio.wait_for(runner, timeout=5)
                except (asyncio.TimeoutError, asyncio.CancelledError):
                    runner.cancel()
            yield 'data: {"event":"complete"}\n\n'
        finally:
            if not job.done:
                job.cancelled = True
                if job.process and job.process.returncode is None:
                    await _kill_process(job.process)
                if not runner.done():
                    runner.cancel()

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/api/jobs/{job_id}/events")
async def events(job_id: str):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    async def stream():
        sent = 0
        while True:
            while sent < len(job.events):
                payload = json.dumps(job.events[sent], ensure_ascii=False, separators=(",", ":"))
                yield f"data: {payload}\n\n"
                sent += 1
            if job.done:
                yield "event: complete\ndata: {}\n\n"
                break
            yield ": keepalive\n\n"
            await asyncio.sleep(0.2)
    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/api/jobs/{job_id}/cancel")
async def cancel(job_id: str):
    job = jobs.get(job_id)
    if job and job.done:
        return {"cancelled": False, "message": "Job already completed"}
    if job:
        job.cancelled = True
        job.events.append({"event": "cancel_requested"})
        return {"cancelled": True}
    if not upstash_configured():
        raise HTTPException(status_code=404, detail="Job not found")
    try:
        await request_cancel(job_id)
    except (httpx.HTTPError, RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=503, detail="Could not signal the running job; verify Upstash Redis configuration") from exc
    return {"cancelled": True}


@app.get("/api/jobs/{job_id}")
async def job_status(job_id: str):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"job_id": job_id, "done": job.done, "result": job.result.model_dump(mode="json") if job.result else None,
            "exit_code": job.exit_code, "duration_ms": job.duration_ms, "stderr_tail": job.stderr_tail,
            "argv": job.argv, "killed": job.killed}


@app.get("/", include_in_schema=False)
async def index():
    entry = Path(__file__).resolve().parents[2] / "frontend" / "dist" / "index.html"
    if entry.exists():
        return FileResponse(entry)
    return {"message": "Frontend is not built. Run npm install && npm run dev in frontend/."}


@app.get("/favicon.svg", include_in_schema=False)
async def favicon():
    icon = Path(__file__).resolve().parents[2] / "frontend" / "dist" / "favicon.svg"
    if icon.exists():
        return FileResponse(icon, media_type="image/svg+xml")
    raise HTTPException(status_code=404, detail="Favicon not found")


dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if dist.exists():
    app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")
