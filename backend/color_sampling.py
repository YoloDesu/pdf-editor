import fitz

PdfColor = tuple[float, float, float]
RgbPixel = tuple[int, int, int]


def background_fill_for_rect(page: fitz.Page, rect: fitz.Rect) -> PdfColor:
    """Return a PDF fill color matching the dominant background in a rect.

    Example: `background_fill_for_rect(page, fitz.Rect(0, 0, 10, 10))`
    """
    return _rgb_to_pdf_color(background_rgb_for_rect(page, rect))


def background_color_int_for_rect(page: fitz.Page, rect: fitz.Rect) -> int:
    """Return a CSS-friendly integer color matching a PDF rect background.

    Example: `hex(background_color_int_for_rect(page, rect))`
    """
    red, green, blue = background_rgb_for_rect(page, rect)
    return (red << 16) + (green << 8) + blue


def background_rgb_for_rect(page: fitz.Page, rect: fitz.Rect) -> RgbPixel:
    """Sample the dominant non-text background color in a page rect.

    Example: `background_rgb_for_rect(page, fitz.Rect(0, 0, 10, 10))`
    """
    pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), clip=rect, alpha=False)
    pixels = _sampled_rgb_pixels(pixmap)
    if not pixels:
        return (255, 255, 255)
    return _dominant_background_rgb(pixels)


def _sampled_rgb_pixels(pixmap: fitz.Pixmap) -> list[RgbPixel]:
    pixel_count = pixmap.width * pixmap.height
    if pixmap.n < 3 or pixel_count <= 0:
        return []

    samples = pixmap.samples
    step = max(1, pixel_count // 1600)
    return [_rgb_pixel(samples, index, pixmap.n) for index in range(0, pixel_count, step)]


def _rgb_pixel(samples: bytes, index: int, channels: int) -> RgbPixel:
    offset = index * channels
    return samples[offset], samples[offset + 1], samples[offset + 2]


def _dominant_background_rgb(pixels: list[RgbPixel]) -> RgbPixel:
    candidates = _background_pixels(pixels)
    buckets: dict[RgbPixel, list[RgbPixel]] = {}
    for pixel in candidates:
        buckets.setdefault(_color_bucket(pixel), []).append(pixel)
    return _mean_rgb(max(buckets.values(), key=len))


def _background_pixels(pixels: list[RgbPixel]) -> list[RgbPixel]:
    light_pixels = [pixel for pixel in pixels if _luminance(pixel) >= 70]
    if len(light_pixels) >= max(8, len(pixels) // 5):
        return light_pixels
    return pixels


def _color_bucket(pixel: RgbPixel) -> RgbPixel:
    return pixel[0] // 16, pixel[1] // 16, pixel[2] // 16


def _mean_rgb(pixels: list[RgbPixel]) -> RgbPixel:
    red = sum(pixel[0] for pixel in pixels) // len(pixels)
    green = sum(pixel[1] for pixel in pixels) // len(pixels)
    blue = sum(pixel[2] for pixel in pixels) // len(pixels)
    return red, green, blue


def _luminance(pixel: RgbPixel) -> float:
    return (0.2126 * pixel[0]) + (0.7152 * pixel[1]) + (0.0722 * pixel[2])


def _rgb_to_pdf_color(pixel: RgbPixel) -> PdfColor:
    return pixel[0] / 255, pixel[1] / 255, pixel[2] / 255
