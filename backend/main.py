from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List
import fitz  # PyMuPDF
import os
import uuid
import pytesseract
from PIL import Image
import io

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

TEMP_DIR = "temp_pdfs"
os.makedirs(TEMP_DIR, exist_ok=True)

class EditRequest(BaseModel):
    page_num: int
    bbox: List[float]  # [x0, y0, x1, y1]
    old_text: str
    new_text: str

class SaveRequest(BaseModel):
    edits: List[EditRequest]

@app.post("/upload")
async def upload_pdf(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")
        
    doc_id = str(uuid.uuid4())
    file_path = os.path.join(TEMP_DIR, f"{doc_id}.pdf")
    
    with open(file_path, "wb") as f:
        f.write(await file.read())
        
    return {"doc_id": doc_id}

@app.get("/document/{doc_id}/pages")
async def get_document_pages(doc_id: str):
    file_path = os.path.join(TEMP_DIR, f"{doc_id}.pdf")
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Document not found")
        
    try:
        doc = fitz.open(file_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to open PDF: {str(e)}")
        
    pages_data = []
    
    for page_num in range(len(doc)):
        page = doc[page_num]
        
        # We use "dict" extraction to get bounding boxes with text and formatting
        text_dict = page.get_text("dict")
        blocks = []
        
        native_text_len = 0
        for block in text_dict.get("blocks", []):
            if "lines" in block:
                for line in block["lines"]:
                    for span in line["spans"]:
                        text = span["text"].strip()
                        if text:
                            native_text_len += len(text)
                            blocks.append({
                                "bbox": span["bbox"],
                                "text": text,
                                "font": span["font"],
                                "size": span["size"],
                                "color": span["color"]
                            })
                            
        # OCR Fallback if page seems to be primarily an image (less than 50 chars of native text)
        has_native_text = native_text_len > 50
        if not has_native_text:
            pix = page.get_pixmap(dpi=300) # High DPI for better OCR
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            ocr_data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
            
            # Since OCR is on a 300 DPI image, we need to map coordinates back to PDF space (72 DPI)
            scale_x = page.rect.width / pix.width
            scale_y = page.rect.height / pix.height
            
            n_boxes = len(ocr_data['text'])
            for i in range(n_boxes):
                if int(ocr_data['conf'][i]) > 60: # Confidence threshold
                    text = ocr_data['text'][i].strip()
                    if text:
                        (x, y, w, h) = (ocr_data['left'][i], ocr_data['top'][i], ocr_data['width'][i], ocr_data['height'][i])
                        # Map to PDF points
                        x0 = x * scale_x
                        y0 = y * scale_y
                        x1 = (x + w) * scale_x
                        y1 = (y + h) * scale_y
                        blocks.append({
                            "bbox": [x0, y0, x1, y1],
                            "text": text,
                            "font": "Helvetica", # Default fallback
                            "size": h * scale_y * 0.8, # Rough estimate
                            "color": 0 # Black
                        })
            
        pages_data.append({
            "page_num": page_num,
            "width": page.rect.width,
            "height": page.rect.height,
            "text_blocks": blocks
        })
        
    doc.close()
    return {"pages": pages_data}

@app.get("/document/{doc_id}/page/{page_num}/image")
async def get_page_image(doc_id: str, page_num: int):
    file_path = os.path.join(TEMP_DIR, f"{doc_id}.pdf")
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Document not found")
        
    doc = fitz.open(file_path)
    if page_num < 0 or page_num >= len(doc):
        doc.close()
        raise HTTPException(status_code=404, detail="Page not found")
        
    page = doc[page_num]
    pix = page.get_pixmap(dpi=150) # Standard DPI for web viewing
    img_path = os.path.join(TEMP_DIR, f"{doc_id}_page_{page_num}.png")
    pix.save(img_path)
    doc.close()
    
    return FileResponse(img_path, media_type="image/png")

@app.post("/document/{doc_id}/save")
async def save_document(doc_id: str, request: SaveRequest):
    file_path = os.path.join(TEMP_DIR, f"{doc_id}.pdf")
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Document not found")
        
    doc = fitz.open(file_path)
    
    for edit in request.edits:
        if 0 <= edit.page_num < len(doc):
            page = doc[edit.page_num]
            
            # Extract coordinates
            rect = fitz.Rect(edit.bbox)
            
            # Redact old text
            page.add_redact_annot(rect, fill=(1, 1, 1)) # White fill
            page.apply_redactions()
            
            # Calculate font size to fit the height of the original bbox
            font_size = rect.height * 0.8 # Rough estimation
            
            # Insert new text using insert_text so it isn't constrained by the rect width
            # We place it at the x0 coordinate, and approximate the baseline using y1 - 20% of height
            baseline_y = rect.y1 - (rect.height * 0.2)
            page.insert_text(fitz.Point(rect.x0, baseline_y), edit.new_text, fontsize=font_size, color=(0, 0, 0))
            
    output_path = os.path.join(TEMP_DIR, f"{doc_id}_edited.pdf")
    doc.save(output_path)
    doc.close()
    
    return FileResponse(
        output_path, 
        media_type="application/pdf", 
        filename="edited_document.pdf"
    )
