*** Settings ***
Documentation     A server that listens on a pipe with --pipe-server: two libraries connect to it with the same
...               pipe:// URI, each over a connection of its own.
Library           IsolatedServerControl.py
Variables         pipe_vars.py
Suite Setup       Start The Server And Import Two Libraries
Suite Teardown    Stop Jsonrpc Server


*** Test Cases ***
Keywords Of The First Library Run
    ${result}=    PipeEcho.Echo    over a pipe
    Should Be Equal    ${result}    echo: over a pipe

Keywords Of The Second Library Run
    ${result}=    PipeProbe.Format Pair    first=left    second=right
    Should Be Equal    ${result}    left/right

Both Libraries Take Turns On Their Connections
    FOR    ${i}    IN RANGE    5
        ${echo}=    PipeEcho.Echo    call ${i}
        Should Be Equal    ${echo}    echo: call ${i}
        ${pair}=    PipeProbe.Format Pair    first=${i}    second=${i}
        Should Be Equal    ${pair}    ${i}/${i}
    END

The Import From A Pipe That Nobody Listens On Names The Pipe
    Run Keyword And Expect Error    *FileNotFoundError*${NOBODY_LISTENS}*
    ...    Import Library    JsonRpcRemote    pipe://${NOBODY_LISTENS}    StdioEchoLib    AS    NobodyListens


*** Keywords ***
Start The Server And Import Two Libraries
    Start Jsonrpc Server    StdioEchoLib ServerProbeLib    pythonpath=${CURDIR}    pipe=${PIPE_SERVER_NAME}
    Import Library    JsonRpcRemote    pipe://${PIPE_SERVER_NAME}    StdioEchoLib    AS    PipeEcho
    Import Library    JsonRpcRemote    pipe://${PIPE_SERVER_NAME}    ServerProbeLib    AS    PipeProbe
