*** Settings ***
Documentation     Server-side conversion of typed library-init arguments.
...               The client sends strings; Robot converts them via the __init__ signature.
Library           JsonRpcRemote    tcp://127.0.0.1:${PORT}    TypedInitLib
...                   mode=FAST    count=5    ratio=1.5    flag=true    amount=1.50
...                   when=2025-01-15    items=[1, 2, 3]    mapping={'a': 1, 'b': 2}    tags={'x', 'y'}    tag=hello


*** Variables ***
${PORT}           8271


*** Test Cases ***
Typed Init Arguments Are Converted Server-Side
    ${types}=    Get Arg Types
    Should Be Equal    ${types}[mode]       Mode
    Should Be Equal    ${types}[count]      int
    Should Be Equal    ${types}[ratio]      float
    Should Be Equal    ${types}[flag]       bool
    Should Be Equal    ${types}[amount]     Decimal
    Should Be Equal    ${types}[when]       date
    Should Be Equal    ${types}[items]      list
    Should Be Equal    ${types}[mapping]    dict
    Should Be Equal    ${types}[tags]       set

Enum Init Argument Resolves To The Member
    ${name}=    Get Mode Name
    Should Be Equal    ${name}    FAST

Init Argument Values Are Correct
    [Documentation]    Also checks nested conversion (list[int], dict[str, int] items).
    ${items}=    Get Value    items
    Should Be Equal    ${items}    ${{[1, 2, 3]}}
    ${mapping}=    Get Value    mapping
    Should Be Equal    ${mapping}    ${{ {'a': 1, 'b': 2} }}
    ${count}=    Get Value    count
    Should Be Equal    ${count}    ${5}

Custom Type Init Argument Stays A String
    [Documentation]    @library converters apply to keyword calls, not to library init args.
    ${types}=    Get Arg Types
    Should Be Equal    ${types}[tag]    str

Custom Type Keyword Argument Is Converted
    [Documentation]    The converter does apply to keyword-call arguments.
    ${type}=    Tag Type Of    hello
    Should Be Equal    ${type}    Tag
