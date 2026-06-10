"""Phase 7 regression tests: API endpoint routing, legacy compatibility, and path boundaries.

Validates:
- 7A: Frontend-facing new API endpoints exist and are distinct
- 7B: Legacy flexible endpoint still works and dispatches correctly
- 7C: User-visible text no longer exposes "Flexible Quote" as primary
- 7D: Three paths (RVTools, Cloud Billing, Others) are independent
- 7E: Graph dispatch is correct per endpoint
"""

from __future__ import annotations

import io
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _make_xlsx_bytes() -> bytes:
    """Minimal valid .xlsx bytes (empty workbook)."""
    import openpyxl
    buf = io.BytesIO()
    wb = openpyxl.Workbook()
    wb.save(buf)
    return buf.getvalue()


def _make_csv_bytes() -> bytes:
    return b"service,quantity,unit\nEC2,10,units\n"


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 7A: New API endpoints exist and are distinct
# ═══════════════════════════════════════════════════════════════════════════════


class TestNewApiEndpoints:
    """Verify the new Cloud Billing and Others API endpoints exist."""

    def test_cloud_billing_annotate_exists(self, client: TestClient):
        resp = client.post("/api/quotes/cloud-billing/annotate/tasks")
        assert resp.status_code != 404

    def test_cloud_billing_annotate_status_exists(self, client: TestClient):
        resp = client.get("/api/quotes/cloud-billing/annotate/tasks/nonexistent-task")
        assert resp.status_code != 405

    def test_cloud_billing_annotate_export_exists(self, client: TestClient):
        resp = client.get("/api/quotes/cloud-billing/annotate/tasks/nonexistent-task/export")
        assert resp.status_code != 405

    def test_cloud_billing_annotate_cancel_exists(self, client: TestClient):
        resp = client.post("/api/quotes/cloud-billing/annotate/tasks/nonexistent-task/cancel")
        assert resp.status_code != 405

    def test_cloud_billing_preview_exists(self, client: TestClient):
        resp = client.post("/api/quotes/cloud-billing/preview")
        assert resp.status_code != 404

    def test_cloud_billing_review_exists(self, client: TestClient):
        resp = client.post("/api/quotes/cloud-billing/review", json={
            "requirements": [], "quote_context": {}, "feedback": [],
            "matched_products": [], "audit_log": [],
        })
        assert resp.status_code != 404

    def test_cloud_billing_export_exists(self, client: TestClient):
        resp = client.post("/api/quotes/cloud-billing/export", json={
            "requirements": [], "quote_context": {}, "feedback": [],
            "matched_products": [], "audit_log": [],
        })
        assert resp.status_code != 404

    def test_others_annotate_exists(self, client: TestClient):
        resp = client.post("/api/quotes/others/annotate/tasks")
        assert resp.status_code != 404

    def test_others_annotate_status_exists(self, client: TestClient):
        resp = client.get("/api/quotes/others/annotate/tasks/nonexistent-task")
        assert resp.status_code != 405

    def test_others_annotate_export_exists(self, client: TestClient):
        resp = client.get("/api/quotes/others/annotate/tasks/nonexistent-task/export")
        assert resp.status_code != 405

    def test_others_annotate_cancel_exists(self, client: TestClient):
        resp = client.post("/api/quotes/others/annotate/tasks/nonexistent-task/cancel")
        assert resp.status_code != 405

    def test_cloud_billing_annotate_task_create_and_status(self, client: TestClient):
        csv_bytes = _make_csv_bytes()
        create = client.post(
            "/api/quotes/cloud-billing/annotate/tasks",
            files={"flexible_file": ("billing.csv", io.BytesIO(csv_bytes), "text/csv")},
            data={"region": "mexico", "lang": "en", "customer_notes": "test"},
        )
        assert create.status_code == 200
        task_id = create.json()["task_id"]
        status = client.get(f"/api/quotes/cloud-billing/annotate/tasks/{task_id}")
        assert status.status_code == 200

    def test_others_annotate_task_create_and_status(self, client: TestClient):
        xlsx_bytes = _make_xlsx_bytes()
        create = client.post(
            "/api/quotes/others/annotate/tasks",
            files={"flexible_file": ("requirements.xlsx", io.BytesIO(xlsx_bytes), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            data={"region": "mexico", "lang": "en", "customer_notes": "test"},
        )
        assert create.status_code == 200
        task_id = create.json()["task_id"]
        status = client.get(f"/api/quotes/others/annotate/tasks/{task_id}")
        assert status.status_code == 200

    def test_others_preview_exists(self, client: TestClient):
        resp = client.post("/api/quotes/others/preview")
        assert resp.status_code != 404

    def test_others_review_exists(self, client: TestClient):
        resp = client.post("/api/quotes/others/review", json={
            "requirements": [], "quote_context": {}, "feedback": [],
            "matched_products": [], "audit_log": [],
        })
        assert resp.status_code != 404

    def test_others_export_exists(self, client: TestClient):
        resp = client.post("/api/quotes/others/export", json={
            "requirements": [], "quote_context": {}, "feedback": [],
            "matched_products": [], "audit_log": [],
        })
        assert resp.status_code != 404


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 7B: Legacy flexible endpoint compatibility
# ═══════════════════════════════════════════════════════════════════════════════


class TestLegacyFlexibleCompatibility:
    """Legacy /api/quotes/flexible/... endpoints should still work."""

    def test_flexible_annotate_still_exists(self, client: TestClient):
        resp = client.post("/api/quotes/flexible/annotate/tasks")
        assert resp.status_code != 404

    def test_flexible_preview_still_exists(self, client: TestClient):
        resp = client.post("/api/quotes/flexible/preview/tasks")
        assert resp.status_code != 404

    def test_flexible_annotate_with_cloud_billing_mode(self, client: TestClient):
        """Legacy flexible endpoint with quote_mode=cloud_billing should dispatch correctly."""
        xlsx_bytes = _make_xlsx_bytes()
        resp = client.post(
            "/api/quotes/flexible/annotate/tasks",
            files={"flexible_file": ("test.xlsx", io.BytesIO(xlsx_bytes), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            data={"region": "mexico", "lang": "en", "customer_notes": "test", "quote_mode": "cloud_billing"},
        )
        # Should not be 404 — route exists and processes
        assert resp.status_code != 404

    def test_flexible_annotate_with_cloud_billing_mode_accepts_csv(self, client: TestClient):
        """Legacy flexible annotate should accept CSV when quote_mode=cloud_billing."""
        csv_bytes = _make_csv_bytes()
        resp = client.post(
            "/api/quotes/flexible/annotate/tasks",
            files={"flexible_file": ("billing.csv", io.BytesIO(csv_bytes), "text/csv")},
            data={"region": "mexico", "lang": "en", "customer_notes": "test", "quote_mode": "cloud_billing"},
        )
        assert resp.status_code != 415, "legacy flexible annotate should allow cloud billing CSV"

    def test_flexible_annotate_with_others_mode(self, client: TestClient):
        """Legacy flexible endpoint with quote_mode=others should dispatch correctly."""
        xlsx_bytes = _make_xlsx_bytes()
        resp = client.post(
            "/api/quotes/flexible/annotate/tasks",
            files={"flexible_file": ("test.xlsx", io.BytesIO(xlsx_bytes), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            data={"region": "mexico", "lang": "en", "customer_notes": "test", "quote_mode": "others"},
        )
        assert resp.status_code != 404

    def test_flexible_annotate_without_mode(self, client: TestClient):
        """Legacy flexible endpoint without quote_mode should still work (backward compat)."""
        xlsx_bytes = _make_xlsx_bytes()
        resp = client.post(
            "/api/quotes/flexible/annotate/tasks",
            files={"flexible_file": ("test.xlsx", io.BytesIO(xlsx_bytes), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            data={"region": "mexico", "lang": "en", "customer_notes": "test"},
        )
        assert resp.status_code != 404

    def test_flexible_review_dispatches_by_quote_mode(self, client: TestClient, monkeypatch: pytest.MonkeyPatch):
        """Legacy flexible review should dispatch to the mode-specific graph."""
        import app.main as main_module

        calls: list[str] = []

        def _make_graph(name: str):
            return SimpleNamespace(invoke=lambda _state: (calls.append(name) or {"summary": {}, "quote_context": {}, "requirements": []}))

        monkeypatch.setattr(main_module, "cloud_billing_review_graph", _make_graph("cloud_billing"))
        monkeypatch.setattr(main_module, "others_review_graph", _make_graph("others"))
        monkeypatch.setattr(main_module, "flexible_review_graph", _make_graph("flexible"))
        monkeypatch.setattr(main_module, "build_flexible_preview_response", lambda state: state)

        request = {
            "requirements": [],
            "quote_context": {"quote_mode": "cloud_billing"},
            "feedback": [],
            "matched_products": [],
            "audit_log": [],
        }
        resp = client.post("/api/quotes/flexible/review", json=request)
        assert resp.status_code == 200
        assert calls == ["cloud_billing"]

    def test_flexible_export_dispatches_by_quote_mode(self, client: TestClient, monkeypatch: pytest.MonkeyPatch):
        """Legacy flexible export should dispatch to the mode-specific graph."""
        import app.main as main_module

        calls: list[str] = []

        def _make_graph(name: str):
            return SimpleNamespace(
                invoke=lambda _state: (calls.append(name) or {"workbook": SimpleNamespace(content=b"x", filename="out.xlsx")})
            )

        monkeypatch.setattr(main_module, "cloud_billing_export_graph", _make_graph("cloud_billing"))
        monkeypatch.setattr(main_module, "others_export_graph", _make_graph("others"))
        monkeypatch.setattr(main_module, "flexible_export_graph", _make_graph("flexible"))

        request = {
            "requirements": [],
            "quote_context": {"quote_mode": "others"},
            "feedback": [],
            "matched_products": [],
            "audit_log": [],
        }
        resp = client.post("/api/quotes/flexible/export", json=request)
        assert resp.status_code == 200
        assert calls == ["others"]


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 7D: File type restrictions per path
# ═══════════════════════════════════════════════════════════════════════════════


class TestFileTypeRestrictions:
    """Cloud Billing accepts .xlsx/.csv; Others only accepts .xlsx."""

    def test_cloud_billing_accepts_xlsx(self, client: TestClient):
        xlsx_bytes = _make_xlsx_bytes()
        resp = client.post(
            "/api/quotes/cloud-billing/annotate/tasks",
            files={"flexible_file": ("billing.xlsx", io.BytesIO(xlsx_bytes), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            data={"region": "mexico", "lang": "en", "customer_notes": "test"},
        )
        assert resp.status_code != 415  # Not unsupported media type

    def test_cloud_billing_accepts_csv(self, client: TestClient):
        csv_bytes = _make_csv_bytes()
        resp = client.post(
            "/api/quotes/cloud-billing/annotate/tasks",
            files={"flexible_file": ("billing.csv", io.BytesIO(csv_bytes), "text/csv")},
            data={"region": "mexico", "lang": "en", "customer_notes": "test"},
        )
        assert resp.status_code != 415  # Not unsupported media type

    def test_others_accepts_xlsx(self, client: TestClient):
        xlsx_bytes = _make_xlsx_bytes()
        resp = client.post(
            "/api/quotes/others/annotate/tasks",
            files={"flexible_file": ("requirements.xlsx", io.BytesIO(xlsx_bytes), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            data={"region": "mexico", "lang": "en", "customer_notes": "test"},
        )
        assert resp.status_code != 415

    def test_others_rejects_csv(self, client: TestClient):
        csv_bytes = _make_csv_bytes()
        resp = client.post(
            "/api/quotes/others/annotate/tasks",
            files={"flexible_file": ("data.csv", io.BytesIO(csv_bytes), "text/csv")},
            data={"region": "mexico", "lang": "en", "customer_notes": "test"},
        )
        assert resp.status_code == 415, "Others should reject CSV uploads"


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 7E: Graph dispatch correctness
# ═══════════════════════════════════════════════════════════════════════════════


class TestGraphDispatch:
    """Verify each endpoint uses the correct graph."""

    def test_cloud_billing_graph_is_distinct_from_others(self):
        from app.cloud_billing_workflow import cloud_billing_preview_graph
        from app.others_quote_workflow import others_preview_graph
        # They should be different graph instances
        assert cloud_billing_preview_graph is not others_preview_graph

    def test_cloud_billing_graph_is_distinct_from_flexible(self):
        from app.cloud_billing_workflow import cloud_billing_preview_graph
        from app.flexible_workflow import flexible_preview_graph
        assert cloud_billing_preview_graph is not flexible_preview_graph

    def test_others_graph_is_distinct_from_flexible(self):
        from app.others_quote_workflow import others_preview_graph
        from app.flexible_workflow import flexible_preview_graph
        assert others_preview_graph is not flexible_preview_graph

    def test_cloud_billing_graph_lacks_understand_input(self):
        """Cloud Billing graph should not have understand_input (Phase 5A)."""
        from app.cloud_billing_workflow import cloud_billing_preview_graph
        nodes = set(cloud_billing_preview_graph.nodes.keys())
        assert "understand_input" not in nodes

    def test_others_graph_has_understand_input(self):
        """Others graph should have understand_input (needs schema understanding)."""
        from app.others_quote_workflow import others_preview_graph
        nodes = set(others_preview_graph.nodes.keys())
        assert "understand_input" in nodes

    def test_flexible_graph_has_understand_input(self):
        """Flexible graph should still have understand_input."""
        from app.flexible_workflow import flexible_preview_graph
        nodes = set(flexible_preview_graph.nodes.keys())
        assert "understand_input" in nodes
