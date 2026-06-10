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
    apply_manual_review_from_api,
    build_flexible_preview_response,
    build_flexible_review_state,
    flexible_export_graph,
    flexible_preview_graph,
    flexible_review_graph,
)
from app.cloud_billing_workflow import (
    cloud_billing_preview_graph,
    cloud_billing_review_graph,
    cloud_billing_export_graph,
)
from app.others_quote_workflow import (
    others_preview_graph,
    others_review_graph,
    others_export_graph,
)
from app.models import (
    FlexibleCatalogResponse,
    FlexiblePreviewTaskCreatedResponse,
    FlexiblePreviewTaskResponse,
    FlexibleQuotePreviewResponse,
    FlexibleReviewRequest,
    ManualReviewApplyError,
    ManualReviewApplyRequest,
    ManualReviewApplyResponse,
    ManualReviewApplyResult,
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
    SheetSelection,
)
from app.row_quote_tasks import cancel_annotation_task, create_annotation_task, get_annotation_task, get_annotation_workbook
from app.row_quote_workflow import _safe_ascii_filename
from app.rvtools_preview_tasks import get_preview_state, store_preview_result
from app.workflow import build_preview_response, export_excel, export_graph, preview_graph, multi_preview_graph, multi_export_graph, parse_rvtools_multi

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
    sheet_selection_mode: str = Form(default="first"),
    sheet_selection_input: str = Form(default=""),
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

    sheet_selection = SheetSelection(mode=sheet_selection_mode, selected_input=sheet_selection_input or None)

    try:
        result = export_graph.invoke({"request": request, "file_bytes": file_bytes, "sheet_selection": sheet_selection})
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


@app.get("/api/quotes/tasks/{task_id}/export")
def export_quote_from_preview(task_id: str) -> Response:
    state = get_preview_state(task_id)
    try:
        export_state = export_excel(state)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    workbook = export_state["workbook"]
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
    sheet_selection_mode: str = Form(default="first"),
    sheet_selection_input: str = Form(default=""),
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

    sheet_selection = SheetSelection(mode=sheet_selection_mode, selected_input=sheet_selection_input or None)

    try:
        result = preview_graph.invoke({"request": request, "file_bytes": file_bytes, "sheet_selection": sheet_selection})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        return JSONResponse(status_code=500, content={"detail": str(exc)})

    preview_resp = build_preview_response(result)
    task_id = store_preview_result(preview_resp, result)
    preview_resp.task_id = task_id
    return preview_resp


# ── Multi-file RVTools endpoints (Phase 6) ────────────────────────────────────────


@app.post("/api/quotes/multi/preview", response_model=QuotePreviewResponse)
def preview_quote_multi(
    files: list[UploadFile] = File(...),
    region: str = Form(...),
    evs_type: str = Form(...),
    lang: str = Form(...),
    sheet_selection_mode: str = Form(default="first"),
    sheet_selection_input: str = Form(default=""),
) -> QuotePreviewResponse:
    """Preview quote from multiple RVTools/inventory files."""
    if not files:
        raise HTTPException(status_code=400, detail="At least one file is required.")

    file_entries: list[dict] = []
    source_filenames: list[str] = []
    for f in files:
        if not f.filename or not f.filename.lower().endswith((".xlsx", ".xls", ".csv")):
            raise HTTPException(status_code=415, detail=f"File '{f.filename}' is not a supported format (.xlsx/.xls/.csv).")
        content = f.file.read()
        if not content:
            raise HTTPException(status_code=400, detail=f"File '{f.filename}' is empty.")
        file_entries.append({"filename": f.filename, "content": content})
        source_filenames.append(f.filename)

    try:
        request = QuoteRequest(
            region=region,
            evs_type=evs_type,
            lang=lang,
            source_filename=source_filenames[0] if len(source_filenames) == 1 else f"{len(source_filenames)}_files",
        )
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    sheet_selection = SheetSelection(mode=sheet_selection_mode, selected_input=sheet_selection_input or None)

    try:
        result = multi_preview_graph.invoke({
            "request": request,
            "files": file_entries,
            "sheet_selection": sheet_selection,
        })
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        return JSONResponse(status_code=500, content={"detail": str(exc)})

    preview_resp = build_preview_response(result)
    task_id = store_preview_result(preview_resp, result)
    preview_resp.task_id = task_id
    return preview_resp


