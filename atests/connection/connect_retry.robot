*** Settings ***
Documentation     With connect retry, the client waits for a server that is still starting and
...               replaces a lost session at the next call, with a warning; an import that the server
...               refuses fails at once. Uses its own server on port 8277, so the shared server used by
...               the other suites is unaffected.
Library           Collections
Library           OperatingSystem
Library           LogCapture.py
Library           IsolatedServerControl.py
Variables         paths.py
Suite Setup       Start Server And Import Libraries
Suite Teardown    Stop Jsonrpc Server


*** Variables ***
${PORT}           8277
${URI}            tcp://127.0.0.1:${PORT}
${RECORD}         jsonrpcremote-connect-retry-record.txt
${RECONNECTED}    Connection to '${URI}' was lost: *. Reconnected after *; the remote library was
...               imported again, so its server-side state was reset.
${GAVE_UP}        ConnectionError: Could not connect to '${URI}' within 1 second (*): *
# MissingDependencyLib fails to import on the server.
${SERVER_LIBRARIES}    ConnectionLossLib MissingDependencyLib


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
    Start Jsonrpc Server    ${SERVER_LIBRARIES}    port=${PORT}    pythonpath=${LIBRARIES}    wait=${False}
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
    Start Jsonrpc Server    ${SERVER_LIBRARIES}    port=${PORT}    pythonpath=${LIBRARIES}
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

A Refused Import Fails At Once Despite Connect Retry
    ${error}=    Error Of An Import With Connect Retry    OtherLibrary
    Should End With    ${error.strip()}    Library 'OtherLibrary' is not available.

A Library That Fails To Import Fails At Once Despite Connect Retry
    ${error}=    Error Of An Import With Connect Retry    MissingDependencyLib
    Should Contain    ${error}    No module named 'a_module_that_does_not_exist'


*** Keywords ***
Start Server And Import Libraries
    Remove File    ${TEMPDIR}${/}${RECORD}
    Start Jsonrpc Server    ${SERVER_LIBRARIES}    port=${PORT}    pythonpath=${LIBRARIES}
    Import Library    JsonRpcRemote    ${URI}    ConnectionLossLib    rpc_scope=TEST
    ...    rpc_connect_retry_timeout=30s    rpc_connect_retry_interval=0.2s    AS    Retry
    Import Library    JsonRpcRemote    ${URI}    ConnectionLossLib    rpc_scope=TEST
    ...    rpc_connect_retry_timeout=1s    rpc_connect_retry_interval=0.2s    AS    Short Retry

Error Of An Import With Connect Retry
    [Documentation]    The error of an import of ${library} with a window of 10 seconds, which must
    ...                come within 5 seconds: the server answers, so the client does not try again.
    [Arguments]    ${library}
    # Waits for the server, for a test that follows one that restarted it.
    Retry.Echo    ready
    ${started}=    Evaluate    time.monotonic()
    ${error}=    Run Keyword And Expect Error    *    Import Library    JsonRpcRemote    ${URI}    ${library}
    ...    rpc_connect_retry_timeout=10s    rpc_connect_retry_interval=0.2s    AS    Refused
    ${elapsed}=    Evaluate    time.monotonic() - ${started}
    Should Be True    ${elapsed} < 5    The import failed only after ${elapsed} seconds.
    RETURN    ${error}

Restart Server
    Stop Jsonrpc Server
    Start Jsonrpc Server    ${SERVER_LIBRARIES}    port=${PORT}    pythonpath=${LIBRARIES}
