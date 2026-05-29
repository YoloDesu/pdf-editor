from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
import re

import fitz

from font_catalog import font_file_for_family


@dataclass(frozen=True)
class PdfFontChoice:
    source_name: str
    fitz_name: str
    file_path: str | None = None


@dataclass(frozen=True)
class PdfFontStyle:
    bold: bool
    italic: bool


COMMON_FONT_ALIASES = {
    "arial": "helv",
    "arialmt": "helv",
    "calibri": "helv",
    "comicsansms": "helv",
    "courier": "cour",
    "couriernew": "cour",
    "garamond": "tiro",
    "georgia": "tiro",
    "helvetica": "helv",
    "helveticaneue": "helv",
    "tahoma": "helv",
    "times": "tiro",
    "timesnewroman": "tiro",
    "timesroman": "tiro",
    "trebuchetms": "helv",
    "verdana": "helv",
}

FONT_STYLE_ALIASES = {
    ("helv", False, False): "helv",
    ("helv", True, False): "hebo",
    ("helv", False, True): "heit",
    ("helv", True, True): "hebi",
    ("cour", False, False): "cour",
    ("cour", True, False): "cobo",
    ("cour", False, True): "coit",
    ("cour", True, True): "cobi",
    ("tiro", False, False): "tiro",
    ("tiro", True, False): "tibo",
    ("tiro", False, True): "tiit",
    ("tiro", True, True): "tibi",
}

WINDOWS_FONT_DIR = Path("C:/Windows/Fonts")
FONT_FILE_FAMILIES = {
    "arial": ("arial.ttf", "arialbd.ttf", "ariali.ttf", "arialbi.ttf"),
    "calibri": ("calibri.ttf", "calibrib.ttf", "calibrii.ttf", "calibriz.ttf"),
    "couriernew": ("cour.ttf", "courbd.ttf", "couri.ttf", "courbi.ttf"),
    "comicsansms": ("comic.ttf", "comicbd.ttf", "comici.ttf", "comicz.ttf"),
    "garamond": ("GARA.TTF", "GARABD.TTF", "GARAIT.TTF", ""),
    "georgia": ("georgia.ttf", "georgiab.ttf", "georgiai.ttf", "georgiaz.ttf"),
    "helvetica": ("arial.ttf", "arialbd.ttf", "ariali.ttf", "arialbi.ttf"),
    "tahoma": ("tahoma.ttf", "tahomabd.ttf", "", ""),
    "timesnewroman": ("times.ttf", "timesbd.ttf", "timesi.ttf", "timesbi.ttf"),
    "trebuchetms": ("trebuc.ttf", "trebucbd.ttf", "trebucit.ttf", "trebucbi.ttf"),
    "verdana": ("verdana.ttf", "verdanab.ttf", "verdanai.ttf", "verdanaz.ttf"),
}


def resolve_pdf_font(
    source_name: str,
    bold: bool = False,
    italic: bool = False,
) -> PdfFontChoice:
    """Map a common PDF font name into a PyMuPDF built-in font.

    Example: `resolve_pdf_font("Arial", bold=True).fitz_name`
    """
    normalized_name = _normalized_font_name(source_name)
    style = detect_pdf_font_style(source_name)
    resolved_bold = bold or style.bold
    resolved_italic = italic or style.italic
    font_file = _font_file_for(source_name, normalized_name, resolved_bold, resolved_italic)
    if font_file is not None:
        name = _font_resource_name(normalized_name, resolved_bold, resolved_italic)
        return PdfFontChoice(source_name or "Helvetica", name, str(font_file))

    base_name = _fitz_alias_for(normalized_name)
    fitz_name = _styled_fitz_alias(base_name, resolved_bold, resolved_italic)
    return PdfFontChoice(source_name or "Helvetica", fitz_name)


