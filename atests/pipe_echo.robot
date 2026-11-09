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

A Command As A List With The Scheme As An Element Of Its Own
    # Pipe mode ignores --port; the number shows that the client turns an element into a string.
    VAR    @{server}    pipe:    @{SERVER_ARGS}    --port    ${8271}
    Import Library    JsonRpcRemote    ${server}    StdioEchoLib    AS    SchemeOnItsOwn
    ${result}=    SchemeOnItsOwn.Echo    from a list
    Should Be Equal    ${result}    echo: from a list

A Command As A List With The Scheme In Front Of The Program
    VAR    @{server}    pipe:${SERVER_ARGS}[0]    @{SERVER_ARGS}[1:]
    Import Library    JsonRpcRemote    ${server}    StdioEchoLib    AS    SchemeInFront
    ${result}=    SchemeInFront.Echo    from a list
    Should Be Equal    ${result}    echo: from a list

A List Without A Command Is Refused
    VAR    @{lists}
    ...    ${{[]}}
    ...    ${{['pipe:']}}
    ...    ${{['pipe://robot']}}
    ...    ${{['tcp://127.0.0.1:8271']}}
    ...    ${{['robot-jsonrpcremote-server', 'StdioEchoLib']}}
    FOR    ${uri}    IN    @{lists}
        Run Keyword And Expect Error    *A list for uri must hold the command of a pipe: or stdio: URI*
        ...    Import Library    JsonRpcRemote    ${uri}    StdioEchoLib
    END

A String That Looks Like A List Stays A String
    Run Keyword And Expect Error    *Unsupported URI scheme ''*
    ...    Import Library    JsonRpcRemote    ['pipe:', 'server']    StdioEchoLib
