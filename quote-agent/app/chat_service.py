from __future__ import annotations

import json
import logging
import math
import os
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from typing import Any, Iterable

import httpx
import pandas as pd
from docx import Document
from pypdf import PdfReader

from app.models import (
    ChatMessage,
    ChatMessageRequest,
    ChatSessionCreatedResponse,
    ChatSessionResponse,
    ChatStreamEvent,
    ChatUploadResponse,
    ChatUploadedFile,
)
from app.web_search import SearchResult, WebSearchError, search_web_context

CHAT_INPUT_TOKEN_BUDGET = 160000
CHAT_UPLOAD_CHAR_CAP_PER_FILE = 20000
CHAT_UPLOAD_CHAR_CAP_TOTAL = 60000
CHAT_STREAM_DELTA_CHARS = 200
KB_FILE_1 = Path("/mnt/new-quota-agent/huawei_cloud_maas_faq_rag_en_zh.txt")
KB_FILE_2 = Path("/mnt/new-quota-agent/huawei_latam_smb_rag_2026-05-18.txt")

_lock = threading.Lock()
_sessions: dict[str, dict[str, Any]] = {}


@dataclass
class StoredUpload:
    public: ChatUploadedFile
    content: bytes
    extracted_text: str


_uploads: dict[str, StoredUpload] = {}
logger = logging.getLogger(__name__)


class ChatServiceError(RuntimeError):
    pass


class ChatConfigurationError(ChatServiceError):
    pass


class KnowledgeBaseError(ChatServiceError):
    pass


@dataclass(frozen=True)
class WebSearchPromptData:
    context: str
    results: list[SearchResult]
    failed: bool


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
            filename = str(item.get("filename") or "upload.bin")
            content = bytes(item.get("content") or b"")
            media_type = item.get("media_type")
            upload = ChatUploadedFile(
                file_id=str(uuid.uuid4()),
                filename=filename,
                size_bytes=len(content),
                media_type=media_type,
                created_at=_now_iso(),
            )
            extracted_text = extract_upload_text(filename=filename, content=content, media_type=media_type)
            _uploads[upload.file_id] = StoredUpload(public=upload, content=content, extracted_text=extracted_text)
            uploaded.append(upload)
    return ChatUploadResponse(files=uploaded)


def stream_chat(session_id: str, request: ChatMessageRequest) -> Iterable[str]:
    _persist_message(session_id, "user", request.message)
    try:
        web_search_data = build_web_search_prompt_data(request)
        prompt_messages = build_chat_messages(session_id, request, web_search_data=web_search_data)
        client = build_chat_client_from_env()
    except ChatServiceError as exc:
        yield _format_sse(ChatStreamEvent(event="error", session_id=session_id, error=str(exc)))
        return

    assistant_message_id = str(uuid.uuid4())
    yield _format_sse(ChatStreamEvent(event="message_start", session_id=session_id, message_id=assistant_message_id))

    collected = ""
    emitted_stream_chunk = False
    try:
        for chunk in client.stream_text(prompt_messages):
            emitted_stream_chunk = True
            if not chunk:
                continue
            collected += chunk
            yield _format_sse(
                ChatStreamEvent(
                    event="message_delta",
                    session_id=session_id,
                    message_id=assistant_message_id,
                    delta=chunk,
                )
            )
    except Exception as stream_exc:
        if emitted_stream_chunk:
            if collected:
                _persist_message(session_id, "assistant", collected)
            yield _format_sse(
                ChatStreamEvent(
                    event="error",
                    session_id=session_id,
                    message_id=assistant_message_id,
                    error=f"Upstream chat stream failed: {stream_exc}",
                )
            )
            return

        try:
            fallback_text = client.complete_text(prompt_messages)
            fallback_text = finalize_assistant_text(
                fallback_text,
                language=request.language,
                web_search_data=web_search_data,
            )
            for chunk in _chunk_text(fallback_text, CHAT_STREAM_DELTA_CHARS):
                collected += chunk
                yield _format_sse(
                    ChatStreamEvent(
                        event="message_delta",
                        session_id=session_id,
                        message_id=assistant_message_id,
                        delta=chunk,
                    )
                )
        except Exception as fallback_exc:
            if collected:
                _persist_message(session_id, "assistant", collected)
            yield _format_sse(
                ChatStreamEvent(
                    event="error",
                    session_id=session_id,
                    message_id=assistant_message_id,
                    error=f"Upstream chat request failed: {fallback_exc}",
                )
            )
            return

    finalized_text = finalize_assistant_text(
        collected,
        language=request.language,
        web_search_data=web_search_data,
    )
    if finalized_text != collected:
        suffix = finalized_text[len(collected):]
        for chunk in _chunk_text(suffix, CHAT_STREAM_DELTA_CHARS):
            yield _format_sse(
                ChatStreamEvent(
                    event="message_delta",
                    session_id=session_id,
                    message_id=assistant_message_id,
                    delta=chunk,
                )
            )
        collected = finalized_text

    _persist_message(session_id, "assistant", collected)
    yield _format_sse(ChatStreamEvent(event="message_end", session_id=session_id, message_id=assistant_message_id))


