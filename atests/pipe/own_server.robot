*** Settings ***
Documentation     The hand-written example server over a pipe: the client starts it with --pipe=<address>,
...               and the server connects to that pipe with open_pipe_connection().
Library           LogCapture.py
Variables         pipe_vars.py
Library           JsonRpcRemote    pipe:${OWN_SERVER_COMMAND}    SimpleRobotLibrary


*** Test Cases ***
Echo Returns The Message
    ${result}=    Echo    Grüße
    Should Be Equal    ${result}    Grüße

Log Messages Of The Keyword Reach The Log
    ${result}=    Echo    with log messages
    Should Be Equal    ${result}    with log messages
    ${messages}=    Get Captured Log Messages
    Should Contain    ${messages}    RUN_KEYWORD_REQUEST processing...

Repeated Calls
    FOR    ${i}    IN RANGE    10
        ${result}=    Echo    message ${i}
        Should Be Equal    ${result}    message ${i}
    END
