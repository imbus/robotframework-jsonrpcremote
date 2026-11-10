*** Settings ***
Documentation     Run by console_messages.robot in a nested Robot process, not on its own: Robot skips directories
...               starting with an underscore. Imports the library locally, or from the server at the variable URI.
Suite Setup       Import The Library


*** Variables ***
${URI}            ${EMPTY}


*** Test Cases ***
Logs At Three Levels
    Log At Three Levels


*** Keywords ***
Import The Library
    IF    '${URI}'
        Import Library    JsonRpcRemote    ${URI}    ConsoleMessagesLib
    ELSE
        Import Library    ${CURDIR}${/}..${/}libraries${/}ConsoleMessagesLib.py
    END