def build_chat_messages(
    session_id: str,
    request: ChatMessageRequest,
    *,
    token_budget: int = CHAT_INPUT_TOKEN_BUDGET,
    upload_char_cap_per_file: int = CHAT_UPLOAD_CHAR_CAP_PER_FILE,
    upload_char_cap_total: int = CHAT_UPLOAD_CHAR_CAP_TOTAL,
    web_search_data: WebSearchPromptData | None = None,
) -> list[dict[str, str]]:
    behavior_prompt = build_behavior_prompt(request.language)
    kb1 = load_knowledge_base(KB_FILE_1)
    kb2 = load_knowledge_base(KB_FILE_2)
    web_search_data = web_search_data or build_web_search_prompt_data(request)
    upload_context = build_upload_context(
        request.file_ids,
        per_file_cap=upload_char_cap_per_file,
        total_cap=upload_char_cap_total,
    )
    history = _history_for_prompt(session_id=session_id, current_message=request.message)

    messages: list[dict[str, str]] = [
        {"role": "system", "content": behavior_prompt},
        {"role": "system", "content": f"Knowledge Base 1: {KB_FILE_1.name}\n\n{kb1}"},
        {"role": "system", "content": f"Knowledge Base 2: {KB_FILE_2.name}\n\n{kb2}"},
    ]
    if web_search_data.context:
        messages.append({"role": "system", "content": web_search_data.context})
    elif web_search_data.failed:
        messages.append({"role": "system", "content": build_web_search_unavailable_instruction()})
    if upload_context:
        messages.append({"role": "system", "content": upload_context})

    current_user = {"role": "user", "content": request.message}
    static_messages = messages + [current_user]
    static_tokens = _estimate_messages_tokens(static_messages)
    upload_index = next((index for index, message in enumerate(messages) if message["content"].startswith("Uploaded file extracts:")), None)

    if static_tokens > token_budget and upload_index is not None:
        reserved_without_upload = _estimate_messages_tokens(
            [message for index, message in enumerate(messages) if index != upload_index] + [current_user]
        )
        allowed_upload_tokens = max(token_budget - reserved_without_upload, 0)
        if allowed_upload_tokens > 0:
            messages[upload_index]["content"] = _trim_text_to_token_budget(messages[upload_index]["content"], allowed_upload_tokens)
        else:
            messages.pop(upload_index)
        static_messages = messages + [current_user]

    remaining_tokens = max(token_budget - _estimate_messages_tokens(static_messages), 0)
    trimmed_history = _trim_history_messages(history, remaining_tokens)
    return messages + trimmed_history + [current_user]


