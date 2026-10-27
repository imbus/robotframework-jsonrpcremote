*** Settings ***
Documentation     With connect retry, the client waits for a server that is still starting and
...               replaces a lost session at the next call, with a warning. Uses its own server on
...               port 8277, so the shared server used by the other suites is unaffected.
Library           Collections
Library           OperatingSystem
Library           LogCapture.py
Library           IsolatedServerControl.py
Suite Setup       Start Server And Import Libraries
Suite Teardown    Stop Jsonrpc Server


*** Variables ***
${PORT}           8277
${URI}            tcp://127.0.0.1:${PORT}
${RECORD}         jsonrpcremote-connect-retry-record.txt
${RECONNECTED}    Connection to '${URI}' was lost: *. Reconnected after *; the remote library was
...               imported again, so its server-side state was reset.
${GAVE_UP}        ConnectionError: Could not connect to '${URI}' within 1 second (*): *


*** Test Cases ***
Restart While Idle Reconnects With A Warning
    ${result}=    Retry.Echo    before
    Should Be Equal    ${result}    echo: before
    Restart Server
    ${result}=    Retry.Echo    after
    Should Be Equal    ${result}    echo: after
    ${logs}=    Get Captured Log Messages
    Should Contain Match    ${logs}    ${RECONNECTED}

Call While The Server Is Still Starting Waits For It
    [Documentation]    The previous session ended with its test (rpc_scope=TEST), so this call
    ...                starts a new session while the server is still starting.
    Stop Jsonrpc Server
    Start Jsonrpc Server    ConnectionLossLib    port=${PORT}    pythonpath=${CURDIR}    wait=${False}
    ${result}=    Retry.Echo    starting
    Should Be Equal    ${result}    echo: starting

Keyword Running When The Connection Is Lost Fails And Is Not Sent Again
    Run Keyword And Expect Error    *lost while running keyword 'Exit Server'*    Retry.Exit Server    ${RECORD}
    Restart Server
    ${result}=    Retry.Echo    after
    Should Be Equal    ${result}    echo: after
    ${record}=    Get File    ${TEMPDIR}${/}${RECORD}
    Length Should Be    ${record.splitlines()}    1

Gives Up After The Window And Then Tries Once Per Call Until The Server Is Back
    Stop Jsonrpc Server
    Run Keyword And Expect Error    ${GAVE_UP}    Short Retry.Echo    down
    # A single attempt: waiting for the window again would fail with the error above.
    Run Keyword And Expect Error    ConnectionRefusedError: *    Short Retry.Echo    still down
    Start Jsonrpc Server    ConnectionLossLib    port=${PORT}    pythonpath=${CURDIR}
    ${result}=    Short Retry.Echo    back
    Should Be Equal    ${result}    echo: back

Several Restarts In One Session Reconnect Each Time
    ${result}=    Retry.Echo    first
    Should Be Equal    ${result}    echo: first
    FOR    ${message}    IN    second    third
        Restart Server
        ${result}=    Retry.Echo    ${message}
        Should Be Equal    ${result}    echo: ${message}
    END
    ${logs}=    Get Captured Log Messages
    ${warnings}=    Get Matches    ${logs}    ${RECONNECTED}
    Length Should Be    ${warnings}    2


*** Keywords ***
Start Server And Import Libraries
    Remove File    ${TEMPDIR}${/}${RECORD}
    Start Jsonrpc Server    ConnectionLossLib    port=${PORT}    pythonpath=${CURDIR}
    Import Library    JsonRpcRemote    ${URI}    ConnectionLossLib    rpc_scope=TEST
    ...    rpc_connect_retry_timeout=30s    rpc_connect_retry_interval=0.2s    AS    Retry
    Import Library    JsonRpcRemote    ${URI}    ConnectionLossLib    rpc_scope=TEST
    ...    rpc_connect_retry_timeout=1s    rpc_connect_retry_interval=0.2s    AS    Short Retry

Restart Server
    Stop Jsonrpc Server
    Start Jsonrpc Server    ConnectionLossLib    port=${PORT}    pythonpath=${CURDIR}
