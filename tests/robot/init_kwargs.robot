*** Settings ***
Documentation     Named library-init arguments are forwarded to the server library, while the
...               client's own options (rpc_timeout, rpc_scope) are consumed by the client and
...               not leaked into the remote library. rpc_scope=TEST also restarts the session
...               per test, which the two test cases exercise. ServerProbeLib is loaded via --pythonpath.
Library           JsonRpcRemote    tcp://127.0.0.1:${PORT}    ServerProbeLib
...                   greeting=hello    times=3    enabled=true    note=a b c
...                   rpc_timeout=20    rpc_scope=TEST


*** Variables ***
${PORT}           8271


*** Test Cases ***
Named Init Arguments Are Forwarded
    ${kwargs}=    Get Init Kwargs
    Should Be Equal    ${kwargs}[greeting]    hello
    Should Be Equal    ${kwargs}[times]       3
    Should Be Equal    ${kwargs}[enabled]     true
    Should Be Equal    ${kwargs}[note]        a b c

Client Options Are Not Forwarded To The Library
    [Documentation]    rpc_timeout/rpc_scope bind to JsonRpcRemote.__init__, not to the remote lib.
    ${kwargs}=    Get Init Kwargs
    Should Not Contain    ${kwargs}    rpc_timeout
    Should Not Contain    ${kwargs}    rpc_scope
