"""Test-only library, locally and on the server: a keyword that logs at the levels that matter for the console."""

from robot.api import logger


def log_at_three_levels() -> None:
    logger.info("an info message")
    logger.warn("a warning")
    logger.error("an error")
