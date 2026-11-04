*** Settings ***
Documentation     Run by protocol_mistakes.robot in a nested Robot process, not on its own: Robot skips directories
...               starting with an underscore. Needs the variable PORT.
Library           JsonRpcRemote    tcp://127.0.0.1:${PORT}    Anything    rpc_timeout=1


*** Test Cases ***
Calls A Keyword
    ${value}=    Say Hello
    Should Be Equal    ${value}    hello
