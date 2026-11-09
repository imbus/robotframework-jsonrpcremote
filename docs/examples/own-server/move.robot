*** Settings ***
Library    JsonRpcRemote    uri=tcp://127.0.0.1:8271    library_name=SimpleRobotLibrary


*** Test Cases ***
Move Returns The Moved Point
    ${point}=    Evaluate    simple_robot_jsonrpcserver.shapes.Point(1, 2)    modules=simple_robot_jsonrpcserver.shapes
    ${moved}=    Move    ${point}    2    3
    Should Be Equal    ${moved}    ${{simple_robot_jsonrpcserver.shapes.Point(3, 5)}}
