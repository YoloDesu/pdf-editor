from dataclasses import dataclass
from io import BytesIO
import os
from pathlib import Path
from typing import TypedDict, cast

import fitz
from PIL import Image, ImageFilter, ImageOps
import pytesseract

from color_sampling import background_color_int_for_rect
from font_mapping import detect_pdf_font_style
from pdf_editing import TextEdit, apply_document_edits
from runtime_paths import bundled_tessdata_dir, bundled_tesseract_cmd

OCR_DPI = 350
PREVIEW_DPI = 150
MIN_NATIVE_TEXT_CHARS = 50
MIN_OCR_WORD_CONFIDENCE = 35.0
MIN_OCR_LINE_CONFIDENCE = 45.0


class OcrData(TypedDict):
    text: list[str]
    conf: list[str]
    left: list[int]
    top: list[int]
    width: list[int]
    height: list[int]
    block_num: list[int]
    par_num: list[int]
    line_num: list[int]


@dataclass(frozen=True)
class TextBlock:
    bbox: tuple[float, float, float, float]
    text: str
    font: str
    size: float
    color: int
    bold: bool = False
    italic: bool = False
    background_color: int = 16777215

    def as_payload(self) -> dict[str, object]:
        """Return JSON-ready text metadata.

        Example: `TextBlock((0, 0, 10, 10), "A", "helv", 8, 0).as_payload()`
        """
        return {
            "bbox": self.bbox,
            "text": self.text,
            "font": self.font,
            "size": self.size,
            "color": self.color,
            "bold": self.bold,
            "italic": self.italic,
            "background_color": self.background_color,
        }


@dataclass(frozen=True)
class OcrWord:
    text: str
    confidence: float
    left: int
    top: int
    width: int
    height: int
    block_num: int
    par_num: int
    line_num: int


def analyze_document_pages(pdf_path: Path) -> list[dict[str, object]]:
    """Read text blocks and page sizes from a PDF.

    Example: `analyze_document_pages(Path("temp_pdfs/example.pdf"))`
    """
    doc = fitz.open(pdf_path)
    try:
        return [_analyze_page(page) for page in doc]
    finally:
        doc.close()


def render_original_page_png(pdf_path: Path, page_num: int) -> bytes:
    """Render one unedited PDF page to PNG bytes.

    Example: `render_original_page_png(Path("a.pdf"), 0)`
    """
    doc = fitz.open(pdf_path)
    try:
        return _render_page_png(_validated_page(doc, page_num), PREVIEW_DPI)
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
    doc = fitz.open(pdf_path)
    try:
        apply_document_edits(doc, edits)
        return _render_page_png(_validated_page(doc, page_num), PREVIEW_DPI)
    finally:
        doc.close()


def create_edited_pdf_bytes(pdf_path: Path, edits: list[TextEdit]) -> bytes:
    """Create a PDF containing all accepted text edits.

    Example: `create_edited_pdf_bytes(Path("a.pdf"), edits)`
    """
    doc = fitz.open(pdf_path)
    try:
        apply_document_edits(doc, edits)
        return doc.tobytes(garbage=4, deflate=True)
    finally:
        doc.close()


def _analyze_page(page: fitz.Page) -> dict[str, object]:
    native_blocks = _native_text_blocks(page)
    blocks = native_blocks
    if _needs_ocr(native_blocks):
        blocks = _ocr_text_blocks(page)
    blocks = _blocks_with_background_colors(page, blocks)

    return {
        "page_num": page.number,
        "width": page.rect.width,
        "height": page.rect.height,
        "text_blocks": [block.as_payload() for block in blocks],
    }


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
    background_color = background_color_int_for_rect(page, rect)
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


def _ocr_text_blocks(page: fitz.Page) -> list[TextBlock]:
    image = _prepare_ocr_image(_page_to_image(page, OCR_DPI))
    ocr_data = _run_tesseract_data(image, page.number)
    scale_x = page.rect.width / image.width
    scale_y = page.rect.height / image.height
    words = _extract_ocr_words(ocr_data)
    return _group_ocr_words_into_lines(words, scale_x, scale_y)


def _page_to_image(page: fitz.Page, dpi: int) -> Image.Image:
    pixmap = page.get_pixmap(dpi=dpi, alpha=False)
    png_bytes = pixmap.tobytes("png")
    return Image.open(BytesIO(png_bytes)).convert("RGB")


def _prepare_ocr_image(image: Image.Image) -> Image.Image:
    grayscale = ImageOps.grayscale(image)
    contrasted = ImageOps.autocontrast(grayscale)
    return contrasted.filter(ImageFilter.UnsharpMask(radius=1, percent=160))


def _run_tesseract_data(image: Image.Image, page_num: int) -> OcrData:
    _configure_tesseract_runtime()
    language = os.getenv("TESSERACT_LANG", "eng")
    config = _tesseract_config()
    try:
        raw_data = pytesseract.image_to_data(
            image,
            lang=language,
            config=config,
            output_type=pytesseract.Output.DICT,
        )
    except pytesseract.TesseractError as error:
        message = f"OCR failed on page {page_num}; expected Tesseract word data"
        raise RuntimeError(f"{message}: {error}") from error
    return cast(OcrData, raw_data)


def _configure_tesseract_runtime() -> None:
    command = bundled_tesseract_cmd()
    if command is not None:
        pytesseract.pytesseract.tesseract_cmd = str(command)


