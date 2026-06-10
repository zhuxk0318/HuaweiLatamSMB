from __future__ import annotations

import logging
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException

from app.cloud_billing_workflow import cloud_billing_preview_graph
from app.flexible_workflow import (
    _detect_billing_document,
    _route_after_validation,
    deduplicate_items,
    export_flexible_workbook,
    extract_requirement_items,
    ingest_files,
    load_pricebook,
    map_to_huawei_product,
    normalize_requirements,
    parse_documents,
    quote_items,
    resolve_price_components,
    return_blockers,
    summarize_quote,
    validate_quote_readiness,
)
from app.models import (
    FlexibleQuoteSummary,
    QuoteWorkbook,
    RowQuoteProgress,
    RowQuoteSummary,
    RowQuoteTaskCreatedResponse,
    RowQuoteTaskError,
    RowQuoteTaskResponse,
    SheetSelection,
)
from app.others_quote_workflow import others_preview_graph
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


def _billing_summary_from_state(state: dict[str, Any]) -> RowQuoteSummary:
    summary = FlexibleQuoteSummary.model_validate(state.get("summary", {}))
    blockers = state.get("quote_blockers", [])
    unquoted = state.get("unquoted_items", [])
    quote_lines = state.get("quote_lines", [])
    mapped = state.get("mapped_billing_resources", [])
    unmatched = sum(1 for item in mapped if not item.get("huawei_product"))
    manual_review = max(
        len(blockers),
        sum(1 for item in mapped if item.get("needs_manual_review")),
    )
    return RowQuoteSummary(
        total_rows=len(mapped) or len(state.get("billing_lines", [])),
        quoted_rows=len(quote_lines),
        unmatched_rows=unmatched,
        manual_review_rows=manual_review,
        missing_price_rows=len(unquoted),
        non_quote_rows=0,
        total_ondemand_monthly=summary.total_monthly_price,
        total_monthly=summary.total_monthly_price,
        total_ri_1y_monthly=0,
        currency=summary.currency,
    )


def _billing_progress_from_state(state: dict[str, Any]) -> RowQuoteProgress:
    total_rows = len(state.get("mapped_billing_resources", [])) or len(state.get("billing_lines", []))
    quoted_rows = len(state.get("quote_lines", []))
    blocker_rows = len(state.get("quote_blockers", []))
    unquoted_rows = len(state.get("unquoted_items", []))
    mapped_rows = len(state.get("requirements", []))
    priced_rows = quoted_rows + unquoted_rows
    return RowQuoteProgress(
        total_rows=total_rows,
        processed_rows=priced_rows,
        quoted_rows=quoted_rows,
        manual_review_rows=blocker_rows,
        missing_price_rows=unquoted_rows,
        unmatched_rows=sum(1 for item in state.get("mapped_billing_resources", []) if not item.get("huawei_product")),
        non_quote_rows=0,
        mapped_rows=mapped_rows,
        priced_rows=priced_rows,
        stage_processed_rows=priced_rows,
        stage_total_rows=total_rows,
    )


def _quote_summary_from_state(state: dict[str, Any]) -> RowQuoteSummary:
    summary = FlexibleQuoteSummary.model_validate(state.get("summary", {}))
    requirements = state.get("requirements", [])
    quote_lines = state.get("quote_lines", [])
    blockers = state.get("quote_blockers", [])
    unquoted = state.get("unquoted_items", [])
    total_rows = summary.total_input_items or len(requirements)
    quoted_rows = len(quote_lines)
    manual_review_rows = len(blockers)
    missing_price_rows = len(unquoted)
    unmatched_rows = max(total_rows - quoted_rows - manual_review_rows - missing_price_rows, 0)
    return RowQuoteSummary(
        total_rows=total_rows,
        quoted_rows=quoted_rows,
        unmatched_rows=unmatched_rows,
        manual_review_rows=manual_review_rows,
        missing_price_rows=missing_price_rows,
        non_quote_rows=0,
        total_ondemand_monthly=summary.total_monthly_price,
        total_monthly=summary.total_monthly_price,
        total_ri_1y_monthly=0,
        currency=summary.currency,
    )


def _quote_progress_from_state(state: dict[str, Any]) -> RowQuoteProgress:
    summary = _quote_summary_from_state(state)
    processed_rows = summary.quoted_rows + summary.manual_review_rows + summary.missing_price_rows + summary.unmatched_rows
    return RowQuoteProgress(
        total_rows=summary.total_rows,
        processed_rows=processed_rows,
        quoted_rows=summary.quoted_rows,
        manual_review_rows=summary.manual_review_rows,
        missing_price_rows=summary.missing_price_rows,
        unmatched_rows=summary.unmatched_rows,
        non_quote_rows=summary.non_quote_rows,
        mapped_rows=summary.total_rows,
        priced_rows=summary.quoted_rows + summary.missing_price_rows,
        stage_processed_rows=processed_rows,
        stage_total_rows=summary.total_rows,
    )


