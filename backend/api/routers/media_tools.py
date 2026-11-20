"""Media-tools endpoints — the backend for Settings → Audio tools and the
wizard's invisible media-engine self-heal.

Every route is loopback-gated: ``custom-path`` / ``use-system`` point the app
at an arbitrary executable (an RCE primitive if remote-reachable), and the
rest mutate local state. Same contract as ``/system/set-env``.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.dependencies import require_admin

logger = logging.getLogger("omnivoice.api")
router = APIRouter(dependencies=[Depends(require_admin)])


class CustomPathRequest(BaseModel):
    authorization: str


def _svc():
    # Late import so a service-level failure surfaces as a 500 with detail,
    # not an app-boot failure.
    from services import media_tools
    return media_tools


@router.get("/media-tools/status")
def media_tools_status():
    """Per-tool {ok, path, version, origin} + background-op states."""
    return _svc().status()


@router.post("/media-tools/acquire")
def media_tools_acquire():
    """(Re-)fetch the pinned, checksummed static ffmpeg/ffprobe build in the
    background. Idempotent; poll /media-tools/status for progress."""
    return _svc().acquire_bundled()


@router.post("/media-tools/{tool}/custom-path")
def media_tools_custom_path(tool: str, body: CustomPathRequest):
    from core.path_authorization import PathAuthorizationError, consume

    try:
        path = consume(body.authorization, tool)
        return _svc().set_custom_path(tool, path)
    except PathAuthorizationError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/media-tools/{tool}/use-system")
def media_tools_use_system(tool: str):
    try:
        return _svc().use_system(tool)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/media-tools/{tool}/restore")
def media_tools_restore(tool: str):
    try:
        return _svc().restore_bundled(tool)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