def build_behavior_prompt(language: str) -> str:
    language_map = {
        "es": "The user language for this request is Spanish. Answer in Spanish unless the user explicitly asks for bilingual output.",
        "en": "The user language for this request is English. Answer in English unless the user explicitly asks for bilingual output.",
        "zh": "The user language for this request is Simplified Chinese. Answer in Simplified Chinese unless the user explicitly asks for bilingual output.",
    }
    language_instruction = language_map.get(language, language_map["en"])
    return (
        "You are a professional Huawei Cloud MaaS solution assistant.\n\n"
        "Your role is to answer questions about Huawei Cloud MaaS, Model as a Service, enterprise AI adoption, "
        "MaaS API integration, RAG, AI agents, AI coding, model routing, token cost optimization, security, "
        "governance, and pilot planning.\n\n"
        "You must answer based on the retrieved knowledge context first. If the retrieved context contains relevant "
        "FAQ IDs, use them as the primary source of truth.\n\n"
        "When live web search context is provided, treat it as supplementary evidence only after the knowledge base.\n"
        "Prefer official Huawei and Huawei Cloud sources over public web sources.\n"
        "If live web search context was used successfully, append a localized plain-text source section at the end:\n"
        '- English: "Sources:"\n'
        '- Spanish: "Fuentes:"\n'
        '- Chinese: "来源："\n'
        "List short titles or domains with URLs. Do not add a source section if live web search was unavailable.\n\n"
        "Core principles:\n\n"
        "1. Answer in the same language as the user.\n"
        "   - If the user asks in Chinese, answer in Chinese.\n"
        "   - If the user asks in English, answer in English.\n"
        "   - If the user asks for bilingual output, provide both English and Chinese.\n\n"
        "2. Be concise, professional, and customer-facing.\n"
        "   - Use clear business language.\n"
        "   - Avoid overly technical explanations unless the user asks for details.\n"
        "   - Put the conclusion first.\n"
        "   - Use bullet points when helpful.\n\n"
        "3. Stay grounded in the knowledge base.\n"
        "   - Do not invent unavailable model names, prices, regions, latency numbers, compliance commitments, or SLA promises.\n"
        "   - If the knowledge base does not contain enough information, say clearly:\n"
        "     \"This needs to be confirmed with the latest Huawei Cloud console, official documentation, contract, or local Huawei Cloud team.\"\n"
        "   - Do not pretend uncertain information is confirmed.\n\n"
        "4. Position Huawei Cloud MaaS correctly.\n"
        "   - Huawei Cloud MaaS should be positioned as an enterprise AI model supply layer.\n"
        "   - It is not only a model API.\n"
        "   - It helps enterprises add model diversity, token cost optimization, regional support, and governance.\n"
        "   - It should not be described as replacing OpenAI, Azure OpenAI, Anthropic, Google, or other model providers.\n"
        "   - The recommended positioning is: \"second AI model supply chain\" or \"additional model supply layer.\"\n\n"
        "5. Recommended messaging:\n"
        "   - Huawei Cloud MaaS helps enterprises build a second, scalable, and cost-efficient AI model supply chain.\n"
        "   - It enables faster AI application development, better token cost control, and stronger enterprise AI governance.\n"
        "   - It can stay behind the customer's existing AI platform, RAG system, AI agent platform, or model gateway.\n"
        "   - The goal is to enrich the model supply layer, not replace the customer-facing platform.\n\n"
        "6. When answering technical questions:\n"
        "   - Mention that MaaS can be accessed through APIs.\n"
        "   - If relevant, mention Python, cURL, and OpenAI-compatible API access.\n"
        "   - Explain that actual endpoint, model availability, region, pricing, and parameters must be confirmed in the Huawei Cloud console or with the local Huawei Cloud team.\n"
        "   - For integration, recommend a small API test before production use.\n\n"
        "7. When answering architecture questions:\n"
        "   - Use this reference architecture when relevant:\n"
        "     Enterprise application / AI agent / RAG system\n"
        "     -> model routing layer or MaaS gateway\n"
        "     -> Huawei Cloud MaaS and other model providers\n"
        "     -> monitoring, audit, quota, fallback, and cost management.\n"
        "   - Explain MaaS Gateway as the control layer for authentication, routing, quota, audit, caching, fallback, cost tracking, and policy enforcement.\n\n"
        "8. When answering security or compliance questions:\n"
        "   - Do not make absolute claims about data retention, no-training, zero data retention, or compliance certification unless retrieved context explicitly confirms it.\n"
        "   - Recommend confirming service terms, region, contract, and data processing terms.\n"
        "   - Suggest data minimization, masking, access control, audit logging, and human review for high-risk scenarios.\n\n"
        "9. When answering business or sales questions:\n"
        "   - Emphasize business value: model optionality, cost optimization, resilience, API-based adoption, faster pilots, and enterprise governance.\n"
        "   - For objections, use the following logic:\n"
        "     - \"We already use OpenAI/Azure OpenAI\": Keep using it. MaaS adds a second model supply chain for cost-sensitive, high-frequency, localized, benchmarking, and resilience scenarios.\n"
        "     - \"Model quality is more important than price\": Agree. Quality comes first. The right approach is task-by-task benchmarking, not blindly choosing the cheapest model.\n"
        "     - \"We do not want another AI platform\": MaaS does not need to be another front-end platform. It can stay behind the existing AI platform as a model supply layer.\n\n"
        "10. When recommending a pilot:\n"
        "   - Prefer low-risk, high-frequency, measurable scenarios.\n"
        "   - Good first scenarios include: AI coding, customer conversation summarization, intent classification, FAQ Q&A, document summarization, internal knowledge assistant, and RAG-based enterprise Q&A.\n"
        "   - Recommend a 30-day pilot:\n"
        "     Week 1: API access and technical validation.\n"
        "     Week 2: select two low-risk scenarios.\n"
        "     Week 3: benchmark cost, quality, and latency.\n"
        "     Week 4: executive review and next-step decision.\n\n"
        "11. When the user asks for a customer-ready answer:\n"
        "   - Use polished executive language.\n"
        "   - Avoid internal-only phrases unless the user asks for internal communication.\n"
        "   - Do not overclaim.\n"
        "   - Do not sound like generic AI marketing.\n"
        "   - Make the message specific to MaaS, model supply chain, token consumption, and enterprise AI governance.\n\n"
        "12. When the user asks for a short answer:\n"
        "   - Provide a direct answer in 3 to 5 bullets.\n"
        "   - Do not include long background explanations.\n\n"
        "13. When the user asks for a slide, email, proposal, FAQ, or script:\n"
        "   - Generate business-ready content.\n"
        "   - Use clear structure.\n"
        "   - Put the key message first.\n"
        "   - Keep wording professional, concise, and suitable for Huawei Cloud enterprise communication.\n\n"
        "14. Citation behavior:\n"
        "   - If the retrieved context includes FAQ IDs, cite the relevant FAQ IDs at the end of the answer, for example:\n"
        "     \"Reference: FAQ-009, FAQ-020, FAQ-055.\"\n"
        "   - If no FAQ ID is available, do not fabricate citations.\n\n"
        "Response style:\n"
        "- Professional\n"
        "- Clear\n"
        "- Concise\n"
        "- Enterprise-facing\n"
        "- Practical\n"
        "- No exaggerated claims\n"
        "- No unsupported commitments\n\n"
        "Default answer structure:\n"
        "1. Direct answer\n"
        "2. Key points\n"
        "3. Suggested next step\n"
        "4. Reference FAQ IDs, if available\n\n"
        f"{language_instruction}\n"
        "Return plain text only. Do not emit cards or structured blocks."
    )


