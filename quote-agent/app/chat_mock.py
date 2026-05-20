from __future__ import annotations

import json
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Iterable

from app.models import (
    ChatCardAction,
    ChatMessage,
    ChatMessageBlock,
    ChatMessageRequest,
    ChatSessionCreatedResponse,
    ChatSessionResponse,
    ChatStreamEvent,
    ChatUploadResponse,
    ChatUploadedFile,
)

_lock = threading.Lock()
_sessions: dict[str, dict[str, Any]] = {}
_uploads: dict[str, ChatUploadedFile] = {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_chat_session() -> ChatSessionCreatedResponse:
    session_id = str(uuid.uuid4())
    now = _now_iso()
    with _lock:
        _sessions[session_id] = {
            "session_id": session_id,
            "status": "active",
            "messages": [],
            "created_at": now,
            "updated_at": now,
        }
    return ChatSessionCreatedResponse(session_id=session_id, status="active", created_at=now)


def get_chat_session(session_id: str) -> ChatSessionResponse | None:
    with _lock:
        session = _sessions.get(session_id)
        if not session:
            return None
        return ChatSessionResponse.model_validate(session)


def register_uploads(files: list[dict[str, Any]]) -> ChatUploadResponse:
    uploaded: list[ChatUploadedFile] = []
    with _lock:
        for item in files:
            file_id = str(uuid.uuid4())
            upload = ChatUploadedFile(
                file_id=file_id,
                filename=str(item.get("filename") or "upload.bin"),
                size_bytes=len(item.get("content") or b""),
                media_type=item.get("media_type"),
                created_at=_now_iso(),
            )
            _uploads[file_id] = upload
            uploaded.append(upload)
    return ChatUploadResponse(files=uploaded)


def _route_solution_card(title: str, body: str, route: str, image_url: str | None = None, tags: list[str] | None = None) -> ChatMessageBlock:
    return ChatMessageBlock(
        block_type="solution_card",
        title=title,
        body=body,
        route=route,
        image_url=image_url,
        tags=tags or [],
        action=ChatCardAction(label="Open solution", action_type="open_route", target=route),
    )


def _route_pricing_card(title: str, body: str, route: str, tags: list[str] | None = None) -> ChatMessageBlock:
    return ChatMessageBlock(
        block_type="pricing_card",
        title=title,
        body=body,
        route=route,
        tags=tags or [],
        action=ChatCardAction(label="Open workflow", action_type="open_route", target=route),
    )


def _uploaded_files(file_ids: list[str]) -> list[ChatUploadedFile]:
    with _lock:
        return [upload for file_id in file_ids if (upload := _uploads.get(file_id))]


def _mock_answer_payload(request: ChatMessageRequest) -> tuple[str, list[ChatMessageBlock]]:
    prompt = request.message.strip()
    normalized = prompt.lower()
    uploads = _uploaded_files(request.file_ids)
    upload_note = ""
    if uploads:
        names = ", ".join(item.filename for item in uploads[:3])
        upload_note = f" I also received: {names}."

    blocks: list[ChatMessageBlock] = []

    if any(token in normalized for token in ["rvtools", "quote", "pricing", "excel", "estimator"]):
        text = (
            "I can guide the customer into the most suitable quote workflow based on the input format. "
            "For VMware migration assessment, the RVTools quote flow is the most direct path. "
            "For customer-created comparison or procurement spreadsheets, the Flexible Quote flow is the better fit."
            f"{upload_note}"
        )
        blocks.extend(
            [
                _route_pricing_card(
                    "RVTools Quote",
                    "Use this when the customer provides an RVTools export and needs ECS/EVS sizing and pricing.",
                    "#/estimator?mode=rvtools",
                    ["Migration", "RVTools", "ECS/EVS"],
                ),
                _route_pricing_card(
                    "Flexible Quote",
                    "Use this when the customer provides an arbitrary Excel workbook and needs row-level Huawei quotation guidance.",
                    "#/estimator?mode=flexible",
                    ["Workbook", "Excel", "Quotation"],
                ),
            ]
        )
        return text, blocks

    if any(token in normalized for token in ["pathology", "hospital", "medical", "imaging", "radiology"]):
        text = (
            "For healthcare customers, the most relevant content is the enterprise medical imaging and digital pathology solution set. "
            "These pages describe deployment models, hospital workflows, and Huawei infrastructure positioning rather than generic cloud services."
        )
        blocks.extend(
            [
                _route_solution_card(
                    "AI-Assisted Medical Imaging",
                    "Hospital imaging workflow with Huawei AI Server, all-flash storage, partner AI applications, and PACS integration.",
                    "#/solutions/ai-medical-imaging",
                    "/assets/huawei/enterprise-healthcare/medical-imaging-banner.jpg",
                    ["Healthcare", "AI Imaging", "Enterprise"],
                ),
                _route_solution_card(
                    "Digital Pathology",
                    "On-prem digital pathology deployment with AI computing nodes, layered slide retrieval, and all-flash storage.",
                    "#/solutions/digital-pathology",
                    "/assets/huawei/enterprise-healthcare/digital-pathology-banner.jpg",
                    ["Healthcare", "Pathology", "Enterprise"],
                ),
            ]
        )
        return text, blocks

    if any(token in normalized for token in ["wifi", "wlan", "branch", "campus", "network"]):
        text = (
            "For branch, campus, or public-sector connectivity, the Enterprise entry is the best starting point. "
            "From there, the WLAN scenario can be expanded with deployment scope, user density, and security requirements."
        )
        blocks.append(
            _route_solution_card(
                "Enterprise WLAN",
                "Huawei enterprise WLAN solution entry for campus and branch connectivity scenarios.",
                "#/solutions?entry=enterprise",
                "/assets/huawei/official-cache/enterprise-wlan-banner.jpg",
                ["Enterprise", "WLAN", "Connectivity"],
            )
        )
        return text, blocks

    text = (
        "I can help translate business needs into Huawei solutions, pricing workflows, and next-step actions. "
        "A typical conversation can cover AI assistants, migration planning, IT modernization, healthcare solutions, or quotation guidance."
        f"{upload_note}"
    )
    blocks.extend(
        [
            _route_solution_card(
                "AI Assistants and Smarter Workflows",
                "Customer service, knowledge assistant, and analytics scenarios for SMB transformation.",
                "#/solutions?entry=ai-maas",
                "/assets/huawei/hero-maas.jpg",
                ["AI", "Assistants", "SMB"],
            ),
            _route_solution_card(
                "Modernize IT Foundations",
                "Infrastructure modernization, backup, DR, VMware, and ERP/SAP foundation scenarios.",
                "#/solutions?entry=on-prem-to-cloud",
                "/assets/huawei/flexus.jpg",
                ["Infrastructure", "Modernization", "SMB"],
            ),
            _route_pricing_card(
                "Quotation Workflows",
                "Open the quotation workspace for RVTools-based or workbook-based customer pricing support.",
                "#/estimator",
                ["Quote", "Pricing", "Workflow"],
            ),
        ]
    )
    return text, blocks


def _persist_message(session_id: str, role: str, text: str, blocks: list[ChatMessageBlock]) -> ChatMessage:
    message = ChatMessage(
        message_id=str(uuid.uuid4()),
        role=role,
        text=text,
        blocks=blocks,
        created_at=_now_iso(),
    )
    with _lock:
        session = _sessions.get(session_id)
        if session is None:
            now = _now_iso()
            session = {
                "session_id": session_id,
                "status": "active",
                "messages": [],
                "created_at": now,
                "updated_at": now,
            }
            _sessions[session_id] = session
        session["messages"].append(message.model_dump())
        session["updated_at"] = _now_iso()
    return message


def stream_mock_chat(session_id: str, request: ChatMessageRequest) -> Iterable[str]:
    _persist_message(session_id, "user", request.message, [])

    assistant_text, blocks = _mock_answer_payload(request)
    assistant_message = ChatMessage(
        message_id=str(uuid.uuid4()),
        role="assistant",
        text=assistant_text,
        blocks=blocks,
        created_at=_now_iso(),
    )

    start_event = ChatStreamEvent(event="message_start", session_id=session_id, message_id=assistant_message.message_id)
    yield _format_sse(start_event)

    for chunk in _chunk_text(assistant_text, 42):
        delta_event = ChatStreamEvent(
            event="message_delta",
            session_id=session_id,
            message_id=assistant_message.message_id,
            delta=chunk,
        )
        yield _format_sse(delta_event)
        time.sleep(0.03)

    for block in blocks:
        block_event = ChatStreamEvent(
            event="message_block",
            session_id=session_id,
            message_id=assistant_message.message_id,
            block=block,
        )
        yield _format_sse(block_event)

    _persist_message(session_id, "assistant", assistant_text, blocks)
    end_event = ChatStreamEvent(event="message_end", session_id=session_id, message_id=assistant_message.message_id)
    yield _format_sse(end_event)


def _chunk_text(text: str, size: int) -> list[str]:
    return [text[index : index + size] for index in range(0, len(text), size)] or [text]


def _format_sse(event: ChatStreamEvent) -> str:
    payload = json.dumps(event.model_dump(exclude_none=True), ensure_ascii=False)
    return f"event: {event.event}\ndata: {payload}\n\n"
