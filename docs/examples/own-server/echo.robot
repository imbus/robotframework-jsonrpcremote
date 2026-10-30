*** Settings ***
Library    JsonRpcRemote    uri=tcp://127.0.0.1:8271    library_name=SimpleRobotLibrary


*** Test Cases ***
Echo Returns The Message
    ${result}=    Echo    Hello World
    Should Be Equal    ${result}    Hello World
