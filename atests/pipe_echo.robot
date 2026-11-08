*** Settings ***
Documentation     Keyword execution over a pipe: the client starts the server with --pipe=<address>.
Variables         pipe_vars.py
Library           JsonRpcRemote    pipe:${SERVER_COMMAND}    StdioEchoLib


*** Test Cases ***
Echo Over A Pipe Returns Prefixed Message
    ${result}=    Echo    Hello Pipe
    Should Be Equal    ${result}    echo: Hello Pipe

Echo Over A Pipe Uses Default Argument
    ${result}=    Echo
    Should Be Equal    ${result}    echo: qwerty

Echo Over A Pipe Handles Repeated Calls
    FOR    ${i}    IN RANGE    5
        ${result}=    Echo    msg-${i}
        Should Be Equal    ${result}    echo: msg-${i}
    END

A Command That Does Not Exist Names The URI Of A Listening Server
    Run Keyword And Expect Error
    ...    *'jsonrpcremote-no-such-server' (pipe://<name> connects to a server that listens on a pipe)*
    ...    Import Library    JsonRpcRemote    pipe:jsonrpcremote-no-such-server    StdioEchoLib