def text_width(
    font_name: str,
    text: str,
    font_size: float,
    bold: bool = False,
    italic: bool = False,
) -> float:
    """Measure text width using the closest available built-in font.

    Example: `text_width("Arial", "Hello", 12, bold=True)`
    """
    choice = resolve_pdf_font(font_name, bold, italic)
    if choice.file_path is not None:
        return _font_from_file(choice.file_path).text_length(text, fontsize=font_size)
    return fitz.get_text_length(text, fontname=choice.fitz_name, fontsize=font_size)


def detect_pdf_font_style(source_name: str) -> PdfFontStyle:
    """Infer bold and italic flags from common PDF font names.

    Example: `detect_pdf_font_style("Arial-BoldItalic").bold`
    """
    normalized_name = source_name.split("+", 1)[-1].lower()
    bold = "bold" in normalized_name or "black" in normalized_name
    italic = "italic" in normalized_name or "oblique" in normalized_name
    return PdfFontStyle(bold, italic)


def _normalized_font_name(source_name: str) -> str:
    subset_removed = source_name.split("+", 1)[-1].lower()
    base_name = re.sub(r"[^a-z]", "", subset_removed)
    return _without_style_suffix(base_name)


def _fitz_alias_for(normalized_name: str) -> str:
    if normalized_name in COMMON_FONT_ALIASES:
        return COMMON_FONT_ALIASES[normalized_name]
    if normalized_name.startswith(("arial", "calibri", "helvetica")):
        return "helv"
    if normalized_name.startswith(("comic", "tahoma", "trebuchet", "verdana")):
        return "helv"
    if normalized_name.startswith("times"):
        return "tiro"
    if normalized_name.startswith(("garamond", "georgia")):
        return "tiro"
    if normalized_name.startswith("courier"):
        return "cour"
    return "helv"


def _styled_fitz_alias(base_name: str, bold: bool, italic: bool) -> str:
    return FONT_STYLE_ALIASES.get((base_name, bold, italic), base_name)


def _font_file_for(
    source_name: str,
    normalized_name: str,
    bold: bool,
    italic: bool,
) -> Path | None:
    catalog_file = font_file_for_family(source_name, bold, italic)
    if catalog_file is not None:
        return catalog_file

    family = _font_file_family(normalized_name)
    file_names = FONT_FILE_FAMILIES.get(family)
    if file_names is None:
        return None

    file_name = file_names[_style_index(bold, italic)]
    if file_name == "":
        return None

    font_path = WINDOWS_FONT_DIR / file_name
    if font_path.exists():
        return font_path
    return None


def _font_file_family(normalized_name: str) -> str:
    if normalized_name.startswith(("arial", "helvetica")):
        return "arial" if normalized_name.startswith("arial") else "helvetica"
    if normalized_name.startswith("times"):
        return "timesnewroman"
    return _family_by_prefix(normalized_name)


def _family_by_prefix(normalized_name: str) -> str:
    for family in FONT_FILE_FAMILIES:
        if normalized_name.startswith(family):
            return family
    return normalized_name


def _style_index(bold: bool, italic: bool) -> int:
    if bold and italic:
        return 3
    if italic:
        return 2
    if bold:
        return 1
    return 0


def _font_resource_name(normalized_name: str, bold: bool, italic: bool) -> str:
    family = _font_file_family(normalized_name).title()
    suffix = _style_suffix(bold, italic)
    return f"F{family}{suffix}"


def _style_suffix(bold: bool, italic: bool) -> str:
    if bold and italic:
        return "BoldItalic"
    if italic:
        return "Italic"
    if bold:
        return "Bold"
    return "Regular"


@lru_cache(maxsize=32)
def _font_from_file(font_file: str) -> fitz.Font:
    return fitz.Font(fontfile=font_file)


def _without_style_suffix(base_name: str) -> str:
    suffixes = ("bolditalic", "boldoblique", "italic", "oblique", "regular", "bold")
    for suffix in suffixes:
        if base_name.endswith(suffix):
            return base_name[: -len(suffix)]
    return base_name
