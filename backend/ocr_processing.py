from dataclasses import dataclass
from io import BytesIO
import os
from typing import TypedDict, cast

import fitz
from PIL import Image, ImageFilter, ImageOps
import pytesseract

from pdf_rendering import MAX_OCR_PIXELS, page_pixmap_with_pixel_limit
from pdf_text import TextBlock
from runtime_paths import bundled_tessdata_dir, bundled_tesseract_cmd

OCR_DPI = 350
MIN_OCR_WORD_CONFIDENCE = 35.0
MIN_OCR_LINE_CONFIDENCE = 45.0
DEFAULT_TESSERACT_CONFIGS = (
    "--oem 3 --psm 3 -c preserve_interword_spaces=1",
    "--oem 3 --psm 6 -c preserve_interword_spaces=1",
    "--oem 3 --psm 11",
)


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


def ocr_text_blocks(page: fitz.Page) -> list[TextBlock]:
    """Extract editable line blocks from a rasterized PDF page with OCR.

    Example: `ocr_text_blocks(page)`
    """
    image = _prepare_ocr_image(_page_to_image(page, OCR_DPI))
    ocr_data = _best_ocr_data(image, page.number)
    scale_x = page.rect.width / image.width
    scale_y = page.rect.height / image.height
    words = _extract_ocr_words(ocr_data)
    return _group_ocr_words_into_lines(words, scale_x, scale_y)


def _page_to_image(page: fitz.Page, dpi: int) -> Image.Image:
    pixmap = page_pixmap_with_pixel_limit(page, dpi, MAX_OCR_PIXELS)
    png_bytes = pixmap.tobytes("png")
    return Image.open(BytesIO(png_bytes)).convert("RGB")


def _prepare_ocr_image(image: Image.Image) -> Image.Image:
    corrected = ImageOps.exif_transpose(image.convert("RGB"))
    grayscale = ImageOps.grayscale(corrected)
    denoised = grayscale.filter(ImageFilter.MedianFilter(size=3))
    contrasted = ImageOps.autocontrast(denoised, cutoff=1)
    return contrasted.filter(ImageFilter.UnsharpMask(radius=1, percent=180))


def _best_ocr_data(image: Image.Image, page_num: int) -> OcrData:
    best_data: OcrData | None = None
    best_score = (-1, -1.0)
    last_error: RuntimeError | None = None
    for config in _ocr_config_candidates():
        try:
            data = _run_tesseract_data(image, page_num, config)
        except RuntimeError as error:
            last_error = error
            continue

        score = _ocr_data_score(data)
        if score > best_score:
            best_data = data
            best_score = score
        if _ocr_score_is_good(score):
            return data

    if best_data is not None:
        return best_data
    if last_error is not None:
        raise last_error
    raise RuntimeError(f"OCR failed on page {page_num}; expected Tesseract word data")


def _ocr_config_candidates() -> tuple[str, ...]:
    configured = os.getenv("TESSERACT_CONFIG")
    if configured:
        return (configured,)
    return DEFAULT_TESSERACT_CONFIGS


def _ocr_data_score(ocr_data: OcrData) -> tuple[int, float]:
    words = _extract_ocr_words(ocr_data)
    if not words:
        return 0, 0.0
    average_confidence = sum(word.confidence for word in words) / len(words)
    return len(words), average_confidence


def _ocr_score_is_good(score: tuple[int, float]) -> bool:
    word_count, average_confidence = score
    return word_count >= 12 and average_confidence >= 55.0


def _run_tesseract_data(image: Image.Image, page_num: int, config: str) -> OcrData:
    _configure_tesseract_runtime()
    language = os.getenv("TESSERACT_LANG", "eng")
    try:
        raw_data = pytesseract.image_to_data(
            image,
            lang=language,
            config=_tesseract_config(config),
            output_type=pytesseract.Output.DICT,
        )
    except (pytesseract.TesseractError, pytesseract.TesseractNotFoundError) as error:
        message = f"OCR failed on page {page_num}; expected Tesseract word data"
        raise RuntimeError(f"{message}: {error}") from error
    return cast(OcrData, raw_data)


def _configure_tesseract_runtime() -> None:
    command = bundled_tesseract_cmd()
    if command is not None:
        pytesseract.pytesseract.tesseract_cmd = str(command)


def _tesseract_config(config: str | None = None) -> str:
    selected_config = config or os.getenv("TESSERACT_CONFIG", DEFAULT_TESSERACT_CONFIGS[0])
    tessdata_dir = bundled_tessdata_dir()
    if tessdata_dir is None:
        return selected_config
    return f'{selected_config} --tessdata-dir "{tessdata_dir}"'


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
    segments = [segment for line in lines for segment in _split_ocr_line_segments(line)]
    return [
        _ocr_line_text_block(line_words, scale_x, scale_y)
        for line_words in segments
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


def _split_ocr_line_segments(words: list[OcrWord]) -> list[list[OcrWord]]:
    segments: list[list[OcrWord]] = []
    current: list[OcrWord] = []
    previous_word: OcrWord | None = None
    for word in words:
        if previous_word is not None and _starts_new_line_segment(previous_word, word):
            segments.append(current)
            current = []
        current.append(word)
        previous_word = word

    if current:
        segments.append(current)
    return segments


def _starts_new_line_segment(previous_word: OcrWord, word: OcrWord) -> bool:
    gap = word.left - (previous_word.left + previous_word.width)
    max_height = max(previous_word.height, word.height)
    return gap > max(22, max_height * 3.5)


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
