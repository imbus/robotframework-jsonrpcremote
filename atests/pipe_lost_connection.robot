*** Settings ***
Documentation     A server process that the client started over a pipe exits during a call: the call fails
...               with the exit code in its cause, and the rest of the session fails with the
...               lost-connection error.
Library           OperatingSystem
Variables         pipe_vars.py
Library           JsonRpcRemote    pipe:${LOSS_SERVER_COMMAND}    ConnectionLossLib
Suite Setup       Remove File    ${TEMPDIR}${/}${RECORD}


*** Variables ***
${RECORD}         jsonrpcremote-pipe-lost-connection-record.txt


*** Test Cases ***
Server Process Exiting During A Call Reports Its Exit Code
    Run Keyword And Expect Error    *lost while running keyword 'Exit Server'*server process exited with code 3*
    ...    Exit Server    ${RECORD}    exit_code=${3}
    Run Keyword And Expect Error    ConnectionError: Connection to 'pipe:*' was lost: *    Echo    after

A List URI In The Lost-Connection Error
    VAR    @{server}    pipe:    @{LOSS_SERVER_ARGS}
    Import Library    JsonRpcRemote    ${server}    ConnectionLossLib    AS    LossFromList
    # The URI as its string form, not as the repr of the list.
    Run Keyword And Expect Error
    ...    *Connection to 'pipe:*ConnectionLossLib' was lost while running keyword 'Exit Server'*server process exited with code 3*
    ...    LossFromList.Exit Server    ${RECORD}    exit_code=${3}
