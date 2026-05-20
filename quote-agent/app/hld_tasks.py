"""In-memory async task queue for HLD design generation."""
from __future__ import annotations

import logging
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from app.hld_workflow import (
    ARTIFACTS_ROOT,
    cleanup_artifacts,
    cleanup_orphan_artifacts,
    generate_hld_design,
    validate_drawio_cli,
    validate_xvfb,
)
from app.models import (
    HldDesignTaskCreatedResponse,
    HldDesignTaskError,
    HldDesignTaskResponse,
    HldRequirements,
)

logger = logging.getLogger(__name__)

TASK_TTL_SECONDS = 1800

_tasks: dict[str, dict[str, Any]] = {}
_lock = threading.Lock()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _cleanup_expired_tasks() -> None:
    cutoff = time.time() - TASK_TTL_SECONDS
    expired = []
    with _lock:
        for design_id, task in _tasks.items():
            finished_at = task.get("finished_at_epoch")
            if finished_at is not None and finished_at < cutoff:
                expired.append(design_id)
        for design_id in expired:
            _tasks.pop(design_id, None)
            cleanup_artifacts(design_id)


def startup_cleanup() -> None:
    """Call once at service startup to clean orphan artifacts."""
    cleanup_orphan_artifacts()


def _touch(task: dict[str, Any]) -> None:
    task["updated_at"] = _now_iso()


def _make_response(design_id: str, task: dict[str, Any]) -> HldDesignTaskResponse:
    return HldDesignTaskResponse(
        design_id=design_id,
        status=task["status"],
        current_stage=task.get("current_stage"),
        error=HldDesignTaskError.model_validate(task["error"]) if task.get("error") else None,
        output_basename=task.get("output_basename"),
        created_at=task["created_at"],
        updated_at=task["updated_at"],
        finished_at=task.get("finished_at"),
    )


def _set_stage(design_id: str, stage: str) -> None:
    with _lock:
        task = _tasks.get(design_id)
        if not task:
            return
        task["status"] = "running"
        task["current_stage"] = stage
        _touch(task)


def _run_hld_design_task(design_id: str, requirements: HldRequirements) -> None:
    artifacts_dir = ARTIFACTS_ROOT / design_id
    try:
        # Stage: validate_cli
        _set_stage(design_id, "validate_cli")
        logger.info("HLD task %s: validating CLI", design_id)
        cli_cmd = validate_drawio_cli()
        validate_xvfb()

        # Run the full pipeline with stage_callback
        def on_stage(stage: str) -> None:
            _set_stage(design_id, stage)

        result = generate_hld_design(
            requirements, artifacts_dir,
            cli_cmd=cli_cmd,
            stage_callback=on_stage,
        )

        # Completed — but first verify artifacts actually exist on disk
        for key in ("drawio", "png"):
            artifact_path = result.get(key)
            if not artifact_path or not Path(artifact_path).exists() or Path(artifact_path).stat().st_size == 0:
                raise RuntimeError(f"Artifact {key} missing or empty after generation: {artifact_path}")

        with _lock:
            task = _tasks.get(design_id)
            if not task:
                return
            task["status"] = "succeeded"
            task["current_stage"] = "completed"
            task["output_basename"] = result.get("basename")
            task["artifacts"] = result
            task["finished_at"] = _now_iso()
            task["finished_at_epoch"] = time.time()
            _touch(task)
            logger.info("HLD task %s: succeeded, basename=%s", design_id, result.get("basename"))

    except Exception as exc:
        logger.exception("HLD task %s failed at stage %s", design_id, _tasks.get(design_id, {}).get("current_stage"))
        with _lock:
            task = _tasks.get(design_id)
            if not task:
                return
            current_stage = task.get("current_stage")
            task["status"] = "failed"
            task["error"] = {
                "message": "HLD design generation failed.",
                "detail": str(exc),
                "last_stage": current_stage,
            }
            task["finished_at"] = _now_iso()
            task["finished_at_epoch"] = time.time()
            _touch(task)


def create_hld_design_task(requirements: HldRequirements) -> HldDesignTaskCreatedResponse:
    _cleanup_expired_tasks()
    design_id = str(uuid.uuid4())
    task = {
        "status": "queued",
        "current_stage": None,
        "error": None,
        "output_basename": None,
        "artifacts": None,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
        "finished_at": None,
        "finished_at_epoch": None,
    }
    with _lock:
        _tasks[design_id] = task
    worker = threading.Thread(target=_run_hld_design_task, args=(design_id, requirements), daemon=True)
    worker.start()
    return HldDesignTaskCreatedResponse(design_id=design_id, status="queued")


def get_hld_design_task(design_id: str) -> HldDesignTaskResponse:
    _cleanup_expired_tasks()
    with _lock:
        task = _tasks.get(design_id)
        if not task:
            raise HTTPException(status_code=404, detail="HLD design task not found.")
        return _make_response(design_id, task)


def get_hld_design_artifact(design_id: str, artifact_type: str) -> tuple[bytes, str, str]:
    """Return (content_bytes, media_type, filename) for the artifact."""
    with _lock:
        task = _tasks.get(design_id)
        if not task:
            raise HTTPException(status_code=404, detail="HLD design task not found.")
        if task["status"] != "succeeded":
            raise HTTPException(status_code=409, detail="HLD design task has not succeeded yet.")
        artifacts = task.get("artifacts", {})
        basename = task.get("output_basename", "hld-design")

    if artifact_type == "png":
        path = artifacts.get("png")
        if not path:
            raise HTTPException(status_code=404, detail="PNG artifact not found.")
        p = Path(path)
        if not p.exists() or not p.is_file():
            raise HTTPException(status_code=404, detail="PNG artifact is missing from disk.")
        if p.stat().st_size == 0:
            raise HTTPException(status_code=409, detail="PNG artifact exists but is empty.")
        with open(path, "rb") as f:
            content = f.read()
        return content, "image/png", f"{basename}.png"

    if artifact_type == "drawio":
        path = artifacts.get("drawio")
        if not path:
            raise HTTPException(status_code=404, detail="Drawio artifact not found.")
        p = Path(path)
        if not p.exists() or not p.is_file():
            raise HTTPException(status_code=404, detail="Drawio artifact is missing from disk.")
        if p.stat().st_size == 0:
            raise HTTPException(status_code=409, detail="Drawio artifact exists but is empty.")
        with open(path, "rb") as f:
            content = f.read()
        return content, "application/xml", f"{basename}.drawio"

    raise HTTPException(status_code=400, detail=f"Unknown artifact type: {artifact_type}")
