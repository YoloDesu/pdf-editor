import fitz

MAX_OCR_PIXELS = 10_000_000
MAX_PREVIEW_PIXELS = 16_000_000


def page_pixmap_with_pixel_limit(
    page: fitz.Page,
    dpi: int,
    max_pixels: int,
) -> fitz.Pixmap:
    """Render a page pixmap without exceeding an approximate pixel budget.

    Example: `page_pixmap_with_pixel_limit(page, 150, 16_000_000)`
    """
    limited_dpi = pixel_limited_dpi(page.rect, dpi, max_pixels)
    return page.get_pixmap(dpi=limited_dpi, alpha=False)


def pixel_limited_dpi(rect: fitz.Rect, dpi: int, max_pixels: int) -> int:
    """Return a DPI capped by a page pixel budget.

    Example: `pixel_limited_dpi(fitz.Rect(0, 0, 5000, 5000), 350, 10_000_000)`
    """
    page_area = max(rect.width, 1.0) * max(rect.height, 1.0)
    requested_pixels = page_area * (dpi / 72) ** 2
    if requested_pixels <= max_pixels:
        return dpi

    scaled_dpi = int(72 * (max_pixels / page_area) ** 0.5)
    return max(1, min(dpi, scaled_dpi))
