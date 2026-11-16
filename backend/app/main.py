from __future__ import annotations

import asyncio
import json
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .executor import _kill_process, run_job
from .planner import plan
from .policy import validate_task
from .schemas import ChatRequest, ChatResponse, Intent, JobState

load_dotenv()
jobs: dict[str, JobState] = {}
running_job: str | None = None
job_tasks: dict[str, asyncio.Task] = {}


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


@app.post("/api/chat", response_model=ChatResponse)
async def chat(body: ChatRequest):
    global running_job
    spec, planner_name = await plan(body.message)
    if spec.intent == Intent.NEED_INPUT:
        return ChatResponse(reply="Which website should I crawl? Please include its full http or https URL.", planner=planner_name)
    if spec.intent == Intent.UNSUPPORTED:
        return ChatResponse(reply="I can crawl a public website over HTTP or HTTPS, extract page and contact details, and summarize the pages I fetched. Include the site's URL to start.", planner=planner_name)
    try:
        accepted = validate_task(spec)
    except ValueError as exc:
        return ChatResponse(reply=str(exc), planner=planner_name)
    if running_job and running_job in jobs and not jobs[running_job].done:
        return ChatResponse(reply="A crawl is already running. Cancel it or wait for it to finish before starting another.", planner=planner_name)
    job_id = uuid.uuid4().hex[:12]
    job = JobState(job_id)
    jobs[job_id] = job
    running_job = job_id
    job.events.append({"event": "task", "url": accepted.url, "focus": spec.focus, "planner": planner_name})
    job_tasks[job_id] = asyncio.create_task(run_job(job, accepted))
    return ChatResponse(job_id=job_id, planner=planner_name)


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
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.done:
        return {"cancelled": False, "message": "Job already completed"}
    job.cancelled = True
    job.events.append({"event": "cancel_requested"})
    if job.process and job.process.returncode is None:
        await _kill_process(job.process)
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


dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if dist.exists():
    app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")
