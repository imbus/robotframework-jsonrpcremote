*** Settings ***
Library    JsonRpcRemote    uri=tcp://127.0.0.1:8271    library_name=Counter
...        rpc_scope=TEST


*** Test Cases ***
The First Test Counts From One
    ${count}=    Increment
    Should Be Equal As Integers    ${count}    1
    ${count}=    Increment
    Should Be Equal As Integers    ${count}    2

The Next Test Counts From One Again
    ${count}=    Increment
    Should Be Equal As Integers    ${count}    1
