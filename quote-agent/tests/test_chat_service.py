from __future__ import annotations

import json
from io import BytesIO

import pandas as pd
import pytest
from docx import Document
from fastapi.testclient import TestClient
from pypdf import PdfWriter

import app.chat_service as chat_service
import app.web_search as web_search
from app.main import app


class FakeChatClient:
    def __init__(self, *, stream_chunks=None, stream_error: Exception | None = None, fallback_text: str = "") -> None:
        self.stream_chunks = stream_chunks or []
        self.stream_error = stream_error
        self.fallback_text = fallback_text
        self.calls: list[list[dict[str, str]]] = []

    def stream_text(self, messages: list[dict[str, str]]):
        self.calls.append(messages)
        if self.stream_error is not None:
            raise self.stream_error
        for chunk in self.stream_chunks:
            yield chunk

    def complete_text(self, messages: list[dict[str, str]]) -> str:
        self.calls.append(messages)
        if isinstance(self.stream_error, RuntimeError) and self.fallback_text == "":
            raise RuntimeError("fallback failed")
        return self.fallback_text


@pytest.fixture(autouse=True)
def reset_chat_state(monkeypatch: pytest.MonkeyPatch):
    chat_service._reset_chat_state_for_tests()
    monkeypatch.setenv("HUAWEI_MAAS_API_KEY", "test-key")
    monkeypatch.setenv("HUAWEI_MAAS_BASE_URL", "https://maas.example.com/openai/v1")
    monkeypatch.setenv("HUAWEI_MAAS_MODEL", "deepseek-v3.2")
    yield
    chat_service._reset_chat_state_for_tests()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _parse_sse_events(text: str) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    for block in text.strip().split("\n\n"):
        payload_line = next(line for line in block.splitlines() if line.startswith("data: "))
        events.append(json.loads(payload_line[6:]))
    return events


def _make_csv_bytes() -> bytes:
    frame = pd.DataFrame([{"service": "ECS", "region": "mexico"}, {"service": "EVS", "region": "brazil"}])
    return frame.to_csv(index=False).encode("utf-8")


def _make_xlsx_bytes() -> bytes:
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
        pd.DataFrame([{"service": "CCI", "region": "mexico"}]).to_excel(writer, sheet_name="Sizing", index=False)
    return buffer.getvalue()


