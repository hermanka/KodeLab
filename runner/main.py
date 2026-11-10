import asyncio
from contextlib import asynccontextmanager
import logging
import os
import secrets
import threading

import anyio.to_thread
from fastapi import FastAPI, Header, HTTPException

from app.config import required_secret
from app.body_limit import BodyLimitMiddleware
from app.contracts import JudgeRequest, JudgeResult
from runner.engine import DockerRunner

logger = logging.getLogger(__name__)
slot_count = max(1, int(os.getenv("RUNNER_SLOTS", "3")))
slots = threading.BoundedSemaphore(slot_count)
active = set()
active_lock = threading.Lock()


@asynccontextmanager
async def lifespan(app):
    required_secret("RUNNER_TOKEN")
    limiter = anyio.to_thread.current_default_thread_limiter()
    # Spare threads keep /health answering while every slot is busy.
    limiter.total_tokens = max(limiter.total_tokens, slot_count + 4)
    app.state.runner = DockerRunner(os.getenv("SANDBOX_IMAGE", "judgementsystem-sandbox:gcc12-v3"))

    async def reap():
        while True:
            try:
                await asyncio.to_thread(app.state.runner.cleanup_expired)
            except Exception as exc:
                logger.warning("Sandbox cleanup error: %s", type(exc).__name__)
            await asyncio.sleep(5)

    task = asyncio.create_task(reap())
    try:
        yield
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        app.state.runner.client.close()


app = FastAPI(title="Internal C/C++ runner", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(BodyLimitMiddleware, max_bytes=2097152)


@app.get("/health")
def health():
    try:
        app.state.runner.health()
    except Exception:
        raise HTTPException(503, "Docker or sandbox image unavailable")
    return {"status": "ready"}


@app.post("/judge", response_model=JudgeResult)
def judge(request: JudgeRequest, x_runner_token: str = Header(default="")):
    if not secrets.compare_digest(x_runner_token, required_secret("RUNNER_TOKEN")):
        raise HTTPException(401, "Invalid runner token")
    if request.mode == "judge" and any(case.expected is None for case in request.cases):
        raise HTTPException(422, "Judge cases require expected output")
    if request.mode == "run" and len(request.cases) != 1:
        raise HTTPException(422, "Run mode requires exactly one input")
    key = str(request.attempt_id)
    with active_lock:
        if key in active:
            raise HTTPException(409, "Attempt is already running")
        if not slots.acquire(blocking=False):
            raise HTTPException(503, "Runner is busy")
        active.add(key)
    try:
        return app.state.runner.judge(request)
    except Exception as exc:
        logger.warning("Sandbox infrastructure error attempt=%s category=%s", key, type(exc).__name__)
        raise HTTPException(503, "Sandbox infrastructure error")
    finally:
        with active_lock:
            active.discard(key)
        slots.release()
