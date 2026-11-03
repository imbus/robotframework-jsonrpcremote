*** Settings ***
Documentation     A remote library gets the same values as a local one: the client has resolved them, and
...               the server does not resolve them a second time. Each test runs the same keyword locally
...               and remotely and compares the results.
Library           ArgumentValuesLib.py    AS    Local
Library           JsonRpcRemote    tcp://127.0.0.1:${PORT}    ArgumentValuesLib    AS    Remote
Library           ArgumentValuesLib.py    C:\\temp\\new    \${amount}    key\=value    AS    LocalPositional
Library           JsonRpcRemote    tcp://127.0.0.1:${PORT}    ArgumentValuesLib
...               C:\\temp\\new    \${amount}    key\=value    AS    RemotePositional
Library           ArgumentValuesLib.py    path=C:\\temp\\new    text=\${amount}    a\\b=1    \${key}=2    a\=b=3
...               AS    LocalNamed
Library           JsonRpcRemote    tcp://127.0.0.1:${PORT}    ArgumentValuesLib
...               path=C:\\temp\\new    text=\${amount}    a\\b=1    \${key}=2    a\=b=3    AS    RemoteNamed
Test Template     Remote Gives The Same As Local


*** Variables ***
${PORT}           8271
${KEY}            c\\d


*** Test Cases ***
Windows Path
    Echo    C:\\temp\\new

Regular Expression
    Echo    \\d+

Trailing Backslash
    Echo    end\\

Lone Backslash
    Echo    \\

Backslash Before A Letter That Means Something
    Echo    a\\nb

Text Like A Scalar Variable
    Echo    \${amount}

Text Like A List Variable
    Echo    \@{items}

Text Like A Dict Variable
    Echo    \&{map}

Text Like An Environment Variable
    Echo    \%{PATH}

Text Like Inline Python
    Echo    \${{1+1}}

Equals Sign
    Echo    key\=value

Equals Sign After The Name Of An Argument
    Echo    value\=1

Several Values
    Var Args    C:\\temp    \${amount}    a\=b

List That Holds Such Strings
    Echo    ${{["C:\\\\temp", "$" + "{amount}"]}}

Dict That Holds Such Strings
    Echo    ${{{"path": "C:\\\\temp", "text": "$" + "{amount}"}}}

Named Value With A Path
    Var Kwargs    path=C:\\temp

Named Value With The Syntax Of A Variable
    Var Kwargs    text=\${amount}

Named Argument Called With A Backslash
    Var Kwargs    a\\b=1

Named Argument Called With The Syntax Of A Variable
    Var Kwargs    \${key}=1

Named Argument Called With An Equals Sign
    Var Kwargs    a\=b=1

Named Argument Called From A Variable
    Var Kwargs    ${KEY}=1

And As A Value
    Echo    AND

Else As A Value
    Echo    ELSE

Else If As A Value
    Echo    ELSE IF

As As A Value
    Echo    AS

With Name As A Value
    Echo    WITH NAME

A Run Keyword Variant Finds Control Words
    [Documentation]    Its arguments stay unresolved, so a value passed on in a list variable would stay one too.
    [Template]    NONE
    ${local}=    Local.Words Of A Variant    first    AND    second    ELSE    C:\\temp    \${amount}
    ${remote}=    Remote.Words Of A Variant    first    AND    second    ELSE    C:\\temp    \${amount}
    Should Be Equal    ${remote}    ${local}

Var Args Without Values
    Var Args

Var Args With Values Of Several Types
    Var Args    a    ${1}    ${True}    ${None}

Var Args From A List Variable
    Var Args    @{{[1, "b"]}}

Var Kwargs From Named Arguments
    Var Kwargs    x=1    y=${2}

Var Kwargs From A Dict Variable
    Var Kwargs    &{{{"a": 1}}}

Positional Only With One Value
    [Documentation]    Without the template: Robot would take its empty dict variable as the second value.
    [Template]    NONE
    ${local}=    Local.Positional Only    a
    ${remote}=    Remote.Positional Only    a
    Should Be Equal    ${remote}    ${local}

Positional Only With Two Values
    [Template]    NONE
    ${local}=    Local.Positional Only    a    b
    ${remote}=    Remote.Positional Only    a    b
    Should Be Equal    ${remote}    ${local}

A Positional-Only Argument Given By Name Stays Text
    [Template]    NONE
    ${local}=    Local.Positional Only    first=a
    ${remote}=    Remote.Positional Only    first=a
    Should Be Equal    ${remote}    ${local}

Named Only With Its Required Argument
    Named Only    a    key=b

Named Only With Its Optional Argument
    Named Only    a    key=b    other=c

All Kinds Of Arguments At Once
    All Kinds    a    b    c    d    key=e    f=g

A Missing Named-Only Argument Fails As For A Local Keyword
    [Template]    NONE
    Run Keyword And Expect Error    Keyword 'Local.Named Only' missing named-only argument 'key'.
    ...    Local.Named Only    a
    Run Keyword And Expect Error    Keyword 'Remote.Named Only' missing named-only argument 'key'.
    ...    Remote.Named Only    a

Positional Values Of A Library Import
    [Template]    NONE
    ${local}=    LocalPositional.Init Values
    ${remote}=    RemotePositional.Init Values
    Should Be Equal    ${remote}    ${local}

Named Values And Names Of A Library Import
    [Template]    NONE
    ${local}=    LocalNamed.Init Values
    ${remote}=    RemoteNamed.Init Values
    Should Be Equal    ${remote}    ${local}


*** Keywords ***
Remote Gives The Same As Local
    [Documentation]    Passes the values on in list and dict variables, so that they are not resolved here again.
    [Arguments]    ${keyword}    @{args}    &{named}
    ${local}=    Run Keyword    Local.${keyword}    @{args}    &{named}
    ${remote}=    Run Keyword    Remote.${keyword}    @{args}    &{named}
    Should Be Equal    ${remote}    ${local}
