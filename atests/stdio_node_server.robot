*** Settings ***
Documentation     A server written in Node, started over stdio: keywords in another language are what the
...               protocol is for. The suite skips if node is missing, except in CI, whose runners have it.
Library           LogCapture.py
Variables         stdio_vars.py
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

Lists And Dicts Reach A Server In Another Language As JSON
    [Documentation]    The Node server states no pickle protocol, so the client sends it no pickles.
    ${json}=    Json Of    ${{[1, 2]}}
    Should Be Equal    ${json}    [1,2]
    &{dict}=    Create Dictionary    a=${1}
    ${json}=    Json Of    ${dict}
    Should Be Equal    ${json}    {"a":1}

A Tuple Comes Back Through A Server In Another Language
    [Documentation]    The tuple travels as typed JSON that names its type, which the Node server returns as it is.
    ${json}=    Json Of    ${{(1, "a")}}
    Should Be Equal    ${json}    {"__type__":"tuple","value":[1,"a"]}
    ${result}=    Echo    ${{(1, "a")}}
    Should Be Equal    ${result}    ${{(1, "a")}}
    Should Be True    isinstance($result, tuple)

An Object That Needs A Pickle Fails Before It Is Sent
    Run Keyword And Expect Error
    ...    TypeError: Argument 'message' of type 'object' cannot be sent: it is not JSON, and the server reads no pickles.
    ...    Echo    ${{object()}}

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
    Import Library    JsonRpcRemote    stdio:${NODE_WRAPPER_COMMAND}    NodeKeywords    AS    NodeThroughWrapper
    ${result}=    NodeThroughWrapper.Echo    through the wrapper
    Should Be Equal    ${result}    through the wrapper


*** Keywords ***
Import The Node Library
    ${node}=    Evaluate    shutil.which("node")    modules=shutil
    IF    $node is None and not os.environ.get("CI")    Skip    node is not installed
    Import Library    JsonRpcRemote    stdio:${NODE_SERVER_COMMAND}    NodeKeywords
