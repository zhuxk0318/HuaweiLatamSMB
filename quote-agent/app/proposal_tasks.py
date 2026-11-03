"""In-memory async task queue for proposal generation."""
from __future__ import annotations

import csv
import io
import json
import logging
import os
import re
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from app.chat_service import ChatCompletionsClient, build_chat_client_from_env
from app.flexible_workflow import build_flexible_preview_response, flexible_preview_graph
from app.hld_tasks import create_hld_design_task, get_hld_design_task
from app.models import (
    FlexibleQuotePreviewResponse,
    HldDesignTaskResponse,
    ProposalArtifacts,
    ProposalArtifactInfo,
    ProposalContentResult,
    ProposalContentStatus,
    ProposalGeneratedSections,
    ProposalQuoteMode,
    ProposalQuoteResult,
    ProposalQuoteSummary,
    ProposalQuoteStatus,
    ProposalRequest,
    ProposalTaskCreatedResponse,
    ProposalTaskError,
    ProposalTaskResponse,
)
from app.proposal_workflow import generate_proposal_with_hld_stub

logger = logging.getLogger(__name__)

TASK_TTL_SECONDS = 1800
ARTIFACTS_ROOT = Path("/tmp/proposal-designs")

HLD_POLL_INTERVAL = 2.0
HLD_POLL_TIMEOUT = 300.0

PROPOSAL_LLM_TIMEOUT = 180.0
PROPOSAL_MAAS_MODEL_ENV = "PROPOSAL_MAAS_MODEL"
DEFAULT_PROPOSAL_MAAS_MODEL = "glm-5.1"

_tasks: dict[str, dict[str, Any]] = {}
_lock = threading.Lock()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _cleanup_expired_tasks() -> None:
    cutoff = time.time() - TASK_TTL_SECONDS
    expired = []
    with _lock:
        for task_id, task in _tasks.items():
            finished_at = task.get("finished_at_epoch")
            if finished_at is not None and finished_at < cutoff:
                expired.append(task_id)
        for task_id in expired:
            _tasks.pop(task_id, None)


def _touch(task: dict[str, Any]) -> None:
    task["updated_at"] = _now_iso()


def _make_response(task_id: str, task: dict[str, Any]) -> ProposalTaskResponse:
    artifacts = None
    if task.get("artifacts_info"):
        info = task["artifacts_info"]
        artifacts = ProposalArtifacts(
            json_info=ProposalArtifactInfo(**info["json"]) if info.get("json") else None,
            pptx_info=ProposalArtifactInfo(**info["pptx"]) if info.get("pptx") else None,
            hld_png=ProposalArtifactInfo(**info["hld_png"]) if info.get("hld_png") else None,
            hld_drawio=ProposalArtifactInfo(**info["hld_drawio"]) if info.get("hld_drawio") else None,
        )
    return ProposalTaskResponse(
        task_id=task_id,
        status=task["status"],
        current_stage=task.get("current_stage"),
        error=ProposalTaskError.model_validate(task["error"]) if task.get("error") else None,
        artifacts=artifacts,
        hld_design_id=task.get("hld_design_id"),
        created_at=task["created_at"],
        updated_at=task["updated_at"],
        finished_at=task.get("finished_at"),
    )


def _set_stage(task_id: str, stage: str) -> None:
    with _lock:
        task = _tasks.get(task_id)
        if not task:
            return
        task["status"] = "running"
        task["current_stage"] = stage
        _touch(task)


def _fail_task(task_id: str, message: str, detail: str) -> None:
    with _lock:
        task = _tasks.get(task_id)
        if not task:
            return
        current_stage = task.get("current_stage")
        task["status"] = "failed"
        task["error"] = {
            "message": message,
            "detail": detail,
            "last_stage": current_stage,
        }
        task["finished_at"] = _now_iso()
        task["finished_at_epoch"] = time.time()
        _touch(task)


def _await_hld_completion(hld_design_id: str) -> HldDesignTaskResponse:
    """Poll HLD task until succeeded/failed or timeout."""
    deadline = time.time() + HLD_POLL_TIMEOUT
    while time.time() < deadline:
        resp = get_hld_design_task(hld_design_id)
        if resp.status in ("succeeded", "failed"):
            return resp
        time.sleep(HLD_POLL_INTERVAL)
    raise TimeoutError(f"HLD task {hld_design_id} did not complete within {HLD_POLL_TIMEOUT}s")


