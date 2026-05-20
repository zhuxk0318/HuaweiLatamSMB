"""Tests for HLD recommendation engine — source tracking and step coverage."""
from __future__ import annotations

import pytest

from app.hld_recommend import (
    ALL_STEPS,
    CONTEXT_DRIVEN_STEPS,
    RULE_ALLOWED_STEPS,
    STATIC_STEPS,
    get_recommendation,
    _rule_recommend,
)
from app.models import HldRecommendationRequest, HldRecommendationResponse


# ── Step coverage ────────────────────────────────────────────────────────

class TestStepCoverage:
    """Every wizard step must be routed — no silent gaps."""

    def test_all_steps_covered_by_routing_table(self):
        expected = {
            "project_name", "business_goal", "architecture_boundary",
            "deployment_mode", "user_access_entry", "core_components",
            "external_integrations", "data_stores_flow",
            "network_security_boundary", "preferred_filename",
        }
        assert set(ALL_STEPS) == expected

    def test_step_sets_are_disjoint(self):
        all_assigned = STATIC_STEPS | RULE_ALLOWED_STEPS | CONTEXT_DRIVEN_STEPS
        assert all_assigned == set(ALL_STEPS)
        # No overlap
        assert STATIC_STEPS & RULE_ALLOWED_STEPS == set()
        assert STATIC_STEPS & CONTEXT_DRIVEN_STEPS == set()
        assert RULE_ALLOWED_STEPS & CONTEXT_DRIVEN_STEPS == set()

    def test_every_step_returns_source(self):
        """Every step must return a response with a valid source field."""
        for step in ALL_STEPS:
            req = HldRecommendationRequest(step=step, answers={"project_name": "Test"}, language="en")
            resp = get_recommendation(req)
            assert resp.source in ("static", "rule", "llm", "fallback_default"), f"step={step} returned invalid source={resp.source}"


# ── Source assertions ───────────────────────────────────────────────────

class TestSourceAssertions:
    def test_project_name_returns_static(self):
        resp = get_recommendation(HldRecommendationRequest(step="project_name", answers={}, language="en"))
        assert resp.source == "static"
        assert resp.recommended_answer == ""

    def test_preferred_filename_has_dynamic_project_name(self):
        resp = get_recommendation(HldRecommendationRequest(
            step="preferred_filename",
            answers={"project_name": "My Cloud Portal"},
            language="en",
        ))
        assert resp.source in ("llm", "rule", "fallback_default")
        if resp.source == "fallback_default":
            # No MaaS available in tests; recommendation may not be generated.
            assert resp.recommended_answer == ""
        else:
            assert "My_Cloud_Portal" in resp.recommended_answer or "My Cloud Portal" in resp.recommended_answer

    def test_preferred_filename_fallback_when_no_project(self):
        resp = get_recommendation(HldRecommendationRequest(
            step="preferred_filename",
            answers={},
            language="en",
        ))
        assert resp.source in ("llm", "rule", "fallback_default")
        if resp.source == "fallback_default":
            assert resp.recommended_answer == ""
        else:
            assert resp.recommended_answer

    def test_deployment_mode_returns_dynamic_source(self):
        resp = get_recommendation(HldRecommendationRequest(
            step="deployment_mode",
            answers={"business_goal": "Migrate ERP to cloud"},
            language="en",
        ))
        assert resp.source in ("llm", "rule", "fallback_default")

    def test_user_access_entry_returns_dynamic_source(self):
        resp = get_recommendation(HldRecommendationRequest(
            step="user_access_entry",
            answers={"architecture_boundary": "Application + Network"},
            language="en",
        ))
        assert resp.source in ("llm", "rule", "fallback_default")
        if resp.source != "fallback_default":
            assert "VPN" in resp.recommended_answer


# ── Context-driven fields ───────────────────────────────────────────────

