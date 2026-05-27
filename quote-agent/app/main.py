from __future__ import annotations

from fastapi import Body, FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse, Response, StreamingResponse

from app.chat_service import create_chat_session, get_chat_session, register_uploads, stream_chat
from app.flexible_preview_tasks import create_preview_task, get_preview_task
from app.hld_tasks import create_hld_design_task, get_hld_design_artifact, get_hld_design_task
from app.hld_recommend import get_recommendation
from app.proposal_tasks import create_proposal_task, get_proposal_artifact, get_proposal_task
from app.flexible_pricing import query_flexible_pricing_catalog
from app.flexible_workflow import (
    build_flexible_preview_response,
    build_flexible_review_state,
    flexible_export_graph,
    flexible_preview_graph,
    flexible_review_graph,
)
from app.models import (
    FlexibleCatalogResponse,
    FlexiblePreviewTaskCreatedResponse,
    FlexiblePreviewTaskResponse,
    FlexibleQuotePreviewResponse,
    FlexibleReviewRequest,
    ChatMessageRequest,
    ChatSessionCreatedResponse,
    ChatSessionResponse,
    ChatUploadResponse,
    HldDesignTaskCreatedResponse,
    HldDesignTaskResponse,
    HldRecommendationRequest,
    HldRecommendationResponse,
    HldRequirements,
    QuotePreviewResponse,
    QuoteRequest,
    RowQuoteTaskCreatedResponse,
    RowQuoteTaskResponse,
    ProposalRequest,
    ProposalTaskCreatedResponse,
    ProposalTaskResponse,
)
from app.row_quote_tasks import cancel_annotation_task, create_annotation_task, get_annotation_task, get_annotation_workbook
from app.row_quote_workflow import _safe_ascii_filename
from app.workflow import build_preview_response, export_graph, preview_graph

app = FastAPI(title="LangGraph Quote Agent", version="0.1.0")


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/flexible-pricing/catalog", response_model=FlexibleCatalogResponse)
def get_flexible_pricing_catalog(
    product: str | None = Query(default=None),
    region: str | None = Query(default=None),
) -> FlexibleCatalogResponse:
    items = query_flexible_pricing_catalog(product=product, region=region)
    return FlexibleCatalogResponse(items=items)


@app.post("/api/chat/sessions", response_model=ChatSessionCreatedResponse)
def create_chat_portal_session() -> ChatSessionCreatedResponse:
    return create_chat_session()


@app.get("/api/chat/sessions/{session_id}", response_model=ChatSessionResponse)
def get_chat_portal_session(session_id: str) -> ChatSessionResponse:
    session = get_chat_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Chat session not found.")
    return session


@app.post("/api/chat/uploads", response_model=ChatUploadResponse)
def upload_chat_files(files: list[UploadFile] = File(...)) -> ChatUploadResponse:
    uploads = _read_flexible_files(files)
    for index, upload in enumerate(files):
        uploads[index]["media_type"] = upload.content_type
    return register_uploads(uploads)


@app.post("/api/chat/sessions/{session_id}/messages/stream")
def stream_chat_portal_message(
    session_id: str,
    request: ChatMessageRequest = Body(...),
) -> StreamingResponse:
    if get_chat_session(session_id) is None:
        raise HTTPException(status_code=404, detail="Chat session not found.")
    stream = stream_chat(session_id, request)
    return StreamingResponse(
        stream,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/quotes/export")
def export_quote(
    rvtools_file: UploadFile = File(...),
    region: str = Form(...),
    evs_type: str = Form(...),
    lang: str = Form(...),
) -> Response:
    if not rvtools_file.filename or not rvtools_file.filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=415, detail="Only RVTools .xlsx files are supported in V1.")

    try:
        request = QuoteRequest(
            region=region,
            evs_type=evs_type,
            lang=lang,
            source_filename=rvtools_file.filename,
        )
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    file_bytes = rvtools_file.file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Uploaded RVTools file is empty.")

    try:
        result = export_graph.invoke({"request": request, "file_bytes": file_bytes})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        return JSONResponse(status_code=500, content={"detail": str(exc)})

    workbook = result["workbook"]
    return Response(
        content=workbook.content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{workbook.filename}"'},
    )


