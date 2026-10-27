*** Settings ***
Documentation     A stdio server process that exits during a call: the call fails with the exit
...               code in its cause, and the rest of the session fails with the lost-connection
...               error.
Library           OperatingSystem
Variables         stdio_vars.py
Library           JsonRpcRemote    stdio:${LOSS_SERVER_COMMAND}    ConnectionLossLib
Suite Setup       Remove File    ${TEMPDIR}${/}${RECORD}
Test Tags         posix


*** Variables ***
${RECORD}         jsonrpcremote-stdio-lost-connection-record.txt


*** Test Cases ***
Server Process Exiting During A Call Reports Its Exit Code
    Run Keyword And Expect Error    *lost while running keyword 'Exit Server'*server process exited with code 3*
    ...    Exit Server    ${RECORD}    exit_code=${3}
    Run Keyword And Expect Error    ConnectionError: Connection to 'stdio:*' was lost: *    Echo    after
