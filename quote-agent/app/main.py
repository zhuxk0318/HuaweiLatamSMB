from __future__ import annotations

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse, Response

from app.flexible_preview_tasks import create_preview_task, get_preview_task
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
    QuotePreviewResponse,
    QuoteRequest,
    RowQuoteTaskCreatedResponse,
    RowQuoteTaskResponse,
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
