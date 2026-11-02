*** Settings ***
Library    JsonRpcRemote    tcp://127.0.0.1:8271    OtherLibrary


*** Test Cases ***
Without The Library
    Log    The suite runs, but the keywords of the library are not available.
