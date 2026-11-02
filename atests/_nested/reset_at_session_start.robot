*** Settings ***
Documentation     Run by connection_reset.robot in a nested Robot process, not on its own: Robot skips directories
...               starting with an underscore. Needs the variable PORT.
Library           ../ResetServer.py
Library           ../ServerControl.py
Suite Teardown    Stop Jsonrpc Server


*** Test Cases ***
First Session Works
    [Documentation]    rpc_scope=TEST ends this session when the test ends, so the next test
    ...                has to start a new one.
    Start Jsonrpc Server    JsonRpcRemote.Echo    port=${PORT}
    Import Library    JsonRpcRemote    tcp://127.0.0.1:${PORT}    JsonRpcRemote.Echo    rpc_scope=TEST
    ${result}=    Echo    up
    Should Be Equal    ${result}    echo: up

Reset While The Next Session Starts Fails The Call
    Stop Jsonrpc Server
    Start Reset Server    ${PORT}
    Run Keyword And Expect Error    JsonRpcConnectionClosedError: Connection closed before a response was received
    ...    Echo    down
    [Teardown]    Stop Reset Server

Next Call Connects Again
    Start Jsonrpc Server    JsonRpcRemote.Echo    port=${PORT}
    ${result}=    Echo    back
    Should Be Equal    ${result}    echo: back
