*** Settings ***
Documentation     A library that only the server can import, as in a container: the client cannot import the
...               classes of its defaults, and the keywords still run without these arguments, and Libdoc shows
...               the defaults. Uses its own server on port 8286, whose module search path holds the library.
Library           IsolatedServerControl.py
Library           LibdocSpecs.py
Suite Setup       Start The Server And Import The Library
Suite Teardown    Stop Jsonrpc Server


*** Variables ***
${PORT}               8286
${URI}                tcp://127.0.0.1:${PORT}
# Not on the module search path of this Robot run.
${LIBRARY FOLDER}     ${CURDIR}${/}_server_only


*** Test Cases ***
A Keyword With An Enum Default Runs Without The Argument
    ${result}=    Click
    Should Be Equal    ${result}    LEFT

The Server Converts A String For An Enum Argument
    ${result}=    Click    RIGHT
    Should Be Equal    ${result}    RIGHT

A Keyword With A Default That Cannot Be Pickled Runs Without The Argument
    ${result}=    Call
    Should Be Equal    ${result}    ${1}

Libdoc Shows The Default Of A Type That Only The Server Has
    ${keywords}=    Keywords In Json Spec    JsonRpcRemote::${URI}::ServerOnlyLib
    ...    ${OUTPUT_DIR}${/}libdoc-server-only.json
    Should Be Equal    ${keywords}[Click][args][0][repr]    button: Button = LEFT


*** Keywords ***
Start The Server And Import The Library
    Start Jsonrpc Server    ServerOnlyLib    port=${PORT}    pythonpath=${LIBRARY FOLDER}
    Import Library    JsonRpcRemote    ${URI}    ServerOnlyLib
