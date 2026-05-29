from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
import re

import fitz

WINDOWS_FONT_DIR = Path("C:/Windows/Fonts")
FONT_EXTENSIONS = (".ttf", ".otf", ".ttc")
SOURCE_TRAILING_MARKERS = ("psmt", "mt", "std", "cid")
SOURCE_STYLE_SUFFIXES = ("bolditalic", "boldoblique", "italic", "oblique", "regular", "bold")
FONT_NAME_STYLE_SUFFIXES = ("Bold Italic", "Bold Oblique", "Italic", "Oblique", "Regular", "Bold")
FONT_KEY_ALIASES = {
    "arialmt": "arial",
    "helvetica": "arial",
    "helveticaneue": "arial",
    "times": "timesnewroman",
    "timesroman": "timesnewroman",
}


@dataclass(frozen=True)
class FontFace:
    family: str
    path: Path
    bold: bool
    italic: bool


def available_font_names(limit: int = 140) -> list[str]:
    """Return installed font family names for editor controls.

    Example: `available_font_names(100)`
    """
    names = [faces[0].family for faces in _system_font_faces_by_family().values()]
    return sorted(names, key=str.lower)[:limit]


def font_file_for_family(
    source_name: str,
    bold: bool,
    italic: bool,
) -> Path | None:
    """Return the best installed font file for a PDF or editor font name.

    Example: `font_file_for_family("Arial-BoldMT", True, False)`
    """
    family_key = _matching_family_key(normalized_font_key(source_name))
    if family_key is None:
        return None
    return _best_face_for_style(_system_font_faces_by_family()[family_key], bold, italic).path


def normalized_font_key(name: str) -> str:
    """Normalize a PDF, browser, or Windows font family name for matching.

    Example: `normalized_font_key("ABCDEE+TimesNewRomanPSMT")`
    """
    compact = _compact_font_name(name)
    compact = _without_trailing_markers(compact)
    return _without_style_suffix(compact)


@lru_cache(maxsize=1)
def _system_font_faces_by_family() -> dict[str, tuple[FontFace, ...]]:
    families: dict[str, list[FontFace]] = {}
    for path in _system_font_files():
        face = _font_face_from_path(path)
        if face is None:
            continue
        families.setdefault(normalized_font_key(face.family), []).append(face)
    return {key: tuple(_sorted_faces(faces)) for key, faces in families.items()}


def _system_font_files() -> list[Path]:
    if not WINDOWS_FONT_DIR.exists():
        return []
    return sorted(
        path for path in WINDOWS_FONT_DIR.iterdir()
        if path.suffix.lower() in FONT_EXTENSIONS
    )


def _font_face_from_path(path: Path) -> FontFace | None:
    try:
        font_name = fitz.Font(fontfile=str(path)).name.strip()
    except (RuntimeError, OSError, ValueError):
        return None
    if not font_name:
        return None
    return FontFace(_family_from_font_name(font_name), path, _is_bold(font_name), _is_italic(font_name))


def _family_from_font_name(font_name: str) -> str:
    normalized = re.sub(r"\s+", " ", font_name).strip()
    for suffix in FONT_NAME_STYLE_SUFFIXES:
        suffix_text = f" {suffix}"
        if normalized.lower().endswith(suffix_text.lower()):
            return normalized[: -len(suffix_text)]
    return normalized


def _is_bold(font_name: str) -> bool:
    compact = _compact_font_name(font_name)
    return any(marker in compact for marker in ("bold", "black", "heavy"))


def _is_italic(font_name: str) -> bool:
    compact = _compact_font_name(font_name)
    return "italic" in compact or "oblique" in compact


def _matching_family_key(source_key: str) -> str | None:
    if not source_key:
        return None
    families = _system_font_faces_by_family()
    aliased_key = FONT_KEY_ALIASES.get(source_key, source_key)
    if aliased_key in families:
        return aliased_key

    matches = [key for key in families if aliased_key.startswith(key) or key.startswith(aliased_key)]
    if not matches:
        return None
    return max(matches, key=len)


def _best_face_for_style(faces: tuple[FontFace, ...], bold: bool, italic: bool) -> FontFace:
    return max(faces, key=lambda face: _style_score(face, bold, italic))


def _style_score(face: FontFace, bold: bool, italic: bool) -> tuple[int, int, int, int]:
    exact = face.bold == bold and face.italic == italic
    regular = not face.bold and not face.italic
    return int(exact), int(face.bold == bold), int(face.italic == italic), int(regular)


def _sorted_faces(faces: list[FontFace]) -> list[FontFace]:
    return sorted(faces, key=lambda face: (face.family.lower(), face.path.name.lower()))


def _without_trailing_markers(compact: str) -> str:
    current = compact
    for marker in SOURCE_TRAILING_MARKERS:
        if current.endswith(marker):
            return current[: -len(marker)]
    return current


def _compact_font_name(name: str) -> str:
    subset_removed = name.split("+", 1)[-1].lower()
    return re.sub(r"[^a-z0-9]", "", subset_removed)


def _without_style_suffix(compact: str) -> str:
    for suffix in SOURCE_STYLE_SUFFIXES:
        if compact.endswith(suffix):
            return compact[: -len(suffix)]
    return compact
