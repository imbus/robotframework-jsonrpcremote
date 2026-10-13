*** Settings ***
Documentation     The client reconnects after the server was restarted, if reconnect_timeout
...               is set. Uses an isolated server on its own port, so the shared server used
...               by the other suites is unaffected. Each test restarts that server first.
Library           Collections
Library           OperatingSystem
Library           LogCapture.py
Library           IsolatedServerControl.py
Test Setup        Restart Server
Suite Teardown    Kill Jsonrpc Server


*** Variables ***
${RECONNECT_PORT}     8273
${URI}                tcp://127.0.0.1:${RECONNECT_PORT}


*** Test Cases ***
Without Reconnect Timeout A Lost Connection Fails Clearly
    Import Library    JsonRpcRemote    ${URI}    ReconnectProbeLib    rpc_scope=TEST    AS    NoReconnect
    NoReconnect.Echo    before
    Restart Server
    Run Keyword And Expect Error    ConnectionError: *Automatic reconnect is disabled*
    ...    NoReconnect.Echo    after
    Run Keyword And Expect Error    ConnectionError: *Automatic reconnect is disabled*
    ...    NoReconnect.Echo    still off

Reconnects After The Server Was Restarted
    Import Library    JsonRpcRemote    ${URI}    ReconnectProbeLib    rpc_scope=TEST
    ...    reconnect_timeout=20s    reconnect_interval=0.2s    AS    Restarted
    Restarted.Echo    before
    Restart Server
    ${result}=    Restarted.Echo    after
    Should Be Equal    ${result}    echo: after
    ${logs}=    Get Captured Log Messages
    Should Contain Match    ${logs}    Connection to '${URI}' was lost (*). Reconnected after *

Call Made While The Server Is Down Waits For It
    Import Library    JsonRpcRemote    ${URI}    ReconnectProbeLib    rpc_scope=TEST
    ...    reconnect_timeout=30s    reconnect_interval=0.2s    AS    Waiting
    Waiting.Echo    before
    Kill Jsonrpc Server
    # Returns while the server is still starting, so the call below finds the port closed.
    Start Jsonrpc Server    ReconnectProbeLib    port=${RECONNECT_PORT}    pythonpath=${CURDIR}    wait=${False}
    ${result}=    Waiting.Echo    while down
    Should Be Equal    ${result}    echo: while down

Running Call Fails And Is Not Sent Again
    VAR    ${record}    ${TEMPDIR}${/}jsonrpcremote-reconnect-calls.txt
    Remove File    ${record}
    Import Library    JsonRpcRemote    ${URI}    ReconnectProbeLib    rpc_scope=TEST
    ...    reconnect_timeout=20s    reconnect_interval=0.2s    AS    Running
    Run Keyword And Expect Error    ConnectionError: *lost while running keyword*not retried*
    ...    Running.Exit Server After Recording    ${record}
    Restart Server
    ${result}=    Running.Echo    after
    Should Be Equal    ${result}    echo: after
    ${calls}=    Get File    ${record}
    Should Be Equal    ${calls}    called\n

Gives Up After The Timeout And Recovers Later
    Import Library    JsonRpcRemote    ${URI}    ReconnectProbeLib    rpc_scope=TEST
    ...    reconnect_timeout=1s    reconnect_interval=0.2s    AS    GivingUp
    GivingUp.Echo    before
    Kill Jsonrpc Server
    Run Keyword And Expect Error    ConnectionError: *could not be re-established within 1s*
    ...    GivingUp.Echo    while down
    Start Server
    ${result}=    GivingUp.Echo    after
    Should Be Equal    ${result}    echo: after

Survives Several Restarts
    Import Library    JsonRpcRemote    ${URI}    ReconnectProbeLib    rpc_scope=TEST
    ...    reconnect_timeout=20s    reconnect_interval=0.2s    AS    Repeated
    FOR    ${i}    IN RANGE    3
        Restart Server
        ${result}=    Repeated.Echo    round ${i}
        Should Be Equal    ${result}    echo: round ${i}
    END


*** Keywords ***
Start Server
    Start Jsonrpc Server    ReconnectProbeLib    port=${RECONNECT_PORT}    pythonpath=${CURDIR}

Restart Server
    Kill Jsonrpc Server
    Start Server
