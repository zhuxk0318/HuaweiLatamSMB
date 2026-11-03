"""Tests for Proposal content selection controls — content_selection fields."""
from __future__ import annotations

import json
import time

import pytest
from pptx import Presentation

from app.models import (
    ProposalQuoteInput,
    ProposalRequest,
    RequirementItem,
    HldRequirements,
)
from app.proposal_pptx import DEFAULT_TEMPLATE_PATH, render_proposal_pptx
from app.proposal_tasks import (
    _tasks,
    _lock,
    create_proposal_task,
    get_proposal_artifact,
    get_proposal_task,
)


def _wait_for_task(task_id: str, timeout: float = 15.0) -> None:
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


def _make_request(**overrides) -> ProposalRequest:
    defaults = dict(
        project_name="test-project",
        business_background="Moving to cloud",
        current_pain_points="High on-prem costs",
        target_outcomes="Reduce TCO by 30%",
    )
    defaults.update(overrides)
    return ProposalRequest(**defaults)


def _force_fallback(monkeypatch):
    """Force content fallback so tests don't need MaaS."""
    def _fake_build(*, timeout=None):
        raise RuntimeError("No MaaS in test")
    monkeypatch.setattr("app.proposal_tasks.build_proposal_chat_client_from_env", _fake_build)


# --- 1. Old request without new fields still succeeds ---

class TestBackwardCompatibility:
    def test_old_request_succeeds(self):
        req = _make_request()
        created = create_proposal_task(req)
        _wait_for_task(created.task_id)
        task = get_proposal_task(created.task_id)
        assert task.status == "succeeded"

    def test_old_request_has_content_selection_defaults(self):
        req = _make_request()
        created = create_proposal_task(req)
        _wait_for_task(created.task_id)
        content, _, _ = get_proposal_artifact(created.task_id, "json")
        data = json.loads(content)
        cs = data["content_selection"]
        assert cs["include_hld"] is False
        assert cs["include_price"] is False
        assert cs["include_migration"] is False
        assert cs["include_support_training"] is False
        assert cs["include_huawei_capability"] is True


# --- 2. New fields written to proposal.json ---

class TestNewFieldsInJson:
    @pytest.fixture(autouse=True)
    def _patch(self, monkeypatch):
        _force_fallback(monkeypatch)

    def test_proposal_title_written(self):
        req = _make_request(proposal_title="My Proposal", proposal_subtitle="Cloud Migration")
        created = create_proposal_task(req)
        _wait_for_task(created.task_id)
        content, _, _ = get_proposal_artifact(created.task_id, "json")
        data = json.loads(content)
        assert data["proposal_title"] == "My Proposal"
        assert data["proposal_subtitle"] == "Cloud Migration"

    def test_content_selection_written(self):
        req = _make_request(include_hld=True, include_price=True, include_migration=True)
        created = create_proposal_task(req)
        _wait_for_task(created.task_id)
        content, _, _ = get_proposal_artifact(created.task_id, "json")
        data = json.loads(content)
        cs = data["content_selection"]
        assert cs["include_hld"] is True
        assert cs["include_price"] is True
        assert cs["include_migration"] is True

    def test_asset_linking_written(self):
        req = _make_request(hld_mode="create_new", price_mode="create_new")
        created = create_proposal_task(req)
        _wait_for_task(created.task_id)
        content, _, _ = get_proposal_artifact(created.task_id, "json")
        data = json.loads(content)
        assert data["asset_linking"]["hld_mode"] == "create_new"
        assert data["asset_linking"]["price_mode"] == "create_new"

    def test_migration_context_written(self):
        req = _make_request(
            include_migration=True,
            migration_scope="Full data center",
            migration_constraints="No downtime",
            migration_notes="Phased approach",
        )
        created = create_proposal_task(req)
        _wait_for_task(created.task_id)
        content, _, _ = get_proposal_artifact(created.task_id, "json")
        data = json.loads(content)
        mc = data["migration_context"]
        assert mc["scope"] == "Full data center"
        assert mc["constraints"] == "No downtime"
        assert mc["notes"] == "Phased approach"


# --- 3. include_hld=false skips HLD ---

class TestIncludeHldFalse:
    @pytest.fixture(autouse=True)
    def _patch(self, monkeypatch):
        _force_fallback(monkeypatch)

    def test_hld_skipped_when_include_false(self):
        req = _make_request(include_hld=False)
        created = create_proposal_task(req)
        _wait_for_task(created.task_id)
        content, _, _ = get_proposal_artifact(created.task_id, "json")
        data = json.loads(content)
        assert data["hld_status"] == "skipped"


# --- 4. include_price=false skips quote ---

class TestIncludePriceFalse:
    @pytest.fixture(autouse=True)
    def _patch(self, monkeypatch):
        _force_fallback(monkeypatch)

    def test_quote_skipped_when_include_false(self):
        req = _make_request(include_price=False, quote_mode="flexible")
        created = create_proposal_task(req)
        _wait_for_task(created.task_id)
        content, _, _ = get_proposal_artifact(created.task_id, "json")
        data = json.loads(content)
        assert data["quote_status"] == "skipped"


# --- 5. include_hld=true + create_new + no hld_requirements → pending_external_workflow ---

class TestHldPendingExternalWorkflow:
    @pytest.fixture(autouse=True)
    def _patch(self, monkeypatch):
        _force_fallback(monkeypatch)

    def test_hld_pending_when_create_new_no_requirements(self):
        req = _make_request(include_hld=True, hld_mode="create_new")
        created = create_proposal_task(req)
        _wait_for_task(created.task_id)
        content, _, _ = get_proposal_artifact(created.task_id, "json")
        data = json.loads(content)
        assert data["hld_status"] == "pending_external_workflow"


