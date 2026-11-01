*** Settings ***
Documentation     The log messages of a remote keyword follow the log level of the suite: the client reports
...               it to the server when a session starts and when it changes. DEBUG and TRACE messages from
...               the server are marked, to tell them from the client's own.
Library           LogCapture.py
Library           NestedRobot.py
Library           JsonRpcRemote    tcp://127.0.0.1:${PORT}    ServerProbeLib


*** Variables ***
${PORT}           8271


*** Test Cases ***
Log Messages Follow Set Log Level
    Set Log Level    DEBUG
    Log At Each Level    first
    ${logs}=    Get Captured Log Messages
    Should Contain    ${logs}    first at INFO
    Should Contain    ${logs}    [remote] first at DEBUG
    Should Not Contain    ${logs}    [remote] first at TRACE
    Set Log Level    TRACE
    Log At Each Level    second
    ${logs}=    Get Captured Log Messages
    Should Contain    ${logs}    second at INFO
    Should Contain    ${logs}    [remote] second at DEBUG
    Should Contain    ${logs}    [remote] second at TRACE
    Should Contain    ${logs}    Arguments: [ 'second' ]
    Should Contain    ${logs}    [remote] Arguments: [ 'second' ]
    [Teardown]    Reset Log Level

Log Messages Follow The Log Level Of The Run From The Start Of A Session
    ${output}=    Run Nested Suite    ${CURDIR}${/}_nested${/}log_levels.robot    ${OUTPUT_DIR}${/}nested-log-levels
    ...    PORT:${PORT}    log_level=DEBUG
    ${messages}=    Get Messages    ${output}    Uses The Remote Library    DEBUG
    Should Contain    ${messages}    [remote] marker at DEBUG
