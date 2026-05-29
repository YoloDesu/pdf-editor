from pathlib import Path

import fitz


class PdfDocumentError(RuntimeError):
    pass


def open_pdf_document(pdf_path: Path) -> fitz.Document:
    """Open an unlocked, valid PDF document for editing.

    Example: `open_pdf_document(Path("temp_pdfs/example.pdf"))`
    """
    try:
        doc = fitz.open(pdf_path)
    except (fitz.FileDataError, fitz.EmptyFileError, RuntimeError, ValueError, OSError) as error:
        message = f"PDF {pdf_path.name!r} could not be opened; expected a valid PDF file"
        raise PdfDocumentError(f"{message}: {error}") from error

    if doc.needs_pass and doc.authenticate("") == 0:
        doc.close()
        message = f"PDF {pdf_path.name!r} requires a password; expected an unlocked PDF file"
        raise PdfDocumentError(message)
    return doc
