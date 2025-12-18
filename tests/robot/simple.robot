*** Settings ***
Library     JsonRpcRemote    tcp://localhost:8888    simple_library    123    named=hallo  named_int=${123}   rpc_scope=TEST    rpc_timeout=10


*** Test Cases ***
first
    ${result}  JsonRpcRemote.Echo    Hello World
    Should Be Equal    ${result}    Hello World

second
    ${a}    JsonRpcRemote.Echo    ${12}

    Log    ${a}
