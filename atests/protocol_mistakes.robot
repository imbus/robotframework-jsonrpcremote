*** Settings ***
Documentation     What a Robot Framework user sees when a server breaks the protocol. Uses a raw server of its own
...               on port 8285, and calls it from a nested Robot process, so that the errors stay out of this run.
Library           Collections
Library           NestedRobot.py
Library           RawServerLib.py
Test Teardown     Stop Raw Server


*** Variables ***
${PORT}           8285
${URI}            tcp://127.0.0.1:${PORT}
${TEST}           Calls A Keyword


*** Test Cases ***
Error For A Message Without A Valid Length During A Keyword Call
    ${output}=    Run Against A Server With The Mistake    invalid_length_during_a_keyword
    The Keyword Should Have Passed    ${output}
    ${messages}=    Get Messages    ${output}    ${TEST}    ERROR
    Should Contain Match    ${messages}    *'${URI}'*'abc'*
    The Execution Errors Should Hold    ${output}    *'${URI}'*'abc'*
    ${console}=    Get Console Output
    Should Match    ${console}    *\[ ERROR \]*'${URI}'*'abc'*

Error For A Message Without A Valid Length While The Library Is Imported
    ${output}=    Run Against A Server With The Mistake    invalid_length_at_the_import
    The Execution Errors Should Hold    ${output}    *'abc'*
    The Execution Errors Should Hold    ${output}    *Timeout waiting*

Error For A Log Message With Params That Cannot Be Converted
    ${output}=    Run Against A Server With The Mistake    log_params_that_cannot_be_converted
    The Keyword Should Have Passed    ${output}
    The Execution Errors Should Hold    ${output}    *'robot/log'*

Error For An Error Response Without An Id
    ${output}=    Run Against A Server With The Mistake    error_without_an_id
    The Keyword Should Have Passed    ${output}
    The Execution Errors Should Hold    ${output}    *-32700*bad*

Response With A Null Error Counts As Success
    ${output}=    Run Against A Server With The Mistake    null_error
    The Keyword Should Have Passed    ${output}
    There Should Be No Execution Errors    ${output}

Header Name In Lower Case Works
    ${output}=    Run Against A Server With The Mistake    lower_case_header
    The Keyword Should Have Passed    ${output}
    There Should Be No Execution Errors    ${output}

Response Without Jsonrpc Fails The Import With Its Reason
    ${output}=    Run Against A Server With The Mistake    no_version
    The Execution Errors Should Hold    ${output}    *JSON-RPC version*
    ${errors}=    Get Execution Errors    ${output}
    Should Not Contain Match    ${errors}    *Timeout*

Warning That Is Not For The Console
    ${has it}=    Robot Framework Has The Console Option
    Skip If    not ${has it}    Robot Framework has no such option before 7.4.
    ${output}=    Run Against A Server With The Mistake    warning_off_the_console
    ${messages}=    Get Messages    ${output}    ${TEST}    WARN
    Should Contain    ${messages}    not for the console
    ${console}=    Get Console Output
    Should Not Contain    ${console}    not for the console


*** Keywords ***
Run Against A Server With The Mistake
    [Arguments]    ${mistake}
    Start Raw Server    ${mistake}    ${PORT}
    ${output}=    Run Nested Suite    ${CURDIR}${/}_nested${/}raw_server.robot
    ...    ${OUTPUT_DIR}${/}nested-raw-server-${mistake}    PORT:${PORT}    allow_failures=${True}
    RETURN    ${output}

The Keyword Should Have Passed
    [Arguments]    ${output}
    ${results}=    Get Test Results    ${output}
    Should Be Equal    ${results}[${TEST}]    PASS:${SPACE}

The Execution Errors Should Hold
    [Arguments]    ${output}    ${pattern}
    ${errors}=    Get Execution Errors    ${output}
    Should Contain Match    ${errors}    ${pattern}

There Should Be No Execution Errors
    [Arguments]    ${output}
    ${errors}=    Get Execution Errors    ${output}
    Should Be Empty    ${errors}