def _requirements_to_csv_file(requirements: list[Any]) -> dict[str, bytes | str]:
    """Serialize RequirementItem list to an in-memory CSV file entry."""
    buf = io.StringIO()
    if not requirements:
        writer = csv.writer(buf)
        writer.writerow(["product", "quantity", "unit", "region"])
    else:
        dicts = [r.model_dump() if hasattr(r, "model_dump") else r for r in requirements]
        writer = csv.DictWriter(buf, fieldnames=dicts[0].keys())
        writer.writeheader()
        for d in dicts:
            writer.writerow({k: v for k, v in d.items() if v is not None})
    return {"filename": "proposal_requirements.csv", "content": buf.getvalue().encode("utf-8")}


def _run_flexible_quote(request: ProposalRequest) -> ProposalQuoteResult:
    """Run flexible quote workflow and return structured result."""
    quote_input = request.quote_input
    if not quote_input or not quote_input.requirements:
        raise ValueError("quote_input with requirements is required for flexible quote mode.")

    csv_file = _requirements_to_csv_file(quote_input.requirements)
    quote_context = {
        "region": quote_input.region or None,
        "language": request.language,
        "customer_notes": quote_input.customer_notes,
    }

    state = flexible_preview_graph.invoke({
        "files": [csv_file],
        "quote_context": quote_context,
    })

    response = build_flexible_preview_response(state)
    summary = response.summary

    return ProposalQuoteResult(
        status="succeeded",
        mode="flexible",
        summary=ProposalQuoteSummary(
            total_monthly_price=summary.total_monthly_price,
            currency=summary.currency,
            quoted_items=summary.quoted_items,
            blocker_count=summary.blocker_count,
            summary=summary.summary,
        ),
    )


# --- Proposal content generation ---

_REQUIRED_CONTENT_KEYS = {"executive_summary", "current_challenges", "target_solution"}


def build_proposal_chat_client_from_env(*, timeout: float | None = None) -> ChatCompletionsClient:
    """Build a Proposal-only LLM client reusing MaaS URL/key but overriding model."""
    base_client = build_chat_client_from_env(timeout=timeout)
    proposal_model = os.getenv(PROPOSAL_MAAS_MODEL_ENV) or DEFAULT_PROPOSAL_MAAS_MODEL
    return ChatCompletionsClient(
        api_key=base_client.api_key,
        base_url=base_client.base_url,
        model=proposal_model,
        timeout=base_client.timeout,
    )


