from pathlib import Path
import os
import sys

APP_NAME = "PdfEditor"


def bundle_root() -> Path:
    """Return the PyInstaller bundle root or the backend source directory.

    Example: `bundle_root() / "frontend_dist"`
    """
    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root is not None:
        return Path(str(frozen_root))
    return Path(__file__).resolve().parent


def frontend_dist_dir() -> Path | None:
    """Return the compiled Angular directory when it exists.

    Example: `frontend_dist_dir() is not None`
    """
    candidates = [bundle_root() / "frontend_dist", _repo_frontend_dist()]
    for candidate in candidates:
        if (candidate / "index.html").exists():
            return candidate
    return None


def runtime_temp_dir() -> Path:
    """Return a writable temp directory for uploaded PDFs.

    Example: `runtime_temp_dir().name == "temp_pdfs"`
    """
    configured = os.getenv("PDF_EDITOR_DATA_DIR")
    if configured:
        return Path(configured) / "temp_pdfs"
    if getattr(sys, "frozen", False):
        return _executable_dir() / "data" / "temp_pdfs"
    return Path("temp_pdfs")


def bundled_tesseract_cmd() -> Path | None:
    """Return the bundled Tesseract executable if present.

    Example: `bundled_tesseract_cmd()`
    """
    configured = os.getenv("TESSERACT_CMD")
    if configured:
        return Path(configured)
    return _existing_path(bundle_root() / "tesseract" / "tesseract.exe")


def bundled_tessdata_dir() -> Path | None:
    """Return the bundled tessdata directory if present.

    Example: `bundled_tessdata_dir()`
    """
    configured = os.getenv("TESSDATA_PREFIX")
    if configured:
        return Path(configured)
    return _existing_path(bundle_root() / "tesseract" / "tessdata")


def _repo_frontend_dist() -> Path:
    repo_root = Path(__file__).resolve().parent.parent
    return repo_root / "frontend" / "dist" / "frontend" / "browser"


def _executable_dir() -> Path:
    executable = getattr(sys, "executable", "")
    if executable:
        return Path(str(executable)).resolve().parent
    return bundle_root()


def _existing_path(path: Path) -> Path | None:
    if path.exists():
        return path
    return None