@app.post("/api/quotes/preview", response_model=QuotePreviewResponse)
def preview_quote(
    rvtools_file: UploadFile = File(...),
    region: str = Form(...),
    evs_type: str = Form(...),
    lang: str = Form(...),
) -> QuotePreviewResponse:
    if not rvtools_file.filename or not rvtools_file.filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=415, detail="Only RVTools .xlsx files are supported in V1.")

    try:
        request = QuoteRequest(
            region=region,
            evs_type=evs_type,
            lang=lang,
            source_filename=rvtools_file.filename,
        )
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    file_bytes = rvtools_file.file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Uploaded RVTools file is empty.")

    try:
        result = preview_graph.invoke({"request": request, "file_bytes": file_bytes})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        return JSONResponse(status_code=500, content={"detail": str(exc)})

    return build_preview_response(result)


def _read_flexible_files(files: list[UploadFile]) -> list[dict[str, bytes | str]]:
    uploads: list[dict[str, bytes | str]] = []
    for upload in files:
        if not upload.filename:
            continue
        uploads.append({"filename": upload.filename, "content": upload.file.read()})
    if not uploads:
        raise HTTPException(status_code=400, detail="At least one xlsx/csv/txt file is required.")
    return uploads


def _read_single_excel(upload: UploadFile) -> dict[str, bytes | str]:
    if not upload.filename or not upload.filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=415, detail="Only Excel .xlsx files are supported for row-level flexible quotes.")
    content = upload.file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded Excel file is empty.")
    return {"filename": upload.filename, "content": content}


@app.post("/api/quotes/flexible/annotate/tasks", response_model=RowQuoteTaskCreatedResponse)
def create_flexible_annotate_task(
    flexible_file: UploadFile = File(...),
    region: str | None = Form(default=None),
    lang: str = Form(default="en"),
    customer_notes: str = Form(default=""),
) -> RowQuoteTaskCreatedResponse:
    if not customer_notes.strip():
        raise HTTPException(status_code=422, detail="customer_notes is required. Provide AI quote guidance for the annotation task.")
    upload = _read_single_excel(flexible_file)
    return create_annotation_task(
        upload,
        {"region": region or None, "language": lang, "customer_notes": customer_notes},
    )


@app.get("/api/quotes/flexible/annotate/tasks/{task_id}", response_model=RowQuoteTaskResponse)
def get_flexible_annotate_task(task_id: str) -> RowQuoteTaskResponse:
    return get_annotation_task(task_id)


@app.get("/api/quotes/flexible/annotate/tasks/{task_id}/export")
def export_flexible_annotate_task(task_id: str) -> Response:
    workbook = get_annotation_workbook(task_id)
    workbook = workbook.model_copy(update={"filename": f"{_safe_ascii_filename(workbook.filename)}.xlsx"})
    return Response(
        content=workbook.content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{workbook.filename}"'},
    )


@app.post("/api/quotes/flexible/annotate/tasks/{task_id}/cancel", response_model=RowQuoteTaskResponse)
def cancel_flexible_annotate_task(task_id: str) -> RowQuoteTaskResponse:
    return cancel_annotation_task(task_id)


@app.post("/api/quotes/flexible/preview/tasks", response_model=FlexiblePreviewTaskCreatedResponse)
def create_flexible_preview_task(
    flexible_files: list[UploadFile] = File(...),
    region: str | None = Form(default=None),
    lang: str = Form(default="en"),
    customer_notes: str = Form(default=""),
) -> FlexiblePreviewTaskCreatedResponse:
    uploads = _read_flexible_files(flexible_files)
    return create_preview_task(
        uploads,
        {"region": region or None, "language": lang, "customer_notes": customer_notes},
    )


