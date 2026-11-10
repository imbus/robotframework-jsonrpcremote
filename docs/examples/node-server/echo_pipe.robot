*** Settings ***
Library    JsonRpcRemote    uri=${SERVER}    library_name=NodeLibrary


*** Variables ***
@{SERVER}    pipe:    node    ${CURDIR}/../../../examples/node-robot-jsonrpcserver/src/server.ts


*** Test Cases ***
Echo Returns The Message
    ${result}=    Echo    Hello World
    Should Be Equal    ${result}    Hello World
