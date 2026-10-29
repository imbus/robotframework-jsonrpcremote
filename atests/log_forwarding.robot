*** Settings ***
Documentation     Log messages emitted on the server are forwarded to the client during execution.
Library           LogCapture.py
Library           JsonRpcRemote    tcp://127.0.0.1:${PORT}    ServerProbeLib


*** Variables ***
${PORT}           8271


*** Test Cases ***
Server Log Is Forwarded To The Client
    Emit Log    forwarded-log-marker
    ${logs}=    Get Captured Log Messages
    Should Contain    ${logs}    forwarded-log-marker
