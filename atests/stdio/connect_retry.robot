*** Settings ***
Documentation     With connect retry, the call after a stdio server process exited starts a new
...               server process, and the warning names the exit code of the old one and says that the
...               server-side state was reset, also for a library with the scope GLOBAL.
Library           Collections
Library           OperatingSystem
Library           LogCapture.py
Variables         stdio_vars.py
Library           JsonRpcRemote    stdio:${LOSS_SERVER_COMMAND}    ConnectionLossLib
...               rpc_connect_retry_timeout=10s    rpc_connect_retry_interval=0.2s
Suite Setup       Remove File    ${TEMPDIR}${/}${RECORD}


*** Variables ***
${RECORD}         jsonrpcremote-stdio-connect-retry-record.txt
${GLOBAL_RESET}   Connection to 'stdio:*GlobalCounterLib' was lost: *; the remote library was imported again,
...               so its server-side state was reset.


*** Test Cases ***
Next Call After The Server Process Exited Starts A New One
    Run Keyword And Expect Error    *lost while running keyword 'Exit Server'*server process exited with code 3*
    ...    Exit Server    ${RECORD}    exit_code=${3}
    ${result}=    Echo    after
    Should Be Equal    ${result}    echo: after
    ${logs}=    Get Captured Log Messages
    Should Contain Match    ${logs}
    ...    Connection to 'stdio:*ConnectionLossLib' was lost: *(server process exited with code 3). Reconnected after *
    ${record}=    Get File    ${TEMPDIR}${/}${RECORD}
    Length Should Be    ${record.splitlines()}    1

A Reconnect To A Global Library Over Stdio Says Its State Was Reset
    [Documentation]    The client started the server process, so the new session has a new one, whatever the
    ...                scope of the library. rpc_scope=TEST gives the test a server process of its own.
    Import Library    JsonRpcRemote    stdio:${GLOBAL_COUNTER_COMMAND}    GlobalCounterLib    rpc_scope=TEST
    ...    rpc_connect_retry_timeout=10s    rpc_connect_retry_interval=0.2s    AS    Global Counter
    ${count}=    Global Counter.Count
    Should Be Equal As Integers    ${count}    1
    Run Keyword And Expect Error    *lost while running keyword 'End Server Process'*server process exited with code 3*
    ...    Global Counter.End Server Process
    ${count}=    Global Counter.Count
    Should Be Equal As Integers    ${count}    1
    ${logs}=    Get Captured Log Messages
    Should Contain Match    ${logs}    ${GLOBAL_RESET}
