*** Settings ***
Documentation     A failing remote keyword behaves in Robot Framework like a failing local keyword. How a
...               test ends shows only in the result of a run, so the suite in _nested/failure_modes.robot
...               runs in a nested Robot process, and this suite reads its result. Uses its own server on
...               port 8280: the keywords fail fatally on it, and the shared server stays unaffected.
Library           IsolatedServerControl.py
Library           NestedRobot.py
Suite Setup       Run The Failing Suite
Suite Teardown    Stop Jsonrpc Server


*** Variables ***
${PORT}           8280


*** Test Cases ***
Normal Failure Has The Message Of A Local Keyword
    Should Be Equal    ${RESULTS}[Normal Failure]    FAIL: ValueError: bad value

Traceback Of The Library Is Logged Once At DEBUG Under The Keyword
    ${messages}=    Get Messages    ${NESTED OUTPUT}    Normal Failure    DEBUG
    ${debug log}=    Catenate    SEPARATOR=\n    @{messages}
    Should Contain X Times    ${debug log}    [remote] Traceback (most recent call last):    1
    Should Contain X Times    ${debug log}    raise ValueError("bad value")    1

Skip Skips The Test
    Should Be Equal    ${RESULTS}[Skipped]    SKIP: not today

Continuable Failure Lets The Test Continue
    Should Be Equal    ${RESULTS}[Continuable Failure]    FAIL: go on
    ${messages}=    Get Messages    ${NESTED OUTPUT}    Continuable Failure    INFO
    Should Contain    ${messages}    Continued: pong

Fatal Failure Stops The Run
    Should Be Equal    ${RESULTS}[Fatal Failure]    FAIL: FatalError: stop all
    Should Be Equal    ${RESULTS}[After The Fatal Failure]    FAIL: Test execution stopped due to a fatal error.

A Long Message Is Cut In The Report And Complete In The Log
    ${output}=    Run The Long Failure
    ${results}=    Get Test Results    ${output}
    Should Contain    ${results}[Long Failure]    [ Message content over the limit has been removed. ]
    The Log Should Hold The Whole Message    ${output}

The Run Of The Client Decides How Much Of A Long Message The Report Shows
    ${output}=    Run The Long Failure    max_error_lines=NONE
    ${message}=    Long Message
    ${results}=    Get Test Results    ${output}
    Should Be Equal    ${results}[Long Failure]    FAIL: ${message}
    The Log Should Hold The Whole Message    ${output}

Server Runs Keywords After A Fatal Failure
    Import Library    JsonRpcRemote    tcp://127.0.0.1:${PORT}    FailureModesLib    rpc_scope=TEST
    ${result}=    Ping
    Should Be Equal    ${result}    pong


*** Keywords ***
Long Message
    ${message}=    Evaluate    "\\n".join(f"line {number}" for number in range(1, 101))
    RETURN    ${message}

Run The Long Failure
    [Arguments]    ${max_error_lines}=${EMPTY}
    ${output}=    Run Nested Suite    ${CURDIR}${/}_nested${/}long_message.robot
    ...    ${OUTPUT_DIR}${/}nested-long-message    PORT:${PORT}    allow_failures=${True}
    ...    max_error_lines=${max_error_lines}
    RETURN    ${output}

The Log Should Hold The Whole Message
    [Arguments]    ${output}
    ${message}=    Long Message
    ${messages}=    Get Messages    ${output}    Long Failure    FAIL
    Should Be Equal    ${messages}[0]    ${message}

Run The Failing Suite
    Start Jsonrpc Server    FailureModesLib    port=${PORT}    pythonpath=${CURDIR}
    ${output}=    Run Nested Suite    ${CURDIR}${/}_nested${/}failure_modes.robot
    ...    ${OUTPUT_DIR}${/}nested-failure-modes    PORT:${PORT}    log_level=DEBUG    allow_failures=${True}
    ${results}=    Get Test Results    ${output}
    Set Suite Variable    ${NESTED OUTPUT}    ${output}
    Set Suite Variable    ${RESULTS}    ${results}
