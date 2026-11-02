*** Settings ***
Documentation     A connection reset while a session starts fails only the call that started it. A regression
...               would crash Robot Framework, so the scenarios run in a nested Robot process, and this suite
...               reads their results. Uses port 8282, for a server that resets and for a real server.
Library           NestedRobot.py
Library           ResetServer.py


*** Variables ***
${PORT}           8282


*** Test Cases ***
Reset During The Library Import Fails The Import And The Run Goes On
    Start Reset Server    ${PORT}
    ${output}=    Run Nested Suite    ${CURDIR}${/}_nested${/}failing_import.robot
    ...    ${OUTPUT_DIR}${/}nested-reset-at-import    PORT:${PORT}    LIBRARY:JsonRpcRemote.Echo
    ${errors}=    Get Execution Errors    ${output}
    Length Should Be    ${errors}    1
    Should Contain    ${errors}[0]    JsonRpcConnectionClosedError: Connection closed before a response was received
    ${results}=    Get Test Results    ${output}
    Should Be Equal    ${results}[Without The Library]    PASS:${SPACE}
    [Teardown]    Stop Reset Server

Reset When A Later Session Starts Fails The Call And The Run Goes On
    ${output}=    Run Nested Suite    ${CURDIR}${/}_nested${/}reset_at_session_start.robot
    ...    ${OUTPUT_DIR}${/}nested-reset-at-session-start    PORT:${PORT}
    ${results}=    Get Test Results    ${output}
    Length Should Be    ${results}    3
