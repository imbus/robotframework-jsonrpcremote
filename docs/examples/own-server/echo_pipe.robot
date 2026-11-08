*** Settings ***
Library    JsonRpcRemote    uri=pipe:simple-robot-jsonrpcserver    library_name=SimpleRobotLibrary


*** Test Cases ***
Echo Returns The Message
    ${result}=    Echo    Hello World
    Should Be Equal    ${result}    Hello World
