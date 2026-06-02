*** Settings ***
Documentation     The stdio transport carries the full protocol surface -- not just plain
...               returns: error responses, log notifications, and typed value round-trips.
...               Reuses ServerProbeLib so behaviour matches the TCP suites byte-for-byte.
Variables         stdio_vars.py
Library           LogCapture.py
Library           JsonRpcRemote    stdio:${PROBE_SERVER_COMMAND}    ServerProbeLib
Test Tags         posix


*** Test Cases ***
Failing Keyword Propagates As Error Over Stdio
    Run Keyword And Expect Error    *boom*    Fail With    boom

Server Log Is Forwarded To The Client Over Stdio
    # Exercises log notifications over the stdout frame channel and confirms the
    # server's own logging does not leak onto stdout and corrupt the stream.
    Emit Log    forwarded-stdio-marker
    ${logs}=    Get Captured Log Messages
    Should Contain    ${logs}    forwarded-stdio-marker

Integer Keeps Its Type Over Stdio
    ${type}=    Type Name Of    ${42}
    Should Be Equal    ${type}    int

List Round Trips Over Stdio
    ${result}=    Echo Value    ${{[1, 2, 3]}}
    Should Be Equal    ${result}    ${{[1, 2, 3]}}

Dict Round Trips Over Stdio
    ${result}=    Echo Value    ${{ {'a': 1, 'b': 2} }}
    Should Be Equal    ${result}    ${{ {'a': 1, 'b': 2} }}

Keyword Named Arguments Are Passed Over Stdio
    ${result}=    Format Pair    first=left    second=right
    Should Be Equal    ${result}    left/right
