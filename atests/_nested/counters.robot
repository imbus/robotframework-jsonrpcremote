*** Settings ***
Documentation     A client of its own for global_library.robot: counts once with each of the three counter
...               libraries on the server on port ${PORT}. Its session ends with the run, which finalizes its
...               imports. The GLOBAL library returns ${GLOBAL}, the other two 1.
Library           JsonRpcRemote    tcp://127.0.0.1:${PORT}    GlobalCounterLib    AS    Global Counter
Library           JsonRpcRemote    tcp://127.0.0.1:${PORT}    SuiteCounterLib    AS    Suite Counter
Library           JsonRpcRemote    tcp://127.0.0.1:${PORT}    TestCounterLib    AS    Test Counter


*** Test Cases ***
Count Once With Each Library
    ${count}=    Global Counter.Count    nested
    Should Be Equal As Integers    ${count}    ${GLOBAL}
    ${count}=    Suite Counter.Count
    Should Be Equal As Integers    ${count}    1
    ${count}=    Test Counter.Count
    Should Be Equal As Integers    ${count}    1
