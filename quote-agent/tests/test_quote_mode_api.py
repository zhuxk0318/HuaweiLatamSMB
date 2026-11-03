"""Tests for Phase 3+4: Cloud Billing / Others Quote API endpoints, quote_mode, and graph dispatch."""

from __future__ import annotations

import io
from datetime import datetime, timezone

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


# ── Route existence ─────────────────────────────────────────────────────────────


def test_cloud_billing_annotate_route_exists(client: TestClient):
    """POST /api/quotes/cloud-billing/annotate/tasks should be a known route."""
    # We just verify the route exists (will fail on validation, not 404)
    resp = client.post("/api/quotes/cloud-billing/annotate/tasks")
    assert resp.status_code != 404, "cloud-billing annotate route should exist"


def test_others_annotate_route_exists(client: TestClient):
    """POST /api/quotes/others/annotate/tasks should be a known route."""
    resp = client.post("/api/quotes/others/annotate/tasks")
    assert resp.status_code != 404, "others annotate route should exist"


def test_cloud_billing_preview_route_exists(client: TestClient):
    """POST /api/quotes/cloud-billing/preview should be a known route."""
    resp = client.post("/api/quotes/cloud-billing/preview")
    assert resp.status_code != 404, "cloud-billing preview route should exist"


def test_others_preview_route_exists(client: TestClient):
    """POST /api/quotes/others/preview should be a known route."""
    resp = client.post("/api/quotes/others/preview")
    assert resp.status_code != 404, "others preview route should exist"


def test_cloud_billing_review_route_exists(client: TestClient):
    """POST /api/quotes/cloud-billing/review should be a known route."""
    resp = client.post("/api/quotes/cloud-billing/review", json={"requirements": [], "quote_context": {}})
    assert resp.status_code != 404, "cloud-billing review route should exist"


def test_others_review_route_exists(client: TestClient):
    """POST /api/quotes/others/review should be a known route."""
    resp = client.post("/api/quotes/others/review", json={"requirements": [], "quote_context": {}})
    assert resp.status_code != 404, "others review route should exist"


def test_cloud_billing_export_route_exists(client: TestClient):
    """POST /api/quotes/cloud-billing/export should be a known route."""
    resp = client.post("/api/quotes/cloud-billing/export", json={"requirements": [], "quote_context": {}})
    assert resp.status_code != 404, "cloud-billing export route should exist"


def test_others_export_route_exists(client: TestClient):
    """POST /api/quotes/others/export should be a known route."""
    resp = client.post("/api/quotes/others/export", json={"requirements": [], "quote_context": {}})
    assert resp.status_code != 404, "others export route should exist"


# ── File type guards ────────────────────────────────────────────────────────────


def test_others_annotate_rejects_csv(client: TestClient):
    """Others Quote annotate should reject .csv files."""
    csv_bytes = _make_csv_bytes()
    resp = client.post(
        "/api/quotes/others/annotate/tasks",
        files={"flexible_file": ("billing.csv", csv_bytes, "text/csv")},
        data={"region": "mexico", "lang": "en", "customer_notes": "test guidance"},
    )
    assert resp.status_code == 415, f"Others Quote should reject .csv, got {resp.status_code}"
    assert "xlsx" in resp.json()["detail"].lower()


def test_cloud_billing_annotate_accepts_csv(client: TestClient):
    """Cloud Billing Quote annotate should accept .csv files."""
    csv_bytes = _make_csv_bytes()
    resp = client.post(
        "/api/quotes/cloud-billing/annotate/tasks",
        files={"flexible_file": ("billing.csv", csv_bytes, "text/csv")},
        data={"region": "mexico", "lang": "en", "customer_notes": "test guidance"},
    )
    # Should not be a 415 (unsupported type). It may fail for other reasons
    # (e.g. no MaaS key), but the file type should be accepted.
    assert resp.status_code != 415, f"Cloud Billing should accept .csv, got {resp.status_code}: {resp.text}"


