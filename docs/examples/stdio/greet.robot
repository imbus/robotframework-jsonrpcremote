*** Settings ***
Library    JsonRpcRemote    uri=stdio:robot-jsonrpcremote-server --stdio --pythonpath . MyLibrary
...        library_name=MyLibrary


*** Test Cases ***
Greet Returns A Greeting
    ${greeting}=    Greet    World
    Should Be Equal    ${greeting}    Hello, World!
