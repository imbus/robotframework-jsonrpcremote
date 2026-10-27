*** Settings ***
Documentation     A lost connection fails every later call of its session with the cause, until
...               the session ends with its rpc_scope; a keyword running at that moment fails
...               and is not sent again. Uses its own server on port 8275, so the shared server
...               used by the other suites is unaffected.
Library           OperatingSystem
Library           IsolatedServerControl.py
Suite Setup       Start Server And Import Library
Suite Teardown    Stop Jsonrpc Server


*** Variables ***
${PORT}           8275
${URI}            tcp://127.0.0.1:${PORT}
${RECORD}         jsonrpcremote-lost-connection-record.txt


*** Test Cases ***
Calls After A Lost Connection Fail With The Cause
    ${result}=    Echo    up
    Should Be Equal    ${result}    echo: up
    Kill Jsonrpc Server
    # Give the client a moment to see the closed connection, so the next call is not sent.
    Sleep    0.5s
    Run Keyword And Expect Error    ConnectionError: Connection to '${URI}' was lost: *    Echo    first
    Run Keyword And Expect Error    ConnectionError: Connection to '${URI}' was lost: *    Echo    second

Keyword Running When The Connection Is Lost Fails And Is Not Sent Again
    [Setup]    Start Jsonrpc Server    ConnectionLossLib    port=${PORT}    pythonpath=${CURDIR}
    Run Keyword And Expect Error    *lost while running keyword 'Exit Server'*    Exit Server    ${RECORD}
    ${record}=    Get File    ${TEMPDIR}${/}${RECORD}
    Length Should Be    ${record.splitlines()}    1
    # Collects the exit code of the server process that ended itself.
    [Teardown]    Stop Jsonrpc Server

New Session Works After The Server Is Back
    [Documentation]    The lost sessions ended with their tests (rpc_scope=TEST), so this call
    ...                starts a new one.
    [Setup]    Start Jsonrpc Server    ConnectionLossLib    port=${PORT}    pythonpath=${CURDIR}
    ${result}=    Echo    back
    Should Be Equal    ${result}    echo: back


*** Keywords ***
Start Server And Import Library
    Remove File    ${TEMPDIR}${/}${RECORD}
    Start Jsonrpc Server    ConnectionLossLib    port=${PORT}    pythonpath=${CURDIR}
    Import Library    JsonRpcRemote    ${URI}    ConnectionLossLib    rpc_scope=TEST
