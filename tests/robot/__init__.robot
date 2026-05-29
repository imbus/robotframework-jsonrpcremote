*** Settings ***
Documentation     Integration tests running against a live robot_jsonrpcremote server.
Library           ServerControl.py
Suite Setup       Start Jsonrpc Server    JsonRpcRemote.Echo ServerProbeLib TypedInitLib
...                   port=${PORT}    pythonpath=${CURDIR}    variables=GREETING:hello
Suite Teardown    Stop Jsonrpc Server


*** Variables ***
${PORT}           8271
