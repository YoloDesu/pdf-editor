import os
import shutil
import unittest
import uuid
from pathlib import Path

from frontend_static import _frontend_response
from pdf_processing import _tesseract_config
from runtime_paths import runtime_temp_dir


class RuntimePackagingTests(unittest.TestCase):
    def test_runtime_temp_dir_uses_configured_data_dir(self) -> None:
        with TemporaryEnvironmentVariable("PDF_EDITOR_DATA_DIR", "C:/temp/pdf-editor-test"):
            self.assertEqual(runtime_temp_dir(), Path("C:/temp/pdf-editor-test/temp_pdfs"))

    def test_tesseract_config_uses_configured_tessdata_dir(self) -> None:
        with TemporaryWorkspaceDirectory() as directory:
            with TemporaryEnvironmentVariable("TESSDATA_PREFIX", str(directory)):
                self.assertIn(f'--tessdata-dir "{directory}"', _tesseract_config())

    def test_frontend_response_serves_existing_asset(self) -> None:
        with TemporaryWorkspaceDirectory() as static_dir:
            (static_dir / "main.js").write_text("console.log('ok')")
            (static_dir / "index.html").write_text("<app-root></app-root>")

            response = _frontend_response(static_dir, "main.js")

            self.assertEqual(Path(response.path), static_dir / "main.js")

    def test_frontend_response_falls_back_to_index(self) -> None:
        with TemporaryWorkspaceDirectory() as static_dir:
            (static_dir / "index.html").write_text("<app-root></app-root>")

            response = _frontend_response(static_dir, "editor/page")

            self.assertEqual(Path(response.path), static_dir / "index.html")


class TemporaryEnvironmentVariable:
    def __init__(self, name: str, value: str) -> None:
        self.name = name
        self.value = value
        self.previous = os.environ.get(name)

    def __enter__(self) -> None:
        os.environ[self.name] = self.value

    def __exit__(self, *_: object) -> None:
        if self.previous is None:
            os.environ.pop(self.name, None)
            return
        os.environ[self.name] = self.previous


class TemporaryWorkspaceDirectory:
    def __init__(self) -> None:
        self.path = Path(__file__).parent / ".test_runtime" / uuid.uuid4().hex

    def __enter__(self) -> Path:
        self.path.mkdir(parents=True)
        return self.path

    def __exit__(self, *_: object) -> None:
        shutil.rmtree(self.path, ignore_errors=True)
        try:
            self.path.parent.rmdir()
        except OSError:
            return


if __name__ == "__main__":
    unittest.main()
