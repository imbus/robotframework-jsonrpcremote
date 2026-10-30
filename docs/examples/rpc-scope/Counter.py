class Counter:
    """Counts the calls of ``Increment`` in this instance of the library."""

    def __init__(self) -> None:
        self.count = 0

    def increment(self) -> int:
        """Adds one to the count and returns the new count."""
        self.count += 1
        return self.count
