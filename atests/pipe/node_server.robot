*** Settings ***
Documentation     A server written in Node, started over a pipe: it connects to the address of its --pipe=
...               argument. The suite skips if node is missing, except in CI, whose runners have it.
Library           LogCapture.py
Variables         pipe_vars.py
Suite Setup       Import The Node Library


*** Test Cases ***
Keywords Return Their Results
    ${sum}=    Add Numbers    ${2}    ${40}
    Should Be Equal    ${sum}    ${42}
    ${echo}=    Echo    from Robot Framework
    Should Be Equal    ${echo}    from Robot Framework

Umlauts Pass Unchanged
    ${result}=    Echo    Grüße aus Köln
    Should Be Equal    ${result}    Grüße aus Köln

A Failing Keyword Fails Only Its Call
    Run Keyword And Expect Error    Boom from Node    Fail With    Boom from Node
    ${result}=    Echo    still there
    Should Be Equal    ${result}    still there

A Log Message Reaches The Log
    Write To The Log    message-from-node
    ${messages}=    Get Captured Log Messages
    Should Contain    ${messages}    message-from-node

An Asynchronous Keyword Returns Later
    ${result}=    Wait And Return    ${200}    after a while
    Should Be Equal    ${result}    after a while

One MiB Passes In Both Directions
    ${data}=    Evaluate    "x" * 1048576
    ${result}=    Echo    ${data}
    Should Be Equal    ${result}    ${data}

A Hundred Calls
    FOR    ${index}    IN RANGE    100
        ${result}=    Echo    call ${index}
        Should Be Equal    ${result}    call ${index}
    END

A Wrapper Script Starts The Server
    [Tags]    windows
    Import Library    JsonRpcRemote    pipe:${NODE_WRAPPER_COMMAND}    NodeKeywords    AS    NodeThroughWrapper
    ${result}=    NodeThroughWrapper.Echo    through the wrapper
    Should Be Equal    ${result}    through the wrapper


*** Keywords ***
Import The Node Library
    ${node}=    Evaluate    shutil.which("node")    modules=shutil
    IF    $node is None and not os.environ.get("CI")    Skip    node is not installed
    Import Library    JsonRpcRemote    pipe:${NODE_SERVER_COMMAND}    NodeKeywords
