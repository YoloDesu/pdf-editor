from pathlib import Path
import uuid

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel

from font_catalog import available_font_names
from frontend_static import mount_frontend
from pdf_document import PdfDocumentError
from pdf_editing import TextEdit
from pdf_processing import (
    analyze_document_pages,
    create_edited_pdf_bytes,
    render_original_page_png,
    render_preview_page_png,
)
from runtime_paths import runtime_temp_dir

app = FastAPI()
TEMP_DIR = runtime_temp_dir()
TEMP_DIR.mkdir(parents=True, exist_ok=True)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class EditRequest(BaseModel):
    page_num: int
    bbox: tuple[float, float, float, float]
    old_text: str
    new_text: str
    font: str = "Helvetica"
    size: float = 12.0
    color: int = 0
    insert_only: bool = False
    redaction_bbox: tuple[float, float, float, float] | None = None
    bold: bool = False
    italic: bool = False


class SaveRequest(BaseModel):
    edits: list[EditRequest]


@app.post("/upload")
async def upload_pdf(file: UploadFile = File(...)) -> dict[str, str]:
    if file.filename is None or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    doc_id = str(uuid.uuid4())
    file_path = _document_path(doc_id)
    file_path.write_bytes(await file.read())
    return {"doc_id": doc_id}


@app.get("/fonts")
async def get_fonts() -> dict[str, list[str]]:
    return {"fonts": available_font_names()}


@app.get("/document/{doc_id}/pages")
async def get_document_pages(doc_id: str) -> dict[str, list[dict[str, object]]]:
    file_path = _existing_document_path(doc_id)
    try:
        return {"pages": analyze_document_pages(file_path)}
    except PdfDocumentError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@app.get("/document/{doc_id}/page/{page_num}/image")
async def get_page_image(doc_id: str, page_num: int) -> Response:
    file_path = _existing_document_path(doc_id)
    try:
        image = render_original_page_png(file_path, page_num)
    except PdfDocumentError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return Response(content=image, media_type="image/png")


@app.post("/document/{doc_id}/page/{page_num}/preview")
async def preview_page_image(
    doc_id: str,
    page_num: int,
    request: SaveRequest,
) -> Response:
    file_path = _existing_document_path(doc_id)
    edits = _request_edits(request)
    try:
        image = render_preview_page_png(file_path, page_num, edits)
    except PdfDocumentError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return Response(content=image, media_type="image/png")


@app.post("/document/{doc_id}/save")
async def save_document(doc_id: str, request: SaveRequest) -> Response:
    file_path = _existing_document_path(doc_id)
    try:
        pdf_bytes = create_edited_pdf_bytes(file_path, _request_edits(request))
    except PdfDocumentError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    headers = {"Content-Disposition": 'attachment; filename="edited_document.pdf"'}
    return Response(content=pdf_bytes, media_type="application/pdf", headers=headers)


def _request_edits(request: SaveRequest) -> list[TextEdit]:
    return [
        TextEdit(
            edit.page_num,
            edit.bbox,
            edit.old_text,
            edit.new_text,
            edit.font,
            edit.size,
            edit.color,
            edit.insert_only,
            edit.redaction_bbox,
            edit.bold,
            edit.italic,
        )
        for edit in request.edits
    ]


def _existing_document_path(doc_id: str) -> Path:
    file_path = _document_path(doc_id)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"Document {doc_id} not found.")
    return file_path


def _document_path(doc_id: str) -> Path:
    try:
        uuid.UUID(doc_id)
    except ValueError as error:
        detail = f"Document id {doc_id!r} must be a UUID string."
        raise HTTPException(status_code=400, detail=detail) from error
    return TEMP_DIR / f"{doc_id}.pdf"


mount_frontend(app)