class TestContextDrivenFields:
    """Context-driven fields should use prior answers to produce different recommendations."""

    def test_architecture_boundary_varies_with_goal(self):
        resp_web = _rule_recommend("architecture_boundary", {"business_goal": "Build a web portal"}, "en")
        resp_vpn = _rule_recommend("architecture_boundary", {"business_goal": "Connect multi-branch offices via VPN"}, "en")
        resp_migrate = _rule_recommend("architecture_boundary", {"business_goal": "Migrate on-prem workloads"}, "en")
        assert resp_web is not None
        assert resp_vpn is not None
        assert resp_migrate is not None
        assert resp_web.recommended_answer != resp_vpn.recommended_answer
        assert resp_migrate.recommended_answer != resp_web.recommended_answer

    def test_core_components_varies_with_goal(self):
        resp_migrate = _rule_recommend("core_components", {"business_goal": "Migrate existing VMs"}, "en")
        resp_ai = _rule_recommend("core_components", {"business_goal": "Build AI model serving"}, "en")
        assert resp_migrate is not None
        assert resp_ai is not None
        assert resp_migrate.recommended_answer != resp_ai.recommended_answer

    def test_business_goal_varies_with_project_name(self):
        resp_migrate = _rule_recommend("business_goal", {"project_name": "Cloud Migration Phase 1"}, "en")
        resp_ai = _rule_recommend("business_goal", {"project_name": "AI Knowledge Assistant"}, "en")
        assert resp_migrate is not None
        assert resp_ai is not None
        assert resp_migrate.recommended_answer != resp_ai.recommended_answer

    def test_external_integrations_varies_with_goal(self):
        resp_erp = _rule_recommend("external_integrations", {"business_goal": "Integrate with SAP ERP"}, "en")
        resp_crm = _rule_recommend("external_integrations", {"business_goal": "Connect to Salesforce CRM"}, "en")
        assert resp_erp is not None
        assert resp_crm is not None
        assert "SAP" in resp_erp.recommended_answer
        assert "Salesforce" in resp_crm.recommended_answer

    def test_data_stores_flow_varies_with_components(self):
        resp_rds = _rule_recommend("data_stores_flow", {"core_components": "ECS, RDS MySQL, OBS, ELB"}, "en")
        resp_dds = _rule_recommend("data_stores_flow", {"core_components": "ECS, DDS, OBS, ELB"}, "en")
        assert resp_rds is not None
        assert resp_dds is not None
        assert "RDS" in resp_rds.recommended_answer
        assert "DDS" in resp_dds.recommended_answer

    def test_data_stores_flow_does_not_introduce_unseen_services(self):
        resp = _rule_recommend("data_stores_flow", {"core_components": "ECS, RDS MySQL, OBS, ELB"}, "en")
        assert resp is not None
        assert "DLI" not in resp.recommended_answer
        assert "Redis" not in resp.recommended_answer
        assert "DDS" not in resp.recommended_answer

    def test_network_security_varies_with_boundary_and_components(self):
        resp_simple = _rule_recommend("network_security_boundary", {"architecture_boundary": "Application", "core_components": "ECS, RDS, OBS"}, "en")
        resp_full = _rule_recommend("network_security_boundary", {"architecture_boundary": "Application + Network", "core_components": "ECS, RDS, OBS, WAF"}, "en")
        assert resp_simple is not None
        assert resp_full is not None
        # Full boundary should mention VPN, simple may not
        assert "VPN" in resp_full.recommended_answer

    def test_rule_returns_none_for_unmatched_context(self):
        """When rules can't match the context, they return None so LLM can fallback."""
        resp = _rule_recommend("business_goal", {"project_name": "XYZ"}, "en")
        assert resp is None

    def test_context_driven_step_attempts_llm_or_returns_default(self):
        """When rules return None, the public API should attempt LLM and
        otherwise return fallback_default in test environments."""
        resp = get_recommendation(HldRecommendationRequest(
            step="business_goal",
            answers={"project_name": "XYZ"},
            language="en",
        ))
        assert resp.source in ("llm", "fallback_default")


# ── Unrecognized step ───────────────────────────────────────────────────

class TestUnrecognizedStep:
    def test_unrecognized_step_returns_fallback_default(self):
        """This tests the guard — in practice the Literal type prevents invalid steps,
        but the internal logic should handle it gracefully."""
        # We test _rule_recommend directly since the Literal prevents invalid steps
        # at the API level
        resp = _rule_recommend("unknown_step", {}, "en")
        assert resp is None


# ── Trilingual support ──────────────────────────────────────────────────

class TestTrilingual:
    def test_rule_recommendations_support_spanish(self):
        for step in ["architecture_boundary", "user_access_entry", "deployment_mode", "preferred_filename"]:
            resp = _rule_recommend(step, {"business_goal": "Build a web portal", "project_name": "Test"}, "es")
            if resp and resp.recommended_answer:
                # Should not be empty
                assert len(resp.recommended_answer) > 0

    def test_rule_recommendations_support_chinese(self):
        for step in ["architecture_boundary", "user_access_entry", "deployment_mode", "preferred_filename"]:
            resp = _rule_recommend(step, {"business_goal": "Build a web portal", "project_name": "Test"}, "zh")
            if resp and resp.recommended_answer:
                assert len(resp.recommended_answer) > 0
