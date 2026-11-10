*** Settings ***
Library    JsonRpcRemote    tcp://127.0.0.1:8271    Drawing


*** Test Cases ***
A Point Comes Back As A Point
    ${point}=    Evaluate    shapes.Point(1, 2)    modules=shapes
    ${moved}=    Move    ${point}    2    3
    Should Be Equal    ${moved}    ${{shapes.Point(3, 5)}}

The Name Of A Member Becomes The Member
    ${text}=    Paint    ${{shapes.Point(1, 2)}}    red
    Should Be Equal    ${text}    RED at 1,2
