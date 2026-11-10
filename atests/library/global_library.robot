*** Settings ***
Documentation     A library with the scope GLOBAL has one instance on the server, which all clients share for
...               the lifetime of the server process; finalizing it for one client leaves it and its listener
...               to the others, and the warning after a reconnect says that its state is kept unless the
...               server restarted. Each test starts a server of its own on port 8287 and removes the events
...               file of the listener first, so no test depends on another. Sessions one after the other run
...               as nested runs of atests/_nested/counters.robot: each is a client of its own, whose session ends
...               with its run.
Library           Collections
Library           OperatingSystem
Library           IsolatedServerControl.py
Library           LogCapture.py
Library           NestedRobot.py
Variables         paths.py
Test Setup        Start A Server Of Its Own
Test Teardown     Stop Jsonrpc Server


*** Variables ***
${PORT}           8287
${URI}            tcp://127.0.0.1:${PORT}
${COUNTERS}       ${NESTED}${/}counters.robot
# Named after GlobalCounterLib.EVENTS_FILE. Not ${events}: Robot Framework ignores the case of variable names.
${EVENTS_FILE}    ${TEMPDIR}${/}jsonrpcremote-global-counter-events.txt
${KEPT}           Connection to '${URI}' was lost: *. Reconnected after *; the remote library was imported
...               again; its library scope is GLOBAL, so its server-side state is kept unless the server
...               restarted.


*** Test Cases ***
Only A Global Library Keeps Its Instance From One Session To The Next
    Run Nested Suite    ${COUNTERS}    ${OUTPUT_DIR}${/}global-library-first-session    PORT:${PORT}    GLOBAL:1
    Run Nested Suite    ${COUNTERS}    ${OUTPUT_DIR}${/}global-library-second-session    PORT:${PORT}    GLOBAL:2

Finalizing A Global Library For One Client Leaves It To The Others
    Import Library    JsonRpcRemote    ${URI}    GlobalCounterLib    rpc_scope=TEST    AS    Remaining Client
    ${count}=    Remaining Client.Count    before
    Should Be Equal As Integers    ${count}    1
    # The other client: its import is finalized when its run ends.
    Run Nested Suite    ${COUNTERS}    ${OUTPUT_DIR}${/}global-library-other-client    PORT:${PORT}    GLOBAL:2
    ${count}=    Remaining Client.Count    after
    Should Be Equal As Integers    ${count}    3
    ${content}=    Get File    ${EVENTS_FILE}
    Should Match Regexp    ${content}    (?m)^start_keyword .* after$
    Should Not Contain    ${content.splitlines()}    close

The Server Closes The Listener Of A Global Library Once When It Stops
    [Tags]    posix
    Import Library    JsonRpcRemote    ${URI}    GlobalCounterLib    rpc_scope=TEST    AS    Closing Client
    ${count}=    Closing Client.Count    closing
    Should Be Equal As Integers    ${count}    1
    # Another client, whose import is finalized when its run ends, before the stop.
    Run Nested Suite    ${COUNTERS}    ${OUTPUT_DIR}${/}global-library-client-before-stop    PORT:${PORT}    GLOBAL:2
    ${content}=    Get File    ${EVENTS_FILE}
    Should Not Contain    ${content.splitlines()}    close
    Stop Jsonrpc Server
    ${content}=    Get File    ${EVENTS_FILE}
    Should Contain X Times    ${content.splitlines()}    close    1

A Reconnect To A Global Library Over TCP Says Its State Is Kept Unless The Server Restarted
    Import Library    JsonRpcRemote    ${URI}    GlobalCounterLib    rpc_scope=TEST
    ...    rpc_connect_retry_timeout=30s    rpc_connect_retry_interval=0.2s    AS    Reconnecting Client
    ${count}=    Reconnecting Client.Count    before
    Should Be Equal As Integers    ${count}    1
    Stop Jsonrpc Server
    Start A Server Of Its Own
    # The restarted server has a new instance, which the client cannot tell from a reconnect to the old one.
    ${count}=    Reconnecting Client.Count    after
    Should Be Equal As Integers    ${count}    1
    ${logs}=    Get Captured Log Messages
    Should Contain Match    ${logs}    ${KEPT}


*** Keywords ***
Start A Server Of Its Own
    Remove File    ${EVENTS_FILE}
    Start Jsonrpc Server    GlobalCounterLib SuiteCounterLib TestCounterLib    port=${PORT}    pythonpath=${LIBRARIES}
