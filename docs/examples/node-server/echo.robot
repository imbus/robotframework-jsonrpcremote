*** Settings ***
Library    JsonRpcRemote    uri=tcp://127.0.0.1:8271    library_name=NodeLibrary


*** Test Cases ***
Echo Returns The Message
    ${result}=    Echo    Hello World
    Should Be Equal    ${result}    Hello World

Sum Of Adds A List
    ${sum}=    Sum Of    ${{[1, 2, 39]}}
    Should Be Equal    ${sum}    ${42}

Fail With Fails
    Run Keyword And Expect Error    Boom    Fail With    Boom
