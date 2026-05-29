*** Settings ***
Documentation     Keyword-call argument and return values round-trip with their types preserved.
Library           JsonRpcRemote    tcp://127.0.0.1:${PORT}    ServerProbeLib


*** Variables ***
${PORT}           8271


*** Test Cases ***
Integer Round Trips
    ${result}=    Echo Value    ${42}
    Should Be Equal    ${result}    ${42}

Integer Keeps Its Type On The Server
    ${type}=    Type Name Of    ${42}
    Should Be Equal    ${type}    int

String Round Trips
    ${result}=    Echo Value    hello
    Should Be Equal    ${result}    hello

Boolean Keeps Its Type On The Server
    ${type}=    Type Name Of    ${True}
    Should Be Equal    ${type}    bool

None Round Trips
    ${result}=    Echo Value    ${None}
    Should Be Equal    ${result}    ${None}

List Round Trips
    ${result}=    Echo Value    ${{[1, 2, 3]}}
    Should Be Equal    ${result}    ${{[1, 2, 3]}}

Dict Round Trips
    ${result}=    Echo Value    ${{ {'a': 1, 'b': 2} }}
    Should Be Equal    ${result}    ${{ {'a': 1, 'b': 2} }}

Keyword Named Arguments Are Passed
    ${result}=    Format Pair    first=left    second=right
    Should Be Equal    ${result}    left/right
