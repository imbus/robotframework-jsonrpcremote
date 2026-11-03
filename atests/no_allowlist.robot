*** Settings ***
Documentation     A server without libraries imports any library that a client names, and refuses an import
...               without a name. Uses its own server on port 8284, so the shared server used by the other
...               suites is unaffected.
Library           IsolatedServerControl.py
Suite Setup       Start Jsonrpc Server    ${EMPTY}    port=${PORT}    pythonpath=${CURDIR}
Suite Teardown    Stop Jsonrpc Server


*** Variables ***
${PORT}           8284
${URI}            tcp://127.0.0.1:${PORT}


*** Test Cases ***
A Server Without Libraries Imports The Library A Client Names
    Import Library    JsonRpcRemote    ${URI}    SessionValueLib
    Remember Value    kept
    ${value}=    Recalled Value
    Should Be Equal    ${value}    kept

A Server Without Libraries Refuses An Import Without A Name
    Run Keyword And Expect Error
    ...    *Library name cannot be empty when there are no libraries defined at server startup.*
    ...    Import Library    JsonRpcRemote    ${URI}
