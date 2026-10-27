*** Settings ***
Documentation     With connect retry, the call after a stdio server process exited starts a new
...               server process, and the warning names the exit code of the old one.
Library           Collections
Library           OperatingSystem
Library           LogCapture.py
Variables         stdio_vars.py
Library           JsonRpcRemote    stdio:${LOSS_SERVER_COMMAND}    ConnectionLossLib
...               rpc_connect_retry_timeout=10s    rpc_connect_retry_interval=0.2s
Suite Setup       Remove File    ${TEMPDIR}${/}${RECORD}
Test Tags         posix


*** Variables ***
${RECORD}         jsonrpcremote-stdio-connect-retry-record.txt


*** Test Cases ***
Next Call After The Server Process Exited Starts A New One
    Run Keyword And Expect Error    *lost while running keyword 'Exit Server'*server process exited with code 3*
    ...    Exit Server    ${RECORD}    exit_code=${3}
    ${result}=    Echo    after
    Should Be Equal    ${result}    echo: after
    ${logs}=    Get Captured Log Messages
    Should Contain Match    ${logs}
    ...    Connection to 'stdio:*' was lost: *(server process exited with code 3). Reconnected after *
    ${record}=    Get File    ${TEMPDIR}${/}${RECORD}
    Length Should Be    ${record.splitlines()}    1