def _tesseract_config() -> str:
    config = os.getenv("TESSERACT_CONFIG", "--oem 3 --psm 6")
    tessdata_dir = bundled_tessdata_dir()
    if tessdata_dir is None:
        return config
    return f'{config} --tessdata-dir "{tessdata_dir}"'


def _extract_ocr_words(ocr_data: OcrData) -> list[OcrWord]:
    words: list[OcrWord] = []
    for index, text in enumerate(ocr_data["text"]):
        word = _ocr_word_from_row(ocr_data, index, text)
        if word is not None:
            words.append(word)
    return words


def _ocr_word_from_row(
    ocr_data: OcrData,
    index: int,
    text: str,
) -> OcrWord | None:
    confidence = _ocr_confidence(ocr_data["conf"][index])
    if confidence < MIN_OCR_WORD_CONFIDENCE or not text.strip():
        return None

    return OcrWord(
        text.strip(),
        confidence,
        int(ocr_data["left"][index]),
        int(ocr_data["top"][index]),
        int(ocr_data["width"][index]),
        int(ocr_data["height"][index]),
        int(ocr_data["block_num"][index]),
        int(ocr_data["par_num"][index]),
        int(ocr_data["line_num"][index]),
    )


def _ocr_confidence(raw_confidence: str) -> float:
    try:
        return float(raw_confidence)
    except ValueError:
        return -1.0


def _group_ocr_words_into_lines(
    words: list[OcrWord],
    scale_x: float,
    scale_y: float,
) -> list[TextBlock]:
    lines = _ocr_line_groups(words)
    return [
        _ocr_line_text_block(line_words, scale_x, scale_y)
        for line_words in lines
        if _line_confidence(line_words) >= MIN_OCR_LINE_CONFIDENCE
    ]


def _ocr_line_groups(words: list[OcrWord]) -> list[list[OcrWord]]:
    lines: list[list[OcrWord]] = []
    sorted_words = sorted(words, key=lambda word: (_word_center_y(word), word.left))
    for word in sorted_words:
        line = _matching_visual_line(lines, word)
        if line is None:
            lines.append([word])
            continue
        line.append(word)

    for line_words in lines:
        line_words.sort(key=lambda word: word.left)
    return sorted(lines, key=_line_sort_key)


def _matching_visual_line(
    lines: list[list[OcrWord]],
    word: OcrWord,
) -> list[OcrWord] | None:
    for line in lines:
        if _same_visual_line(line, word):
            return line
    return None


def _same_visual_line(line: list[OcrWord], word: OcrWord) -> bool:
    top, _, _, bottom = _line_bounds(line)
    row_height = max(1, bottom - top)
    center_gap = abs(_word_center_y(word) - ((top + bottom) / 2))
    return center_gap <= max(row_height, word.height) * 0.45


def _line_sort_key(words: list[OcrWord]) -> tuple[int, int]:
    first_word = words[0]
    return (first_word.top, first_word.left)


def _line_confidence(words: list[OcrWord]) -> float:
    return sum(word.confidence for word in words) / len(words)


def _ocr_line_text_block(
    words: list[OcrWord],
    scale_x: float,
    scale_y: float,
) -> TextBlock:
    left, top, right, bottom = _line_bounds(words)
    height = max(1, bottom - top)
    text = _join_ocr_words(words)
    return TextBlock(
        (left * scale_x, top * scale_y, right * scale_x, bottom * scale_y),
        text,
        "Helvetica",
        max(6.0, height * scale_y * 0.78),
        0,
    )


def _line_bounds(words: list[OcrWord]) -> tuple[int, int, int, int]:
    left = min(word.left for word in words)
    top = min(word.top for word in words)
    right = max(word.left + word.width for word in words)
    bottom = max(word.top + word.height for word in words)
    return left, top, right, bottom


def _join_ocr_words(words: list[OcrWord]) -> str:
    sorted_words = sorted(words, key=lambda word: word.left)
    text = ""
    previous_word: OcrWord | None = None
    for word in sorted_words:
        if previous_word is None or _ocr_word_attaches_left(previous_word, word, text):
            text = f"{text}{word.text}"
        else:
            text = f"{text} {word.text}"
        previous_word = word
    return text


def _ocr_word_attaches_left(
    previous_word: OcrWord,
    word: OcrWord,
    text: str,
) -> bool:
    gap = word.left - (previous_word.left + previous_word.width)
    max_join_gap = max(2, min(previous_word.height, word.height) * 0.25)
    return gap <= max_join_gap or _token_attaches_left(word.text, text)


def _word_center_y(word: OcrWord) -> float:
    return word.top + (word.height / 2)


def _join_ocr_tokens(tokens: list[str]) -> str:
    text = ""
    for token in tokens:
        if not text or _token_attaches_left(token, text):
            text = f"{text}{token}"
            continue
        text = f"{text} {token}"
    return text


def _token_attaches_left(token: str, text: str) -> bool:
    left_punctuation = ".,:;!?%)]}"
    right_punctuation = "([{"
    return token in left_punctuation or text[-1] in right_punctuation


def _validated_page(doc: fitz.Document, page_num: int) -> fitz.Page:
    if page_num < 0 or page_num >= len(doc):
        expected = f"0..{max(len(doc) - 1, 0)}"
        raise ValueError(f"page_num {page_num} must be in range {expected}")
    return doc[page_num]


def _render_page_png(page: fitz.Page, dpi: int) -> bytes:
    pixmap = page.get_pixmap(dpi=dpi, alpha=False)
    return pixmap.tobytes("png")
