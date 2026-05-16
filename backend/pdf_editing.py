from dataclasses import dataclass

import fitz

from color_sampling import PdfColor, background_fill_for_rect
from font_mapping import resolve_pdf_font, text_width

PdfRect = tuple[float, float, float, float]


@dataclass(frozen=True)
class TextEdit:
    page_num: int
    bbox: PdfRect
    old_text: str
    new_text: str
    font: str
    size: float
    color: int
    insert_only: bool = False
    redaction_bbox: PdfRect | None = None
    bold: bool = False
    italic: bool = False


def apply_document_edits(doc: fitz.Document, edits: list[TextEdit]) -> None:
    """Apply redactions and text insertions to every edited page.

    Example: `apply_document_edits(doc, [TextEdit(0, bbox, "A", "B", "Arial", 12, 0)])`
    """
    page_edits = _edits_by_page(doc, edits)
    for page_num, edits_for_page in page_edits.items():
        apply_page_edits(doc[page_num], edits_for_page)


def apply_page_edits(page: fitz.Page, edits: list[TextEdit]) -> None:
    """Apply redactions and text insertions to one page.

    Example: `apply_page_edits(page, [TextEdit(0, bbox, "", "New", "Arial", 12, 0, True)])`
    """
    redactions = [_redaction_for_edit(page, edit) for edit in edits if not edit.insert_only]
    for rect, fill in redactions:
        page.add_redact_annot(rect, fill=fill)

    if redactions:
        page.apply_redactions()
    for edit in edits:
        _insert_edit_text(page, edit)


def _edits_by_page(
    doc: fitz.Document,
    edits: list[TextEdit],
) -> dict[int, list[TextEdit]]:
    page_edits: dict[int, list[TextEdit]] = {}
    for edit in edits:
        _validated_page(doc, edit.page_num)
        page_edits.setdefault(edit.page_num, []).append(edit)
    return page_edits


def _validated_page(doc: fitz.Document, page_num: int) -> fitz.Page:
    if page_num < 0 or page_num >= len(doc):
        expected = f"0..{max(len(doc) - 1, 0)}"
        raise ValueError(f"page_num {page_num} must be in range {expected}")
    return doc[page_num]


def _redaction_rect(edit: TextEdit) -> fitz.Rect:
    bbox = edit.redaction_bbox or edit.bbox
    return _fitz_rect(bbox, "redaction_bbox")


def _redaction_for_edit(page: fitz.Page, edit: TextEdit) -> tuple[fitz.Rect, PdfColor]:
    rect = _redaction_rect(edit)
    return rect, background_fill_for_rect(page, rect)


def _edit_rect(edit: TextEdit) -> fitz.Rect:
    return _fitz_rect(edit.bbox, "bbox")


def _fitz_rect(bbox: PdfRect, name: str) -> fitz.Rect:
    rect = fitz.Rect(bbox)
    if rect.is_empty or rect.is_infinite:
        raise ValueError(f"{name} {bbox} must be [x0, y0, x1, y1]")
    return rect


def _insert_edit_text(page: fitz.Page, edit: TextEdit) -> None:
    if not edit.new_text:
        return

    rect = _edit_rect(edit)
    if "\n" in edit.new_text:
        _insert_multiline_text(page, rect, edit)
        return

    if edit.insert_only:
        _insert_new_single_line(page, rect, edit)
        return
    _insert_replacement_single_line(page, rect, edit)


def _insert_multiline_text(
    page: fitz.Page,
    rect: fitz.Rect,
    edit: TextEdit,
) -> None:
    font = resolve_pdf_font(edit.font, edit.bold, edit.italic)
    page.insert_textbox(
        rect,
        edit.new_text,
        fontsize=_textbox_font_size(rect, edit),
        fontname=font.fitz_name,
        fontfile=font.file_path,
        set_simple=_font_set_simple(font.file_path),
        color=_pdf_rgb(edit.color),
    )


def _insert_new_single_line(
    page: fitz.Page,
    rect: fitz.Rect,
    edit: TextEdit,
) -> None:
    if _insert_new_textbox_line(page, rect, edit):
        return

    point = fitz.Point(rect.x0, rect.y0 + _line_baseline_offset(edit.size))
    font = resolve_pdf_font(edit.font, edit.bold, edit.italic)
    page.insert_text(
        point,
        edit.new_text,
        fontsize=_safe_font_size(edit.size),
        fontname=font.fitz_name,
        fontfile=font.file_path,
        set_simple=_font_set_simple(font.file_path),
        color=_pdf_rgb(edit.color),
        overlay=True,
    )


def _insert_new_textbox_line(
    page: fitz.Page,
    rect: fitz.Rect,
    edit: TextEdit,
) -> bool:
    font = resolve_pdf_font(edit.font, edit.bold, edit.italic)
    spare_height = page.insert_textbox(
        rect,
        edit.new_text,
        fontsize=_safe_font_size(edit.size),
        fontname=font.fitz_name,
        fontfile=font.file_path,
        set_simple=_font_set_simple(font.file_path),
        color=_pdf_rgb(edit.color),
        overlay=True,
    )
    return spare_height >= 0


def _insert_replacement_single_line(
    page: fitz.Page,
    rect: fitz.Rect,
    edit: TextEdit,
) -> None:
    point = fitz.Point(rect.x0, rect.y0 + rect.height * 0.78)
    font_size = _single_line_font_size(rect, edit)
    font = resolve_pdf_font(edit.font, edit.bold, edit.italic)
    page.insert_text(
        point,
        edit.new_text,
        fontsize=font_size,
        fontname=font.fitz_name,
        fontfile=font.file_path,
        set_simple=_font_set_simple(font.file_path),
        color=_pdf_rgb(edit.color),
        overlay=True,
    )


def _font_set_simple(font_file: str | None) -> int:
    if font_file is None:
        return 0
    return 1


def _textbox_font_size(rect: fitz.Rect, edit: TextEdit) -> float:
    if edit.insert_only:
        return _safe_font_size(edit.size)
    return max(4.0, min(_safe_font_size(edit.size), rect.height * 0.36))


def _single_line_font_size(
    rect: fitz.Rect,
    edit: TextEdit,
) -> float:
    height_size = _height_limited_font_size(rect, edit.size)
    measured_width = text_width(edit.font, edit.new_text, 1, edit.bold, edit.italic)
    if measured_width <= 0:
        return height_size

    width_size = rect.width / measured_width
    return max(4.0, min(height_size, width_size))


def _height_limited_font_size(
    rect: fitz.Rect,
    original_size: float | None,
) -> float:
    if original_size is None:
        return max(4.0, rect.height * 0.72)
    return max(4.0, min(original_size, rect.height * 0.92))


def _line_baseline_offset(font_size: float) -> float:
    return _safe_font_size(font_size) * 0.95


def _safe_font_size(font_size: float) -> float:
    return max(4.0, min(font_size, 96.0))


def _pdf_rgb(color: int) -> tuple[float, float, float]:
    red = ((color >> 16) & 255) / 255
    green = ((color >> 8) & 255) / 255
    blue = (color & 255) / 255
    return (red, green, blue)
