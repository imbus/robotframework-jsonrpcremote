*** Settings ***
Documentation     Keyword (named) library-init arguments are forwarded to the server library.
...               ServerProbeLib is loaded on the server via --pythonpath.
Library           JsonRpcRemote    tcp://127.0.0.1:${PORT}    ServerProbeLib    greeting=hello    times=3


*** Variables ***
${PORT}           8271


*** Test Cases ***
Init Keyword Arguments Are Forwarded
    ${kwargs}=    Get Init Kwargs
    Should Be Equal    ${kwargs}[greeting]    hello
    Should Be Equal    ${kwargs}[times]    3
