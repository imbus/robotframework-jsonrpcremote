*** Settings ***
Documentation     Run by log_outside_keyword_calls.robot in a nested Robot process, not on its own:
...               Robot skips directories starting with an underscore. Needs the variable PORT.
Library           JsonRpcRemote    tcp://127.0.0.1:${PORT}    CloseLogLib


*** Test Cases ***
Uses The Remote Library
    ${result}=    Ping
    Should Be Equal    ${result}    pong
