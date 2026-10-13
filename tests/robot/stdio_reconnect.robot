*** Settings ***
Documentation     Over stdio a reconnect spawns a fresh server process after the old one exited.
Variables         stdio_vars.py
Library           Collections
Library           OperatingSystem
Library           LogCapture.py
Library           JsonRpcRemote    stdio:${RECONNECT_SERVER_COMMAND}    ReconnectProbeLib
...                   rpc_scope=TEST    reconnect_timeout=20s    reconnect_interval=0.2s
Test Tags         posix


*** Test Cases ***
Server Process Is Respawned After It Exited
    VAR    ${record}    ${TEMPDIR}${/}jsonrpcremote-stdio-reconnect-calls.txt
    Remove File    ${record}
    Run Keyword And Expect Error    ConnectionError: *lost while running keyword*exited with code 3*
    ...    Exit Server After Recording    ${record}    exit_code=${3}
    ${result}=    Echo    respawned
    Should Be Equal    ${result}    echo: respawned
    ${logs}=    Get Captured Log Messages
    Should Contain Match    ${logs}    *server process exited with code 3*
    ${calls}=    Get File    ${record}
    Should Be Equal    ${calls}    called\n
