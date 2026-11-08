*** Settings ***
Documentation     Full protocol surface over a pipe: errors, log notifications, typed round-trips.
Variables         pipe_vars.py
Library           LogCapture.py
Library           JsonRpcRemote    pipe:${PROBE_SERVER_COMMAND}    ServerProbeLib


*** Test Cases ***
Failing Keyword Propagates As Error Over A Pipe
    Run Keyword And Expect Error    *boom*    Fail With    boom

Server Log Is Forwarded To The Client Over A Pipe
    Emit Log    forwarded-pipe-marker
    ${logs}=    Get Captured Log Messages
    Should Contain    ${logs}    forwarded-pipe-marker

Integer Keeps Its Type Over A Pipe
    ${type}=    Type Name Of    ${42}
    Should Be Equal    ${type}    int

List Round Trips Over A Pipe
    ${result}=    Echo Value    ${{[1, 2, 3]}}
    Should Be Equal    ${result}    ${{[1, 2, 3]}}

Dict Round Trips Over A Pipe
    ${result}=    Echo Value    ${{ {'a': 1, 'b': 2} }}
    Should Be Equal    ${result}    ${{ {'a': 1, 'b': 2} }}

Keyword Named Arguments Are Passed Over A Pipe
    ${result}=    Format Pair    first=left    second=right
    Should Be Equal    ${result}    left/right
