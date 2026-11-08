*** Settings ***
Library    JsonRpcRemote    uri=pipe://robot.sock    library_name=MyLibrary


*** Test Cases ***
Greet Returns A Greeting
    ${greeting}=    Greet    World
    Should Be Equal    ${greeting}    Hello, World!
