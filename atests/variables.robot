*** Settings ***
Documentation     Variables passed to the server via --variable reach keyword execution.
Library           JsonRpcRemote    tcp://127.0.0.1:${PORT}    ServerProbeLib


*** Variables ***
${PORT}           8271


*** Test Cases ***
Server Variable Is Available During Keyword Execution
    ${value}=    Get Robot Variable    GREETING
    Should Be Equal    ${value}    hello