@app.post("/api/quotes/multi/export")
def export_quote_multi(
    files: list[UploadFile] = File(...),
    region: str = Form(...),
    evs_type: str = Form(...),
    lang: str = Form(...),
    sheet_selection_mode: str = Form(default="first"),
    sheet_selection_input: str = Form(default=""),
) -> Response:
    """Export quote from multiple RVTools/inventory files."""
    if not files:
        raise HTTPException(status_code=400, detail="At least one file is required.")

    file_entries: list[dict] = []
    source_filenames: list[str] = []
    for f in files:
        if not f.filename or not f.filename.lower().endswith((".xlsx", ".xls", ".csv")):
            raise HTTPException(status_code=415, detail=f"File '{f.filename}' is not a supported format (.xlsx/.xls/.csv).")
        content = f.file.read()
        if not content:
            raise HTTPException(status_code=400, detail=f"File '{f.filename}' is empty.")
        file_entries.append({"filename": f.filename, "content": content})
        source_filenames.append(f.filename)

    try:
        request = QuoteRequest(
            region=region,
            evs_type=evs_type,
            lang=lang,
            source_filename=source_filenames[0] if len(source_filenames) == 1 else f"{len(source_filenames)}_files",
        )
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    sheet_selection = SheetSelection(mode=sheet_selection_mode, selected_input=sheet_selection_input or None)

    try:
        result = multi_export_graph.invoke({
            "request": request,
            "files": file_entries,
            "sheet_selection": sheet_selection,
        })
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
        raise HTTPException(status_code=415, detail="Only Excel .xlsx files are supported for Others Quote.")
    content = upload.file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded Excel file is empty.")
    return {"filename": upload.filename, "content": content}


def _read_billing_file(upload: UploadFile) -> dict[str, bytes | str]:
    """Read a single file for Cloud Billing Quote (.xlsx or .csv)."""
    if not upload.filename or not upload.filename.lower().endswith((".xlsx", ".csv")):
        raise HTTPException(status_code=415, detail="Cloud Billing Quote supports .xlsx and .csv files only.")
    content = upload.file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded billing file is empty.")
    return {"filename": upload.filename, "content": content}


def _read_others_excel(upload: UploadFile) -> dict[str, bytes | str]:
    """Read a single file for Others Quote (.xlsx only)."""
    if not upload.filename or not upload.filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=415, detail="Others Quote only supports .xlsx files.")
    content = upload.file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded Excel file is empty.")
    return {"filename": upload.filename, "content": content}


# ── Legacy flexible endpoints (compatibility only) ──────────────────────────────
# These routes are kept for backward compatibility. New code should use
# /api/quotes/cloud-billing/... or /api/quotes/others/... instead.
# The flexible endpoint dispatches to the correct graph based on quote_mode.


