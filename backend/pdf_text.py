from dataclasses import dataclass


@dataclass(frozen=True)
class TextBlock:
    bbox: tuple[float, float, float, float]
    text: str
    font: str
    size: float
    color: int
    bold: bool = False
    italic: bool = False
    background_color: int = 16777215

    def as_payload(self) -> dict[str, object]:
        """Return JSON-ready text metadata.

        Example: `TextBlock((0, 0, 10, 10), "A", "helv", 8, 0).as_payload()`
        """
        return {
            "bbox": self.bbox,
            "text": self.text,
            "font": self.font,
            "size": self.size,
            "color": self.color,
            "bold": self.bold,
            "italic": self.italic,
            "background_color": self.background_color,
        }
