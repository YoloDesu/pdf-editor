# PDF Editor

A web-based PDF editing application built with a **Python/FastAPI** backend and an **Angular** frontend. 

This application allows you to upload PDFs, automatically detects existing text (using PyMuPDF for native text, and falling back to Tesseract OCR for scanned images), and enables in-place editing of that text through a seamless web interface.

## Prerequisites

Before you begin, ensure you have the following installed:
- **Node.js** (v18 or higher recommended) & npm
- **Python** (3.10 or higher)
- **Tesseract OCR** (Must be installed on your system to process scanned PDFs)

## Running the Application

This project consists of two separate applications that need to be run concurrently: the backend API and the frontend web server.

### 1. Start the Backend (FastAPI)

The backend handles PDF parsing, text extraction, OCR, and saving the final document.

1. Open a terminal and navigate to the `backend` directory:
   ```bash
   cd backend
   ```
2. Create a virtual environment (optional but recommended):
   ```bash
   python -m venv venv
   ```
3. Activate the virtual environment:
   - On Windows: `venv\Scripts\activate`
   - On macOS/Linux: `source venv/bin/activate`
   > **Note:** If you are using MSYS2 on Windows (like in the original development environment), you might use system packages instead.
4. Install the required dependencies:
   ```bash
   pip install fastapi uvicorn pymupdf pytesseract Pillow python-multipart
   ```
5. Start the FastAPI server:
   ```bash
   python -m uvicorn main:app --port 8000 --reload
   ```
   The backend will be running at `http://localhost:8000`.

### 2. Start the Frontend (Angular)

The frontend provides the user interface for viewing and editing the PDFs.

1. Open a new, separate terminal and navigate to the `frontend` directory:
   ```bash
   cd frontend
   ```
2. Install the Node.js dependencies:
   ```bash
   npm install
   ```
3. Start the Angular development server:
   ```bash
   npm start
   ```
   The frontend will compile and start running.

### 3. Use the Editor

Once both servers are running:
1. Open your web browser and navigate to `http://localhost:4200`.
2. Click "Choose File" to upload a `.pdf` document.
3. Wait for the application to analyze the text and rasterize the pages.
4. Click on any text block on the document image to edit it inline.
5. Click "Save Changes" to download the modified PDF.

## How it Works

- **Native Text:** The backend first tries to read text directly from the PDF structures.
- **OCR Fallback:** If a page contains very little or no native text (less than 50 characters), the backend assumes it's a scanned image, rasterizes it, and runs Tesseract OCR to find the bounding boxes of the words.
- **Saving:** When you save, the backend locates the original coordinates of the text you edited, redacts the original area, and inserts your new text at the correct baseline.