def build_web_search_prompt_data(request: ChatMessageRequest) -> WebSearchPromptData:
    if not request.web_search_enabled:
        return WebSearchPromptData(context="", results=[], failed=False)
    try:
        context, results = search_web_context(request.message)
        logger.info(
            "web_search requested sessionless_query=%r status=ok result_count=%s",
            request.message[:120],
            len(results),
        )
        return WebSearchPromptData(context=context, results=results, failed=False)
    except WebSearchError as exc:
        logger.warning(
            "web_search requested sessionless_query=%r status=failed error=%s",
            request.message[:120],
            exc,
        )
        return WebSearchPromptData(context="", results=[], failed=True)


def build_web_search_prompt_context(request: ChatMessageRequest) -> tuple[str, list[SearchResult], bool]:
    data = build_web_search_prompt_data(request)
    return data.context, data.results, data.failed


def build_web_search_unavailable_instruction() -> str:
    return (
        "Live web search was requested for this turn, but the search backend was unavailable.\n"
        "Do not imply that external web verification succeeded.\n"
        "Answer from the knowledge base and uploaded files only.\n"
        "Do not include a Sources/Fuentes/来源 section."
    )


def finalize_assistant_text(text: str, *, language: str, web_search_data: WebSearchPromptData) -> str:
    finalized = text.rstrip()
    if web_search_data.failed:
        note = _localized_web_search_unavailable_note(language)
        if note not in finalized:
            finalized = f"{finalized}\n\n{note}" if finalized else note
        return finalized
    if not web_search_data.results:
        return finalized
    if _has_source_section(finalized):
        return finalized
    source_block = _format_sources_block(web_search_data.results, language=language)
    if not source_block:
        return finalized
    return f"{finalized}\n\n{source_block}" if finalized else source_block


