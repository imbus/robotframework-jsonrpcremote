*** Settings ***
Documentation     A keyword with embedded arguments works on a remote library as on a local one: the client
...               sends the name from its definition and the values as arguments. The calls stand here without
...               a template, because Run Keyword would resolve the values in the names a second time.
Library           ArgumentValuesLib.py    AS    Local
Library           JsonRpcRemote    tcp://127.0.0.1:${PORT}    ArgumentValuesLib    AS    Remote


*** Variables ***
${PORT}           8271
@{LIST}           1    2


*** Test Cases ***
Plain Value
    ${local}=    Local.Embedded hello In The Name
    ${remote}=    Remote.Embedded hello In The Name
    Should Be Equal    ${remote}    ${local}

Value That Is Not A String
    ${local}=    Local.Embedded ${LIST} In The Name
    ${remote}=    Remote.Embedded ${LIST} In The Name
    Should Be Equal    ${remote}    ${local}

Value With A Backslash
    ${local}=    Local.Embedded C:\\temp In The Name
    ${remote}=    Remote.Embedded C:\\temp In The Name
    Should Be Equal    ${remote}    ${local}

Value With The Syntax Of A Variable
    ${local}=    Local.Embedded \${amount} In The Name
    ${remote}=    Remote.Embedded \${amount} In The Name
    Should Be Equal    ${remote}    ${local}

Type With Its Own Pattern
    ${local}=    Local.Embedded 42 With A Type
    ${remote}=    Remote.Embedded 42 With A Type
    Should Be Equal    ${remote}    ${local}

Further Positional Argument
    ${local}=    Local.Embedded a And Another    C:\\b
    ${remote}=    Remote.Embedded a And Another    C:\\b
    Should Be Equal    ${remote}    ${local}

Further Named Argument
    ${local}=    Local.Embedded a And Another    other=C:\\b
    ${remote}=    Remote.Embedded a And Another    other=C:\\b
    Should Be Equal    ${remote}    ${local}

The Keyword That Fits Best Among Overlapping Patterns
    ${local}=    Local.Overlapping a And More
    ${remote}=    Remote.Overlapping a And More
    Should Be Equal    ${remote}    ${local}

The Other Keyword Among Overlapping Patterns
    ${local}=    Local.Overlapping a And b
    ${remote}=    Remote.Overlapping a And b
    Should Be Equal    ${remote}    ${local}

Normal Keyword Whose Name Fits A Pattern
    ${local}=    Local.Normal Keyword Next To A Pattern
    ${remote}=    Remote.Normal Keyword Next To A Pattern
    Should Be Equal    ${remote}    ${local}

Embedded Keyword Next To A Normal Keyword
    ${local}=    Local.Normal other Next To A Pattern
    ${remote}=    Remote.Normal other Next To A Pattern
    Should Be Equal    ${remote}    ${local}
