*** Settings ***
Documentation     The stdio transport is unsupported on Windows (the asyncio Proactor loop
...               cannot attach to stdin). Using it must fail with a clear, bounded error
...               instead of hanging. POSIX runners skip this suite -- the transport works
...               there and is covered by stdio_echo/stdio_probe/stdio_scope.
Variables         stdio_vars.py
Test Tags         windows


*** Test Cases ***
Stdio Transport Reports A Clear Error On Windows
    Skip If    not ${IS_WINDOWS}    The stdio transport is only unsupported on Windows.
    # Importing spawns the server subprocess, which exits because stdio is unavailable;
    # the client must surface that as an error within rpc_timeout, not block forever.
    Run Keyword And Expect Error    *
    ...    Import Library    JsonRpcRemote    stdio:${SERVER_COMMAND}    StdioEchoLib    rpc_timeout=${5}
