*** Settings ***
Library    JsonRpcRemote    tcp://127.0.0.1:8271    Drawing


*** Test Cases ***
Arguments Travel Without The Types
    &{point}=    Create Dictionary    x=${1}    y=${2}
    ${text}=    Paint    ${point}    red
    Should Be Equal    ${text}    RED at 1,2

A Return Value Needs Its Type
    &{point}=    Create Dictionary    x=${1}    y=${2}
    Run Keyword And Expect Error
    ...    ValueError: Return value '{'x': 3, 'y': 5}' (dictionary) cannot be converted to shapes.Point: it cannot be imported: No module named 'shapes'
    ...    Move    ${point}    2    3
