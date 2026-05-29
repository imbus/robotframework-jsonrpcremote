*** Settings ***
Documentation     Integration tests running against a live robot_jsonrpcremote server.
Library           ServerControl.py
Suite Setup       Start Jsonrpc Server    JsonRpcRemote.Echo    ${PORT}
Suite Teardown    Stop Jsonrpc Server


*** Variables ***
${PORT}           8271
