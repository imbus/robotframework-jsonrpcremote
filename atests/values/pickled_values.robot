*** Settings ***
Documentation     Python objects travel unchanged between the client and a server in Python. Each value goes
...               to the server, which reports its type, and comes back from there.
Library           ArgumentValuesLib.py    AS    Local
Library           JsonRpcRemote    tcp://127.0.0.1:${PORT}    ArgumentValuesLib    AS    Remote
Test Template     Object Travels Unchanged


*** Variables ***
${PORT}           8271


*** Test Cases ***
Date And Time
    ${{datetime.datetime(2025, 1, 2, 3, 4, 5)}}

Decimal
    ${{decimal.Decimal("1.50")}}

Set
    ${{ {1, 2} }}

Bytes
    ${{bytes([0, 255])}}

Tuple
    ${{(1, "a")}}

An Instance Of A Custom Class Reaches The Server
    [Template]    NONE
    ${thing}=    Local.Make Thing    kept
    ${value}=    Remote.Value Of Thing    ${thing}
    Should Be Equal    ${value}    kept

An Instance Of A Custom Class Comes Back From The Server
    [Template]    NONE
    ${thing}=    Remote.Make Thing    kept
    ${value}=    Local.Value Of Thing    ${thing}
    Should Be Equal    ${value}    kept


*** Keywords ***
Object Travels Unchanged
    [Arguments]    ${value}
    ${type}=    Remote.Type Name Of    ${value}
    Should Be Equal    ${type}    ${{type($value).__name__}}
    ${result}=    Remote.Same Value    ${value}
    Should Be Equal    ${{type($result).__name__}}    ${type}
    Should Be True    $result == $value
