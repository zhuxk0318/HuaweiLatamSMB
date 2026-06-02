from __future__ import annotations

import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException

from app.models import QuotePreviewResponse

TASK_TTL_SECONDS = 1800

_tasks: dict[str, dict[str, Any]] = {}
_lock = threading.Lock()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _cleanup_expired_tasks() -> None:
    cutoff = time.time() - TASK_TTL_SECONDS
    expired = []
    with _lock:
        for task_id, task in _tasks.items():
            epoch = task.get("finished_at_epoch")
            if epoch is not None and epoch < cutoff:
                expired.append(task_id)
        for task_id in expired:
            _tasks.pop(task_id, None)


def store_preview_result(
    preview_response: QuotePreviewResponse,
    state: dict[str, Any],
) -> str:
    _cleanup_expired_tasks()
    task_id = str(uuid.uuid4())
    now = _now_iso()
    with _lock:
        _tasks[task_id] = {
            "preview_response": preview_response.model_dump(),
            "state": state,
            "created_at": now,
            "finished_at_epoch": time.time(),
        }
    return task_id


def get_preview_state(task_id: str) -> dict[str, Any]:
    _cleanup_expired_tasks()
    with _lock:
        task = _tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="RVTools preview task not found.")
    return task["state"]
