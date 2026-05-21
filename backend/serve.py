from threading import Timer
import os
import webbrowser

import uvicorn

from main import app


def main() -> None:
    """Run the packaged local PDF editor server.

    Example: `python serve.py`
    """
    host = os.getenv("PDF_EDITOR_HOST", "127.0.0.1")
    port = int(os.getenv("PDF_EDITOR_PORT", "8000"))
    _open_browser_later(f"http://{host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="info")


def _open_browser_later(url: str) -> None:
    if os.getenv("PDF_EDITOR_OPEN_BROWSER", "1") == "0":
        return
    Timer(1.0, lambda: webbrowser.open(url)).start()


if __name__ == "__main__":
    main()
