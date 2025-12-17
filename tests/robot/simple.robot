*** Settings ***
Library  JsonRpcRemote    localhost:8888    scope=TEST

*** Test Cases ***
first
    JsonRpcRemote.Echo    Hello World


second
    ${a}  JsonRpcRemote.Echo    ${12}

    Log  ${a}
