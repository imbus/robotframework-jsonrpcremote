class Echo:
    """A simple robot library that echoes messages.

    The purpose of this library is to demonstrate a basic keyword
    that can be called via JSON-RPC and to test if the connection is working correctly.
    """

    def __init__(self, *args: object, **kwargs: object) -> None:
        """
        Initializes the Echo library.

        :param self: Description
        :param args: Description
        :type args: object
        :param kwargs: Description
        :type kwargs: object
        """
        self.ROBOT_LIBRARY_SCOPE = "TEST"
        self.args = args
        self.kwargs = kwargs

    ROBOT_LIBRARY_DOC_FORMAT = "ROBOT"
    ROBOT_LIBRARY_VERSION = "1.0"

    def echo(self, message: str = "qwerty", *args: object, **kwargs: object) -> str:
        """Returns the given message prefixed with 'echo: '.

        :param message: The message to echo.
        :return: The echoed message.
        """
        print(f"Echo called with message: {message}, args: {args}, kwargs: {kwargs}")
        return f"echo: {message}"
