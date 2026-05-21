# PDF Editor

A web-based PDF editing application built with a **Python/FastAPI** backend and an **Angular** frontend. 

This application allows you to upload PDFs, automatically detects existing text (using PyMuPDF for native text, and falling back to Tesseract OCR for scanned images), previews edits directly on the page, preserves common PDF fonts when replacing text, and enables in-place editing through a seamless web interface.

## Prerequisites

Before you begin, ensure you have the following installed:
- **Node.js** (v18 or higher recommended) & npm
- **Python** (3.10 or higher)
- **Tesseract OCR** (Must be installed on your system to process scanned PDFs)

## Running the Application

This project consists of two separate applications that need to be run concurrently: the backend API and the frontend web server.

### Simple Manual Run

Install dependencies once:

```powershell
pip install -r backend/requirements.txt
npm --prefix frontend install
```

Then open two terminals from the repository root:

```powershell
.\scripts\backend.ps1
```

```powershell
.\scripts\frontend.ps1
```

Both scripts run in the foreground. Stop either server with `Ctrl+C`.

### Self-Contained Windows Publish

To create a local Windows package that does not require the end user to install
Python, Node.js, or Tesseract, run this from the repository root on the build
machine:

```powershell
.\scripts\publish-windows.ps1
```

The build machine still needs Python, Node.js, npm, and an installed Tesseract
runtime so the script can package them. The script installs PyInstaller if it is
missing, builds the Angular frontend, bundles Tesseract and `tessdata`, and
creates:

```text
publish\PdfEditor\PdfEditor.exe
publish\PdfEditor-windows.zip
```

Send the `publish\PdfEditor` folder or the zip to users. They can run
`PdfEditor.exe`; the app starts a local server and opens the browser at
`http://127.0.0.1:8000`. Runtime upload scratch files are stored inside
`publish\PdfEditor\data`, keeping the app portable.

### Manual Backend (FastAPI)

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
   pip install -r requirements.txt
   ```
5. Start the FastAPI server:
   ```bash
   python -m uvicorn main:app --host 127.0.0.1 --port 8000
   ```
   The backend will be running at `http://localhost:8000`.

### Manual Frontend (Angular)

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

### Use the Editor

Once both servers are running:
1. Open your web browser and navigate to `http://localhost:4200`.
2. Click "Choose File" to upload a `.pdf` document.
3. Wait for the application to analyze the text and rasterize the pages.
4. Click on any text block on the document image to edit it inline.
5. Choose a font, size, bold, and italic style for new or focused text.
6. Use "Add Text" to place new text anywhere on the current page.
7. Use each text block's arrow handle to reposition created or edited text.
8. Drag the right, bottom, or corner handles to stretch a text box.
9. Edit text and watch the page preview update without downloading.
10. Click "Download PDF" when you are ready to export the modified file.

## How it Works

- **Native Text:** The backend first tries to read text directly from the PDF structures.
- **OCR Fallback:** If a page contains very little or no native text (less than 50 characters), the backend assumes it's a scanned image, rasterizes it, cleans up the image for OCR, and groups confident Tesseract words into editable line blocks.
- **Live Preview:** While you edit, the frontend sends pending page edits to the backend, which renders a PNG preview using the same edit logic as the final PDF.
- **Self-Contained Runtime:** The packaged Windows build serves the compiled Angular frontend directly from FastAPI and uses bundled Tesseract files for OCR.
- **Font Matching:** Replacement edits send the detected source font, size, color, bold, and italic state so the backend can map common families like Arial, Helvetica, Calibri, Verdana, Times New Roman, Georgia, Garamond, and Courier New to compatible PDF fonts.
- **New Text:** Added text is inserted as text drawing only. The editor overlay is transparent and does not create a visible PDF rectangle.
- **Moving Text:** Replacement edits keep the original redaction area separate from the current placement, so moved text hides the old source text and renders at the new position.
- **Saving:** When you export, the backend locates the original coordinates of the text you edited, redacts the original area, and inserts your new text at the correct baseline.
