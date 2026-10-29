*** Settings ***
Documentation     End-to-end keyword execution through the JSON-RPC remote library.
Library           JsonRpcRemote    tcp://127.0.0.1:${PORT}    JsonRpcRemote.Echo


*** Variables ***
${PORT}           8271


*** Test Cases ***
Echo Returns Prefixed Message
    ${result}=    Echo    Hello World
    Should Be Equal    ${result}    echo: Hello World

Echo Uses Default Argument
    ${result}=    Echo
    Should Be Equal    ${result}    echo: qwerty

Echo Handles Repeated Calls
    FOR    ${i}    IN RANGE    5
        ${result}=    Echo    msg-${i}
        Should Be Equal    ${result}    echo: msg-${i}
    END