def _has_source_section(text: str) -> bool:
    normalized = text.lower()
    return "sources:" in normalized or "fuentes:" in normalized or "来源：" in text or "来源:" in text


def _localized_web_search_unavailable_note(language: str) -> str:
    if language == "es":
        return "Nota: la búsqueda web en vivo no estuvo disponible en este turno; esta respuesta se basa solo en la base de conocimiento y los archivos cargados."
    if language == "zh":
        return "说明：本轮联网搜索暂时不可用，因此以上回答仅基于知识库和已上传文件。"
    return "Note: live web search was unavailable for this turn, so this answer is based only on the knowledge base and uploaded files."


def _localized_sources_heading(language: str) -> str:
    if language == "es":
        return "Fuentes:"
    if language == "zh":
        return "来源："
    return "Sources:"


def _format_sources_block(results: list[SearchResult], *, language: str) -> str:
    if not results:
        return ""
    lines = [_localized_sources_heading(language)]
    for result in results:
        host = _extract_host_for_display(result.url)
        lines.append(f"- {result.title} ({host})")
    return "\n".join(lines)


def _extract_host_for_display(url: str) -> str:
    try:
        return urlparse(url).hostname or url
    except Exception:
        return url


def load_knowledge_base(path: Path) -> str:
    try:
        return _load_knowledge_base_cached(str(path))
    except FileNotFoundError as exc:
        raise KnowledgeBaseError(f"Knowledge base file is missing: {path}") from exc


@lru_cache(maxsize=4)
def _load_knowledge_base_cached(path_str: str) -> str:
    path = Path(path_str)
    return path.read_text(encoding="utf-8")


def extract_upload_text(*, filename: str, content: bytes, media_type: str | None = None) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix == ".txt":
        return _decode_text(content)
    if suffix == ".csv":
        return _extract_csv_text(content)
    if suffix == ".xlsx":
        return _extract_xlsx_text(content)
    if suffix == ".pdf":
        return _extract_pdf_text(content)
    if suffix == ".docx":
        return _extract_docx_text(content)
    if suffix == ".doc":
        return "legacy .doc not supported for direct extraction; only filename available"
    if media_type and media_type.startswith("text/"):
        return _decode_text(content)
    return "Binary file uploaded. No direct text extraction is available for this file type."


