from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import fitz
from PIL import Image

from color_sampling import background_color_int_for_rect
from font_catalog import available_font_names, font_file_for_family, normalized_font_key
from font_mapping import resolve_pdf_font
from ocr_processing import (
    OcrData,
    _extract_ocr_words,
    _group_ocr_words_into_lines,
    _join_ocr_tokens,
    _prepare_ocr_image,
)
from pdf_document import PdfDocumentError, open_pdf_document
from pdf_editing import (
    TextEdit,
    _single_line_font_size,
    apply_page_edits,
)
from pdf_rendering import page_pixmap_with_pixel_limit, pixel_limited_dpi
from pdf_processing import (
    TextBlock,
    _analyze_page,
    _blocks_with_background_colors,
    _needs_ocr,
    analyze_document_pages,
    create_edited_pdf_bytes,
    render_preview_page_png,
)


class PdfProcessingTests(unittest.TestCase):
    def test_join_ocr_tokens_attaches_punctuation(self) -> None:
        tokens = ["Hello", ",", "world", "!"]

        self.assertEqual(_join_ocr_tokens(tokens), "Hello, world!")

    def test_extract_ocr_words_filters_low_confidence_rows(self) -> None:
        words = _extract_ocr_words(sample_ocr_data(["Good", "Noise"], ["88", "12"]))

        self.assertEqual([word.text for word in words], ["Good"])

    def test_group_ocr_words_into_lines_merges_words(self) -> None:
        words = _extract_ocr_words(sample_ocr_data(["Hello", "world"], ["90", "92"]))

        blocks = _group_ocr_words_into_lines(words, 0.5, 0.5)

        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0].text, "Hello world")
        self.assertEqual(blocks[0].bbox, (5.0, 6.0, 45.0, 15.0))

    def test_group_ocr_words_joins_same_word_fragments(self) -> None:
        words = _extract_ocr_words(split_word_ocr_data())

        blocks = _group_ocr_words_into_lines(words, 1, 1)

        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0].text, "GOVERNO")

    def test_group_ocr_words_splits_distant_columns(self) -> None:
        words = _extract_ocr_words(column_ocr_data())

        blocks = _group_ocr_words_into_lines(words, 1, 1)

        self.assertEqual([block.text for block in blocks], ["Left label", "Right value"])

    def test_prepare_ocr_image_returns_grayscale_image(self) -> None:
        image = Image.new("RGB", (8, 8), "white")

        prepared = _prepare_ocr_image(image)

        self.assertEqual(prepared.mode, "L")

    def test_needs_ocr_for_sparse_native_text(self) -> None:
        self.assertTrue(_needs_ocr([]))

    def test_analyze_page_keeps_native_text_when_ocr_fails(self) -> None:
        doc = fitz.open()
        page = doc.new_page(width=120, height=80)
        page.insert_text((10, 35), "Short", fontsize=12)

        with patch("pdf_processing.ocr_text_blocks", side_effect=RuntimeError("missing OCR")):
            analyzed = _analyze_page(page)

        blocks = analyzed["text_blocks"]
        self.assertEqual(blocks[0]["text"], "Short")
        doc.close()

    def test_analyze_page_keeps_native_text_when_ocr_render_fails(self) -> None:
        doc = fitz.open()
        page = doc.new_page(width=120, height=80)
        page.insert_text((10, 35), "Short", fontsize=12)

        with patch("ocr_processing._page_to_image", side_effect=ValueError("page too large")):
            analyzed = _analyze_page(page)

        blocks = analyzed["text_blocks"]
        self.assertEqual(blocks[0]["text"], "Short")
        doc.close()

    def test_analyze_page_allows_empty_pages_when_ocr_fails(self) -> None:
        doc = fitz.open()
        page = doc.new_page(width=120, height=80)

        with patch("pdf_processing.ocr_text_blocks", side_effect=RuntimeError("missing OCR")):
            analyzed = _analyze_page(page)

        self.assertEqual(analyzed["text_blocks"], [])
        doc.close()

    def test_analyze_document_keeps_page_when_text_analysis_fails(self) -> None:
        with TemporaryDirectory() as temp_dir:
            pdf_path = Path(temp_dir) / "bad-page.pdf"
            doc = fitz.open()
            doc.new_page(width=120, height=80)
            doc.save(pdf_path)
            doc.close()

            with patch("pdf_processing._native_text_blocks", side_effect=RuntimeError("bad page")):
                pages = analyze_document_pages(pdf_path)

        self.assertEqual(pages[0]["page_num"], 0)
        self.assertEqual(pages[0]["text_blocks"], [])

    def test_analyze_document_rejects_invalid_pdf(self) -> None:
        with TemporaryDirectory() as temp_dir:
            pdf_path = Path(temp_dir) / "invalid.pdf"
            pdf_path.write_bytes(b"not a pdf")

            with self.assertRaisesRegex(PdfDocumentError, "valid PDF file"):
                analyze_document_pages(pdf_path)

    def test_analyze_document_rejects_password_protected_pdf(self) -> None:
        with TemporaryDirectory() as temp_dir:
            pdf_path = Path(temp_dir) / "locked.pdf"
            doc = fitz.open()
            doc.new_page(width=120, height=80)
            doc.save(pdf_path, encryption=fitz.PDF_ENCRYPT_AES_256, owner_pw="owner", user_pw="secret")
            doc.close()

            with self.assertRaisesRegex(PdfDocumentError, "requires a password"):
                analyze_document_pages(pdf_path)

    def test_open_pdf_document_reads_valid_pdf(self) -> None:
        with TemporaryDirectory() as temp_dir:
            pdf_path = Path(temp_dir) / "valid.pdf"
            doc = fitz.open()
            doc.new_page(width=120, height=80)
            doc.save(pdf_path)
            doc.close()

            opened = open_pdf_document(pdf_path)
            self.assertEqual(len(opened), 1)
            opened.close()

    def test_render_preview_wraps_edit_runtime_errors(self) -> None:
        with TemporaryDirectory() as temp_dir:
            pdf_path = Path(temp_dir) / "preview.pdf"
            doc = fitz.open()
            doc.new_page(width=120, height=80)
            doc.save(pdf_path)
            doc.close()
            edit = TextEdit(0, (10, 10, 80, 30), "", "Text", "Helvetica", 12, 0, True)

            with patch("pdf_processing.apply_document_edits", side_effect=RuntimeError("bad edit")):
                with self.assertRaisesRegex(PdfDocumentError, "preview failed"):
                    render_preview_page_png(pdf_path, 0, [edit])

    def test_create_edited_pdf_wraps_save_runtime_errors(self) -> None:
        with TemporaryDirectory() as temp_dir:
            pdf_path = Path(temp_dir) / "save.pdf"
            doc = fitz.open()
            doc.new_page(width=120, height=80)
            doc.save(pdf_path)
            doc.close()

            with patch("pdf_processing.apply_document_edits", side_effect=RuntimeError("bad edit")):
                with self.assertRaisesRegex(PdfDocumentError, "could not be saved"):
                    create_edited_pdf_bytes(pdf_path, [])

    def test_single_line_font_size_respects_rect_width(self) -> None:
        rect = fitz.Rect(0, 0, 20, 20)
        edit = TextEdit(0, (0, 0, 20, 20), "", "Very long replacement text", "Arial", 12, 0)

        font_size = _single_line_font_size(rect, edit)

        self.assertLess(font_size, 10)

    def test_apply_page_edits_replaces_original_text(self) -> None:
        doc = fitz.open()
        page = doc.new_page(width=220, height=120)
        page.insert_text((20, 45), "Original Text", fontsize=12)

        edit = TextEdit(
            0,
            (18, 30, 110, 50),
            "Original Text",
            "Edited Text",
            "ArialMT",
            12,
            0,
        )
        apply_page_edits(page, [edit])

        page_text = page.get_text()
        self.assertIn("Edited Text", page_text)
        self.assertNotIn("Original Text", page_text)
        doc.close()

    def test_apply_page_edits_adds_insert_only_text(self) -> None:
        doc = fitz.open()
        page = doc.new_page(width=220, height=120)
        page.insert_text((20, 45), "Original Text", fontsize=12)

        edit = TextEdit(0, (20, 70, 160, 90), "", "New Text", "Arial", 14, 0, True)
        apply_page_edits(page, [edit])

        page_text = page.get_text()
        self.assertIn("Original Text", page_text)
        self.assertIn("New Text", page_text)
        doc.close()

    def test_apply_page_edits_preserves_inserted_bold_italic(self) -> None:
        doc = fitz.open()
        page = doc.new_page(width=260, height=120)
        edit = TextEdit(0, (20, 30, 240, 58), "", "Styled Text", "Arial", 14, 0, True, None, True, True)

        apply_page_edits(page, [edit])

        span = first_text_span(page)
        font_name = str(span["font"]).lower()
        self.assertIn("bold", font_name)
        self.assertTrue("italic" in font_name or "oblique" in font_name)
        doc.close()

    def test_apply_page_edits_preserves_replacement_bold_italic(self) -> None:
        doc = fitz.open()
        page = doc.new_page(width=260, height=120)
        page.insert_text((20, 45), "Plain Text", fontsize=12)

        edit = TextEdit(0, (18, 30, 130, 52), "Plain Text", "Styled", "Arial", 14, 0, False, None, True, True)
        apply_page_edits(page, [edit])

        font_name = str(first_text_span(page)["font"]).lower()
        self.assertIn("bold", font_name)
        self.assertTrue("italic" in font_name or "oblique" in font_name)
        doc.close()

    def test_apply_page_edits_preserves_gray_replacement_background(self) -> None:
        doc = fitz.open()
        page = doc.new_page(width=260, height=120)
        page.draw_rect(fitz.Rect(20, 20, 220, 55), color=None, fill=(0.82, 0.82, 0.82))
        page.insert_text((30, 43), "Status", fontsize=14)

        edit = TextEdit(0, (28, 25, 150, 50), "Status", "Ok", "Arial", 14, 0)
        apply_page_edits(page, [edit])

        red, green, blue = mean_clip_rgb(page, fitz.Rect(110, 30, 120, 42))
        self.assertLess(abs(red - 209), 20)
        self.assertLess(abs(green - 209), 20)
        self.assertLess(abs(blue - 209), 20)
        doc.close()

    def test_background_color_int_for_rect_reads_gray_fill(self) -> None:
        doc = fitz.open()
        page = doc.new_page(width=120, height=80)
        page.draw_rect(fitz.Rect(10, 10, 90, 50), color=None, fill=(0.82, 0.82, 0.82))

        color = background_color_int_for_rect(page, fitz.Rect(15, 15, 80, 45))

        self.assertEqual(color, 0xD1D1D1)
        doc.close()

    def test_blocks_with_background_colors_adds_payload_color(self) -> None:
        doc = fitz.open()
        page = doc.new_page(width=120, height=80)
        page.draw_rect(fitz.Rect(10, 10, 90, 50), color=None, fill=(0.82, 0.82, 0.82))
        block = TextBlock((20, 20, 80, 40), "Status", "Helvetica", 12, 0)

        sampled = _blocks_with_background_colors(page, [block])[0]

        self.assertEqual(sampled.as_payload()["background_color"], 0xD1D1D1)
        doc.close()

    def test_blocks_with_background_colors_defaults_when_sampling_fails(self) -> None:
        doc = fitz.open()
        page = doc.new_page(width=120, height=80)
        block = TextBlock((20, 20, 80, 40), "Status", "Helvetica", 12, 0)

        with patch("pdf_processing.background_color_int_for_rect", side_effect=RuntimeError("bad clip")):
            sampled = _blocks_with_background_colors(page, [block])[0]

        self.assertEqual(sampled.as_payload()["background_color"], 0xFFFFFF)
        doc.close()

    def test_pixel_limited_dpi_keeps_small_page_resolution(self) -> None:
        dpi = pixel_limited_dpi(fitz.Rect(0, 0, 200, 200), 150, 16_000_000)

        self.assertEqual(dpi, 150)

    def test_pixel_limited_dpi_reduces_large_page_resolution(self) -> None:
        dpi = pixel_limited_dpi(fitz.Rect(0, 0, 5000, 5000), 350, 10_000_000)

        self.assertLess(dpi, 350)
        self.assertGreaterEqual(dpi, 1)

    def test_page_pixmap_with_pixel_limit_renders_page(self) -> None:
        doc = fitz.open()
        page = doc.new_page(width=120, height=80)

        pixmap = page_pixmap_with_pixel_limit(page, 72, 1_000_000)

        self.assertGreater(pixmap.width, 0)
        doc.close()

    def test_resolve_pdf_font_maps_common_font_names(self) -> None:
        self.assertIn(resolve_pdf_font("ABCDEE+ArialMT").fitz_name, ("FArialRegular", "helv"))
        self.assertIn(resolve_pdf_font("TimesNewRomanPSMT").fitz_name, ("FTimesnewromanRegular", "tiro"))
        self.assertIn(resolve_pdf_font("Verdana", bold=True).fitz_name, ("FVerdanaBold", "hebo"))
        self.assertIn(resolve_pdf_font("Courier New", italic=True).fitz_name, ("FCouriernewItalic", "coit"))

    def test_normalized_font_key_strips_pdf_subset_and_postscript_markers(self) -> None:
        self.assertEqual(normalized_font_key("ABCDEE+TimesNewRomanPSMT"), "timesnewroman")

    def test_available_font_names_exposes_large_system_catalog(self) -> None:
        names = available_font_names()
        if len(names) < 100:
            self.skipTest("System font catalog is not available")

        self.assertGreaterEqual(len(names), 100)

    def test_resolve_pdf_font_uses_installed_system_font_catalog(self) -> None:
        font_file = font_file_for_family("Agency FB Bold", True, False)
        if font_file is None:
            self.skipTest("Agency FB is not installed")

        choice = resolve_pdf_font("Agency FB Bold", True, False)

        self.assertEqual(Path(str(choice.file_path)), font_file)

    def test_apply_page_edits_redacts_original_while_moving_text(self) -> None:
        doc = fitz.open()
        page = doc.new_page(width=260, height=140)
        page.insert_text((20, 45), "Move Me", fontsize=12)

        edit = TextEdit(0, (120, 70, 190, 90), "Move Me", "Move Me", "Arial", 12, 0, False, (18, 30, 90, 50))
        apply_page_edits(page, [edit])

        words = page.get_text("words")
        moved_word = next(word for word in words if word[4] == "Move")
        self.assertGreater(moved_word[0], 100)
        doc.close()