def test_cloud_billing_annotate_accepts_xlsx(client: TestClient):
    """Cloud Billing Quote annotate should accept .xlsx files."""
    xlsx_bytes = _make_xlsx_bytes()
    resp = client.post(
        "/api/quotes/cloud-billing/annotate/tasks",
        files={"flexible_file": ("billing.xlsx", xlsx_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        data={"region": "mexico", "lang": "en", "customer_notes": "test guidance"},
    )
    assert resp.status_code != 415, f"Cloud Billing should accept .xlsx, got {resp.status_code}: {resp.text}"


def test_others_annotate_accepts_xlsx(client: TestClient):
    """Others Quote annotate should accept .xlsx files."""
    xlsx_bytes = _make_xlsx_bytes()
    resp = client.post(
        "/api/quotes/others/annotate/tasks",
        files={"flexible_file": ("requirements.xlsx", xlsx_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        data={"region": "mexico", "lang": "en", "customer_notes": "test guidance"},
    )
    assert resp.status_code != 415, f"Others Quote should accept .xlsx, got {resp.status_code}: {resp.text}"


def test_others_preview_rejects_csv(client: TestClient):
    """Others Quote preview should reject .csv files."""
    csv_bytes = _make_csv_bytes()
    resp = client.post(
        "/api/quotes/others/preview",
        files={"flexible_files": ("data.csv", csv_bytes, "text/csv")},
        data={"region": "mexico", "lang": "en", "customer_notes": "test guidance"},
    )
    assert resp.status_code == 415, f"Others Quote preview should reject .csv, got {resp.status_code}"


def test_cloud_billing_preview_accepts_csv(client: TestClient):
    """Cloud Billing Quote preview should accept .csv files."""
    csv_bytes = _make_csv_bytes()
    resp = client.post(
        "/api/quotes/cloud-billing/preview",
        files={"flexible_files": ("billing.csv", csv_bytes, "text/csv")},
        data={"region": "mexico", "lang": "en", "customer_notes": "test guidance"},
    )
    assert resp.status_code != 415, f"Cloud Billing preview should accept .csv, got {resp.status_code}"


# ── Old flexible endpoint compatibility with quote_mode ─────────────────────────


def test_flexible_annotate_accepts_quote_mode_cloud_billing(client: TestClient):
    """Old flexible annotate endpoint should accept quote_mode=cloud_billing."""
    xlsx_bytes = _make_xlsx_bytes()
    resp = client.post(
        "/api/quotes/flexible/annotate/tasks",
        files={"flexible_file": ("data.xlsx", xlsx_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        data={"region": "mexico", "lang": "en", "customer_notes": "test guidance", "quote_mode": "cloud_billing"},
    )
    # Should not be a 422 validation error about quote_mode
    assert resp.status_code != 422 or "quote_mode" not in resp.json().get("detail", ""), \
        f"quote_mode=cloud_billing should be accepted, got {resp.status_code}: {resp.text}"


def test_flexible_annotate_accepts_quote_mode_others(client: TestClient):
    """Old flexible annotate endpoint should accept quote_mode=others."""
    xlsx_bytes = _make_xlsx_bytes()
    resp = client.post(
        "/api/quotes/flexible/annotate/tasks",
        files={"flexible_file": ("data.xlsx", xlsx_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        data={"region": "mexico", "lang": "en", "customer_notes": "test guidance", "quote_mode": "others"},
    )
    assert resp.status_code != 422 or "quote_mode" not in resp.json().get("detail", ""), \
        f"quote_mode=others should be accepted, got {resp.status_code}: {resp.text}"


# ── quote_mode written to context ───────────────────────────────────────────────


def test_cloud_billing_review_sets_quote_mode(client: TestClient):
    """Cloud Billing review endpoint should set quote_mode=cloud_billing in context."""
    resp = client.post(
        "/api/quotes/cloud-billing/review",
        json={"requirements": [], "quote_context": {"region": "mexico", "language": "en", "customer_notes": "test"}},
    )
    # The response should contain quote_context with quote_mode=cloud_billing
    # (even if the result is minimal due to empty requirements)
    if resp.status_code == 200:
        data = resp.json()
        mode = data.get("quote_context", {}).get("quote_mode")
        assert mode == "cloud_billing", f"quote_mode should be cloud_billing, got {mode}"


def test_others_review_sets_quote_mode(client: TestClient):
    """Others review endpoint should set quote_mode=others in context."""
    resp = client.post(
        "/api/quotes/others/review",
        json={"requirements": [], "quote_context": {"region": "mexico", "language": "en", "customer_notes": "test"}},
    )
    if resp.status_code == 200:
        data = resp.json()
        mode = data.get("quote_context", {}).get("quote_mode")
        assert mode == "others", f"quote_mode should be others, got {mode}"


# ── FlexibleQuoteContext model ──────────────────────────────────────────────────


def test_flexible_quote_context_accepts_quote_mode():
    """FlexibleQuoteContext model should accept quote_mode field."""
    from app.models import FlexibleQuoteContext
    ctx = FlexibleQuoteContext(region="mexico", language="en", customer_notes="test", quote_mode="cloud_billing")
    assert ctx.quote_mode == "cloud_billing"

    ctx2 = FlexibleQuoteContext(region="mexico", language="en", customer_notes="test", quote_mode="others")
    assert ctx2.quote_mode == "others"

    ctx3 = FlexibleQuoteContext(region="mexico", language="en", customer_notes="test")
    assert ctx3.quote_mode is None


# ── Phase 4: Graph split tests ──────────────────────────────────────────────────


def test_cloud_billing_graphs_exist():
    """Cloud billing workflow graphs should be importable and compiled."""
    from app.cloud_billing_workflow import (
        cloud_billing_preview_graph,
        cloud_billing_review_graph,
        cloud_billing_export_graph,
    )
    assert cloud_billing_preview_graph is not None
    assert cloud_billing_review_graph is not None
    assert cloud_billing_export_graph is not None


def test_others_graphs_exist():
    """Others quote workflow graphs should be importable and compiled."""
    from app.others_quote_workflow import (
        others_preview_graph,
        others_review_graph,
        others_export_graph,
    )
    assert others_preview_graph is not None
    assert others_review_graph is not None
    assert others_export_graph is not None


def test_cloud_billing_graph_is_distinct_from_others():
    """Cloud billing and others graphs should be separate instances."""
    from app.cloud_billing_workflow import cloud_billing_preview_graph
    from app.others_quote_workflow import others_preview_graph
    assert cloud_billing_preview_graph is not others_preview_graph, \
        "Cloud billing and others preview graphs should be separate instances"


def test_cloud_billing_graph_is_distinct_from_flexible():
    """Cloud billing graph should be a separate instance from the old flexible graph."""
    from app.cloud_billing_workflow import cloud_billing_preview_graph
    from app.flexible_workflow import flexible_preview_graph
    assert cloud_billing_preview_graph is not flexible_preview_graph, \
        "Cloud billing graph should be separate from the old flexible graph"


def test_others_graph_is_distinct_from_flexible():
    """Others graph should be a separate instance from the old flexible graph."""
    from app.others_quote_workflow import others_preview_graph
    from app.flexible_workflow import flexible_preview_graph
    assert others_preview_graph is not flexible_preview_graph, \
        "Others graph should be separate from the old flexible graph"


def test_cloud_billing_graph_nodes_match_flexible():
    """Cloud billing preview graph should have the same node names as the flexible
    preview graph, EXCEPT understand_input (Phase 5A) and plus
    compose_final_billing_quote_items_with_llm (Phase 10/14)."""
    from app.cloud_billing_workflow import cloud_billing_preview_graph
    from app.flexible_workflow import flexible_preview_graph
    billing_nodes = set(cloud_billing_preview_graph.nodes.keys())
    flexible_nodes = set(flexible_preview_graph.nodes.keys())
    # Phase 5A: cloud billing graph intentionally skips understand_input
    # Phase 10/14: cloud billing graph adds compose_final_billing_quote_items_with_llm
    expected_billing_nodes = (flexible_nodes - {"understand_input"}) | {
        "compose_final_billing_quote_items_with_llm",
        "review_cloud_billing_mapping_with_llm",
    }
    assert billing_nodes == expected_billing_nodes, \
        f"Cloud billing nodes {billing_nodes} should match flexible nodes minus understand_input plus compose_final_billing_quote_items_with_llm {expected_billing_nodes}"


def test_others_graph_nodes_match_flexible():
    """Others preview graph should have the same node names as the flexible preview graph."""
    from app.others_quote_workflow import others_preview_graph
    from app.flexible_workflow import flexible_preview_graph
    others_nodes = set(others_preview_graph.nodes.keys())
    flexible_nodes = set(flexible_preview_graph.nodes.keys())
    assert others_nodes == flexible_nodes, \
        f"Others nodes {others_nodes} should match flexible nodes {flexible_nodes}"


def test_cloud_billing_review_graph_nodes():
    """Cloud billing review graph should have review-specific nodes."""
    from app.cloud_billing_workflow import cloud_billing_review_graph
    nodes = set(cloud_billing_review_graph.nodes.keys())
    assert "incorporate_feedback" in nodes
    assert "validate_quote_readiness" in nodes
    assert "summarize_quote" in nodes


def test_others_review_graph_nodes():
    """Others review graph should have review-specific nodes."""
    from app.others_quote_workflow import others_review_graph
    nodes = set(others_review_graph.nodes.keys())
    assert "incorporate_feedback" in nodes
    assert "validate_quote_readiness" in nodes
    assert "summarize_quote" in nodes


def test_cloud_billing_export_graph_has_export_node():
    """Cloud billing export graph should have a billing-specific export node."""
    from app.cloud_billing_workflow import cloud_billing_export_graph
    nodes = set(cloud_billing_export_graph.nodes.keys())
    assert "export_cloud_billing_workbook" in nodes


def test_others_export_graph_has_export_node():
    """Others export graph should have an export_workbook node."""
    from app.others_quote_workflow import others_export_graph
    nodes = set(others_export_graph.nodes.keys())
    assert "export_workbook" in nodes


def test_annotation_task_dispatches_to_cloud_billing_graph(monkeypatch: pytest.MonkeyPatch):
    """Mode-specific annotate task should use the cloud billing graph path, not legacy billing fast-path."""
    import app.row_quote_tasks as tasks
    from app.models import QuoteWorkbook, RowQuoteSummary

    task_id = "test-cloud-billing-task"
    now = datetime.now(timezone.utc).isoformat()
    tasks._tasks[task_id] = {
        "status": "queued",
        "current_stage": None,
        "summary": None,
        "progress": None,
        "error": None,
        "workbook": None,
        "cancelled": False,
        "created_at": now,
        "updated_at": now,
        "finished_at": None,
        "finished_at_epoch": None,
    }

    called: list[str] = []

    def fake_graph_runner(graph, upload, quote_context, **kwargs):
        called.append("graph")
        return QuoteWorkbook(filename="out.xlsx", content=b"x"), RowQuoteSummary(total_rows=1)

    monkeypatch.setattr(tasks, "_run_quote_graph_annotation_task", fake_graph_runner)
    monkeypatch.setattr(tasks, "_run_billing_annotation_task", lambda *a, **k: (_ for _ in ()).throw(AssertionError("legacy billing path should not run")))
    monkeypatch.setattr(tasks, "annotate_row_quote_workbook", lambda *a, **k: (_ for _ in ()).throw(AssertionError("row quote path should not run")))

    tasks._run_annotation_task(
        task_id,
        {"filename": "billing.csv", "content": b"service,quantity\nx,1\n"},
        {"region": "mexico", "language": "en", "customer_notes": "test", "quote_mode": "cloud_billing"},
    )

    assert called == ["graph"]


def test_annotation_task_dispatches_to_others_graph(monkeypatch: pytest.MonkeyPatch):
    """Mode-specific annotate task should use the others graph path."""
    import app.row_quote_tasks as tasks
    from app.models import QuoteWorkbook, RowQuoteSummary

    task_id = "test-others-task"
    now = datetime.now(timezone.utc).isoformat()
    tasks._tasks[task_id] = {
        "status": "queued",
        "current_stage": None,
        "summary": None,
        "progress": None,
        "error": None,
        "workbook": None,
        "cancelled": False,
        "created_at": now,
        "updated_at": now,
        "finished_at": None,
        "finished_at_epoch": None,
    }

    called: list[str] = []

    def fake_graph_runner(graph, upload, quote_context, **kwargs):
        called.append("graph")
        return QuoteWorkbook(filename="out.xlsx", content=b"x"), RowQuoteSummary(total_rows=1)

    monkeypatch.setattr(tasks, "_run_quote_graph_annotation_task", fake_graph_runner)
    monkeypatch.setattr(tasks, "_run_billing_annotation_task", lambda *a, **k: (_ for _ in ()).throw(AssertionError("legacy billing path should not run")))
    monkeypatch.setattr(tasks, "annotate_row_quote_workbook", lambda *a, **k: (_ for _ in ()).throw(AssertionError("row quote path should not run")))

    tasks._run_annotation_task(
        task_id,
        {"filename": "requirements.xlsx", "content": b"x"},
        {"region": "mexico", "language": "en", "customer_notes": "test", "quote_mode": "others"},
    )

    assert called == ["graph"]
