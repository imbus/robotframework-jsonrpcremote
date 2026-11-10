*** Settings ***
Documentation     A TEST-scoped library over a pipe starts and reaps a fresh server per test.
Variables         pipe_vars.py
Library           JsonRpcRemote    pipe:${SERVER_COMMAND}    StdioEchoLib    rpc_scope=TEST


*** Test Cases ***
First Test Runs Against Its Own Server
    ${result}=    Echo    one
    Should Be Equal    ${result}    echo: one

Second Test Runs Against A Freshly Started Server
    ${result}=    Echo    two
    Should Be Equal    ${result}    echo: two
