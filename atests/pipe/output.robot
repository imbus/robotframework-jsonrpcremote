*** Settings ***
Documentation     Output and input of a server that the client started over a pipe: its stdout goes to the
...               stderr of robot, and its stdin is the null device, so the calls keep working. Each test has
...               a server of its own, so that a broken connection fails only that test.
Library           OperatingSystem
Library           LogCapture.py
Variables         pipe_vars.py
Library           JsonRpcRemote    pipe:${OUTPUT_SERVER_COMMAND}    StdioOutputLib
...               child_pid_file=${CHILD_PID_FILE}    rpc_scope=TEST


*** Test Cases ***
Child Process That Prints
    Run Child That Prints    from-child-process
    Connection Should Work

Shell Command That Prints
    Run Shell Command That Prints    from-shell-command
    Connection Should Work

Write To File Descriptor One
    Write To File Descriptor One    from-file-descriptor-one
    Connection Should Work

Console Output Of A Library
    Write To The Console    from-logger-console
    Connection Should Work

Print From A Thread After The Keyword Returned
    Print From A Thread Later    from-thread
    Sleep    0.3s
    Connection Should Work

Print In A Keyword Is Still Captured
    Print In The Keyword    captured-print
    ${messages}=    Get Captured Log Messages
    Should Contain    ${messages}    captured-print
    Connection Should Work

Child Process Reading Stdin Gets The End Of Its Input
    ${result}=    Read Stdin In A Child
    Should Be Equal    ${result}    ''
    Connection Should Work

Server Exiting With A Running Child Is Noticed At Once
    [Setup]    Remove File    ${CHILD_PID_FILE}
    Start Child That Keeps Running    ${15}
    ${started}=    Get Time    epoch
    Run Keyword And Expect Error    *lost while running keyword 'Exit Server'*server process exited with code 3*
    ...    Exit Server    exit_code=${3}
    ${ended}=    Get Time    epoch
    Should Be True    ${ended} - ${started} < 10
    [Teardown]    Stop The Child Process


*** Keywords ***
Connection Should Work
    ${result}=    Echo    still connected
    Should Be Equal    ${result}    echo: still connected

Stop The Child Process
    ${pid}=    Get File    ${CHILD_PID_FILE}
    Evaluate    os.kill(int($pid), signal.SIGTERM)    modules=os,signal