def sample_ocr_data(text: list[str], confidence: list[str]) -> OcrData:
    item_count = len(text)
    return {
        "text": text,
        "conf": confidence,
        "left": [10, 55][:item_count],
        "top": [12, 12][:item_count],
        "width": [35, 35][:item_count],
        "height": [18, 18][:item_count],
        "block_num": [1, 1][:item_count],
        "par_num": [1, 1][:item_count],
        "line_num": [1, 1][:item_count],
    }


def split_word_ocr_data() -> OcrData:
    return {
        "text": ["G", "OVERNO"],
        "conf": ["91", "93"],
        "left": [10, 20],
        "top": [10, 11],
        "width": [10, 58],
        "height": [20, 19],
        "block_num": [1, 2],
        "par_num": [1, 1],
        "line_num": [1, 1],
    }


def column_ocr_data() -> OcrData:
    return {
        "text": ["Left", "label", "Right", "value"],
        "conf": ["91", "93", "94", "92"],
        "left": [10, 52, 230, 280],
        "top": [10, 11, 10, 11],
        "width": [32, 48, 40, 45],
        "height": [18, 17, 18, 17],
        "block_num": [1, 1, 2, 2],
        "par_num": [1, 1, 1, 1],
        "line_num": [1, 1, 1, 1],
    }


def first_text_span(page: fitz.Page) -> dict[str, object]:
    text_page = page.get_text("dict")
    for block in text_page["blocks"]:
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                return span
    raise AssertionError("Expected page to contain at least one text span")


def mean_clip_rgb(page: fitz.Page, rect: fitz.Rect) -> tuple[int, int, int]:
    pixmap = page.get_pixmap(clip=rect, alpha=False)
    red_total = sum(pixmap.samples[index] for index in range(0, len(pixmap.samples), 3))
    green_total = sum(pixmap.samples[index] for index in range(1, len(pixmap.samples), 3))
    blue_total = sum(pixmap.samples[index] for index in range(2, len(pixmap.samples), 3))
    pixel_count = pixmap.width * pixmap.height
    return red_total // pixel_count, green_total // pixel_count, blue_total // pixel_count


if __name__ == "__main__":
    unittest.main()