def _build_content_prompt(
    request: ProposalRequest,
    quote_result: ProposalQuoteResult | None,
    hld_status: str,
) -> str:
    """Build the LLM prompt for proposal content generation."""
    customer_brief = (request.customer_brief or "").strip()
    output_language = {"en": "English", "es": "Spanish", "zh": "Chinese"}.get(request.language, "English")
    parts = [
        "Generate a concise, sales-oriented cloud proposal in JSON format.",
        "Analyze the customer brief and structure it into business context, challenges, outcomes, and a recommended solution.",
        "Treat missing details as explicit assumptions instead of asking the user more questions.",
        "",
        "Project context:",
        f"- Project: {request.project_name}",
        f"- Output language: {output_language}",
    ]
    if customer_brief:
        parts.append(f"- Customer brief: {customer_brief}")
    if request.business_background:
        parts.append(f"- Business background: {request.business_background}")
    if request.current_pain_points:
        parts.append(f"- Current pain points: {request.current_pain_points}")
    if request.target_outcomes:
        parts.append(f"- Target outcomes: {request.target_outcomes}")
    if request.customer_name:
        parts.append(f"- Customer: {request.customer_name}")
    if request.country:
        parts.append(f"- Country: {request.country}")

    # Content selection
    parts.append("")
    parts.append("Content selection (only generate content for selected modules):")
    parts.append(f"- Include HLD: {request.include_hld}")
    parts.append(f"- Include Pricing: {request.include_price}")
    parts.append(f"- Include Migration: {request.include_migration}")
    parts.append(f"- Include Support & Training: {request.include_support_training}")
    parts.append(f"- Include Huawei Capability: {request.include_huawei_capability}")

    # Quote context
    if request.include_price and quote_result and quote_result.status == "succeeded":
        s = quote_result.summary
        parts.append(f"- Pricing: {s.total_monthly_price:.2f} {s.currency}/month, {s.quoted_items} items quoted, {s.blocker_count} blockers.")
    elif not request.include_price:
        parts.append("- Pricing: NOT included in this proposal; do NOT generate pricing_summary content or price commitments.")
    else:
        parts.append("- Pricing: not yet available; do NOT include specific price commitments.")

    # HLD context
    if request.include_hld and hld_status == "succeeded":
        parts.append("- Architecture diagram: has been designed (HLD available).")
    elif not request.include_hld:
        parts.append("- Architecture diagram: NOT included in this proposal; do NOT claim an architecture diagram exists.")
    else:
        parts.append("- Architecture diagram: not yet designed; do NOT claim design is complete.")

    # Migration context
    if request.include_migration:
        parts.append("- Migration: include a migration plan.")
        if request.migration_scope:
            parts.append(f"  Migration scope: {request.migration_scope}")
        if request.migration_constraints:
            parts.append(f"  Migration constraints: {request.migration_constraints}")
        if request.migration_notes:
            parts.append(f"  Migration notes: {request.migration_notes}")
    else:
        parts.append("- Migration: NOT included; do NOT generate migration plan content.")

    if not request.include_support_training:
        parts.append("- Support & Training: NOT included; do NOT generate support or training page content.")

    if not request.include_huawei_capability:
        parts.append("- Huawei Capability: NOT included; do NOT generate vendor endorsement content.")

    parts.extend([
        "",
        "Return ONLY a JSON object with these keys:",
        "  executive_summary, current_challenges, target_solution, pricing_summary",
        "  next_steps (optional array of short actions)",
        "  assumptions (list of strings), risks (list of strings)",
        "",
        "Rules:",
        "- Keep each narrative field under 160 words.",
        "- Do not fabricate prices, products, customer scale, SLA commitments, or timelines.",
        "- Generate next_steps only when concrete immediate actions are justified.",
        "- next_steps must contain at most 3 distinct actions, each no longer than 20 words.",
        "- Do not automatically list assessment, workshop, POC, and migration as a generic sequence.",
    ])
    return "\n".join(parts)


def _normalize_next_steps(value: Any) -> str:
    """Return at most three short, unique actions in a stable display format."""
    if value is None:
        return ""
    if isinstance(value, list):
        candidates = [str(item).strip() for item in value]
    else:
        text = str(value).strip()
        if not text:
            return ""
        candidates = [line.strip() for line in text.splitlines() if line.strip()]
        if len(candidates) == 1:
            numbered = re.split(r"(?=\b\d+[.)]\s*)", candidates[0])
            candidates = [part.strip() for part in numbered if part.strip()]

    normalized: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        cleaned = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", candidate).strip()
        cleaned = re.sub(r"\s+", " ", cleaned)
        if not cleaned:
            continue
        words = cleaned.split()
        if len(words) > 20:
            cleaned = " ".join(words[:20]).rstrip(" ,;:") + "..."
        key = re.sub(r"\W+", " ", cleaned).strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        normalized.append(cleaned)
        if len(normalized) == 3:
            break
    return "\n".join(f"{index}. {step}" for index, step in enumerate(normalized, start=1))


def _content_fallback(
    request: ProposalRequest,
    quote_result: ProposalQuoteResult | None,
    hld_status: str,
    error: str | None = None,
) -> ProposalContentResult:
    """Build deterministic fallback content when LLM is unavailable or fails."""
    customer_brief = (
        request.customer_brief
        or request.business_background
        or request.current_pain_points
        or request.target_outcomes
    ).strip()
    if not request.include_price:
        pricing_summary = "Pricing was not included in this proposal scope."
    elif quote_result and quote_result.status == "succeeded":
        s = quote_result.summary
        pricing_summary = f"Monthly total: {s.total_monthly_price:.2f} {s.currency} ({s.quoted_items} items quoted)."
    elif quote_result and quote_result.status in ("failed", "not_implemented"):
        pricing_summary = "Pricing details to be refined after further assessment."
    else:
        pricing_summary = "Pricing details to be refined."

    target_solution = request.target_outcomes or "A phased Huawei Cloud solution should be refined against the confirmed scope."
    if not request.include_hld and "architecture diagram" in target_solution.lower():
        target_solution = target_solution.replace("architecture diagram", "").strip()

    return ProposalContentResult(
        status="fallback",
        model=None,
        sections=ProposalGeneratedSections(
            executive_summary=f"Proposal for {request.project_name}: {customer_brief}",
            current_challenges=request.current_pain_points or "Key challenges should be confirmed against the customer brief.",
            target_solution=target_solution,
            pricing_summary=pricing_summary,
            next_steps="",
            assumptions=[],
            risks=[],
        ),
        error=error,
    )


