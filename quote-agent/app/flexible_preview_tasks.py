from __future__ import annotations

import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Callable

from fastapi import HTTPException

from app.flexible_workflow import FLEXIBLE_PREVIEW_STAGES, build_flexible_preview_response, flexible_preview_graph
from app.models import (
    FlexiblePreviewTaskCreatedResponse,
    FlexiblePreviewTaskError,
    FlexiblePreviewTaskResponse,
    FlexibleQuoteDiagnostics,
    FlexibleQuotePreviewResponse,
)

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
            finished_at = task.get("finished_at_epoch")
            if finished_at is not None and finished_at < cutoff:
                expired.append(task_id)
        for task_id in expired:
            _tasks.pop(task_id, None)


def _touch(task: dict[str, Any]) -> None:
    task["updated_at"] = _now_iso()


def _make_response(task_id: str, task: dict[str, Any]) -> FlexiblePreviewTaskResponse:
    return FlexiblePreviewTaskResponse(
        task_id=task_id,
        status=task["status"],
        current_stage=task.get("current_stage"),
        stage_events=task.get("stage_events", []),
        error=FlexiblePreviewTaskError.model_validate(task["error"]) if task.get("error") else None,
        result=FlexibleQuotePreviewResponse.model_validate(task["result"]) if task.get("result") else None,
        created_at=task["created_at"],
        updated_at=task["updated_at"],
        finished_at=task.get("finished_at"),
    )


def _mark_remaining_stages(task: dict[str, Any], status: str, message: str) -> None:
    seen = {
        event["stage"]
        for event in task.get("stage_events", [])
        if event["status"] in {"completed", "failed", "skipped"}
    }
    stamp = _now_iso()
    for stage in FLEXIBLE_PREVIEW_STAGES:
        if stage in seen:
            continue
        task.setdefault("stage_events", []).append(
            {"stage": stage, "status": status, "message": message, "timestamp": stamp}
        )


def _set_stage_event(task_id: str, stage: str, status: str, message: str) -> None:
    with _lock:
        task = _tasks.get(task_id)
        if not task:
            return
        task["status"] = "running"
        task["current_stage"] = stage
        task.setdefault("stage_events", []).append(
            {"stage": stage, "status": status, "message": message, "timestamp": _now_iso()}
        )
        _touch(task)


def _run_preview_task(task_id: str, files: list[dict[str, Any]], quote_context: dict[str, Any]) -> None:
    try:
        state = flexible_preview_graph.invoke(
            {
                "files": files,
                "quote_context": quote_context,
                "progress_callback": lambda stage, status, message: _set_stage_event(task_id, stage, status, message),
            }
        )
        result = build_flexible_preview_response(state).model_dump()
        with _lock:
            task = _tasks.get(task_id)
            if not task:
                return
            task["status"] = "succeeded"
            task["result"] = result
            task["finished_at"] = _now_iso()
            task["finished_at_epoch"] = time.time()
            _mark_remaining_stages(task, "skipped", "Stage was not executed for this branch.")
            _touch(task)
    except Exception as exc:
        with _lock:
            task = _tasks.get(task_id)
            if not task:
                return
            current_stage = task.get("current_stage")
            diagnostics = getattr(exc, "diagnostics", None)
            task["status"] = "failed"
            task["error"] = {
                "message": getattr(exc, "message", "Flexible preview failed."),
                "detail": getattr(exc, "detail", str(exc)),
                "last_stage": getattr(exc, "stage", current_stage),
                "diagnostics": diagnostics,
            }
            failed_stage = getattr(exc, "stage", current_stage)
            if failed_stage:
                task.setdefault("stage_events", []).append(
                    {
                        "stage": failed_stage,
                        "status": "failed",
                        "message": getattr(exc, "detail", str(exc)),
                        "timestamp": _now_iso(),
                    }
                )
            task["finished_at"] = _now_iso()
            task["finished_at_epoch"] = time.time()
            _mark_remaining_stages(task, "skipped", "Stage was not reached because the task failed.")
            _touch(task)


def create_preview_task(files: list[dict[str, Any]], quote_context: dict[str, Any]) -> FlexiblePreviewTaskCreatedResponse:
    _cleanup_expired_tasks()
    task_id = str(uuid.uuid4())
    task = {
        "status": "queued",
        "current_stage": None,
        "stage_events": [],
        "error": None,
        "result": None,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
        "finished_at": None,
        "finished_at_epoch": None,
    }
    with _lock:
        _tasks[task_id] = task
    worker = threading.Thread(target=_run_preview_task, args=(task_id, files, quote_context), daemon=True)
    worker.start()
    return FlexiblePreviewTaskCreatedResponse(task_id=task_id, status="queued")


def get_preview_task(task_id: str) -> FlexiblePreviewTaskResponse:
    _cleanup_expired_tasks()
    with _lock:
        task = _tasks.get(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Flexible preview task not found.")
        return _make_response(task_id, task)
