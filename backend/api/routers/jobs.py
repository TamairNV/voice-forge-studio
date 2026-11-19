"""Generic background job and task routes.

Moved unchanged from api/routers/dub_export.py so they survive the removal of dubbing.
"""
import asyncio
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from core.tasks import task_manager

router = APIRouter()

#: Longest quiet spell, in seconds, before `/tasks/stream` writes a keepalive
#: comment. A task can be busy yet silent (a long ffmpeg run, one slow TTS
#: segment, a job waiting behind another); with nothing on the wire, desktop
#: webviews, Chrome (~5 min cap) and proxy idle timeouts close the stream.
#: Read at call time so tests can patch it.
TASK_STREAM_KEEPALIVE_S = 15.0


@router.get("/tasks/stream/{task_id}")
async def stream_task(task_id: str, after_seq: int = 0):
    """Universal Server-Sent Event stream for background tasks.

    `?after_seq=N` enables resumption: on reconnect, the client replays
    persisted events with seq > N, then (if the job is still live) attaches
    to the in-memory listener for live updates. After a server restart the
    in-memory task is gone but the persisted tail + final `jobs.status` are
    still readable, so a mid-stream reload still sees the final state.
    """
    from core import job_store
    job_row = job_store.get(task_id)
    live = task_manager.active_tasks.get(task_id)

    if not live and not job_row:
        raise HTTPException(
            status_code=404,
            detail="No such task. It may have been cleaned up or was never created.",
        )

    async def _reader():
        # 1) Replay any persisted events after the client's last-seen seq.
        try:
            persisted = job_store.events_since(task_id, after_seq=after_seq)
        except Exception:
            persisted = []
        for evt in persisted:
            yield evt["payload"]

        # 2) If the job has finished (whether in-memory or persisted-only), done.
        if not live:
            return
        if live["status"] in ("done", "failed", "cancelled"):
            return

        # 3) Attach to the in-memory listener for live updates.
        q = asyncio.Queue()
        await task_manager.add_listener(task_id, q)
        try:
            while True:
                try:
                    evt = await asyncio.wait_for(q.get(), timeout=TASK_STREAM_KEEPALIVE_S)
                except asyncio.TimeoutError:
                    # SSE comment line: ignored by every client, but keeps bytes flowing.
                    yield ": keepalive\n\n"
                    continue
                if evt is None:
                    break
                yield evt
        finally:
            await task_manager.remove_listener(task_id, q)

    return StreamingResponse(
        _reader(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )


@router.get("/jobs")
async def list_jobs(status: str | None = None, project_id: str | None = None, limit: int = 100):
    """List persisted jobs, newest first.

    `status=active` -> running + pending (what the batch-queue UI wants).
    `status=failed|done|cancelled|pending|running` -> exact match.
    `project_id=...` -> scope to one project.
    """
    from core import job_store
    limit = max(1, min(500, int(limit)))
    return job_store.list_jobs(status=status, project_id=project_id, limit=limit)


@router.get("/jobs/{job_id}")
async def get_job(job_id: str):
    from core import job_store
    row = job_store.get(job_id)
    if not row:
        raise HTTPException(
            status_code=404,
            detail="No such job. It may have been cleaned up or never created.",
        )
    return row


class PersistedJobEvent(BaseModel):
    seq: int
    created_at: float
    payload: str


class JobEventWatermark(BaseModel):
    seq: int
    created_at: Optional[float]


class PersistedJobEvents(BaseModel):
    job: dict[str, Any]
    events: list[PersistedJobEvent]
    event_watermark: JobEventWatermark


@router.get("/jobs/{job_id}/events")
async def list_job_events(job_id: str, after_seq: int = 0, limit: int = 500) -> PersistedJobEvents:
    """A bounded ascending SSE page and true retained-tail watermark.

    Job, page and watermark share one read snapshot. The watermark is not
    limited by the page, so it can fence older history before a live feed.
    """
    from core import job_store
    page = await run_in_threadpool(job_store.event_page, job_id, after_seq, limit)
    if page is None:
        raise HTTPException(
            status_code=404,
            detail="No job with that id. It may have expired, been deleted, or the server restarted before it was persisted — check the dub history in the sidebar.",
        )
    return PersistedJobEvents(**page)


@router.post("/tasks/cancel/{task_id}")
async def cancel_task(task_id: str):
    """Cancel a running background task (e.g. dub generation)."""
    ok = task_manager.cancel_task(task_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"cancelled": True, "task_id": task_id}
