from __future__ import annotations

import logging
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException

from app.models import (
    QuoteWorkbook,
    RowQuoteProgress,
    RowQuoteSummary,
    RowQuoteTaskCreatedResponse,
    RowQuoteTaskError,
    RowQuoteTaskResponse,
    SheetSelection,
)
from app.row_quote_workflow import TaskCancelledError, annotate_row_quote_workbook

logger = logging.getLogger(__name__)

TASK_TTL_SECONDS = 1800

_tasks: dict[str, dict[str, Any]] = {}
_lock = threading.Lock()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _cleanup_expired_tasks() -> None:
    cutoff = time.time() - TASK_TTL_SECONDS
    with _lock:
        expired = [
            task_id
            for task_id, task in _tasks.items()
            if task.get("finished_at_epoch") is not None and task["finished_at_epoch"] < cutoff
        ]
        for task_id in expired:
            _tasks.pop(task_id, None)


def _touch(task: dict[str, Any]) -> None:
    task["updated_at"] = _now_iso()


def _make_response(task_id: str, task: dict[str, Any]) -> RowQuoteTaskResponse:
    return RowQuoteTaskResponse(
        task_id=task_id,
        status=task["status"],
        current_stage=task.get("current_stage"),
        summary=RowQuoteSummary.model_validate(task["summary"]) if task.get("summary") else None,
        progress=RowQuoteProgress.model_validate(task["progress"]) if task.get("progress") else None,
        error=RowQuoteTaskError.model_validate(task["error"]) if task.get("error") else None,
        created_at=task["created_at"],
        updated_at=task["updated_at"],
        finished_at=task.get("finished_at"),
    )


def _set_stage(task_id: str, stage: str) -> None:
    with _lock:
        task = _tasks.get(task_id)
        if not task:
            return
        task["status"] = "running"
        task["current_stage"] = stage
        _touch(task)


def _update_progress(task_id: str, progress: RowQuoteProgress) -> None:
    with _lock:
        task = _tasks.get(task_id)
        if not task:
            return
        task["progress"] = progress.model_dump()
        _touch(task)


def _is_cancelled(task_id: str) -> bool:
    with _lock:
        task = _tasks.get(task_id)
        return bool(task and task.get("cancelled"))


def _run_annotation_task(task_id: str, upload: dict[str, Any], quote_context: dict[str, Any], sheet_selection: SheetSelection | None = None) -> None:
    def on_progress(progress: RowQuoteProgress) -> None:
        _update_progress(task_id, progress)
        if _is_cancelled(task_id):
            raise TaskCancelledError("Task was cancelled by user.")

    def on_stage(stage: str) -> None:
        _set_stage(task_id, stage)
        if _is_cancelled(task_id):
            raise TaskCancelledError("Task was cancelled by user.")

    try:
        workbook, summary = annotate_row_quote_workbook(upload, quote_context, progress_callback=on_progress, stage_callback=on_stage, cancel_check=lambda: _is_cancelled(task_id), sheet_selection=sheet_selection)
        with _lock:
            task = _tasks.get(task_id)
            if not task:
                return
            if task.get("cancelled"):
                return
            task["status"] = "succeeded"
            task["current_stage"] = "completed"
            task["summary"] = summary.model_dump()
            task["workbook"] = workbook.model_dump()
            task["finished_at"] = _now_iso()
            task["finished_at_epoch"] = time.time()
            _touch(task)
    except TaskCancelledError:
        with _lock:
            task = _tasks.get(task_id)
            if not task:
                return
            task["status"] = "cancelled"
            task["current_stage"] = "cancelled"
            task["error"] = None
            task["finished_at"] = _now_iso()
            task["finished_at_epoch"] = time.time()
            _touch(task)
    except Exception as exc:
        logger.exception("Row-level flexible quote annotation task %s failed", task_id)
        with _lock:
            task = _tasks.get(task_id)
            if not task:
                return
            task["status"] = "failed"
            task["error"] = {
                "message": "Row-level flexible quote annotation failed.",
                "detail": str(exc),
                "last_stage": task.get("current_stage") or "collect_rows",
            }
            task["finished_at"] = _now_iso()
            task["finished_at_epoch"] = time.time()
            _touch(task)


def create_annotation_task(upload: dict[str, Any], quote_context: dict[str, Any], sheet_selection: SheetSelection | None = None) -> RowQuoteTaskCreatedResponse:
    _cleanup_expired_tasks()
    task_id = str(uuid.uuid4())
    now = _now_iso()
    with _lock:
        _tasks[task_id] = {
            "status": "queued",
            "current_stage": None,
            "summary": None,
            "progress": RowQuoteProgress().model_dump(),
            "error": None,
            "workbook": None,
            "cancelled": False,
            "created_at": now,
            "updated_at": now,
            "finished_at": None,
            "finished_at_epoch": None,
        }
    worker = threading.Thread(target=_run_annotation_task, args=(task_id, upload, quote_context, sheet_selection), daemon=True)
    worker.start()
    return RowQuoteTaskCreatedResponse(task_id=task_id, status="queued")


def get_annotation_task(task_id: str) -> RowQuoteTaskResponse:
    _cleanup_expired_tasks()
    with _lock:
        task = _tasks.get(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Flexible annotate task not found.")
        return _make_response(task_id, task)


def get_annotation_workbook(task_id: str) -> QuoteWorkbook:
    _cleanup_expired_tasks()
    with _lock:
        task = _tasks.get(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Flexible annotate task not found.")
        if task["status"] != "succeeded" or not task.get("workbook"):
            if task["status"] == "cancelled":
                raise HTTPException(status_code=409, detail="Task was cancelled; no workbook to export.")
            raise HTTPException(status_code=409, detail="Flexible annotate task is not ready for export.")
        return QuoteWorkbook.model_validate(task["workbook"])


def cancel_annotation_task(task_id: str) -> RowQuoteTaskResponse:
    _cleanup_expired_tasks()
    with _lock:
        task = _tasks.get(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Flexible annotate task not found.")
        if task["status"] not in ("queued", "running", "cancelled"):
            raise HTTPException(status_code=409, detail="Task is not running or queued; cannot cancel.")
        task["cancelled"] = True
        _touch(task)
        return _make_response(task_id, task)
