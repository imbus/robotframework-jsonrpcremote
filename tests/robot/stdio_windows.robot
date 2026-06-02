*** Settings ***
Documentation     On Windows the stdio transport must fail with a clear error (excluded on POSIX).
Variables         stdio_vars.py
Test Tags         windows


*** Test Cases ***
Stdio Transport Reports A Clear Error On Windows
    Run Keyword And Expect Error    *
    ...    Import Library    JsonRpcRemote    stdio:${SERVER_COMMAND}    StdioEchoLib    rpc_timeout=${5}
