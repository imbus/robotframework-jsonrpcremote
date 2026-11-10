*** Settings ***
Documentation     A client that names no library gets the first library on the command line of the server.
Library           JsonRpcRemote    tcp://127.0.0.1:${PORT}


*** Variables ***
${PORT}           8271


*** Test Cases ***
A Client That Names No Library Gets The First Library Of The Server
    ${result}=    Echo    hello
    Should Be Equal    ${result}    echo: hello
