*** Settings ***
Documentation     Integration tests running against a live robot_jsonrpcremote server.
Library           ServerControl.py
Suite Setup       Start Jsonrpc Server    JsonRpcRemote.Echo ServerProbeLib TypedInitLib ArgumentValuesLib LibdocLib ConsoleMessagesLib
...                   port=${PORT}    pythonpath=${CURDIR}    variables=GREETING:hello
...                   variablefile=${CURDIR}${/}server_vars.py
Suite Teardown    Stop Jsonrpc Server


*** Variables ***
${PORT}           8271
