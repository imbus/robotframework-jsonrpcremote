*** Settings ***
Documentation     Stopping the server while a client is connected: it delivers the result of a
...               running keyword, closes the client connection and exits with code 0 without
...               the kill fallback. Uses its own server on port 8276, so the shared server used
...               by the other suites is unaffected.
Library           IsolatedServerControl.py
Suite Setup       Start Server And Import Library
Suite Teardown    Stop Jsonrpc Server
# SIGTERM and the graceful stop are POSIX-only; on Windows, terminate() is a hard kill.
Test Tags         posix


*** Variables ***
${PORT}           8276
${URI}            tcp://127.0.0.1:${PORT}


*** Test Cases ***
Stopping With A Connected Client Closes The Connection And Exits
    ${result}=    Echo    connected
    Should Be Equal    ${result}    echo: connected
    Stop Jsonrpc Server
    Server Should Have Exited Gracefully
    Run Keyword And Expect Error    ConnectionError: Connection to '${URI}' was lost: *    Echo    after stop

Keyword Running At The Stop Delivers Its Result
    [Documentation]    The keyword sends SIGTERM to its own server and returns while it stops.
    [Setup]    Start Jsonrpc Server    ConnectionLossLib    port=${PORT}    pythonpath=${CURDIR}
    ${result}=    Terminate Server    delivered
    Should Be Equal    ${result}    delivered
    Wait For Jsonrpc Server To Exit
    Server Should Have Exited Gracefully


*** Keywords ***
Start Server And Import Library
    Start Jsonrpc Server    ConnectionLossLib    port=${PORT}    pythonpath=${CURDIR}
    Import Library    JsonRpcRemote    ${URI}    ConnectionLossLib    rpc_scope=TEST

Server Should Have Exited Gracefully
    ${code}=    Get Server Exit Code
    Should Be Equal As Integers    ${code}    0
    ${killed}=    Server Was Killed
    Should Be Equal    ${killed}    ${False}
