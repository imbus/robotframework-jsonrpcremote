*** Settings ***
Library    JsonRpcRemote    uri=${SERVER}    library_name=MyLibrary


*** Variables ***
@{SERVER ARGS}    robot-jsonrpcremote-server    --pythonpath    .    MyLibrary
@{SERVER}         pipe:    @{SERVER ARGS}


*** Test Cases ***
Greet Returns A Greeting
    ${greeting}=    Greet    World
    Should Be Equal    ${greeting}    Hello, World!
