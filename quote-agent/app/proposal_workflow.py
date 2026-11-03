"""Proposal generation — stub + HLD + quote + content + PPTX integration."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from app.models import ProposalContentResult, ProposalQuoteResult, ProposalRequest
from app.proposal_pptx import DEFAULT_TEMPLATE_PATH, render_proposal_pptx

logger = logging.getLogger(__name__)


def generate_proposal_stub(request: ProposalRequest, artifacts_dir: Path) -> dict[str, Any]:
    """Generate minimal placeholder artifacts for a proposal.

    Returns dict with keys: basename, json, pptx (file paths).
    """
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    basename = request.preferred_filename or request.project_name

    # proposal.json
    proposal_data: dict[str, Any] = {
        "project_name": request.project_name,
        "language": request.language,
        "quote_mode": request.quote_mode,
        "sections": {
            "executive_summary": f"Proposal for {request.project_name}",
            "current_challenges": request.current_pain_points,
            "target_solution": request.target_outcomes,
            "pricing_summary": "Pricing details to be added in Phase 2.",
            "next_steps": "",
        },
    }
    json_path = artifacts_dir / f"{basename}.json"
    json_path.write_text(json.dumps(proposal_data, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("Wrote proposal JSON: %s", json_path)

    # proposal.pptx — placeholder bytes
    pptx_path = artifacts_dir / f"{basename}.pptx"
    pptx_path.write_bytes(b"PK\x03\x04STUB_PPTX_PLACEHOLDER")
    logger.info("Wrote stub PPTX: %s", pptx_path)

    return {
        "basename": basename,
        "json": str(json_path),
        "pptx": str(pptx_path),
    }


def generate_proposal_with_hld_stub(
    request: ProposalRequest,
    artifacts_dir: Path,
    hld_result: dict[str, Any] | None = None,
    hld_design_id: str | None = None,
    hld_status: str = "skipped",
    quote_result: ProposalQuoteResult | None = None,
    content_result: ProposalContentResult | None = None,
    template_path: Path | None = None,
) -> dict[str, Any]:
    """Generate proposal with optional HLD result, quote summary, LLM content, and real PPTX.

    Args:
        hld_result: dict with keys "png", "drawio", "basename" from HLD generation.
        hld_design_id: the HLD design task ID.
        hld_status: the HLD status string (succeeded, skipped, pending_external_workflow).
        quote_result: structured quote result from flexible workflow.
        content_result: LLM-generated or fallback content sections.
        template_path: Path to .pptx template; defaults to DEFAULT_TEMPLATE_PATH.

    Returns dict with keys: basename, json, pptx, and optionally hld_png, hld_drawio.
    """
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    basename = request.preferred_filename or request.project_name

    # Build sections — prefer content_result, then quote-derived, then stub
    if content_result and content_result.sections:
        cs = content_result.sections
        sections = {
            "executive_summary": cs.executive_summary or f"Proposal for {request.project_name}",
            "current_challenges": cs.current_challenges or request.current_pain_points,
            "target_solution": cs.target_solution or request.target_outcomes,
            "pricing_summary": cs.pricing_summary or "Pricing details to be refined.",
            "next_steps": cs.next_steps,
        }
    else:
        sections = {
            "executive_summary": f"Proposal for {request.project_name}",
            "current_challenges": request.current_pain_points,
            "target_solution": request.target_outcomes,
            "pricing_summary": "Pricing details to be added in Phase 2.",
            "next_steps": "",
        }

    # Build proposal.json content
    proposal_data: dict[str, Any] = {
        "project_name": request.project_name,
        "customer_name": request.customer_name or "",
        "country": request.country or "",
        "customer_brief": request.customer_brief or "",
        "business_background": request.business_background,
        "current_pain_points": request.current_pain_points,
        "target_outcomes": request.target_outcomes,
        "language": request.language,
        "quote_mode": request.quote_mode,
        "sections": sections,
    }

    # Content selection fields
    if request.proposal_title:
        proposal_data["proposal_title"] = request.proposal_title
    if request.proposal_subtitle:
        proposal_data["proposal_subtitle"] = request.proposal_subtitle
    proposal_data["content_selection"] = {
        "include_hld": request.include_hld,
        "include_price": request.include_price,
        "include_migration": request.include_migration,
        "include_support_training": request.include_support_training,
        "include_huawei_capability": request.include_huawei_capability,
    }
    proposal_data["asset_linking"] = {
        "hld_mode": request.hld_mode,
        "price_mode": request.price_mode,
    }
    proposal_data["migration_context"] = {
        "scope": request.migration_scope,
        "constraints": request.migration_constraints,
        "notes": request.migration_notes,
    }

    # Quote fields
    if quote_result:
        proposal_data["quote_status"] = quote_result.status
        proposal_data["quote_mode"] = quote_result.mode
        proposal_data["quote_summary"] = quote_result.summary.model_dump()
    else:
        proposal_data["quote_status"] = "skipped"
        proposal_data["quote_mode"] = request.quote_mode
        proposal_data["quote_summary"] = None

    # HLD fields
    if hld_result and hld_design_id:
        proposal_data["hld_status"] = "succeeded"
        proposal_data["hld_design_id"] = hld_design_id
        hld_basename = hld_result.get("basename", "hld-design")
        proposal_data["hld_artifacts"] = {
            "png_filename": f"{hld_basename}.png",
            "drawio_filename": f"{hld_basename}.drawio",
        }
    else:
        proposal_data["hld_status"] = hld_status
        proposal_data["hld_design_id"] = hld_design_id
        proposal_data["hld_artifacts"] = None

    # Content fields
    if content_result:
        proposal_data["content_status"] = content_result.status
        proposal_data["content_model"] = content_result.model
        proposal_data["content_error"] = content_result.error
        proposal_data["assumptions"] = content_result.sections.assumptions
        proposal_data["risks"] = content_result.sections.risks
    else:
        proposal_data["content_status"] = "fallback"
        proposal_data["content_model"] = None
        proposal_data["content_error"] = None
        proposal_data["assumptions"] = []
        proposal_data["risks"] = []

    # Fill pricing_summary from quote if available and not already set by content
    if quote_result and quote_result.status == "succeeded":
        if not content_result or not content_result.sections.pricing_summary:
            s = quote_result.summary
            proposal_data["sections"]["pricing_summary"] = (
                f"Monthly total: {s.total_monthly_price:.2f} {s.currency} "
                f"({s.quoted_items} items quoted, {s.blocker_count} blockers)."
            )

    json_path = artifacts_dir / f"{basename}.json"
    json_path.write_text(json.dumps(proposal_data, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("Wrote proposal JSON (content=%s, quote=%s, hld=%s): %s", proposal_data["content_status"], proposal_data["quote_status"], proposal_data["hld_status"], json_path)

    # Render real PPTX
    effective_template = template_path or DEFAULT_TEMPLATE_PATH
    hld_png_path = None
    if hld_result and hld_result.get("png"):
        hld_png_path = Path(hld_result["png"])

    pptx_path = artifacts_dir / f"{basename}.pptx"
    pptx_meta = render_proposal_pptx(
        template_path=effective_template,
        output_path=pptx_path,
        proposal_data=proposal_data,
        hld_png_path=hld_png_path,
    )
    proposal_data["pptx_render_status"] = "succeeded"
    proposal_data["pptx_slides_generated"] = pptx_meta["slides_generated"]
    proposal_data["pptx_sections_generated"] = pptx_meta.get("sections_generated", [])
    proposal_data["pptx_template_pages_updated"] = pptx_meta.get("template_pages_updated", [])
    proposal_data["pptx_content_controls_applied"] = True

    # Re-write JSON with PPTX metadata
    json_path.write_text(json.dumps(proposal_data, ensure_ascii=False, indent=2), encoding="utf-8")

    result: dict[str, Any] = {
        "basename": basename,
        "json": str(json_path),
        "pptx": str(pptx_path),
    }

    if hld_result:
        result["hld_png"] = hld_result.get("png")
        result["hld_drawio"] = hld_result.get("drawio")

    return result