def _make_docx_bytes(with_text: bool = True) -> bytes:
    document = Document()
    if with_text:
        document.add_paragraph("Customer wants Huawei migration guidance.")
        table = document.add_table(rows=1, cols=2)
        table.rows[0].cells[0].text = "Region"
        table.rows[0].cells[1].text = "Mexico"
    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def _make_blank_pdf() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def test_chat_stream_sse_and_persistence(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    fake = FakeChatClient(stream_chunks=["Hola ", "mundo"])
    monkeypatch.setattr(chat_service, "build_chat_client_from_env", lambda: fake)

    session_id = client.post("/api/chat/sessions").json()["session_id"]
    response = client.post(
        f"/api/chat/sessions/{session_id}/messages/stream",
        json={"message": "Necesito una recomendacion", "language": "es", "file_ids": [], "web_search_enabled": False},
    )
    assert response.status_code == 200

    events = _parse_sse_events(response.text)
    assert [event["event"] for event in events] == ["message_start", "message_delta", "message_delta", "message_end"]

    session = client.get(f"/api/chat/sessions/{session_id}").json()
    assert [message["role"] for message in session["messages"]] == ["user", "assistant"]
    assert session["messages"][1]["text"] == "Hola mundo"
    assert session["messages"][1]["blocks"] == []


def test_chat_prompt_includes_kbs_uploads_language_and_recent_history(monkeypatch: pytest.MonkeyPatch):
    chat_service.create_chat_session()
    session = chat_service.create_chat_session()
    session_id = session.session_id

    upload_response = chat_service.register_uploads(
        [
            {"filename": "notes.txt", "content": b"alpha guidance", "media_type": "text/plain"},
            {"filename": "legacy.doc", "content": b"legacy", "media_type": "application/msword"},
        ]
    )
    chat_service._persist_message(session_id, "user", "older question")
    chat_service._persist_message(session_id, "assistant", "older answer")
    chat_service._persist_message(session_id, "user", "latest prompt")

    messages = chat_service.build_chat_messages(
        session_id,
        chat_service.ChatMessageRequest(
            message="latest prompt",
            language="zh",
            file_ids=[item.file_id for item in upload_response.files],
            web_search_enabled=False,
        ),
    )

    assert messages[0]["role"] == "system"
    assert "Huawei Cloud MaaS solution assistant" in messages[0]["content"]
    assert "Simplified Chinese" in messages[0]["content"]
    assert messages[1]["content"].startswith("Knowledge Base 1:")
    assert messages[2]["content"].startswith("Knowledge Base 2:")
    assert messages[3]["content"].startswith("Uploaded file extracts:")
    assert "notes.txt" in messages[3]["content"]
    assert "legacy .doc not supported for direct extraction" in messages[3]["content"]
    assert messages[-3]["content"] == "older question"
    assert messages[-2]["content"] == "older answer"
    assert messages[-1] == {"role": "user", "content": "latest prompt"}


def test_chat_history_trimming_keeps_recent_messages(monkeypatch: pytest.MonkeyPatch):
    session_id = chat_service.create_chat_session().session_id
    monkeypatch.setattr(chat_service, "load_knowledge_base", lambda path: "kb")
    monkeypatch.setattr(chat_service, "build_behavior_prompt", lambda language: "short prompt")
    for index in range(8):
        chat_service._persist_message(session_id, "user", f"user-{index}-" + ("x" * 120))
        chat_service._persist_message(session_id, "assistant", f"assistant-{index}-" + ("y" * 120))
    chat_service._persist_message(session_id, "user", "current")

    messages = chat_service.build_chat_messages(
        session_id,
        chat_service.ChatMessageRequest(message="current", language="en", file_ids=[], web_search_enabled=False),
        token_budget=700,
    )

    history_contents = [message["content"] for message in messages[3:-1]]
    assert "assistant-7" in history_contents[-1]
    assert not any("user-0" in content for content in history_contents)


def test_upload_extractors_cover_txt_csv_xlsx_pdf_docx_doc():
    txt = chat_service.extract_upload_text(filename="sample.txt", content="hola".encode("utf-8"), media_type="text/plain")
    csv = chat_service.extract_upload_text(filename="sample.csv", content=_make_csv_bytes(), media_type="text/csv")
    xlsx = chat_service.extract_upload_text(
        filename="sample.xlsx",
        content=_make_xlsx_bytes(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    pdf = chat_service.extract_upload_text(filename="blank.pdf", content=_make_blank_pdf(), media_type="application/pdf")
    docx = chat_service.extract_upload_text(
        filename="sample.docx",
        content=_make_docx_bytes(with_text=True),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    doc = chat_service.extract_upload_text(filename="legacy.doc", content=b"legacy", media_type="application/msword")

    assert txt == "hola"
    assert "Columns: service, region" in csv
    assert "Sheet: Sizing" in xlsx
    assert "PDF may be scanned or image-based" in pdf
    assert "Customer wants Huawei migration guidance." in docx
    assert "legacy .doc not supported" in doc


def test_upload_context_truncates_large_files():
    large_text = ("A" * 25000).encode("utf-8")
    uploads = chat_service.register_uploads([{"filename": "big.txt", "content": large_text, "media_type": "text/plain"}])
    context = chat_service.build_upload_context([uploads.files[0].file_id], per_file_cap=100, total_cap=100)
    assert "(excerpted)" in context
    assert len(context) < 300


def test_missing_configuration_returns_error_event(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("HUAWEI_MAAS_API_KEY")
    session_id = client.post("/api/chat/sessions").json()["session_id"]
    response = client.post(
        f"/api/chat/sessions/{session_id}/messages/stream",
        json={"message": "hello", "language": "en", "file_ids": [], "web_search_enabled": False},
    )
    events = _parse_sse_events(response.text)
    assert events[0]["event"] == "error"
    assert "Missing MaaS chat configuration" in events[0]["error"]


def test_missing_knowledge_base_returns_error_event(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(chat_service, "KB_FILE_1", chat_service.Path("/tmp/does-not-exist-chat-kb.txt"))
    session_id = client.post("/api/chat/sessions").json()["session_id"]
    response = client.post(
        f"/api/chat/sessions/{session_id}/messages/stream",
        json={"message": "hello", "language": "en", "file_ids": [], "web_search_enabled": False},
    )
    events = _parse_sse_events(response.text)
    assert events[0]["event"] == "error"
    assert "Knowledge base file is missing" in events[0]["error"]


def test_stream_failure_falls_back_to_non_stream(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    fake = FakeChatClient(stream_error=RuntimeError("stream unavailable"), fallback_text="fallback answer")
    monkeypatch.setattr(chat_service, "build_chat_client_from_env", lambda: fake)
    session_id = client.post("/api/chat/sessions").json()["session_id"]

    response = client.post(
        f"/api/chat/sessions/{session_id}/messages/stream",
        json={"message": "hello", "language": "en", "file_ids": [], "web_search_enabled": False},
    )

    events = _parse_sse_events(response.text)
    assert [event["event"] for event in events] == ["message_start", "message_delta", "message_end"]
    assert events[1]["delta"] == "fallback answer"


def test_partial_stream_failure_emits_error_and_persists_partial(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    class PartialClient(FakeChatClient):
        def stream_text(self, messages: list[dict[str, str]]):
            self.calls.append(messages)
            yield "partial "
            raise RuntimeError("boom")

    monkeypatch.setattr(chat_service, "build_chat_client_from_env", lambda: PartialClient())
    session_id = client.post("/api/chat/sessions").json()["session_id"]

    response = client.post(
        f"/api/chat/sessions/{session_id}/messages/stream",
        json={"message": "hello", "language": "en", "file_ids": [], "web_search_enabled": False},
    )

    events = _parse_sse_events(response.text)
    assert [event["event"] for event in events] == ["message_start", "message_delta", "error"]

    session = client.get(f"/api/chat/sessions/{session_id}").json()
    assert session["messages"][-1]["role"] == "assistant"
    assert session["messages"][-1]["text"] == "partial "


def test_chat_prompt_includes_web_search_context_in_correct_order(monkeypatch: pytest.MonkeyPatch):
    session_id = chat_service.create_chat_session().session_id
    monkeypatch.setattr(chat_service, "load_knowledge_base", lambda path: "kb")
    monkeypatch.setattr(
        chat_service,
        "build_web_search_prompt_context",
        lambda request: ("Web search context:\n\n1. Official result", [], False),
    )
    uploads = chat_service.register_uploads([{"filename": "notes.txt", "content": b"upload text", "media_type": "text/plain"}])
    chat_service._persist_message(session_id, "user", "older question")
    chat_service._persist_message(session_id, "assistant", "older answer")
    chat_service._persist_message(session_id, "user", "current question")

    messages = chat_service.build_chat_messages(
        session_id,
        chat_service.ChatMessageRequest(
            message="current question",
            language="en",
            file_ids=[uploads.files[0].file_id],
            web_search_enabled=True,
        ),
    )

    assert messages[0]["content"].startswith("You are a professional Huawei Cloud MaaS solution assistant.")
    assert messages[1]["content"].startswith("Knowledge Base 1:")
    assert messages[2]["content"].startswith("Knowledge Base 2:")
    assert messages[3]["content"].startswith("Web search context:")
    assert messages[4]["content"].startswith("Uploaded file extracts:")
    assert messages[-3]["content"] == "older question"
    assert messages[-2]["content"] == "older answer"
    assert messages[-1] == {"role": "user", "content": "current question"}


def test_chat_prompt_omits_web_search_when_disabled(monkeypatch: pytest.MonkeyPatch):
    session_id = chat_service.create_chat_session().session_id
    monkeypatch.setattr(chat_service, "load_knowledge_base", lambda path: "kb")

    messages = chat_service.build_chat_messages(
        session_id,
        chat_service.ChatMessageRequest(message="hello", language="en", file_ids=[], web_search_enabled=False),
    )

    assert len(messages) == 4
    assert all("Web search context:" not in message["content"] for message in messages)


def test_search_official_first_falls_back_when_official_results_are_weak():
    class FakeSearchClient:
        def __init__(self) -> None:
            self.queries: list[str] = []

        def search(self, query: str) -> list[web_search.SearchResult]:
            self.queries.append(query)
            if len(self.queries) == 1:
                return [
                    web_search.SearchResult(
                        title="Community thread",
                        url="https://example.com/community",
                        engine="duckduckgo",
                        snippet="Some non-official result.",
                    )
                ]
            return [
                web_search.SearchResult(
                    title="Huawei Cloud CCI Pricing",
                    url="https://support.huaweicloud.com/intl/en-us/productdesc-cci/cci_01_0001.html",
                    engine="google",
                    snippet="Official Huawei Cloud documentation.",
                ),
                web_search.SearchResult(
                    title="Huawei Cloud CCI Overview",
                    url="https://www.huaweicloud.com/intl/en-us/product/cci.html",
                    engine="google",
                    snippet="Official overview page.",
                ),
            ]

    client = FakeSearchClient()
    context, results = web_search.search_web_context("Huawei CCI pricing", client=client)

    assert len(client.queries) == 2
    assert "site:huaweicloud.com" in client.queries[0]
    assert client.queries[1] == "Huawei CCI pricing"
    assert context.startswith("Web search context:")
    assert any("huaweicloud.com" in result.url for result in results)


def test_search_context_is_trimmed_to_limits():
    results = [
        web_search.SearchResult(
            title="Long snippet",
            url="https://www.huaweicloud.com/example",
            engine="google",
            snippet="x" * 500,
        ),
        web_search.SearchResult(
            title="Second result",
            url="https://support.huaweicloud.com/example",
            engine="google",
            snippet="y" * 500,
        ),
    ]

    context = web_search.format_search_context(results, snippet_char_cap=50, total_char_cap=220)

    assert len(context) <= 220
    assert "..." in context


def test_web_search_failure_degrades_gracefully(monkeypatch: pytest.MonkeyPatch):
    session_id = chat_service.create_chat_session().session_id
    monkeypatch.setattr(chat_service, "load_knowledge_base", lambda path: "kb")
    monkeypatch.setattr(
        chat_service,
        "build_web_search_prompt_data",
        lambda request: chat_service.WebSearchPromptData(context="", results=[], failed=True),
    )

    messages = chat_service.build_chat_messages(
        session_id,
        chat_service.ChatMessageRequest(message="verify this", language="en", file_ids=[], web_search_enabled=True),
    )

    assert messages[3]["content"].startswith("Live web search was requested for this turn")
    assert "Do not include a Sources/Fuentes/来源 section." in messages[3]["content"]


def test_chat_stream_with_web_search_toggle_on_preserves_sse_and_persists_sources(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    fake = FakeChatClient(stream_chunks=["Answer from search"])
    monkeypatch.setattr(chat_service, "build_chat_client_from_env", lambda: fake)
    monkeypatch.setattr(
        chat_service,
        "build_web_search_prompt_data",
        lambda request: chat_service.WebSearchPromptData(
            context="Web search context:\n\n1. Huawei Cloud",
            results=[
                web_search.SearchResult(
                    title="Huawei Cloud",
                    url="https://www.huaweicloud.com",
                    engine="google",
                    snippet="Official site.",
                )
            ],
            failed=False,
        ),
    )

    session_id = client.post("/api/chat/sessions").json()["session_id"]
    response = client.post(
        f"/api/chat/sessions/{session_id}/messages/stream",
        json={"message": "Find Huawei Cloud pricing", "language": "en", "file_ids": [], "web_search_enabled": True},
    )

    assert response.status_code == 200
    events = _parse_sse_events(response.text)
    assert [event["event"] for event in events] == ["message_start", "message_delta", "message_delta", "message_end"]

    session = client.get(f"/api/chat/sessions/{session_id}").json()
    assert "Sources:" in session["messages"][-1]["text"]


def test_chat_stream_with_web_search_failure_persists_unavailable_note(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    fake = FakeChatClient(stream_chunks=["Answer without live search"])
    monkeypatch.setattr(chat_service, "build_chat_client_from_env", lambda: fake)
    monkeypatch.setattr(
        chat_service,
        "build_web_search_prompt_data",
        lambda request: chat_service.WebSearchPromptData(context="", results=[], failed=True),
    )

    session_id = client.post("/api/chat/sessions").json()["session_id"]
    response = client.post(
        f"/api/chat/sessions/{session_id}/messages/stream",
        json={"message": "Find Huawei Cloud pricing", "language": "en", "file_ids": [], "web_search_enabled": True},
    )

    assert response.status_code == 200
    session = client.get(f"/api/chat/sessions/{session_id}").json()
    assert "live web search was unavailable for this turn" in session["messages"][-1]["text"]


def test_empty_docx_reports_degraded_extraction():
    text = chat_service.extract_upload_text(
        filename="empty.docx",
        content=_make_docx_bytes(with_text=False),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    assert "contains no readable paragraph or table text" in text
