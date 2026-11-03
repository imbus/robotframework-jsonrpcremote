*** Settings ***
Documentation     Calls two instances of a library on one server in turn, for the check of where their log
...               messages end up.
Library           JsonRpcRemote    tcp://127.0.0.1:${PORT}    ServerProbeLib    first    AS    First
Library           JsonRpcRemote    tcp://127.0.0.1:${PORT}    ServerProbeLib    second    AS    Second


*** Test Cases ***
Call Both In Turn
    First.Emit Log    from first
    Second.Emit Log    from second
    First.Emit Log    from first again