@app.get("/api/quotes/flexible/preview/tasks/{task_id}", response_model=FlexiblePreviewTaskResponse)
def get_flexible_preview_task(task_id: str) -> FlexiblePreviewTaskResponse:
    return get_preview_task(task_id)


@app.post("/api/quotes/flexible/preview", response_model=FlexibleQuotePreviewResponse)
def preview_flexible_quote(
    flexible_files: list[UploadFile] = File(...),
    region: str | None = Form(default=None),
    lang: str = Form(default="en"),
    customer_notes: str = Form(default=""),
) -> FlexibleQuotePreviewResponse:
    try:
        state = flexible_preview_graph.invoke(
            {
                "files": _read_flexible_files(flexible_files),
                "quote_context": {"region": region or None, "language": lang, "customer_notes": customer_notes},
            }
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        return JSONResponse(status_code=500, content={"detail": str(exc)})
    return build_flexible_preview_response(state)


@app.post("/api/quotes/flexible/review", response_model=FlexibleQuotePreviewResponse)
def review_flexible_quote(request: FlexibleReviewRequest) -> FlexibleQuotePreviewResponse:
    try:
        state = flexible_review_graph.invoke(build_flexible_review_state(request))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        return JSONResponse(status_code=500, content={"detail": str(exc)})
    return build_flexible_preview_response(state)


@app.post("/api/quotes/flexible/export")
def export_flexible_quote(request: FlexibleReviewRequest) -> Response:
    try:
        state = flexible_export_graph.invoke(build_flexible_review_state(request))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        return JSONResponse(status_code=500, content={"detail": str(exc)})
    workbook = state["workbook"]
    return Response(
        content=workbook.content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{workbook.filename}"'},
    )


# --- HLD Design endpoints ---


@app.post("/api/hld/designs/recommendations", response_model=HldRecommendationResponse)
def hld_recommendation(request: HldRecommendationRequest) -> HldRecommendationResponse:
    return get_recommendation(request)


@app.post("/api/hld/designs", response_model=HldDesignTaskCreatedResponse)
def create_hld_design(requirements: HldRequirements) -> HldDesignTaskCreatedResponse:
    return create_hld_design_task(requirements)


@app.get("/api/hld/designs/{design_id}", response_model=HldDesignTaskResponse)
def get_hld_design(design_id: str) -> HldDesignTaskResponse:
    return get_hld_design_task(design_id)


@app.get("/api/hld/designs/{design_id}/artifacts/png")
def download_hld_design_png(design_id: str) -> Response:
    content, media_type, filename = get_hld_design_artifact(design_id, "png")
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/hld/designs/{design_id}/artifacts/drawio")
def download_hld_design_drawio(design_id: str) -> Response:
    content, media_type, filename = get_hld_design_artifact(design_id, "drawio")
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# --- Proposal endpoints ---


@app.post("/api/proposals/tasks", response_model=ProposalTaskCreatedResponse)
def create_proposal(request: ProposalRequest) -> ProposalTaskCreatedResponse:
    return create_proposal_task(request)


@app.get("/api/proposals/tasks/{task_id}", response_model=ProposalTaskResponse)
def get_proposal(task_id: str) -> ProposalTaskResponse:
    return get_proposal_task(task_id)


@app.get("/api/proposals/tasks/{task_id}/artifacts/pptx")
def download_proposal_pptx(task_id: str) -> Response:
    content, media_type, filename = get_proposal_artifact(task_id, "pptx")
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/proposals/tasks/{task_id}/artifacts/json")
def download_proposal_json(task_id: str) -> Response:
    content, media_type, filename = get_proposal_artifact(task_id, "json")
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/proposals/tasks/{task_id}/artifacts/hld/png")
def download_proposal_hld_png(task_id: str) -> Response:
    content, media_type, filename = get_proposal_artifact(task_id, "hld_png")
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/proposals/tasks/{task_id}/artifacts/hld/drawio")
def download_proposal_hld_drawio(task_id: str) -> Response:
    content, media_type, filename = get_proposal_artifact(task_id, "hld_drawio")
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
