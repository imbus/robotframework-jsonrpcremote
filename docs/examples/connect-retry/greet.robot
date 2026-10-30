*** Settings ***
Library    JsonRpcRemote    uri=tcp://127.0.0.1:8271    library_name=MyLibrary
...        rpc_connect_retry_timeout=1 minute    rpc_connect_retry_interval=0.5s


*** Test Cases ***
Greet Waits For The Server
    ${greeting}=    Greet    World
    Should Be Equal    ${greeting}    Hello, World!
