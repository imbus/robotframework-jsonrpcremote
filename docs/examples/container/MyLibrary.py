from robot.api import logger


class MyLibrary:
    """A regular Robot Framework library: nothing in it knows that it runs on a server."""

    def greet(self, name: str) -> str:
        """Returns a greeting for ``name``."""
        logger.info(f"Greeting {name}")
        return f"Hello, {name}!"