def _generate_proposal_content(
    request: ProposalRequest,
    quote_result: ProposalQuoteResult | None,
    hld_status: str,
) -> ProposalContentResult:
    """Generate proposal content via LLM, with fallback on any failure."""
    try:
        client = build_proposal_chat_client_from_env(timeout=PROPOSAL_LLM_TIMEOUT)
    except Exception as exc:
        logger.info("MaaS config missing or invalid, using content fallback: %s", exc)
        return _content_fallback(request, quote_result, hld_status, error=str(exc))

    prompt = _build_content_prompt(request, quote_result, hld_status)
    messages = [
        {"role": "system", "content": "You are a cloud solutions proposal writer. Output only valid JSON."},
        {"role": "user", "content": prompt},
    ]

    try:
        raw = client.complete_text(messages)
    except Exception as exc:
        logger.warning("LLM call failed, using content fallback: %s", exc)
        return _content_fallback(request, quote_result, hld_status, error=str(exc))

    if not raw or not raw.strip():
        return _content_fallback(request, quote_result, hld_status, error="LLM returned empty response")

    # Parse JSON — strip markdown fences if present
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines).strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        logger.warning("LLM JSON parse failed, using content fallback: %s", exc)
        return _content_fallback(request, quote_result, hld_status, error=f"JSON parse error: {exc}")

    # Validate required keys
    missing = _REQUIRED_CONTENT_KEYS - set(data.keys())
    if missing:
        return _content_fallback(request, quote_result, hld_status, error=f"Missing keys: {missing}")

    try:
        sections = ProposalGeneratedSections(
            executive_summary=str(data.get("executive_summary", "")),
            current_challenges=str(data.get("current_challenges", "")),
            target_solution=str(data.get("target_solution", "")),
            pricing_summary=str(data.get("pricing_summary", "")),
            next_steps=_normalize_next_steps(data.get("next_steps")),
            assumptions=data.get("assumptions", []) if isinstance(data.get("assumptions"), list) else [],
            risks=data.get("risks", []) if isinstance(data.get("risks"), list) else [],
        )
    except Exception as exc:
        return _content_fallback(request, quote_result, hld_status, error=f"Section validation error: {exc}")

    return ProposalContentResult(
        status="generated",
        model=client.model,
        sections=sections,
    )