@app.post("/api/quotes/flexible/annotate/tasks", response_model=RowQuoteTaskCreatedResponse)
def create_flexible_annotate_task(
    flexible_file: UploadFile = File(...),
    region: str | None = Form(default=None),
    lang: str = Form(default="en"),
    customer_notes: str = Form(default=""),
    sheet_selection_mode: str = Form(default="first"),
    sheet_selection_input: str = Form(default=""),
    quote_mode: str = Form(default=""),
) -> RowQuoteTaskCreatedResponse:
    if not customer_notes.strip():
        raise HTTPException(status_code=422, detail="customer_notes is required. Provide AI quote guidance for the annotation task.")
    if quote_mode == "cloud_billing":
        upload = _read_billing_file(flexible_file)
    else:
        upload = _read_single_excel(flexible_file)
    sheet_selection = SheetSelection(mode=sheet_selection_mode, selected_input=sheet_selection_input or None)
    context = {"region": region or None, "language": lang, "customer_notes": customer_notes}
    if quote_mode in ("cloud_billing", "others"):
        context["quote_mode"] = quote_mode
    return create_annotation_task(
        upload,
        context,
        sheet_selection=sheet_selection,
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
    sheet_selection_mode: str = Form(default="first"),
    sheet_selection_input: str = Form(default=""),
    quote_mode: str = Form(default=""),
) -> FlexiblePreviewTaskCreatedResponse:
    uploads = _read_flexible_files(flexible_files)
    context = {"region": region or None, "language": lang, "customer_notes": customer_notes}
    if quote_mode in ("cloud_billing", "others"):
        context["quote_mode"] = quote_mode
    return create_preview_task(
        uploads,
        context,
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
    sheet_selection_mode: str = Form(default="first"),
    sheet_selection_input: str = Form(default=""),
    quote_mode: str = Form(default=""),
) -> FlexibleQuotePreviewResponse:
    context = {"region": region or None, "language": lang, "customer_notes": customer_notes}
    if quote_mode in ("cloud_billing", "others"):
        context["quote_mode"] = quote_mode
    # Dispatch to the appropriate graph based on quote_mode
    if quote_mode == "cloud_billing":
        graph = cloud_billing_preview_graph
    elif quote_mode == "others":
        graph = others_preview_graph
    else:
        graph = flexible_preview_graph
    try:
        state = graph.invoke(
            {
                "files": _read_flexible_files(flexible_files),
                "quote_context": context,
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
    quote_mode = request.quote_context.quote_mode
    if quote_mode == "cloud_billing":
        graph = cloud_billing_review_graph
    elif quote_mode == "others":
        graph = others_review_graph
    else:
        graph = flexible_review_graph
    try:
        state = graph.invoke(build_flexible_review_state(request))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        return JSONResponse(status_code=500, content={"detail": str(exc)})
    return build_flexible_preview_response(state)


@app.post("/api/quotes/flexible/export")
def export_flexible_quote(request: FlexibleReviewRequest) -> Response:
    quote_mode = request.quote_context.quote_mode
    if quote_mode == "cloud_billing":
        graph = cloud_billing_export_graph
    elif quote_mode == "others":
        graph = others_export_graph
    else:
        graph = flexible_export_graph
    try:
        state = graph.invoke(build_flexible_review_state(request))
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


# ── Cloud Billing Quote endpoints ───────────────────────────────────────────────


# ── Cloud Billing Quote endpoints ────────────────────────────────────────────────
# Public cloud monthly billing aggregation path: ingest Azure/AWS/GCP billing
# exports, aggregate billing lines, map to Huawei Cloud products, price, summarize.


@app.post("/api/quotes/cloud-billing/annotate/tasks", response_model=RowQuoteTaskCreatedResponse)
def create_cloud_billing_annotate_task(
    flexible_file: UploadFile = File(...),
    region: str | None = Form(default=None),
    lang: str = Form(default="en"),
    customer_notes: str = Form(default=""),
    sheet_selection_mode: str = Form(default="first"),
    sheet_selection_input: str = Form(default=""),
) -> RowQuoteTaskCreatedResponse:
    """Create a row-quote annotation task for cloud billing exports (.xlsx/.csv)."""
    if not customer_notes.strip():
        raise HTTPException(status_code=422, detail="customer_notes is required. Provide AI quote guidance for the cloud billing annotation task.")
    upload = _read_billing_file(flexible_file)
    sheet_selection = SheetSelection(mode=sheet_selection_mode, selected_input=sheet_selection_input or None)
    return create_annotation_task(
        upload,
        {"region": region or None, "language": lang, "customer_notes": customer_notes, "quote_mode": "cloud_billing"},
        sheet_selection=sheet_selection,
    )


@app.get("/api/quotes/cloud-billing/annotate/tasks/{task_id}", response_model=RowQuoteTaskResponse)
def get_cloud_billing_annotate_task(task_id: str) -> RowQuoteTaskResponse:
    return get_annotation_task(task_id)


@app.get("/api/quotes/cloud-billing/annotate/tasks/{task_id}/export")
def export_cloud_billing_annotate_task(task_id: str) -> Response:
    workbook = get_annotation_workbook(task_id)
    workbook = workbook.model_copy(update={"filename": f"{_safe_ascii_filename(workbook.filename)}.xlsx"})
    return Response(
        content=workbook.content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{workbook.filename}"'},
    )


@app.post("/api/quotes/cloud-billing/annotate/tasks/{task_id}/cancel", response_model=RowQuoteTaskResponse)
def cancel_cloud_billing_annotate_task(task_id: str) -> RowQuoteTaskResponse:
    return cancel_annotation_task(task_id)


@app.post("/api/quotes/cloud-billing/preview", response_model=FlexibleQuotePreviewResponse)
def preview_cloud_billing_quote(
    flexible_files: list[UploadFile] = File(...),
    region: str | None = Form(default=None),
    lang: str = Form(default="en"),
    customer_notes: str = Form(default=""),
    sheet_selection_mode: str = Form(default="first"),
    sheet_selection_input: str = Form(default=""),
) -> FlexibleQuotePreviewResponse:
    """Preview a cloud billing quote. Accepts .xlsx and .csv billing exports."""
    uploads = _read_flexible_files(flexible_files)
    context = {"region": region or None, "language": lang, "customer_notes": customer_notes, "quote_mode": "cloud_billing"}
    try:
        state = cloud_billing_preview_graph.invoke({"files": uploads, "quote_context": context})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        return JSONResponse(status_code=500, content={"detail": str(exc)})
    return build_flexible_preview_response(state)


@app.post("/api/quotes/cloud-billing/review", response_model=FlexibleQuotePreviewResponse)
def review_cloud_billing_quote(request: FlexibleReviewRequest) -> FlexibleQuotePreviewResponse:
    """Review a cloud billing quote with manual feedback."""
    if request.quote_context.quote_mode is None:
        request.quote_context.quote_mode = "cloud_billing"
    try:
        state = cloud_billing_review_graph.invoke(build_flexible_review_state(request))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        return JSONResponse(status_code=500, content={"detail": str(exc)})
    return build_flexible_preview_response(state)


@app.post("/api/quotes/cloud-billing/export")
def export_cloud_billing_quote(request: FlexibleReviewRequest) -> Response:
    """Export a cloud billing quote workbook."""
    if request.quote_context.quote_mode is None:
        request.quote_context.quote_mode = "cloud_billing"
    try:
        state = cloud_billing_export_graph.invoke(build_flexible_review_state(request))
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


# ── Others Quote endpoints ──────────────────────────────────────────────────────
# Row-by-row requirement matching path: ingest custom requirement sheets,
# match rows one-by-one against Huawei Cloud products, price, summarize.


@app.post("/api/quotes/others/annotate/tasks", response_model=RowQuoteTaskCreatedResponse)
def create_others_annotate_task(
    flexible_file: UploadFile = File(...),
    region: str | None = Form(default=None),
    lang: str = Form(default="en"),
    customer_notes: str = Form(default=""),
    sheet_selection_mode: str = Form(default="first"),
    sheet_selection_input: str = Form(default=""),
) -> RowQuoteTaskCreatedResponse:
    """Create a row-quote annotation task for non-billing Excel files (.xlsx only)."""
    if not customer_notes.strip():
        raise HTTPException(status_code=422, detail="customer_notes is required. Provide AI quote guidance for the Others Quote annotation task.")
    upload = _read_others_excel(flexible_file)
    sheet_selection = SheetSelection(mode=sheet_selection_mode, selected_input=sheet_selection_input or None)
    return create_annotation_task(
        upload,
        {"region": region or None, "language": lang, "customer_notes": customer_notes, "quote_mode": "others"},
        sheet_selection=sheet_selection,
    )


@app.get("/api/quotes/others/annotate/tasks/{task_id}", response_model=RowQuoteTaskResponse)
def get_others_annotate_task(task_id: str) -> RowQuoteTaskResponse:
    return get_annotation_task(task_id)


@app.get("/api/quotes/others/annotate/tasks/{task_id}/export")
def export_others_annotate_task(task_id: str) -> Response:
    workbook = get_annotation_workbook(task_id)
    workbook = workbook.model_copy(update={"filename": f"{_safe_ascii_filename(workbook.filename)}.xlsx"})
    return Response(
        content=workbook.content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{workbook.filename}"'},
    )


@app.post("/api/quotes/others/annotate/tasks/{task_id}/cancel", response_model=RowQuoteTaskResponse)
def cancel_others_annotate_task(task_id: str) -> RowQuoteTaskResponse:
    return cancel_annotation_task(task_id)


@app.post("/api/quotes/others/preview", response_model=FlexibleQuotePreviewResponse)
def preview_others_quote(
    flexible_files: list[UploadFile] = File(...),
    region: str | None = Form(default=None),
    lang: str = Form(default="en"),
    customer_notes: str = Form(default=""),
    sheet_selection_mode: str = Form(default="first"),
    sheet_selection_input: str = Form(default=""),
) -> FlexibleQuotePreviewResponse:
    """Preview an Others Quote. Accepts .xlsx requirement/comparison files only."""
    if not flexible_files:
        raise HTTPException(status_code=400, detail="At least one .xlsx file is required.")
    uploads: list[dict[str, bytes | str]] = []
    for f in flexible_files:
        uploads.append(_read_others_excel(f))
    if not uploads:
        raise HTTPException(status_code=400, detail="At least one .xlsx file is required.")
    context = {"region": region or None, "language": lang, "customer_notes": customer_notes, "quote_mode": "others"}
    try:
        state = others_preview_graph.invoke({"files": uploads, "quote_context": context})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        return JSONResponse(status_code=500, content={"detail": str(exc)})
    return build_flexible_preview_response(state)


@app.post("/api/quotes/others/review", response_model=FlexibleQuotePreviewResponse)
def review_others_quote(request: FlexibleReviewRequest) -> FlexibleQuotePreviewResponse:
    """Review an Others Quote with manual feedback."""
    if request.quote_context.quote_mode is None:
        request.quote_context.quote_mode = "others"
    try:
        state = others_review_graph.invoke(build_flexible_review_state(request))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        return JSONResponse(status_code=500, content={"detail": str(exc)})
    return build_flexible_preview_response(state)


@app.post("/api/quotes/others/export")
def export_others_quote(request: FlexibleReviewRequest) -> Response:
    """Export an Others Quote workbook."""
    if request.quote_context.quote_mode is None:
        request.quote_context.quote_mode = "others"
    try:
        state = others_export_graph.invoke(build_flexible_review_state(request))
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


# --- Manual review apply endpoint (Phase Next+10) ---


@app.post("/api/quotes/flexible/manual-review/apply", response_model=ManualReviewApplyResponse)
def apply_manual_review(request: ManualReviewApplyRequest) -> ManualReviewApplyResponse:
    """Apply manual review decisions to flexible quote candidates.

    Validates the decisions against the provided candidates, applies valid ones,
    and returns structured errors/results/summary.

    When reprice=True, also recomputes readiness/pricing/quote after applying
    overrides and returns reprice_preview_summary with updated counts.
    """
    candidates = request.candidates
    state_for_reprice = None

    if not candidates and request.task_id:
        # Attempt to load candidates from an existing preview task
        try:
            task_resp = get_preview_task(request.task_id)
        except HTTPException:
            raise HTTPException(status_code=404, detail=f"Preview task '{request.task_id}' not found.")
        if task_resp.result and task_resp.result.manual_review_candidates:
            candidates = [c.model_dump() for c in task_resp.result.manual_review_candidates]

    if not candidates:
        raise HTTPException(status_code=400, detail="No candidates provided and none could be loaded from task_id.")

    decisions = [d.model_dump() for d in request.decisions]
    result = apply_manual_review_from_api(
        decisions,
        candidates,
        reprice=request.reprice,
        state=state_for_reprice,
    )

    response = ManualReviewApplyResponse(
        applied_count=result["applied_count"],
        errors=[
            ManualReviewApplyError.model_validate(e) for e in result["errors"]
        ],
        results=[
            ManualReviewApplyResult.model_validate(r) for r in result["results"]
        ],
        summary=result["summary"],
    )
    # Include reprice results if present
    if "reprice_preview_summary" in result:
        response.summary["reprice_preview"] = result["reprice_preview_summary"]
    if "reprice_updated_counts" in result:
        response.summary["updated_counts"] = result["reprice_updated_counts"]

    return response


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
