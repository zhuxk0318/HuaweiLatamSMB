"""Tests for Proposal ↔ Quote integration — Phase 3A."""
from __future__ import annotations

import json
import time

import pytest
from fastapi import HTTPException

from app.models import (
    FlexibleQuotePreviewResponse,
    FlexibleQuoteSummary,
    ProposalQuoteInput,
    ProposalQuoteResult,
    ProposalQuoteSummary,
    ProposalRequest,
    RequirementItem,
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


def _make_request(quote_mode: str = "skip", quote_input: ProposalQuoteInput | None = None, **overrides) -> ProposalRequest:
    defaults = dict(
        project_name="test-project",
        business_background="Moving to cloud",
        current_pain_points="High on-prem costs",
        target_outcomes="Reduce TCO by 30%",
        quote_mode=quote_mode,
    )
    if quote_input:
        defaults["quote_input"] = quote_input
    defaults.update(overrides)
    return ProposalRequest(**defaults)


def _fake_requirement_items() -> list[RequirementItem]:
    return [
        RequirementItem(
            item_id="req-1",
            source_file="proposal_requirements.csv",
            raw_product_name="ECS",
            normalized_product="ECS",
            quantity=2,
            unit="instances",
            region="mexico",
            status="ready",
        ),
    ]


# --- Fake flexible quote graph ---

def _fake_flexible_invoke_success(state):
    """Return a state dict matching FlexibleQuotePreviewResponse structure."""
    return {
        "requirements": [],
        "quote_ready_items": [],
        "quote_blockers": [],
        "quote_lines": [
            {"line_id": "l1", "requirement_item_id": "req-1", "product": "ECS",
             "region": "mexico", "quantity": 2, "unit": "instances",
             "billing_mode": "on-demand", "unit_price": 100.0,
             "monthly_price": 200.0, "currency": "USD"},
        ],
        "unquoted_items": [],
        "matched_products": [],
        "summary": {
            "total_input_items": 1,
            "quote_ready_items": 1,
            "quoted_items": 1,
            "blocker_count": 0,
            "unquoted_count": 0,
            "total_monthly_price": 200.0,
            "currency": "USD",
            "summary": "1 item quoted",
            "assumptions": [],
            "risks": [],
        },
        "audit_log": [],
        "quote_context": {"region": "mexico", "language": "en", "customer_notes": ""},
        "diagnostics": {"llm_used": False},
    }


def _fake_flexible_invoke_failure(state):
    raise RuntimeError("Simulated flexible quote failure")


class TestQuoteModeSkip:
    """quote_mode='skip' — Proposal succeeds, quote_status='skipped'."""

    def test_succeeds_with_skip(self):
        created = create_proposal_task(_make_request(quote_mode="skip"))
        _wait_for_task(created.task_id)
        task = get_proposal_task(created.task_id)
        assert task.status == "succeeded"

    def test_json_has_quote_status_skipped(self):
        created = create_proposal_task(_make_request(quote_mode="skip"))
        _wait_for_task(created.task_id)
        content, _, _ = get_proposal_artifact(created.task_id, "json")
        data = json.loads(content)
        assert data["quote_status"] == "skipped"
        assert data["quote_mode"] == "skip"


class TestQuoteModeFlexible:
    """quote_mode='flexible' — delegates to flexible quote graph."""

    @pytest.fixture(autouse=True)
    def _patch_flexible_graph(self, monkeypatch):
        monkeypatch.setattr(
            "app.proposal_tasks.flexible_preview_graph.invoke",
            _fake_flexible_invoke_success,
        )

    def test_proposal_succeeds_with_flexible_quote(self):
        req = _make_request(
            quote_mode="flexible",
            quote_input=ProposalQuoteInput(
                requirements=_fake_requirement_items(),
                region="mexico",
            ),
        )
        created = create_proposal_task(req)
        _wait_for_task(created.task_id, timeout=15)
        task = get_proposal_task(created.task_id)
        assert task.status == "succeeded"

    def test_json_has_quote_status_succeeded(self):
        req = _make_request(
            quote_mode="flexible",
            quote_input=ProposalQuoteInput(
                requirements=_fake_requirement_items(),
                region="mexico",
            ),
        )
        created = create_proposal_task(req)
        _wait_for_task(created.task_id, timeout=15)
        content, _, _ = get_proposal_artifact(created.task_id, "json")
        data = json.loads(content)
        assert data["quote_status"] == "succeeded"
        assert data["quote_mode"] == "flexible"
        assert data["quote_summary"]["total_monthly_price"] == 200.0
        assert data["quote_summary"]["quoted_items"] == 1
        assert data["quote_summary"]["blocker_count"] == 0

    def test_pricing_summary_filled_from_quote(self):
        req = _make_request(
            quote_mode="flexible",
            quote_input=ProposalQuoteInput(
                requirements=_fake_requirement_items(),
                region="mexico",
            ),
        )
        created = create_proposal_task(req)
        _wait_for_task(created.task_id, timeout=15)
        content, _, _ = get_proposal_artifact(created.task_id, "json")
        data = json.loads(content)
        assert "200.00" in data["sections"]["pricing_summary"]


class TestQuoteModeFlexibleFailure:
    """Flexible quote failure propagates to Proposal task failure."""

    @pytest.fixture(autouse=True)
    def _patch_flexible_graph_fail(self, monkeypatch):
        monkeypatch.setattr(
            "app.proposal_tasks.flexible_preview_graph.invoke",
            _fake_flexible_invoke_failure,
        )

    def test_proposal_fails_when_flexible_fails(self):
        req = _make_request(
            quote_mode="flexible",
            quote_input=ProposalQuoteInput(
                requirements=_fake_requirement_items(),
                region="mexico",
            ),
        )
        created = create_proposal_task(req)
        _wait_for_task(created.task_id, timeout=15)
        task = get_proposal_task(created.task_id)
        assert task.status == "failed"
        assert "flexible quote failure" in task.error.detail


class TestQuoteModeRvtools:
    """quote_mode='rvtools' — not implemented, but task still succeeds."""

    def test_rvtools_not_implemented_but_succeeds(self):
        created = create_proposal_task(_make_request(quote_mode="rvtools"))
        _wait_for_task(created.task_id)
        task = get_proposal_task(created.task_id)
        assert task.status == "succeeded"

    def test_json_has_quote_status_not_implemented(self):
        created = create_proposal_task(_make_request(quote_mode="rvtools"))
        _wait_for_task(created.task_id)
        content, _, _ = get_proposal_artifact(created.task_id, "json")
        data = json.loads(content)
        assert data["quote_status"] == "not_implemented"
        assert data["quote_mode"] == "rvtools"


class TestQuoteAndHldCoexist:
    """Quote + HLD both run in the same Proposal task."""

    @pytest.fixture(autouse=True)
    def _patch_graphs(self, monkeypatch):
        monkeypatch.setattr(
            "app.proposal_tasks.flexible_preview_graph.invoke",
            _fake_flexible_invoke_success,
        )
        import pathlib
        from app.models import HldDesignTaskCreatedResponse

        def _fake_hld_create(requirements):
            design_id = "fake-hld-coexist"
            # Write a valid PNG for PPTX embedding
            from PIL import Image
            img = Image.new("RGB", (100, 100), color="blue")
            img.save("/tmp/fake-hld.png")
            pathlib.Path("/tmp/fake-hld.drawio").write_text("<mxfile/>", encoding="utf-8")
            from app.hld_tasks import _tasks as _hld_tasks, _lock as _hld_lock, _now_iso
            with _hld_lock:
                _hld_tasks[design_id] = {
                    "status": "succeeded",
                    "current_stage": "completed",
                    "error": None,
                    "output_basename": "fake-hld",
                    "artifacts": {
                        "basename": "fake-hld",
                        "png": "/tmp/fake-hld.png",
                        "drawio": "/tmp/fake-hld.drawio",
                    },
                    "created_at": _now_iso(),
                    "updated_at": _now_iso(),
                    "finished_at": _now_iso(),
                    "finished_at_epoch": time.time(),
                }
            return HldDesignTaskCreatedResponse(design_id=design_id, status="queued")

        monkeypatch.setattr("app.proposal_tasks.create_hld_design_task", _fake_hld_create)

    def test_both_quote_and_hld_succeed(self):
        from app.models import HldRequirements, ProposalQuoteInput

        req = _make_request(
            quote_mode="flexible",
            quote_input=ProposalQuoteInput(
                requirements=_fake_requirement_items(),
                region="mexico",
            ),
            hld_requirements=HldRequirements(
                project_name="test-project",
                business_goal="Cloud migration",
                architecture_boundary="VPC",
                deployment_mode="cloud",
                user_access_entry="VPN",
                core_components="ECS, RDS",
                external_integrations="None",
                data_stores_flow="RDS primary",
                network_security_boundary="VPC + WAF",
            ),
        )

        created = create_proposal_task(req)
        _wait_for_task(created.task_id, timeout=15)
        task = get_proposal_task(created.task_id)
        assert task.status == "succeeded"

        content, _, _ = get_proposal_artifact(created.task_id, "json")
        data = json.loads(content)
        assert data["quote_status"] == "succeeded"
        assert data["hld_status"] == "succeeded"