def _run_proposal_task(task_id: str, request: ProposalRequest) -> None:
    artifacts_dir = ARTIFACTS_ROOT / task_id
    hld_design_id: str | None = None
    hld_result: dict[str, Any] | None = None
    hld_status: str = "skipped"
    quote_result: ProposalQuoteResult | None = None
    content_result: ProposalContentResult | None = None
    try:
        # Stage: validate_input
        _set_stage(task_id, "validate_input")
        logger.info("Proposal task %s: validating input", task_id)

        # Stage: generate_quote
        _set_stage(task_id, "generate_quote")
        if not request.include_price:
            quote_result = ProposalQuoteResult(status="skipped", mode="skip")
            logger.info("Proposal task %s: quote skipped (include_price=false)", task_id)
        elif request.quote_mode == "skip":
            quote_result = ProposalQuoteResult(status="skipped", mode="skip")
            logger.info("Proposal task %s: quote skipped", task_id)
        elif request.quote_mode == "rvtools":
            quote_result = ProposalQuoteResult(status="not_implemented", mode="rvtools")
            logger.info("Proposal task %s: rvtools quote not implemented", task_id)
        elif request.quote_mode == "flexible":
            if request.quote_input and request.quote_input.requirements:
                logger.info("Proposal task %s: running flexible quote", task_id)
                quote_result = _run_flexible_quote(request)
                logger.info("Proposal task %s: flexible quote %s", task_id, quote_result.status)
            elif request.price_mode == "create_new":
                quote_result = ProposalQuoteResult(status="pending_external_workflow", mode="flexible")
                logger.info("Proposal task %s: price_mode=create_new but no quote_input, pending_external_workflow", task_id)
            else:
                quote_result = ProposalQuoteResult(status="skipped", mode="skip")
                logger.info("Proposal task %s: no quote_input, skipping", task_id)

        # Stage: summarize_quote
        _set_stage(task_id, "summarize_quote")
        logger.info("Proposal task %s: summarizing quote", task_id)

        # Stage: generate_hld (if hld_requirements provided)
        _set_stage(task_id, "generate_hld")
        if not request.include_hld:
            logger.info("Proposal task %s: HLD skipped (include_hld=false)", task_id)
        elif request.hld_requirements:
            logger.info("Proposal task %s: creating HLD design task", task_id)
            hld_created = create_hld_design_task(request.hld_requirements)
            hld_design_id = hld_created.design_id
            with _lock:
                task = _tasks.get(task_id)
                if task:
                    task["hld_design_id"] = hld_design_id
                    _touch(task)

            # Stage: await_hld_result
            _set_stage(task_id, "await_hld_result")
            logger.info("Proposal task %s: awaiting HLD task %s", task_id, hld_design_id)
            hld_resp = _await_hld_completion(hld_design_id)

            if hld_resp.status == "failed":
                hld_err = hld_resp.error
                raise RuntimeError(
                    f"HLD task failed: {hld_err.message if hld_err else 'unknown'}"
                    f" — {hld_err.detail if hld_err else ''}"
                )

            # HLD succeeded — retrieve artifact paths from the HLD task's internal record
            from app.hld_tasks import _tasks as _hld_tasks, _lock as _hld_lock
            with _hld_lock:
                hld_internal = _hld_tasks.get(hld_design_id, {})
                hld_artifacts = hld_internal.get("artifacts", {})
            hld_result = hld_artifacts
            hld_status = "succeeded"
            logger.info("Proposal task %s: HLD succeeded, artifacts=%s", task_id, list(hld_result.keys()))
        elif request.hld_mode == "create_new":
            hld_status = "pending_external_workflow"
            logger.info("Proposal task %s: hld_mode=create_new but no hld_requirements, pending_external_workflow", task_id)
        else:
            logger.info("Proposal task %s: no HLD requirements, skipping", task_id)

        # Stage: generate_proposal_content
        _set_stage(task_id, "generate_proposal_content")
        logger.info("Proposal task %s: generating proposal content", task_id)
        content_result = _generate_proposal_content(request, quote_result, hld_status)
        logger.info("Proposal task %s: content %s", task_id, content_result.status)

        # Stage: assemble_stub_content
        _set_stage(task_id, "assemble_stub_content")
        logger.info("Proposal task %s: assembling stub content", task_id)

        # Stage: render_pptx
        _set_stage(task_id, "render_pptx")
        logger.info("Proposal task %s: rendering PPTX", task_id)

        result = generate_proposal_with_hld_stub(
            request, artifacts_dir,
            hld_result=hld_result,
            hld_design_id=hld_design_id,
            hld_status=hld_status,
            quote_result=quote_result,
            content_result=content_result,
        )

        # Stage: package_artifacts
        _set_stage(task_id, "package_artifacts")
        logger.info("Proposal task %s: packaging artifacts", task_id)

        # Build artifact info
        json_path = Path(result["json"])
        pptx_path = Path(result["pptx"])
        artifacts_info: dict[str, Any] = {
            "json": {
                "artifact_type": "json",
                "filename": json_path.name,
                "size_bytes": json_path.stat().st_size,
            },
            "pptx": {
                "artifact_type": "pptx",
                "filename": pptx_path.name,
                "size_bytes": pptx_path.stat().st_size,
            },
            "hld_png": None,
            "hld_drawio": None,
        }

        if hld_result and result.get("hld_png"):
            hld_png_path = Path(result["hld_png"])
            if hld_png_path.exists():
                artifacts_info["hld_png"] = {
                    "artifact_type": "hld_png",
                    "filename": hld_png_path.name,
                    "size_bytes": hld_png_path.stat().st_size,
                }
        if hld_result and result.get("hld_drawio"):
            hld_drawio_path = Path(result["hld_drawio"])
            if hld_drawio_path.exists():
                artifacts_info["hld_drawio"] = {
                    "artifact_type": "hld_drawio",
                    "filename": hld_drawio_path.name,
                    "size_bytes": hld_drawio_path.stat().st_size,
                }

        with _lock:
            task = _tasks.get(task_id)
            if not task:
                return
            task["status"] = "succeeded"
            task["current_stage"] = "completed"
            task["artifacts"] = result
            task["artifacts_info"] = artifacts_info
            task["finished_at"] = _now_iso()
            task["finished_at_epoch"] = time.time()
            _touch(task)
            logger.info("Proposal task %s: succeeded", task_id)

    except Exception as exc:
        logger.exception("Proposal task %s failed at stage %s", task_id, _tasks.get(task_id, {}).get("current_stage"))
        _fail_task(task_id, "Proposal generation failed.", str(exc))


