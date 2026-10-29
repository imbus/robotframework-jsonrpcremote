*** Settings ***
Documentation     rpc_scope given as a string from Python, as by a library built on the client, ends the
...               session with each test, and an unknown rpc_scope fails the import and names the valid
...               scopes. The client library is imported in the first test, once the server runs. Uses its
...               own server on port 8279, so the shared server used by the other suites is unaffected.
Library           IsolatedServerControl.py
Suite Setup       Start Jsonrpc Server    SessionValueLib    port=${PORT}    pythonpath=${CURDIR}
Suite Teardown    Stop Jsonrpc Server


*** Variables ***
${PORT}           8279
${URI}            tcp://127.0.0.1:${PORT}


*** Test Cases ***
A Value Is Kept Within A Test
    [Documentation]    Imports the library that passes rpc_scope="TEST" as a string and keeps a value in
    ...                its session.
    Import Library    ${CURDIR}${/}TestScopedRemote.py    ${URI}
    TestScopedRemote.Remember Value    first test
    ${value}=    TestScopedRemote.Recalled Value
    Should Be Equal    ${value}    first test

The Next Test Runs In A Session Of Its Own
    [Documentation]    The session of the previous test ended with it, so this test sees a fresh library
    ...                instance without the value.
    ${value}=    TestScopedRemote.Recalled Value
    Should Be Equal    ${value}    ${None}

An Unknown rpc_scope Fails The Import And Names The Valid Scopes
    [Documentation]    The client converts rpc_scope the way Robot Framework does, with its error.
    Run Keyword And Expect Error    *Available: 'GLOBAL', 'SUITE' and 'TEST'*
    ...    Import Library    JsonRpcRemote    ${URI}    SessionValueLib    rpc_scope=weekly
