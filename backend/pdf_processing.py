from pathlib import Path
from typing import cast

import fitz

from color_sampling import background_color_int_for_rect
from font_mapping import detect_pdf_font_style
from ocr_processing import _tesseract_config, ocr_text_blocks
from pdf_document import PdfDocumentError, open_pdf_document
from pdf_editing import TextEdit, apply_document_edits
from pdf_rendering import MAX_PREVIEW_PIXELS, page_pixmap_with_pixel_limit
from pdf_text import TextBlock

PREVIEW_DPI = 150
MIN_NATIVE_TEXT_CHARS = 50
OPTIONAL_ANALYSIS_ERRORS = (RuntimeError, ValueError, OSError, MemoryError)
PDF_OPERATION_ERRORS = (RuntimeError, OSError, MemoryError)


def analyze_document_pages(pdf_path: Path) -> list[dict[str, object]]:
    """Read text blocks and page sizes from a PDF.

    Example: `analyze_document_pages(Path("temp_pdfs/example.pdf"))`
    """
    doc = open_pdf_document(pdf_path)
    try:
        return [_analyze_page_or_empty(page) for page in doc]
    finally:
        doc.close()


def render_original_page_png(pdf_path: Path, page_num: int) -> bytes:
    """Render one unedited PDF page to PNG bytes.

    Example: `render_original_page_png(Path("a.pdf"), 0)`
    """
    doc = open_pdf_document(pdf_path)
    try:
        page = _validated_page(doc, page_num)
        try:
            return _render_page_png(page, PREVIEW_DPI)
        except PDF_OPERATION_ERRORS as error:
            message = f"PDF {pdf_path.name!r} page {page_num} could not be rendered"
            raise PdfDocumentError(f"{message}; expected renderable PDF page: {error}") from error
    finally:
        doc.close()


def render_preview_page_png(
    pdf_path: Path,
    page_num: int,
    edits: list[TextEdit],
) -> bytes:
    """Render one PDF page after applying pending edits in memory.

    Example: `render_preview_page_png(Path("a.pdf"), 0, edits)`
    """
    doc = open_pdf_document(pdf_path)
    try:
        _validated_page(doc, page_num)
        try:
            apply_document_edits(doc, edits)
            page = _validated_page(doc, page_num)
            return _render_page_png(page, PREVIEW_DPI)
        except PDF_OPERATION_ERRORS as error:
            message = f"PDF {pdf_path.name!r} page {page_num} preview failed"
            raise PdfDocumentError(f"{message}; expected editable PDF content: {error}") from error
    finally:
        doc.close()


def create_edited_pdf_bytes(pdf_path: Path, edits: list[TextEdit]) -> bytes:
    """Create a PDF containing all accepted text edits.

    Example: `create_edited_pdf_bytes(Path("a.pdf"), edits)`
    """
    doc = open_pdf_document(pdf_path)
    try:
        try:
            apply_document_edits(doc, edits)
            return doc.tobytes(garbage=4, deflate=True)
        except PDF_OPERATION_ERRORS as error:
            message = f"PDF {pdf_path.name!r} could not be saved"
            raise PdfDocumentError(f"{message}; expected editable PDF content: {error}") from error
    finally:
        doc.close()


def _analyze_page_or_empty(page: fitz.Page) -> dict[str, object]:
    try:
        return _analyze_page(page)
    except OPTIONAL_ANALYSIS_ERRORS:
        return {
            "page_num": page.number,
            "width": page.rect.width,
            "height": page.rect.height,
            "text_blocks": [],
        }


def _analyze_page(page: fitz.Page) -> dict[str, object]:
    native_blocks = _native_text_blocks(page)
    blocks = _preferred_text_blocks(page, native_blocks)
    blocks = _blocks_with_background_colors(page, blocks)

    return {
        "page_num": page.number,
        "width": page.rect.width,
        "height": page.rect.height,
        "text_blocks": [block.as_payload() for block in blocks],
    }


def _preferred_text_blocks(
    page: fitz.Page,
    native_blocks: list[TextBlock],
) -> list[TextBlock]:
    if not _needs_ocr(native_blocks):
        return native_blocks
    return _ocr_text_blocks_or_native(page, native_blocks)


def _ocr_text_blocks_or_native(
    page: fitz.Page,
    native_blocks: list[TextBlock],
) -> list[TextBlock]:
    try:
        return ocr_text_blocks(page)
    except OPTIONAL_ANALYSIS_ERRORS:
        return native_blocks


def _native_text_blocks(page: fitz.Page) -> list[TextBlock]:
    text_page = page.get_text("dict")
    blocks: list[TextBlock] = []
    for block in text_page.get("blocks", []):
        blocks.extend(_native_block_spans(block))
    return blocks


def _native_block_spans(block: object) -> list[TextBlock]:
    if not isinstance(block, dict) or "lines" not in block:
        return []

    spans: list[TextBlock] = []
    for line in block["lines"]:
        for span in line.get("spans", []):
            text_block = _span_text_block(span)
            if text_block is not None:
                spans.append(text_block)
    return spans


def _span_text_block(span: object) -> TextBlock | None:
    if not isinstance(span, dict):
        return None

    text = str(span.get("text", "")).strip()
    if not text:
        return None

    font_name = str(span.get("font", "Helvetica"))
    font_style = detect_pdf_font_style(font_name)
    return TextBlock(
        tuple(cast(tuple[float, float, float, float], span["bbox"])),
        text,
        font_name,
        float(span.get("size", 10.0)),
        int(span.get("color", 0)),
        font_style.bold,
        font_style.italic,
    )


def _blocks_with_background_colors(
    page: fitz.Page,
    blocks: list[TextBlock],
) -> list[TextBlock]:
    return [_block_with_background_color(page, block) for block in blocks]


def _block_with_background_color(page: fitz.Page, block: TextBlock) -> TextBlock:
    rect = fitz.Rect(block.bbox)
    try:
        background_color = background_color_int_for_rect(page, rect)
    except OPTIONAL_ANALYSIS_ERRORS:
        background_color = 16777215
    return TextBlock(
        block.bbox,
        block.text,
        block.font,
        block.size,
        block.color,
        block.bold,
        block.italic,
        background_color,
    )


def _needs_ocr(native_blocks: list[TextBlock]) -> bool:
    text_length = sum(len(block.text) for block in native_blocks)
    return text_length < MIN_NATIVE_TEXT_CHARS


def _validated_page(doc: fitz.Document, page_num: int) -> fitz.Page:
    if page_num < 0 or page_num >= len(doc):
        expected = f"0..{max(len(doc) - 1, 0)}"
        raise ValueError(f"page_num {page_num} must be in range {expected}")
    return doc[page_num]


def _render_page_png(page: fitz.Page, dpi: int) -> bytes:
    pixmap = page_pixmap_with_pixel_limit(page, dpi, MAX_PREVIEW_PIXELS)
    return pixmap.tobytes("png")
