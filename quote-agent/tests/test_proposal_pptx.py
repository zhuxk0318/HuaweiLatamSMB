"""Tests for Proposal PPTX rendering — Phase 3C."""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from pptx import Presentation

from app.models import ProposalRequest
from app.proposal_pptx import DEFAULT_TEMPLATE_PATH, render_proposal_pptx
from app.proposal_tasks import (
    _tasks,
    _lock,
    create_proposal_task,
    get_proposal_artifact,
    get_proposal_task,
)


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


def _sample_proposal_data(**overrides) -> dict:
    data = {
        "project_name": "Test Project",
        "customer_name": "Acme Corp",
        "language": "en",
        "quote_mode": "skip",
        "quote_status": "skipped",
        "hld_status": "skipped",
        "content_status": "fallback",
        "sections": {
            "executive_summary": "This proposal outlines cloud migration for Acme Corp.",
            "current_challenges": "High on-prem costs and limited scalability.",
            "target_solution": "Migrate to Huawei Cloud with ECS and RDS.",
            "pricing_summary": "Pricing details to be refined.",
            "next_steps": "1. Assessment 2. POC 3. Migration",
        },
        "assumptions": ["Stable network", "Data under 10TB"],
        "risks": ["Migration downtime"],
    }
    data.update(overrides)
    return data


class TestRenderProposalPptx:
    """Direct render_proposal_pptx tests."""

    def test_generates_valid_pptx(self, tmp_path):
        output = tmp_path / "out.pptx"
        result = render_proposal_pptx(
            template_path=DEFAULT_TEMPLATE_PATH,
            output_path=output,
            proposal_data=_sample_proposal_data(),
        )
        assert output.exists()
        assert output.stat().st_size > 0
        assert result["slides_generated"] > 0

    def test_output_reopenable(self, tmp_path):
        output = tmp_path / "out.pptx"
        render_proposal_pptx(
            template_path=DEFAULT_TEMPLATE_PATH,
            output_path=output,
            proposal_data=_sample_proposal_data(),
        )
        prs = Presentation(str(output))
        assert len(prs.slides) > 0

    def test_text_written_to_slides(self, tmp_path):
        output = tmp_path / "out.pptx"
        render_proposal_pptx(
            template_path=DEFAULT_TEMPLATE_PATH,
            output_path=output,
            proposal_data=_sample_proposal_data(),
        )
        prs = Presentation(str(output))
        all_text = []
        for slide in prs.slides:
            for shape in slide.shapes:
                if shape.has_text_frame:
                    all_text.append(shape.text_frame.text)
        combined = " ".join(all_text)
        assert "Acme Corp" in combined
        assert "cloud migration" in combined.lower()

    def test_no_hld_still_works(self, tmp_path):
        output = tmp_path / "out.pptx"
        result = render_proposal_pptx(
            template_path=DEFAULT_TEMPLATE_PATH,
            output_path=output,
            proposal_data=_sample_proposal_data(),
            hld_png_path=None,
        )
        assert result["hld_image_embedded"] is False
        assert output.exists()

    def test_with_hld_png(self, tmp_path):
        # Create a valid PNG using PIL
        from PIL import Image
        hld_png = tmp_path / "hld.png"
        img = Image.new("RGB", (200, 150), color="green")
        img.save(str(hld_png))
        output = tmp_path / "out.pptx"
        result = render_proposal_pptx(
            template_path=DEFAULT_TEMPLATE_PATH,
            output_path=output,
            proposal_data=_sample_proposal_data(hld_status="succeeded"),
            hld_png_path=hld_png,
        )
        assert result["hld_image_embedded"] is True
        prs = Presentation(str(output))
        # HLD image should be embedded into the template architecture page.
        architecture_slide = prs.slides[12]
        has_image = any(s.shape_type == 13 for s in architecture_slide.shapes)
        assert has_image

    def test_template_missing_raises(self, tmp_path):
        output = tmp_path / "out.pptx"
        with pytest.raises(FileNotFoundError):
            render_proposal_pptx(
                template_path=Path("/nonexistent/template.pptx"),
                output_path=output,
                proposal_data=_sample_proposal_data(),
            )


class TestProposalTaskWithRealPptx:
    """Integration: Proposal task generates real downloadable PPTX."""

    @pytest.fixture(autouse=True)
    def _patch_llm_to_fallback(self, monkeypatch):
        # Force content fallback so tests don't need MaaS
        def _fake_build(*, timeout=None):
            raise RuntimeError("No MaaS in test")
        monkeypatch.setattr("app.proposal_tasks.build_proposal_chat_client_from_env", _fake_build)

    def _wait_for_task(self, task_id: str, timeout: float = 15.0) -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            resp = get_proposal_task(task_id)
            if resp.status in ("succeeded", "failed"):
                return
            time.sleep(0.05)
        raise TimeoutError(f"Task {task_id} did not finish within {timeout}s")

    def test_task_produces_valid_pptx_artifact(self):
        created = create_proposal_task(_make_request())
        self._wait_for_task(created.task_id)
        task = get_proposal_task(created.task_id)
        assert task.status == "succeeded"

        content, media_type, filename = get_proposal_artifact(created.task_id, "pptx")
        assert media_type == "application/vnd.openxmlformats-officedocument.presentationml.presentation"
        assert filename.endswith(".pptx")
        assert len(content) > 1000  # Real PPTX, not stub

        # Verify re-openable
        import tempfile, os
        with tempfile.NamedTemporaryFile(suffix=".pptx", delete=False) as f:
            f.write(content)
            tmp_path = f.name
        try:
            prs = Presentation(tmp_path)
            assert len(prs.slides) > 0
        finally:
            os.unlink(tmp_path)

    def test_json_has_pptx_metadata(self):
        created = create_proposal_task(_make_request())
        self._wait_for_task(created.task_id)
        content, _, _ = get_proposal_artifact(created.task_id, "json")
        data = json.loads(content)
        assert data.get("pptx_render_status") == "succeeded"
        assert data.get("pptx_slides_generated", 0) > 0
        assert 1 in data.get("pptx_template_pages_updated", [])