# --- 6. include_price=true + create_new + no quote_input → pending_external_workflow ---

class TestPricePendingExternalWorkflow:
    @pytest.fixture(autouse=True)
    def _patch(self, monkeypatch):
        _force_fallback(monkeypatch)

    def test_quote_pending_when_create_new_no_input(self):
        req = _make_request(include_price=True, price_mode="create_new", quote_mode="flexible")
        created = create_proposal_task(req)
        _wait_for_task(created.task_id)
        content, _, _ = get_proposal_artifact(created.task_id, "json")
        data = json.loads(content)
        assert data["quote_status"] == "pending_external_workflow"


# --- 7. PPT section gating ---

class TestPptSectionGating:
    def _sample_data(self, **overrides) -> dict:
        data = {
            "project_name": "Test",
            "customer_name": "Acme",
            "language": "en",
            "quote_mode": "skip",
            "quote_status": "skipped",
            "hld_status": "skipped",
            "content_status": "fallback",
            "sections": {
                "executive_summary": "Summary",
                "current_challenges": "Challenges",
                "target_solution": "Solution",
                "pricing_summary": "Pricing info",
                "next_steps": "Steps",
            },
            "assumptions": [],
            "risks": [],
            "content_selection": {
                "include_hld": False,
                "include_price": True,
                "include_migration": False,
                "include_support_training": False,
                "include_huawei_capability": True,
            },
            "migration_context": {
                "scope": None,
                "constraints": None,
                "notes": None,
            },
        }
        data.update(overrides)
        return data

    def _get_slide_titles(self, tmp_path, data):
        output = tmp_path / "out.pptx"
        render_proposal_pptx(
            template_path=DEFAULT_TEMPLATE_PATH,
            output_path=output,
            proposal_data=data,
        )
        prs = Presentation(str(output))
        titles = []
        for slide in prs.slides:
            for shape in slide.shapes:
                if shape.has_text_frame:
                    text = shape.text_frame.text.strip()
                    if text:
                        titles.append(text.split("\n")[0])
        return titles

    def _get_combined_text(self, tmp_path, data):
        output = tmp_path / "out.pptx"
        render_proposal_pptx(
            template_path=DEFAULT_TEMPLATE_PATH,
            output_path=output,
            proposal_data=data,
        )
        prs = Presentation(str(output))
        chunks = []
        for slide in prs.slides:
            for shape in slide.shapes:
                if shape.has_text_frame:
                    chunks.append(shape.text_frame.text.strip())
        return "\n".join(chunks)

    def test_no_pricing_summary_when_include_price_false(self, tmp_path):
        data = self._sample_data()
        data["content_selection"]["include_price"] = False
        titles = self._get_slide_titles(tmp_path, data)
        assert "Pricing Summary" not in titles

    def test_pricing_summary_when_include_price_true(self, tmp_path):
        data = self._sample_data()
        data["content_selection"]["include_price"] = True
        combined = self._get_combined_text(tmp_path, data)
        assert "Configuración de Servicios" in combined
        assert "Pricing info" in combined

    def test_empty_next_steps_does_not_add_slide(self, tmp_path):
        data = self._sample_data()
        data["sections"]["next_steps"] = ""

        titles = self._get_slide_titles(tmp_path, data)

        assert "Next Steps" not in titles

    def test_migration_plan_when_include_migration_true(self, tmp_path):
        data = self._sample_data()
        data["content_selection"]["include_migration"] = True
        data["migration_context"] = {"scope": "Full DC", "constraints": None, "notes": None}
        combined = self._get_combined_text(tmp_path, data)
        assert "Plan de Migración" in combined
        assert "Full DC" in combined

    def test_no_migration_plan_when_include_migration_false(self, tmp_path):
        data = self._sample_data()
        data["content_selection"]["include_migration"] = False
        titles = self._get_slide_titles(tmp_path, data)
        assert "Migration Plan" not in titles

    def test_support_training_when_include_true(self, tmp_path):
        data = self._sample_data()
        data["content_selection"]["include_support_training"] = True
        combined = self._get_combined_text(tmp_path, data)
        assert "Plan de formacion para Acme" in combined

    def test_no_support_training_when_include_false(self, tmp_path):
        data = self._sample_data()
        data["content_selection"]["include_support_training"] = False
        titles = self._get_slide_titles(tmp_path, data)
        assert "Support & Training" not in titles


# --- 8. LLM fallback respects price/hld flags ---

class TestFallbackRespectsFlags:
    @pytest.fixture(autouse=True)
    def _patch(self, monkeypatch):
        _force_fallback(monkeypatch)

    def test_fallback_no_price_message(self):
        req = _make_request(include_price=False)
        created = create_proposal_task(req)
        _wait_for_task(created.task_id)
        content, _, _ = get_proposal_artifact(created.task_id, "json")
        data = json.loads(content)
        assert "not included" in data["sections"]["pricing_summary"].lower()

    def test_fallback_with_price_default_message(self):
        req = _make_request(include_price=True)
        created = create_proposal_task(req)
        _wait_for_task(created.task_id)
        content, _, _ = get_proposal_artifact(created.task_id, "json")
        data = json.loads(content)
        assert "not included" not in data["sections"]["pricing_summary"].lower()
