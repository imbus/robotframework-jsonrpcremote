*** Settings ***
Documentation     Errors that are no failures of a keyword: Robot Framework shows the message of the server,
...               without the code of the error and without the traceback of the server's own code. Uses its
...               own server on port 8281, which some tests restart, so the shared server stays unaffected.
Library           Collections
Library           IsolatedServerControl.py
Library           LogCapture.py
Library           NestedRobot.py
Suite Setup       Start The Server
Suite Teardown    Stop Jsonrpc Server


*** Variables ***
${PORT}           8281
${URI}            tcp://127.0.0.1:${PORT}


*** Test Cases ***
A Refused Import Fails With The Message Of The Server
    ${error}=    Import Error Of A Suite With    OtherLibrary
    Should End With    ${error.strip()}    failed: Library 'OtherLibrary' is not available.
    Should Not Contain    ${error}    RPC Error
    Should Not Contain    ${error}    Traceback

A Library That Fails To Import Shows What Is Missing And The Module Search Path
    ${error}=    Import Error Of A Suite With    MissingDependencyLib
    Should Contain    ${error}    No module named 'a_module_that_does_not_exist'
    Should Contain    ${error}    PYTHONPATH:
    Should Not Contain    ${error}    RPC Error
    Should Not Contain    ${error}    peer.py
    Should Not Contain    ${error}    _endpoint.py

A Return Value That Cannot Be Transferred Fails With The Message Of The Server
    Import Library    JsonRpcRemote    ${URI}    ProtocolErrorsLib    rpc_scope=TEST    AS    ProtocolErrors
    Set Log Level    DEBUG
    ${error}=    Run Keyword And Expect Error    *<lambda>*    Return A Lambda
    Should Not Contain    ${error}    Traceback
    ${logs}=    Get Captured Log Messages
    Should Not Contain Match    ${logs}    [[]remote] Traceback*
    [Teardown]    Reset Log Level

A Keyword Runs Before The Server Is Updated
    [Documentation]    With rpc_scope=TEST, the next test starts a session of its own, and Robot Framework
    ...                has registered the keywords of this one.
    Import Library    JsonRpcRemote    ${URI}    VersionedLib    rpc_scope=TEST    AS    Versioned
    ${result}=    Removed Later
    Should Be Equal    ${result}    Removed Later

A Keyword That The Library No Longer Has Fails With The Message Of The Server
    [Setup]    Restart The Server    variables=LIB_VERSION:after
    Run Keyword And Expect Error    Keyword 'Removed Later' not found in library 'VersionedLib'.    Removed Later
    ${result}=    Stays
    Should Be Equal    ${result}    Stays

With The Option The Log Holds The Traceback Of The Server
    [Setup]    Restart The Server    send_tracebacks=${True}
    Set Log Level    DEBUG
    ${error}=    Run Keyword And Expect Error    *<lambda>*    Return A Lambda
    Should Not Contain    ${error}    Traceback
    ${logs}=    Get Captured Log Messages
    Should Contain Match    ${logs}    [[]remote] Traceback (most recent call last):*
    [Teardown]    Reset Log Level

With The Option The Traceback Of The Server Follows The Error Of An Import
    [Setup]    Restart The Server    send_tracebacks=${True}
    ${error}=    Import Error Of A Suite With    MissingDependencyLib
    Should Match Regexp    ${error}
    ...    (?s)No module named 'a_module_that_does_not_exist'.*\\[remote\\] Traceback \\(most recent call last\\):.*_endpoint\\.py


*** Keywords ***
Start The Server
    [Arguments]    ${variables}=LIB_VERSION:before    ${send_tracebacks}=${False}
    Start Jsonrpc Server    ProtocolErrorsLib MissingDependencyLib VersionedLib    port=${PORT}
    ...    pythonpath=${CURDIR}    variables=${variables}    send_tracebacks=${send_tracebacks}

Restart The Server
    [Arguments]    ${variables}=LIB_VERSION:before    ${send_tracebacks}=${False}
    Stop Jsonrpc Server
    Start The Server    ${variables}    ${send_tracebacks}

Import Error Of A Suite With
    [Documentation]    In a nested run: unlike the error of the keyword Import Library, whose middle Robot
    ...                Framework removes if it is long, an execution error stays complete.
    [Arguments]    ${library}
    ${output}=    Run Nested Suite    ${CURDIR}${/}_nested${/}failing_import.robot
    ...    ${OUTPUT_DIR}${/}nested-failing-import    PORT:${PORT}    LIBRARY:${library}
    ${errors}=    Get Execution Errors    ${output}
    Length Should Be    ${errors}    1
    RETURN    ${errors}[0]
