"""Tests for Proposal ↔ HLD integration — Phase 2."""
from __future__ import annotations

import json
import time
import threading

import pytest
from fastapi import HTTPException

from app.models import (
    HldDesignTaskCreatedResponse,
    HldDesignTaskResponse,
    HldRequirements,
    ProposalRequest,
)
from app.proposal_tasks import (
    _tasks,
    _lock,
    create_proposal_task,
    get_proposal_artifact,
    get_proposal_task,
)


def _wait_for_task(task_id: str, timeout: float = 10.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        resp = get_proposal_task(task_id)
        if resp.status in ("succeeded", "failed"):
            return
        time.sleep(0.05)
    raise TimeoutError(f"Task {task_id} did not finish within {timeout}s")


@pytest.fixture(autouse=True)
def _clear_tasks():
    yield
    with _lock:
        _tasks.clear()


def _make_request(with_hld: bool = False, **overrides) -> ProposalRequest:
    defaults = dict(
        project_name="test-project",
        business_background="Moving to cloud",
        current_pain_points="High on-prem costs",
        target_outcomes="Reduce TCO by 30%",
    )
    if with_hld:
        defaults["hld_requirements"] = HldRequirements(
            project_name="test-project",
            business_goal="Cloud migration",
            architecture_boundary="VPC",
            deployment_mode="cloud",
            user_access_entry="VPN",
            core_components="ECS, RDS",
            external_integrations="None",
            data_stores_flow="RDS primary",
            network_security_boundary="VPC + WAF",
        )
    defaults.update(overrides)
    return ProposalRequest(**defaults)


# --- Fake HLD task machinery ---

def _ensure_valid_png():
    """Ensure /tmp/fake-hld.png is a valid PNG for PPTX embedding."""
    import pathlib
    png_path = pathlib.Path("/tmp/fake-hld.png")
    if not png_path.exists() or png_path.stat().st_size < 200:
        from PIL import Image
        img = Image.new("RGB", (100, 100), color="blue")
        img.save(str(png_path))


def _fake_hld_create_success(requirements):
    """Simulate HLD task creation that succeeds immediately."""
    design_id = "fake-hld-" + requirements.project_name
    _ensure_valid_png()
    # Schedule a thread that marks the HLD task as succeeded after a short delay
    def _complete():
        time.sleep(0.1)
        from app.hld_tasks import _tasks as _hld_tasks, _lock as _hld_lock
        with _hld_lock:
            task = _hld_tasks.get(design_id)
            if task:
                task["status"] = "succeeded"
                task["current_stage"] = "completed"
                task["output_basename"] = "fake-hld"
                task["artifacts"] = {
                    "basename": "fake-hld",
                    "png": "/tmp/fake-hld.png",
                    "drawio": "/tmp/fake-hld.drawio",
                }
                task["finished_at"] = task["updated_at"]
                task["finished_at_epoch"] = time.time()
    # Write fake drawio artifact
    import pathlib
    pathlib.Path("/tmp/fake-hld.drawio").write_text("<mxfile/>", encoding="utf-8")
    # Register the HLD task in its internal dict
    from app.hld_tasks import _tasks as _hld_tasks, _lock as _hld_lock, _now_iso
    with _hld_lock:
        _hld_tasks[design_id] = {
            "status": "running",
            "current_stage": "generate_spec",
            "error": None,
            "output_basename": None,
            "artifacts": None,
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
            "finished_at": None,
            "finished_at_epoch": None,
        }
    threading.Thread(target=_complete, daemon=True).start()
    return HldDesignTaskCreatedResponse(design_id=design_id, status="queued")


def _fake_hld_create_failure(requirements):
    """Simulate HLD task creation that fails."""
    design_id = "fake-hld-fail-" + requirements.project_name

    def _fail():
        time.sleep(0.1)
        from app.hld_tasks import _tasks as _hld_tasks, _lock as _hld_lock, _now_iso
        with _hld_lock:
            task = _hld_tasks.get(design_id)
            if task:
                task["status"] = "failed"
                task["current_stage"] = "generate_spec"
                task["error"] = {
                    "message": "HLD design generation failed.",
                    "detail": "Simulated HLD failure",
                    "last_stage": "generate_spec",
                }
                task["finished_at"] = _now_iso()
                task["finished_at_epoch"] = time.time()

    from app.hld_tasks import _tasks as _hld_tasks, _lock as _hld_lock, _now_iso
    with _hld_lock:
        _hld_tasks[design_id] = {
            "status": "running",
            "current_stage": "generate_spec",
            "error": None,
            "output_basename": None,
            "artifacts": None,
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
            "finished_at": None,
            "finished_at_epoch": None,
        }
    threading.Thread(target=_fail, daemon=True).start()
    return HldDesignTaskCreatedResponse(design_id=design_id, status="queued")


class TestNoHldRequirements:
    """Proposal without HLD requirements still succeeds (Phase 1 compat)."""

    def test_succeeds_without_hld(self):
        created = create_proposal_task(_make_request(with_hld=False))
        _wait_for_task(created.task_id)
        task = get_proposal_task(created.task_id)
        assert task.status == "succeeded"
        assert task.hld_design_id is None

    def test_json_has_hld_status_skipped(self):
        created = create_proposal_task(_make_request(with_hld=False))
        _wait_for_task(created.task_id)
        content, _, _ = get_proposal_artifact(created.task_id, "json")
        data = json.loads(content)
        assert data["hld_status"] == "skipped"
        assert data["hld_design_id"] is None


class TestHldSuccess:
    """Proposal with HLD requirements delegates to HLD and records results."""

    @pytest.fixture(autouse=True)
    def _patch_hld_create(self, monkeypatch):
        monkeypatch.setattr("app.proposal_tasks.create_hld_design_task", _fake_hld_create_success)

    def test_proposal_succeeds_with_hld(self):
        created = create_proposal_task(_make_request(with_hld=True))
        _wait_for_task(created.task_id, timeout=15)
        task = get_proposal_task(created.task_id)
        assert task.status == "succeeded"
        assert task.hld_design_id is not None

    def test_json_has_hld_status_succeeded(self):
        created = create_proposal_task(_make_request(with_hld=True))
        _wait_for_task(created.task_id, timeout=15)
        content, _, _ = get_proposal_artifact(created.task_id, "json")
        data = json.loads(content)
        assert data["hld_status"] == "succeeded"
        assert data["hld_design_id"] is not None
        assert data["hld_artifacts"]["png_filename"].endswith(".png")
        assert data["hld_artifacts"]["drawio_filename"].endswith(".drawio")

    def test_hld_png_downloadable(self):
        created = create_proposal_task(_make_request(with_hld=True))
        _wait_for_task(created.task_id, timeout=15)
        content, media_type, filename = get_proposal_artifact(created.task_id, "hld_png")
        assert media_type == "image/png"
        assert len(content) > 0

    def test_hld_drawio_downloadable(self):
        created = create_proposal_task(_make_request(with_hld=True))
        _wait_for_task(created.task_id, timeout=15)
        content, media_type, filename = get_proposal_artifact(created.task_id, "hld_drawio")
        assert media_type == "application/xml"
        assert len(content) > 0


class TestHldFailure:
    """HLD failure propagates to Proposal task failure."""

    @pytest.fixture(autouse=True)
    def _patch_hld_create_fail(self, monkeypatch):
        monkeypatch.setattr("app.proposal_tasks.create_hld_design_task", _fake_hld_create_failure)

    def test_proposal_fails_when_hld_fails(self):
        created = create_proposal_task(_make_request(with_hld=True))
        _wait_for_task(created.task_id, timeout=15)
        task = get_proposal_task(created.task_id)
        assert task.status == "failed"
        assert task.error is not None
        assert "HLD" in task.error.detail
