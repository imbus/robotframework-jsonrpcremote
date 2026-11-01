*** Settings ***
Library    JsonRpcRemote    tcp://127.0.0.1:8271    FailingLibrary


*** Test Cases ***
Normal Failure
    Fail Normally
    Log    This keyword does not run.

Skipped
    Skip The Test
    Log    This keyword does not run.

Continuable Failure
    Fail And Continue
    Log    This keyword still runs.

Fatal Failure
    Stop The Run

Not Run
    Log    This keyword does not run.
