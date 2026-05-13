from __future__ import annotations

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse, Response

from app.models import QuotePreviewResponse, QuoteRequest
from app.workflow import build_preview_response, export_graph, preview_graph

app = FastAPI(title="LangGraph Quote Agent", version="0.1.0")


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


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