def _is_billing_upload(upload: dict[str, Any], quote_context: dict[str, Any]) -> bool:
    state: dict[str, Any] = {"files": [upload], "quote_context": quote_context, "audit_log": []}
    state.update(ingest_files(state))
    state.update(parse_documents(state))
    return any(_detect_billing_document(doc) for doc in state.get("parsed_documents", []))


def _run_billing_annotation_task(
    upload: dict[str, Any],
    quote_context: dict[str, Any],
    *,
    on_progress: Any,
    on_stage: Any,
    cancel_check: Any,
) -> tuple[QuoteWorkbook, RowQuoteSummary]:
    def progress_callback(stage: str, status: str, _message: str) -> None:
        if status == "running":
            on_stage(stage)
        if callable(cancel_check) and cancel_check():
            raise TaskCancelledError("Task was cancelled by user.")

    state: dict[str, Any] = {
        "files": [upload],
        "quote_context": quote_context,
        "audit_log": [],
        "progress_callback": progress_callback,
        "skip_billing_llm": True,
    }

    for stage_fn in (ingest_files, load_pricebook, parse_documents, extract_requirement_items, normalize_requirements, deduplicate_items, map_to_huawei_product):
        state.update(stage_fn(state))
        if callable(cancel_check) and cancel_check():
            raise TaskCancelledError("Task was cancelled by user.")

    on_progress(_billing_progress_from_state(state))

    state.update(validate_quote_readiness(state))
    if callable(cancel_check) and cancel_check():
        raise TaskCancelledError("Task was cancelled by user.")

    if _route_after_validation(state) == "needs_input":
        state.update(return_blockers(state))
    else:
        state.update(resolve_price_components(state))
        if callable(cancel_check) and cancel_check():
            raise TaskCancelledError("Task was cancelled by user.")
        on_progress(_billing_progress_from_state(state))
        state.update(quote_items(state))

    state.update(summarize_quote(state))
    state.update(export_flexible_workbook(state))
    on_progress(_billing_progress_from_state(state))
    return QuoteWorkbook.model_validate(state["workbook"]), _billing_summary_from_state(state)


def _run_quote_graph_annotation_task(
    graph: Any,
    upload: dict[str, Any],
    quote_context: dict[str, Any],
    *,
    on_progress: Any,
    on_stage: Any,
    cancel_check: Any,
) -> tuple[QuoteWorkbook, RowQuoteSummary]:
    def progress_callback(stage: str, status: str, _message: str) -> None:
        if status == "running":
            on_stage(stage)
        if callable(cancel_check) and cancel_check():
            raise TaskCancelledError("Task was cancelled by user.")

    state: dict[str, Any] = {
        "files": [upload],
        "quote_context": quote_context,
        "audit_log": [],
        "progress_callback": progress_callback,
    }

    state = graph.invoke(state)
    if callable(cancel_check) and cancel_check():
        raise TaskCancelledError("Task was cancelled by user.")
    state.update(export_flexible_workbook(state))
    on_progress(_quote_progress_from_state(state))
    return QuoteWorkbook.model_validate(state["workbook"]), _quote_summary_from_state(state)


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
        quote_mode = quote_context.get("quote_mode")
        if quote_mode == "cloud_billing":
            workbook, summary = _run_quote_graph_annotation_task(
                cloud_billing_preview_graph,
                upload,
                quote_context,
                on_progress=on_progress,
                on_stage=on_stage,
                cancel_check=lambda: _is_cancelled(task_id),
            )
        elif quote_mode == "others":
            workbook, summary = _run_quote_graph_annotation_task(
                others_preview_graph,
                upload,
                quote_context,
                on_progress=on_progress,
                on_stage=on_stage,
                cancel_check=lambda: _is_cancelled(task_id),
            )
        elif _is_billing_upload(upload, quote_context):
            workbook, summary = _run_billing_annotation_task(
                upload,
                quote_context,
                on_progress=on_progress,
                on_stage=on_stage,
                cancel_check=lambda: _is_cancelled(task_id),
            )
        else:
            workbook, summary = annotate_row_quote_workbook(
                upload,
                quote_context,
                progress_callback=on_progress,
                stage_callback=on_stage,
                cancel_check=lambda: _is_cancelled(task_id),
                sheet_selection=sheet_selection,
            )
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
