*** Settings ***
Documentation     Variables passed to the server via --variable and --variablefile reach keyword execution.
Library           JsonRpcRemote    tcp://127.0.0.1:${PORT}    ServerProbeLib


*** Variables ***
${PORT}           8271


*** Test Cases ***
Server Variable Is Available During Keyword Execution
    ${value}=    Get Robot Variable    GREETING
    Should Be Equal    ${value}    hello

A Server Variable File Is Available During Keyword Execution
    ${value}=    Get Robot Variable    FROM_FILE
    Should Be Equal    ${value}    value from the file
