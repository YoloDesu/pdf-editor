import fitz
import os
import pytesseract
from PIL import Image

doc = fitz.open()
page = doc.new_page()
page.insert_text((50, 50), "Original Text", fontsize=12)

rect = fitz.Rect(50, 38, 150, 52)
page.add_redact_annot(rect, fill=(1, 1, 1))
page.apply_redactions()

text = "Edited Text That Is Longer"
font_size = rect.height * 0.8

# Test insert_textbox
rc = page.insert_textbox(rect, text, fontsize=font_size, color=(0, 0, 0))
print(f"insert_textbox return code: {rc}. If >= 0, it fit. If < 0, it did not fit.")

# Test insert_text instead
page.insert_text((50, 100), "Inserted with insert_text", fontsize=font_size, color=(0, 0, 0))

doc.save("backend/test_edited.pdf")

try:
    print("Tesseract Version:", pytesseract.get_tesseract_version())
except Exception as e:
    print("Tesseract Error:", e)
