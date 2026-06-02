*** Settings ***
Documentation     The server shuts down cleanly when terminated. The patched Robot signal
...               monitor stops the embedded runner gracefully, so the process exits with
...               code 0 and no kill() fallback is needed (no "Second signal..." noise).
...               Uses an isolated server on its own port so the shared server used by the
...               other suites is unaffected.
Library           IsolatedServerControl.py
Suite Setup       Start Jsonrpc Server    JsonRpcRemote.Echo    port=${SHUTDOWN_PORT}
Suite Teardown    Stop Jsonrpc Server


*** Variables ***
${SHUTDOWN_PORT}    8272


*** Test Cases ***
Keyword Runs Against The Isolated Server
    [Documentation]    Proves the isolated server serves keywords and a client session
    ...                (including its finalize/shutdown/exit teardown) works end-to-end.
    ...                rpc_scope=TEST tears the session down at the end of this test, while
    ...                the server is still alive.
    Import Library    JsonRpcRemote    tcp://127.0.0.1:${SHUTDOWN_PORT}    JsonRpcRemote.Echo
    ...                   rpc_scope=TEST
    ${result}=    Echo    graceful
    Should Be Equal    ${result}    echo: graceful

Server Stops Gracefully On Termination
    [Documentation]    SIGTERM is handled by the patched signal monitor: the runner stops,
    ...                the suite finishes, and the process exits 0 without a kill() fallback.
    [Tags]    posix    # SIGTERM/graceful shutdown is POSIX-only; Windows terminate() is a hard kill.
    Stop Jsonrpc Server
    ${code}=    Get Server Exit Code
    Should Be Equal As Integers    ${code}    0
    ${killed}=    Server Was Killed
    Should Be Equal    ${killed}    ${False}
