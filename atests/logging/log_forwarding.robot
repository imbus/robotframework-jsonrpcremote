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

A Log Message With HTML Stays HTML
    Emit Html Log    <b>marked with an argument</b>
    ${html}=    Get Captured Html Messages
    Should Contain    ${html}    <b>marked with an argument</b>

A Printed Message With The Marker HTML Is HTML
    Print Html    <b>marked in the text</b>
    ${html}=    Get Captured Html Messages
    Should Contain    ${html}    <b>marked in the text</b>

A Plain Log Message Is Not HTML
    Emit Log    <b>plain text</b>
    ${logs}=    Get Captured Log Messages
    Should Contain    ${logs}    <b>plain text</b>
    ${html}=    Get Captured Html Messages
    Should Not Contain    ${html}    <b>plain text</b>
