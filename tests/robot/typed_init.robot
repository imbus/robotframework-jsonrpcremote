*** Settings ***
Documentation     Server-side conversion of typed arguments.
...               Enums and built-in types are converted for library-init args; custom-type
...               converters apply to keyword calls but not to init args (Robot behaviour).
Library           JsonRpcRemote    tcp://127.0.0.1:${PORT}    TypedInitLib    mode=FAST    count=5    tag=hello


*** Variables ***
${PORT}           8271


*** Test Cases ***
Enum Init Argument Is Converted Server-Side
    ${type}=    Get Mode Type
    Should Be Equal    ${type}    Mode
    ${name}=    Get Mode Name
    Should Be Equal    ${name}    FAST

Int Init Argument Is Converted Server-Side
    ${type}=    Get Init Count Type
    Should Be Equal    ${type}    int
    ${count}=    Get Init Count
    Should Be Equal    ${count}    ${5}

Custom Type Init Argument Stays A String
    [Documentation]    @library converters are not applied to library init arguments.
    ${type}=    Get Tag Type
    Should Be Equal    ${type}    str

Custom Type Keyword Argument Is Converted
    [Documentation]    The converter does apply to keyword-call arguments.
    ${type}=    Tag Type Of    hello
    Should Be Equal    ${type}    Tag
