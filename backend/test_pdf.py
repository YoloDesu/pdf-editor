import unittest

import fitz

from pdf_editing import TextEdit, apply_page_edits


class PdfEditSmokeTests(unittest.TestCase):
    def test_text_edit_can_be_rendered_to_pdf_bytes(self) -> None:
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((50, 50), "Original Text", fontsize=12)

        edit = TextEdit(
            0,
            (48, 36, 140, 56),
            "Original Text",
            "Edited Text",
            "Helvetica",
            12,
            0,
        )
        apply_page_edits(page, [edit])

        pdf_bytes = doc.tobytes()
        self.assertGreater(len(pdf_bytes), 0)
        self.assertIn("Edited Text", page.get_text())
        doc.close()


if __name__ == "__main__":
    unittest.main()
