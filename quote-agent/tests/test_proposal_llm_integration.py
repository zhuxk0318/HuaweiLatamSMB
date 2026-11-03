"""Tests for Proposal ↔ LLM content generation — Phase 3B."""
from __future__ import annotations

import json
import time

import pytest

from app.chat_service import ChatCompletionsClient
from app.models import (
    ProposalQuoteInput,
    ProposalQuoteResult,
    ProposalQuoteSummary,
    ProposalRequest,
    RequirementItem,
)
from app.proposal_tasks import (
    _build_content_prompt,
    _normalize_next_steps,
    _tasks,
    _lock,
    create_proposal_task,
    build_proposal_chat_client_from_env,
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


def _make_request(**overrides) -> ProposalRequest:
    defaults = dict(
        project_name="test-project",
        business_background="Moving to cloud",
        current_pain_points="High on-prem costs",
        target_outcomes="Reduce TCO by 30%",
    )
    defaults.update(overrides)
    return ProposalRequest(**defaults)


class TestProposalModelOverride:
    def test_defaults_to_glm_5_1_while_reusing_maas_url_and_key(self, monkeypatch):
        monkeypatch.delenv("PROPOSAL_MAAS_MODEL", raising=False)

        def _fake_base_build(*, timeout=None):
            return ChatCompletionsClient(
                api_key="fake-key",
                base_url="https://maas.example.com/openai/v1",
                model="deepseek-v3.2",
                timeout=timeout or 60.0,
            )

        monkeypatch.setattr("app.proposal_tasks.build_chat_client_from_env", _fake_base_build)

        client = build_proposal_chat_client_from_env(timeout=12.0)

        assert client.api_key == "fake-key"
        assert client.base_url == "https://maas.example.com/openai/v1"
        assert client.timeout == 12.0
        assert client.model == "glm-5.1"

    def test_env_can_override_proposal_model_only(self, monkeypatch):
        monkeypatch.setenv("PROPOSAL_MAAS_MODEL", "glm-5.1-test")

        def _fake_base_build(*, timeout=None):
            return ChatCompletionsClient(
                api_key="fake-key",
                base_url="https://maas.example.com/openai/v1",
                model="deepseek-v3.2",
                timeout=timeout or 60.0,
            )

        monkeypatch.setattr("app.proposal_tasks.build_chat_client_from_env", _fake_base_build)

        client = build_proposal_chat_client_from_env()

        assert client.model == "glm-5.1-test"


class TestSimplifiedProposalInput:
    def test_customer_brief_can_replace_legacy_context_fields(self):
        request = ProposalRequest(
            project_name="ERP modernization",
            customer_name="Example Customer",
            country="Mexico",
            customer_brief="Modernize an on-premises ERP and improve availability.",
        )

        assert request.customer_brief
        assert request.business_background == ""
        assert request.current_pain_points == ""
        assert request.target_outcomes == ""

    def test_prompt_uses_customer_brief_and_limits_follow_up_actions(self):
        request = ProposalRequest(
            project_name="ERP modernization",
            customer_brief="Modernize an on-premises ERP and improve availability.",
        )

        prompt = _build_content_prompt(request, None, "skipped")

        assert "Customer brief: Modernize an on-premises ERP" in prompt
        assert "Output language: English" in prompt
        assert "at most 3 distinct actions" in prompt
        assert "Treat missing details as explicit assumptions" in prompt

    def test_next_steps_are_deduplicated_and_capped(self):
        result = _normalize_next_steps([
            "Confirm the project scope",
            "Confirm the project scope",
            "Validate the target architecture",
            "Agree the implementation sequence",
            "Start another unrelated action",
        ])

        assert result.splitlines() == [
            "1. Confirm the project scope",
            "2. Validate the target architecture",
            "3. Agree the implementation sequence",
        ]

    def test_numbered_single_line_steps_are_split(self):
        result = _normalize_next_steps("1. Confirm scope 2. Validate architecture 3. Agree delivery sequence 4. Start implementation")

        assert result.splitlines() == [
            "1. Confirm scope",
            "2. Validate architecture",
            "3. Agree delivery sequence",
        ]


# --- Fake LLM responses ---

_VALID_LLM_JSON = json.dumps({
    "executive_summary": "Cloud migration proposal for test-project",
    "current_challenges": "High on-prem costs and limited scalability",
    "target_solution": "Migrate to Huawei Cloud with ECS and RDS",
    "pricing_summary": "Estimated monthly cost based on quoted items.",
    "next_steps": "1. Detailed assessment 2. POC 3. Migration",
    "assumptions": ["Customer has stable network", "Data volume under 10TB"],
    "risks": ["Migration downtime", "Skill gap"],
})

_INVALID_LLM_TEXT = "This is not JSON at all, just plain text."

_LLM_JSON_MISSING_KEYS = json.dumps({
    "executive_summary": "Only this field",
})


class _FakeClient:
    """Fake ChatCompletionsClient for testing."""
    def __init__(self, response_text: str):
        self.model = "fake-model"
        self._response = response_text

    def complete_text(self, messages):
        return self._response


class _FailingClient:
    """Client that raises on complete_text."""
    model = "failing-model"

    def complete_text(self, messages):
        raise RuntimeError("Simulated LLM failure")


class TestLlmGeneratesValidJson:
    """LLM returns valid JSON → content_status='generated'."""

    @pytest.fixture(autouse=True)
    def _patch_llm(self, monkeypatch):
        def _fake_build(*, timeout=None):
            return _FakeClient(_VALID_LLM_JSON)
        monkeypatch.setattr("app.proposal_tasks.build_proposal_chat_client_from_env", _fake_build)

    def test_content_status_generated(self):
        created = create_proposal_task(_make_request())
        _wait_for_task(created.task_id)
        task = get_proposal_task(created.task_id)
        assert task.status == "succeeded"

        content, _, _ = get_proposal_artifact(created.task_id, "json")
        data = json.loads(content)
        assert data["content_status"] == "generated"
        assert data["content_model"] == "fake-model"

    def test_sections_populated(self):
        created = create_proposal_task(_make_request())
        _wait_for_task(created.task_id)
        content, _, _ = get_proposal_artifact(created.task_id, "json")
        data = json.loads(content)
        assert "Cloud migration" in data["sections"]["executive_summary"]
        assert "on-prem" in data["sections"]["current_challenges"]

    def test_assumptions_and_risks_written(self):
        created = create_proposal_task(_make_request())
        _wait_for_task(created.task_id)
        content, _, _ = get_proposal_artifact(created.task_id, "json")
        data = json.loads(content)
        assert len(data["assumptions"]) == 2
        assert len(data["risks"]) == 2

    def test_next_steps_are_normalized(self):
        created = create_proposal_task(_make_request())
        _wait_for_task(created.task_id)
        content, _, _ = get_proposal_artifact(created.task_id, "json")
        data = json.loads(content)

        assert data["sections"]["next_steps"].splitlines() == [
            "1. Detailed assessment",
            "2. POC",
            "3. Migration",
        ]


class TestOptionalNextSteps:
    def test_missing_next_steps_does_not_force_fallback(self, monkeypatch):
        response = json.dumps({
            "executive_summary": "Concise summary",
            "current_challenges": "Limited scalability",
            "target_solution": "A phased cloud solution",
            "pricing_summary": "",
            "assumptions": [],
            "risks": [],
        })

        def _fake_build(*, timeout=None):
            return _FakeClient(response)

        monkeypatch.setattr("app.proposal_tasks.build_proposal_chat_client_from_env", _fake_build)
        created = create_proposal_task(_make_request(customer_brief="Modernize the current platform."))
        _wait_for_task(created.task_id)
        content, _, _ = get_proposal_artifact(created.task_id, "json")
        data = json.loads(content)

        assert data["content_status"] == "generated"
        assert data["sections"]["next_steps"] == ""


class TestLlmInvalidJsonFallsBack:
    """LLM returns invalid JSON → fallback, task still succeeds."""

    @pytest.fixture(autouse=True)
    def _patch_llm(self, monkeypatch):
        def _fake_build(*, timeout=None):
            return _FakeClient(_INVALID_LLM_TEXT)
        monkeypatch.setattr("app.proposal_tasks.build_proposal_chat_client_from_env", _fake_build)

    def test_fallback_on_invalid_json(self):
        created = create_proposal_task(_make_request())
        _wait_for_task(created.task_id)
        task = get_proposal_task(created.task_id)
        assert task.status == "succeeded"

        content, _, _ = get_proposal_artifact(created.task_id, "json")
        data = json.loads(content)
        assert data["content_status"] == "fallback"
        assert data["content_error"] is not None


class TestLlmMissingKeysFallsBack:
    """LLM returns valid JSON but missing required keys → fallback."""

    @pytest.fixture(autouse=True)
    def _patch_llm(self, monkeypatch):
        def _fake_build(*, timeout=None):
            return _FakeClient(_LLM_JSON_MISSING_KEYS)
        monkeypatch.setattr("app.proposal_tasks.build_proposal_chat_client_from_env", _fake_build)

    def test_fallback_on_missing_keys(self):
        created = create_proposal_task(_make_request())
        _wait_for_task(created.task_id)
        content, _, _ = get_proposal_artifact(created.task_id, "json")
        data = json.loads(content)
        assert data["content_status"] == "fallback"


class TestMaasConfigMissingFallsBack:
    """MaaS config missing → fallback, task still succeeds."""

    @pytest.fixture(autouse=True)
    def _patch_llm(self, monkeypatch):
        def _fake_build(*, timeout=None):
            raise RuntimeError("Missing HUAWEI_MAAS_API_KEY")
        monkeypatch.setattr("app.proposal_tasks.build_proposal_chat_client_from_env", _fake_build)

    def test_fallback_on_missing_config(self):
        created = create_proposal_task(_make_request())
        _wait_for_task(created.task_id)
        task = get_proposal_task(created.task_id)
        assert task.status == "succeeded"

        content, _, _ = get_proposal_artifact(created.task_id, "json")
        data = json.loads(content)
        assert data["content_status"] == "fallback"
        assert data["content_error"] is not None


class TestLlmCallFailsFallsBack:
    """LLM call raises → fallback, task still succeeds."""

    @pytest.fixture(autouse=True)
    def _patch_llm(self, monkeypatch):
        def _fake_build(*, timeout=None):
            return _FailingClient()
        monkeypatch.setattr("app.proposal_tasks.build_proposal_chat_client_from_env", _fake_build)

    def test_fallback_on_llm_exception(self):
        created = create_proposal_task(_make_request())
        _wait_for_task(created.task_id)
        task = get_proposal_task(created.task_id)
        assert task.status == "succeeded"

        content, _, _ = get_proposal_artifact(created.task_id, "json")
        data = json.loads(content)
        assert data["content_status"] == "fallback"


class TestPricingSummaryVariesByQuoteStatus:
    """Fallback pricing_summary differs when quote is succeeded vs skipped."""

    @pytest.fixture(autouse=True)
    def _patch_llm(self, monkeypatch):
        # Force fallback so we can see the deterministic pricing_summary logic
        def _fake_build(*, timeout=None):
            raise RuntimeError("No MaaS")
        monkeypatch.setattr("app.proposal_tasks.build_proposal_chat_client_from_env", _fake_build)

        def _fake_invoke(state):
            return {
                "requirements": [],
                "quote_ready_items": [],
                "quote_blockers": [],
                "quote_lines": [],
                "unquoted_items": [],
                "matched_products": [],
                "summary": {
                    "total_input_items": 1,
                    "quote_ready_items": 1,
                    "quoted_items": 1,
                    "blocker_count": 0,
                    "unquoted_count": 0,
                    "total_monthly_price": 500.0,
                    "currency": "USD",
                    "summary": "1 item quoted",
                    "assumptions": [],
                    "risks": [],
                },
                "audit_log": [],
                "quote_context": {"region": "mexico", "language": "en", "customer_notes": ""},
                "diagnostics": {"llm_used": False},
            }
        monkeypatch.setattr("app.proposal_tasks.flexible_preview_graph.invoke", _fake_invoke)

    def test_quote_succeeded_pricing_summary(self):
        req = _make_request(
            include_price=True,
            quote_mode="flexible",
            quote_input=ProposalQuoteInput(
                requirements=[RequirementItem(
                    item_id="r1", source_file="f.csv", raw_product_name="ECS",
                    normalized_product="ECS", quantity=1, unit="instances",
                    region="mexico", status="ready",
                )],
                region="mexico",
            ),
        )
        created = create_proposal_task(req)
        _wait_for_task(created.task_id, timeout=15)
        content, _, _ = get_proposal_artifact(created.task_id, "json")
        data = json.loads(content)
        # Fallback pricing_summary should include the quoted price
        assert "500.00" in data["sections"]["pricing_summary"]

    def test_quote_skipped_pricing_summary(self):
        created = create_proposal_task(_make_request(include_price=True, quote_mode="skip"))
        _wait_for_task(created.task_id)
        content, _, _ = get_proposal_artifact(created.task_id, "json")
        data = json.loads(content)
        # Fallback pricing_summary for skipped quote
        assert "refined" in data["sections"]["pricing_summary"].lower() or "Phase 2" in data["sections"]["pricing_summary"]


class TestHldAndQuoteAndContentCoexist:
    """All three: quote + HLD + content generation work together."""

    @pytest.fixture(autouse=True)
    def _patch_all(self, monkeypatch):
        def _fake_build(*, timeout=None):
            return _FakeClient(_VALID_LLM_JSON)
        monkeypatch.setattr("app.proposal_tasks.build_proposal_chat_client_from_env", _fake_build)

        def _fake_invoke(state):
            return {
                "requirements": [],
                "quote_ready_items": [],
                "quote_blockers": [],
                "quote_lines": [],
                "unquoted_items": [],
                "matched_products": [],
                "summary": {
                    "total_input_items": 1,
                    "quote_ready_items": 1,
                    "quoted_items": 1,
                    "blocker_count": 0,
                    "unquoted_count": 0,
                    "total_monthly_price": 300.0,
                    "currency": "USD",
                    "summary": "1 item",
                    "assumptions": [],
                    "risks": [],
                },
                "audit_log": [],
                "quote_context": {"region": "mexico", "language": "en", "customer_notes": ""},
                "diagnostics": {"llm_used": False},
            }
        monkeypatch.setattr("app.proposal_tasks.flexible_preview_graph.invoke", _fake_invoke)

        import pathlib
        from app.models import HldDesignTaskCreatedResponse

        def _fake_hld_create(requirements):
            design_id = "fake-hld-all"
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

    def test_all_three_succeed(self):
        from app.models import HldRequirements

        req = _make_request(
            include_price=True,
            include_hld=True,
            quote_mode="flexible",
            quote_input=ProposalQuoteInput(
                requirements=[RequirementItem(
                    item_id="r1", source_file="f.csv", raw_product_name="ECS",
                    normalized_product="ECS", quantity=1, unit="instances",
                    region="mexico", status="ready",
                )],
                region="mexico",
            ),
            hld_requirements=HldRequirements(
                project_name="test-project",
                business_goal="Cloud migration",
                architecture_boundary="VPC",
                deployment_mode="cloud",
                user_access_entry="VPN",
                core_components="ECS",
                external_integrations="None",
                data_stores_flow="RDS",
                network_security_boundary="VPC",
            ),
        )
        created = create_proposal_task(req)
        _wait_for_task(created.task_id, timeout=15)
        task = get_proposal_task(created.task_id)
        assert task.status == "succeeded"

        content, _, _ = get_proposal_artifact(created.task_id, "json")
        data = json.loads(content)
        assert data["content_status"] == "generated"
        assert data["quote_status"] == "succeeded"
        assert data["hld_status"] == "succeeded"
        assert len(data["assumptions"]) == 2
        assert len(data["risks"]) == 2
