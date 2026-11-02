*** Settings ***
Documentation     Run by failure_modes.robot in a nested Robot process, not on its own: Robot skips
...               directories starting with an underscore. The test fails on purpose. Needs the variable PORT.
Library           JsonRpcRemote    tcp://127.0.0.1:${PORT}    FailureModesLib


*** Test Cases ***
Long Failure
    Fail With A Long Message
