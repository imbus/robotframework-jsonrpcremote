*** Settings ***
Documentation     Remembers a value in a session with the rpc_scope ${SCOPE}, for the suite that runs after it.
Library           JsonRpcRemote    tcp://127.0.0.1:${PORT}    SessionValueLib    rpc_scope=${SCOPE}


*** Test Cases ***
Remember A Value In The First Suite
    Remember Value    kept
