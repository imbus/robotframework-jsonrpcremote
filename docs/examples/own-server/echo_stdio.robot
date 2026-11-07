*** Settings ***
Library    JsonRpcRemote    uri=stdio:simple-robot-jsonrpcserver --stdio    library_name=SimpleRobotLibrary


*** Test Cases ***
Echo Returns The Message
    ${result}=    Echo    Hello World
    Should Be Equal    ${result}    Hello World
