*** Settings ***
Documentation     The example server in Node.js over a pipe: the client starts it with --pipe=<address>. The suite
...               skips without node or without the packages of the example, except in CI, which installs them.
Library           LogCapture.py
Variables         paths.py
Variables         pipe_vars.py
Suite Setup       Import The Example Library


*** Test Cases ***
Echo Returns Its Message And Logs It
    ${result}=    Echo    Grüße aus Köln
    Should Be Equal    ${result}    Grüße aus Köln
    ${messages}=    Get Captured Log Messages
    Should Contain    ${messages}    Echoing Grüße aus Köln

Sum Of Adds A List
    ${sum}=    Sum Of    ${{[1, 2, 39]}}
    Should Be Equal    ${sum}    ${42}

Sum Of Converts Its Argument By The Declared Type
    ${sum}=    Sum Of    [1, 2, 39]
    Should Be Equal    ${sum}    ${42}

A Failing Keyword Fails Only Its Call
    Run Keyword And Expect Error    Boom from Node    Fail With    Boom from Node
    ${result}=    Echo    still there
    Should Be Equal    ${result}    still there


*** Keywords ***
Import The Example Library
    ${node}=    Evaluate    shutil.which("node")    modules=shutil
    IF    $node is None and not os.environ.get("CI")    Skip    node is not installed
    ${installed}=    Evaluate    os.path.isdir(os.path.join($NODE_EXAMPLE, "node_modules", "vscode-jsonrpc"))
    IF    not $installed and not os.environ.get("CI")
        Skip    the packages of the example are not installed: run npm ci in examples/node-robot-jsonrpcserver
    END
    Import Library    JsonRpcRemote    pipe:${NODE_EXAMPLE_COMMAND}    NodeLibrary
