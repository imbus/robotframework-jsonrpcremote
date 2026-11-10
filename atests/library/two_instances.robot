*** Settings ***
Documentation     Two instances of a library on one server stay apart, with their arguments and their logs.
Library           NestedRobot.py
Library           JsonRpcRemote    tcp://127.0.0.1:${PORT}    ServerProbeLib    first    AS    First
Library           JsonRpcRemote    tcp://127.0.0.1:${PORT}    ServerProbeLib    second    AS    Second
Variables         paths.py


*** Variables ***
${PORT}           8271


*** Test Cases ***
Each Instance Has Its Own Arguments
    ${first}=    First.Get Init Args
    ${second}=    Second.Get Init Args
    Should Be Equal    ${first}    ${{["first"]}}
    Should Be Equal    ${second}    ${{["second"]}}

The Log Messages Of Each Instance Stay Under Its Keywords
    ${output}=    Run Nested Suite    ${NESTED}${/}two_instances.robot
    ...    ${OUTPUT_DIR}${/}nested-two-instances    PORT:${PORT}
    ${messages}=    Get Messages By Keyword    ${output}    Call Both In Turn
    VAR    @{expected}    First.Emit Log: from first    Second.Emit Log: from second
    ...    First.Emit Log: from first again
    Should Be Equal    ${messages}    ${expected}