def build_upload_context(
    file_ids: list[str],
    *,
    per_file_cap: int = CHAT_UPLOAD_CHAR_CAP_PER_FILE,
    total_cap: int = CHAT_UPLOAD_CHAR_CAP_TOTAL,
) -> str:
    remaining = total_cap
    sections: list[str] = []
    with _lock:
        records = [record for file_id in file_ids if (record := _uploads.get(file_id))]
    for index, record in enumerate(records, start=1):
        if remaining <= 0:
            break
        excerpt = record.extracted_text
        excerpted = False
        if len(excerpt) > per_file_cap:
            excerpt = excerpt[:per_file_cap].rstrip()
            excerpted = True
        if len(excerpt) > remaining:
            excerpt = excerpt[:remaining].rstrip()
            excerpted = True
        remaining -= len(excerpt)
        suffix = Path(record.public.filename).suffix.lower() or "unknown"
        note = " (excerpted)" if excerpted else ""
        sections.append(
            f"Uploaded file {index}: {record.public.filename} [{suffix}, {record.public.media_type or 'unknown'}]{note}\n{excerpt}"
        )
    if not sections:
        return ""
    return "Uploaded file extracts:\n\n" + "\n\n".join(sections)


def _history_for_prompt(session_id: str, current_message: str) -> list[dict[str, str]]:
    session = get_chat_session(session_id)
    if session is None:
        return []
    messages = list(session.messages)
    if messages and messages[-1].role == "user" and messages[-1].text == current_message:
        messages = messages[:-1]
    return [{"role": item.role, "content": item.text} for item in messages if item.text]


def _trim_history_messages(history: list[dict[str, str]], remaining_tokens: int) -> list[dict[str, str]]:
    kept: list[dict[str, str]] = []
    used = 0
    for message in reversed(history):
        cost = _estimate_messages_tokens([message])
        if used + cost > remaining_tokens:
            continue
        kept.append(message)
        used += cost
    kept.reverse()
    return kept


