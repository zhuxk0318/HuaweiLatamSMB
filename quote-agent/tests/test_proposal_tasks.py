"""Tests for proposal task queue — minimal Phase 1 coverage."""
from __future__ import annotations

import time

import pytest
from fastapi import HTTPException

from app.models import ProposalRequest
from app.proposal_tasks import (
    _tasks,
    _lock,
    create_proposal_task,
    get_proposal_artifact,
    get_proposal_task,
)


def _wait_for_task(task_id: str, timeout: float = 10.0) -> None:
    """Poll until task is no longer queued/running."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        resp = get_proposal_task(task_id)
        if resp.status in ("succeeded", "failed"):
            return
        time.sleep(0.1)
    raise TimeoutError(f"Task {task_id} did not finish within {timeout}s")


@pytest.fixture(autouse=True)
def _clear_tasks():
    yield
    with _lock:
        _tasks.clear()


def _make_request(**overrides) -> ProposalRequest:
    defaults = dict(
        project_name="test-project",
        business_background="Moving to cloud",
        current_pain_points="High on-prem costs",
        target_outcomes="Reduce TCO by 30%",
    )
    defaults.update(overrides)
    return ProposalRequest(**defaults)


class TestCreateProposalTask:
    def test_create_returns_queued(self):
        resp = create_proposal_task(_make_request())
        assert resp.status == "queued"
        assert resp.task_id


class TestProposalTaskSucceeds:
    def test_task_succeeds(self):
        created = create_proposal_task(_make_request())
        _wait_for_task(created.task_id)
        task = get_proposal_task(created.task_id)
        assert task.status == "succeeded"
        assert task.current_stage == "completed"
        assert task.artifacts is not None
        assert task.artifacts.json_info is not None
        assert task.artifacts.pptx_info is not None


class TestProposalArtifacts:
    def test_download_json(self):
        created = create_proposal_task(_make_request())
        _wait_for_task(created.task_id)
        content, media_type, filename = get_proposal_artifact(created.task_id, "json")
        assert media_type == "application/json"
        assert filename.endswith(".json")
        assert b"project_name" in content

    def test_download_pptx(self):
        created = create_proposal_task(_make_request())
        _wait_for_task(created.task_id)
        content, media_type, filename = get_proposal_artifact(created.task_id, "pptx")
        assert media_type == "application/vnd.openxmlformats-officedocument.presentationml.presentation"
        assert filename.endswith(".pptx")
        assert len(content) > 0


class TestProposalTaskNotFound:
    def test_unknown_task_404(self):
        with pytest.raises(HTTPException) as exc_info:
            get_proposal_task("nonexistent-id")
        assert exc_info.value.status_code == 404

    def test_unknown_artifact_404(self):
        with pytest.raises(HTTPException) as exc_info:
            get_proposal_artifact("nonexistent-id", "json")
        assert exc_info.value.status_code == 404
