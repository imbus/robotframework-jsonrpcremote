*** Settings ***
Documentation     A TEST-scoped stdio library spawns its own server subprocess and tears it
...               down after each test, so every test runs against a fresh server. Exercises
...               the spawn/handshake/reap cycle repeatedly over the stdio transport.
Variables         stdio_vars.py
Library           JsonRpcRemote    stdio:${SERVER_COMMAND}    StdioEchoLib    rpc_scope=TEST
Test Tags         posix


*** Test Cases ***
First Test Runs Against Its Own Server
    ${result}=    Echo    one
    Should Be Equal    ${result}    echo: one

Second Test Runs Against A Freshly Spawned Server
    ${result}=    Echo    two
    Should Be Equal    ${result}    echo: two
