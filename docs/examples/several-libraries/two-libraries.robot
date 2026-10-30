*** Settings ***
Library    JsonRpcRemote    uri=tcp://127.0.0.1:8271    library_name=MyLibrary
...        AS    MyLibrary
Library    JsonRpcRemote    uri=tcp://127.0.0.1:8271    library_name=Calculator
...        AS    Calculator


*** Test Cases ***
Keywords Of Both Libraries
    ${greeting}=    Greet    World
    Should Be Equal    ${greeting}    Hello, World!
    ${sum}=    Add    1    2
    Should Be Equal As Integers    ${sum}    3
