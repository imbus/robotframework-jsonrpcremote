*** Settings ***
Documentation     Recalls what is left of the value of the suite that ran before it, which is ${EXPECTED}.
Library           JsonRpcRemote    tcp://127.0.0.1:${PORT}    SessionValueLib    rpc_scope=${SCOPE}


*** Test Cases ***
Recall The Value In The Second Suite
    ${value}=    Recalled Value
    Should Be Equal As Strings    ${value}    ${EXPECTED}