def _persist_message(session_id: str, role: str, text: str) -> ChatMessage:
    message = ChatMessage(
        message_id=str(uuid.uuid4()),
        role=role,
        text=text,
        blocks=[],
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


def _estimate_messages_tokens(messages: list[dict[str, str]]) -> int:
    total_chars = sum(len(message.get("content", "")) for message in messages)
    return math.ceil(total_chars / 4) + (len(messages) * 8)


def _trim_text_to_token_budget(text: str, token_budget: int) -> str:
    char_budget = max((token_budget - 8) * 4, 0)
    if len(text) <= char_budget:
        return text
    if char_budget <= 64:
        return text[:char_budget]
    return text[: char_budget - 28].rstrip() + "\n\n[excerpted due to budget]"


def _decode_text(content: bytes) -> str:
    for encoding in ("utf-8", "utf-8-sig"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="replace")


def _extract_csv_text(content: bytes) -> str:
    frame = pd.read_csv(BytesIO(content), dtype=str, keep_default_na=False)
    return _dataframe_to_compact_text(frame, title="CSV")


def _extract_xlsx_text(content: bytes) -> str:
    sheets: list[str] = []
    with pd.ExcelFile(BytesIO(content)) as workbook:
        for sheet_name in workbook.sheet_names:
            frame = pd.read_excel(workbook, sheet_name=sheet_name, dtype=str).fillna("")
            sheets.append(_dataframe_to_compact_text(frame, title=f"Sheet: {sheet_name}"))
    return "\n\n".join(sheets) if sheets else "Excel workbook contains no readable sheets."


def _extract_pdf_text(content: bytes) -> str:
    reader = PdfReader(BytesIO(content))
    fragments: list[str] = []
    for page in reader.pages:
        page_text = (page.extract_text() or "").strip()
        if page_text:
            fragments.append(page_text)
    if not fragments:
        return "PDF may be scanned or image-based; no direct text could be extracted."
    return "\n\n".join(fragments)


def _extract_docx_text(content: bytes) -> str:
    document = Document(BytesIO(content))
    paragraphs = [paragraph.text.strip() for paragraph in document.paragraphs if paragraph.text.strip()]
    table_rows: list[str] = []
    for table in document.tables:
        for row in table.rows:
            values = [cell.text.strip() for cell in row.cells if cell.text.strip()]
            if values:
                table_rows.append(" | ".join(values))
    if not paragraphs and not table_rows:
        return "DOCX document contains no readable paragraph or table text."
    return "\n".join(paragraphs + table_rows)


def _dataframe_to_compact_text(frame: pd.DataFrame, *, title: str) -> str:
    columns = [str(column) for column in frame.columns.tolist()]
    lines = [title, f"Columns: {', '.join(columns) if columns else '(none)'}"]
    preview = frame.head(10).fillna("")
    if preview.empty:
        lines.append("Rows: (none)")
        return "\n".join(lines)
    lines.append("Rows:")
    for _, row in preview.iterrows():
        cells = [f"{column}={str(row[column]).strip()}" for column in preview.columns]
        lines.append("- " + " | ".join(cells))
    return "\n".join(lines)


class ChatCompletionsClient:
    def __init__(self, *, api_key: str, base_url: str, model: str, timeout: float = 60.0) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _payload(self, messages: list[dict[str, str]], *, stream: bool) -> dict[str, Any]:
        return {
            "model": self.model,
            "temperature": 0.2,
            "stream": stream,
            "messages": messages,
        }

    def stream_text(self, messages: list[dict[str, str]]) -> Iterable[str]:
        with httpx.Client(timeout=self.timeout) as client:
            with client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                headers=self._headers(),
                json=self._payload(messages, stream=True),
            ) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    payload = json.loads(data)
                    choices = payload.get("choices") or []
                    if not choices:
                        continue
                    delta = choices[0].get("delta") or {}
                    text = _normalize_upstream_content(delta.get("content"))
                    if text:
                        yield text

    def complete_text(self, messages: list[dict[str, str]]) -> str:
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(
                f"{self.base_url}/chat/completions",
                headers=self._headers(),
                json=self._payload(messages, stream=False),
            )
            response.raise_for_status()
            payload = response.json()
        choices = payload.get("choices") or []
        if not choices:
            return ""
        message = choices[0].get("message") or {}
        return _normalize_upstream_content(message.get("content"))


def build_chat_client_from_env(*, timeout: float | None = None) -> ChatCompletionsClient:
    api_key = os.getenv("HUAWEI_MAAS_API_KEY")
    base_url = os.getenv("HUAWEI_MAAS_BASE_URL")
    model = os.getenv("HUAWEI_MAAS_MODEL")
    missing = [name for name, value in {
        "HUAWEI_MAAS_API_KEY": api_key,
        "HUAWEI_MAAS_BASE_URL": base_url,
        "HUAWEI_MAAS_MODEL": model,
    }.items() if not value]
    if missing:
        raise ChatConfigurationError(f"Missing MaaS chat configuration: {', '.join(missing)}")
    effective_timeout = timeout if timeout is not None else 60.0
    return ChatCompletionsClient(
        api_key=api_key,
        base_url=base_url,
        model=model,
        timeout=effective_timeout,
    )


def _normalize_upstream_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                if isinstance(item.get("text"), str):
                    parts.append(item["text"])
                elif item.get("type") == "output_text" and isinstance(item.get("content"), str):
                    parts.append(item["content"])
        return "".join(parts)
    return ""


def _chunk_text(text: str, size: int) -> list[str]:
    return [text[index : index + size] for index in range(0, len(text), size)] or [text]


def _format_sse(event: ChatStreamEvent) -> str:
    payload = json.dumps(event.model_dump(exclude_none=True), ensure_ascii=False)
    return f"event: {event.event}\ndata: {payload}\n\n"


def _reset_chat_state_for_tests() -> None:
    with _lock:
        _sessions.clear()
        _uploads.clear()
    _load_knowledge_base_cached.cache_clear()
