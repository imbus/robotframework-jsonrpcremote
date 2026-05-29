*** Settings ***
Documentation     Library initialization arguments keep their JSON types end-to-end.
Library           JsonRpcRemote    tcp://127.0.0.1:${PORT}    JsonRpcRemote.Echo    ${42}    text


*** Variables ***
${PORT}           8271


*** Test Cases ***
Init Arguments Keep Their Types
    ${types}=    Get Init Arg Types
    Should Be Equal    ${types}[0]    int
    Should Be Equal    ${types}[1]    str

Init Arguments Are Passed Through Unchanged
    ${args}=    Get Init Args
    Should Be Equal    ${args}[0]    ${42}
    Should Be Equal    ${args}[1]    text
