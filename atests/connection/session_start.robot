*** Settings ***
Documentation     A session that failed to start is not kept: once the server is reachable
...               again, the next call connects. Uses its own server on port 8274, so the
...               shared server used by the other suites is unaffected.
Library           IsolatedServerControl.py
Suite Setup       Start Jsonrpc Server    JsonRpcRemote.Echo    port=${PORT}
Suite Teardown    Stop Jsonrpc Server


*** Variables ***
${PORT}           8274


*** Test Cases ***
Session Works While The Server Is Up
    [Documentation]    rpc_scope=TEST ends this session when the test ends, so the next test
    ...                has to start a new one.
    Import Library    JsonRpcRemote    tcp://127.0.0.1:${PORT}    JsonRpcRemote.Echo    rpc_scope=TEST
    ${result}=    Echo    up
    Should Be Equal    ${result}    echo: up

Next Call Connects Again After A Failed Start
    [Documentation]    The server is stopped here rather than in the previous test's teardown:
    ...                that teardown runs before the session ends, and the server should shut
    ...                down without a connected client.
    Stop Jsonrpc Server
    Run Keyword And Expect Error    ConnectionRefusedError: *    Echo    down
    Start Jsonrpc Server    JsonRpcRemote.Echo    port=${PORT}
    ${result}=    Echo    back
    Should Be Equal    ${result}    echo: back
