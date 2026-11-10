*** Settings ***
Documentation     Unicode and large values reach both sides unchanged, in calls and in log messages.
Library           LogCapture.py
Library           JsonRpcRemote    tcp://127.0.0.1:${PORT}    ServerProbeLib


*** Variables ***
${PORT}           8271
${UNICODE}        äöü ß € 日本語 😀


*** Test Cases ***
Unicode In An Argument And A Return Value
    ${result}=    Echo Value    ${UNICODE}
    Should Be Equal    ${result}    ${UNICODE}

Unicode In A Log Message
    Emit Log    ${UNICODE}
    ${logs}=    Get Captured Log Messages
    Should Contain    ${logs}    ${UNICODE}

A String Of 5 MB Goes Both Ways
    ${text}=    Evaluate    "x" * 5_000_000
    ${result}=    Echo Value    ${text}
    Should Be True    $result == $text

A List Of 200000 Items Goes Both Ways
    ${items}=    Evaluate    list(range(200_000))
    ${result}=    Echo Value    ${items}
    Should Be True    $result == $items

A Log Message Of 1 MB Arrives
    ${text}=    Evaluate    "y" * 1_000_000
    Emit Log    ${text}
    ${logs}=    Get Captured Log Messages
    Should Be True    $text in $logs
