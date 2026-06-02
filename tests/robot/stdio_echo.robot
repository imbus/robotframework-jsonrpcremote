*** Settings ***
Documentation     End-to-end keyword execution over the stdio transport: the JsonRpcRemote
...               client spawns the server as a subprocess and talks over its stdin/stdout.
...               No separate server start/stop is needed -- the client owns the process.
Variables         stdio_vars.py
Library           JsonRpcRemote    stdio:${SERVER_COMMAND}    StdioEchoLib
Test Tags         posix


*** Test Cases ***
Echo Over Stdio Returns Prefixed Message
    ${result}=    Echo    Hello Stdio
    Should Be Equal    ${result}    echo: Hello Stdio

Echo Over Stdio Uses Default Argument
    ${result}=    Echo
    Should Be Equal    ${result}    echo: qwerty

Echo Over Stdio Handles Repeated Calls
    FOR    ${i}    IN RANGE    5
        ${result}=    Echo    msg-${i}
        Should Be Equal    ${result}    echo: msg-${i}
    END
