from robot.api import logger
from robot.api.deco import keyword, library

_init_counter = 0

@library(scope="SUITE")
class DummyLib:
    def __init__(self) -> None:
        """A dummy library for testing purposes."""
        logger.info("DummyLib initialized.")
        global _init_counter
        _init_counter += 1

    @keyword
    def call_dummy(self) -> None:
        """A dummy keyword for testing purposes."""
        logger.info("Dummy keyword called.")

        logger.info(f"DummyLib has been initialized {_init_counter} times.")
