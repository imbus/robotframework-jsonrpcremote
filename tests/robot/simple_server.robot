*** Settings ***
Library     JsonRpcRemote
...             tcp://localhost:8271
...             JsonRpcRemote.Echo
...             named=asdf
...             rpc_timeout=${20}


*** Test Cases ***
first
    ${result}    Echo    Hello World
    Should Be Equal    ${result}    echo: Hello World
