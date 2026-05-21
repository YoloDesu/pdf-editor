from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

from runtime_paths import frontend_dist_dir


def mount_frontend(app: FastAPI) -> None:
    """Serve the compiled Angular app when it is available.

    Example: `mount_frontend(app)`
    """
    static_dir = frontend_dist_dir()
    if static_dir is None:
        return

    @app.get("/{frontend_path:path}", include_in_schema=False)
    async def serve_frontend(frontend_path: str) -> FileResponse:
        return _frontend_response(static_dir, frontend_path)


def _frontend_response(static_dir: Path, frontend_path: str) -> FileResponse:
    asset_path = _safe_frontend_asset(static_dir, frontend_path)
    if asset_path is not None:
        return FileResponse(asset_path)
    return FileResponse(static_dir / "index.html")


def _safe_frontend_asset(static_dir: Path, frontend_path: str) -> Path | None:
    candidate = (static_dir / frontend_path).resolve()
    if not _is_relative_to(candidate, static_dir.resolve()):
        return None
    if candidate.is_file():
        return candidate
    return None


def _is_relative_to(candidate: Path, parent: Path) -> bool:
    try:
        candidate.relative_to(parent)
    except ValueError:
        return False
    return True
