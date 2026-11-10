*** Settings ***
Documentation     Integration tests running against a live robot_jsonrpcremote server.
Library           ServerControl.py
Variables         paths.py
Suite Setup       Start Jsonrpc Server    JsonRpcRemote.Echo ServerProbeLib TypedInitLib ArgumentValuesLib LibdocLib ConsoleMessagesLib
...                   port=${PORT}    pythonpath=${LIBRARIES}    variables=GREETING:hello
...                   variablefile=${LIBRARIES}${/}server_vars.py
Suite Teardown    Stop Jsonrpc Server


*** Variables ***
${PORT}           8271
