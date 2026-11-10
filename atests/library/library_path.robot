*** Settings ***
Documentation     A library from a path arrives at the server as the suite resolved the path, with text like a
...               variable in it and, on Windows, with its backslashes. Uses its own server on port 8283,
...               without an allowlist, so the shared server used by the other suites is unaffected.
Library           OperatingSystem
Library           IsolatedServerControl.py
Variables         paths.py
Suite Setup       Start Jsonrpc Server    ${EMPTY}    port=${PORT}
Suite Teardown    Stop Jsonrpc Server


*** Variables ***
${PORT}           8283
${DIRECTORY}      ${TEMPDIR}${/}with\${folder}


*** Test Cases ***
A Library From A Path With The Syntax Of A Variable Is Imported
    [Setup]    Copy File    ${LIBRARIES}${/}ArgumentValuesLib.py    ${DIRECTORY}${/}ArgumentValuesLib.py
    Import Library    JsonRpcRemote    tcp://127.0.0.1:${PORT}    ${DIRECTORY}${/}ArgumentValuesLib.py    AS    FromPath
    ${result}=    FromPath.Echo    hello
    Should Be Equal    ${result}    'hello'
    [Teardown]    Remove Directory    ${DIRECTORY}    recursive=${True}
