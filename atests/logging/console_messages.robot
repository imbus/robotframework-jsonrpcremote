*** Settings ***
Documentation     A remote keyword writes to the console what a local keyword writes there: warnings and errors,
...               and no info messages.
Library           NestedRobot.py
Variables         paths.py


*** Variables ***
${PORT}           8271


*** Test Cases ***
A Local Keyword Writes Warnings And Errors To The Console
    Run The Suite And Check The Console    local

A Remote Keyword Writes Warnings And Errors To The Console
    Run The Suite And Check The Console    remote    URI:tcp://127.0.0.1:${PORT}


*** Keywords ***
Run The Suite And Check The Console
    [Arguments]    ${kind}    @{variables}
    Run Nested Suite    ${NESTED}${/}console_messages.robot
    ...    ${OUTPUT_DIR}${/}nested-console-${kind}    @{variables}
    ${console}=    Get Console Output
    Should Contain    ${console}    [ WARN ] a warning
    Should Contain    ${console}    [ ERROR ] an error
    Should Not Contain    ${console}    an info message
