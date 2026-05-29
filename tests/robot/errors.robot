*** Settings ***
Documentation     A failing remote keyword propagates as an error to the client.
Library           JsonRpcRemote    tcp://127.0.0.1:${PORT}    ServerProbeLib


*** Variables ***
${PORT}           8271


*** Test Cases ***
Failing Keyword Propagates As Error
    Run Keyword And Expect Error    *boom*    Fail With    boom
