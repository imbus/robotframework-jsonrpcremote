from shapes import Color, Point


class Drawing:
    def move(self, point: Point, dx: int, dy: int) -> Point:
        """Returns ``point`` moved by ``dx`` and ``dy``."""
        return Point(point.x + dx, point.y + dy)

    def paint(self, point: Point, color: Color) -> str:
        """Returns a text with the name of ``color`` and the place of ``point``."""
        return f"{color.name} at {point.x},{point.y}"
