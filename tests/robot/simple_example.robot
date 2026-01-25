*** Settings ***
Library     JsonRpcRemote
...             tcp://localhost:8271
...             simple_library
...             123
...             named=hallo
...             named_int=${123}
...             rpc_scope=SUITE
...             rpc_timeout=10


*** Test Cases ***
first
    ${result}    JsonRpcRemote.Echo    Hello World
    Should Be Equal    ${result}    Hello World

second
    ${a}    JsonRpcRemote.Echo    ${12}

    Log    ${a}

data driven
    [Template]    template kw
    Hello World
    ${123}
    ${{ [1,2,3] }}
    ${{ {"a": True} }}
    ${{ {"a"} }}    # this should fail because sets are converted to lists at the moment
    ${{ "a" * 4}}


*** Keywords ***
template kw
    [Arguments]    ${value}
    ${result}    JsonRpcRemote.Echo    ${value}
    Should Be Equal    ${result}    ${value}