def create_proposal_task(request: ProposalRequest) -> ProposalTaskCreatedResponse:
    _cleanup_expired_tasks()
    task_id = str(uuid.uuid4())
    task = {
        "status": "queued",
        "current_stage": None,
        "error": None,
        "artifacts": None,
        "artifacts_info": None,
        "hld_design_id": None,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
        "finished_at": None,
        "finished_at_epoch": None,
    }
    with _lock:
        _tasks[task_id] = task
    worker = threading.Thread(target=_run_proposal_task, args=(task_id, request), daemon=True)
    worker.start()
    return ProposalTaskCreatedResponse(task_id=task_id, status="queued")


def get_proposal_task(task_id: str) -> ProposalTaskResponse:
    _cleanup_expired_tasks()
    with _lock:
        task = _tasks.get(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Proposal task not found.")
        return _make_response(task_id, task)


def get_proposal_artifact(task_id: str, artifact_type: str) -> tuple[bytes, str, str]:
    """Return (content_bytes, media_type, filename) for the artifact."""
    with _lock:
        task = _tasks.get(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Proposal task not found.")
        if task["status"] != "succeeded":
            raise HTTPException(status_code=409, detail="Proposal task has not succeeded yet.")
        artifacts = task.get("artifacts", {})
        basename = artifacts.get("basename", "proposal")

    if artifact_type == "json":
        path = artifacts.get("json")
        if not path:
            raise HTTPException(status_code=404, detail="JSON artifact not found.")
        p = Path(path)
        if not p.exists() or not p.is_file():
            raise HTTPException(status_code=404, detail="JSON artifact is missing from disk.")
        with open(path, "rb") as f:
            content = f.read()
        return content, "application/json", f"{basename}.json"

    if artifact_type == "pptx":
        path = artifacts.get("pptx")
        if not path:
            raise HTTPException(status_code=404, detail="PPTX artifact not found.")
        p = Path(path)
        if not p.exists() or not p.is_file():
            raise HTTPException(status_code=404, detail="PPTX artifact is missing from disk.")
        with open(path, "rb") as f:
            content = f.read()
        return content, "application/vnd.openxmlformats-officedocument.presentationml.presentation", f"{basename}.pptx"

    if artifact_type == "hld_png":
        path = artifacts.get("hld_png")
        if not path:
            raise HTTPException(status_code=404, detail="HLD PNG artifact not found.")
        p = Path(path)
        if not p.exists() or not p.is_file():
            raise HTTPException(status_code=404, detail="HLD PNG artifact is missing from disk.")
        with open(path, "rb") as f:
            content = f.read()
        return content, "image/png", p.name

    if artifact_type == "hld_drawio":
        path = artifacts.get("hld_drawio")
        if not path:
            raise HTTPException(status_code=404, detail="HLD Drawio artifact not found.")
        p = Path(path)
        if not p.exists() or not p.is_file():
            raise HTTPException(status_code=404, detail="HLD Drawio artifact is missing from disk.")
        with open(path, "rb") as f:
            content = f.read()
        return content, "application/xml", p.name

    raise HTTPException(status_code=400, detail=f"Unknown artifact type: {artifact_type}")
