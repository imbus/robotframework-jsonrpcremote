*** Settings ***
Documentation     Run by failure_modes.robot in a nested Robot process, not on its own: Robot skips
...               directories starting with an underscore. Most tests here fail on purpose. Needs the
...               variable PORT.
Library           JsonRpcRemote    tcp://127.0.0.1:${PORT}    FailureModesLib


*** Test Cases ***
Normal Failure
    Fail With Value Error
    Log    Not reached.

Skipped
    Skip The Test
    Log    Not reached.

Continuable Failure
    Fail Continuably
    ${result}=    Ping
    Log    Continued: ${result}

Fatal Failure
    Fail Fatally

After The Fatal Failure
    Log    Not reached.
