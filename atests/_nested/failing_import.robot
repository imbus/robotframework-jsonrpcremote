*** Settings ***
Documentation     Run by protocol_errors.robot in a nested Robot process, not on its own: Robot skips directories
...               starting with an underscore. The import of its library fails on purpose. Needs the variables
...               PORT and LIBRARY.
Library           JsonRpcRemote    tcp://127.0.0.1:${PORT}    ${LIBRARY}


*** Test Cases ***
Without The Library
    No Operation
