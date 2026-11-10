*** Settings ***
Documentation     The value format between our client and our server: with pickles turned off on either side, a
...               value that JSON cannot hold travels as typed JSON, and an object without a form fails with a
...               message that names the option; values of declared types travel as typed JSON in any case. Each
...               test starts the server that it needs, on port 8288 with pickles or on port 8289 with
...               --no-pickles, and imports the remote library itself, under an alias of its own. The types of
...               TypedValuesLib come from typed_values_types, which the client imports by its name too; the
...               server alone has the folder _server_only.
Library           ArgumentValuesLib.py    AS    Local
Library           IsolatedServerControl.py
Library           LibdocSpecs.py
Variables         typed_values_vars.py
Test Teardown     Stop Jsonrpc Server


*** Variables ***
${WITH_PICKLES}       8288
${WITHOUT_PICKLES}    8289


*** Test Cases ***
With Pickles Turned Off On The Client An Object Fails With The Option
    Start A Server    ${WITH_PICKLES}
    Import The Library    ${WITH_PICKLES}    ClientWithoutPickles    pickles=no
    ${thing}=    Local.Make Thing    kept
    Run Keyword And Expect Error
    ...    TypeError: Argument 'value' of type 'ArgumentValuesLib.Thing' cannot be sent: it is not JSON, and rpc_pickles is off.
    ...    ClientWithoutPickles.Same Value    ${thing}

With Pickles Turned Off On The Server A Returned Object Fails With The Option
    Start A Server    ${WITHOUT_PICKLES}    pickles=${False}
    Import The Library    ${WITHOUT_PICKLES}    ServerWithoutPickles
    Run Keyword And Expect Error
    ...    *The return value of type 'ArgumentValuesLib.Thing' cannot be sent: it is not JSON, and pickles are turned off with --no-pickles.
    ...    ServerWithoutPickles.Make Thing    kept

A Tuple Makes A Round Trip With Pickles Turned Off On The Client
    Start A Server    ${WITH_PICKLES}
    Import The Library    ${WITH_PICKLES}    TupleWithoutClientPickles    pickles=no
    Tuple Makes A Round Trip    TupleWithoutClientPickles

A Tuple Makes A Round Trip With Pickles Turned Off On The Server
    Start A Server    ${WITHOUT_PICKLES}    pickles=${False}
    Import The Library    ${WITHOUT_PICKLES}    TupleWithoutServerPickles
    Tuple Makes A Round Trip    TupleWithoutServerPickles


Declared Values Make A Round Trip With Pickles
    Start A Typed Server    ${WITH_PICKLES}
    Import The Typed Library    ${WITH_PICKLES}    TypedWithPickles
    Declared Values Make A Round Trip    TypedWithPickles

Declared Values Make A Round Trip With Pickles Turned Off On The Client
    Start A Typed Server    ${WITH_PICKLES}
    Import The Typed Library    ${WITH_PICKLES}    TypedWithoutClientPickles    pickles=no
    Declared Values Make A Round Trip    TypedWithoutClientPickles

Declared Values Make A Round Trip With Pickles Turned Off On The Server
    Start A Typed Server    ${WITHOUT_PICKLES}    pickles=${False}
    Import The Typed Library    ${WITHOUT_PICKLES}    TypedWithoutServerPickles
    Declared Values Make A Round Trip    TypedWithoutServerPickles

Undeclared Values Make A Round Trip Without Pickles
    Start A Typed Server    ${WITHOUT_PICKLES}    pickles=${False}
    Import The Typed Library    ${WITHOUT_PICKLES}    Undeclared
    FOR    ${value}    IN    @{TYPED_VALUES}
        ${result}=    Undeclared.Same Any    ${value}
        Should Be The Same Value    ${result}    ${value}
        ${type}=    Undeclared.Type Name Of    ${value}
        Should Be Equal    ${type}    ${{type($value).__module__ + "." + type($value).__qualname__}}
    END

A Dict From A Robot Variable Reaches The Server As A Dict
    Start A Typed Server    ${WITH_PICKLES}
    Import The Typed Library    ${WITH_PICKLES}    DotDicts
    &{dict}=    Create Dictionary    a=${1}
    ${type}=    DotDicts.Type Name Of    ${dict}
    Should Be Equal    ${type}    builtins.dict
    ${result}=    DotDicts.Same Any    ${dict}
    Should Be Equal    ${result}    ${{ {"a": 1} }}

A Returned Class That The Client Does Not Have Fails
    Start A Typed Server    ${WITHOUT_PICKLES}    pickles=${False}
    Import The Typed Library    ${WITHOUT_PICKLES}    ServerOnly
    Run Keyword And Expect Error
    ...    ValueError: Return value '*' (dictionary) cannot be converted to ServerOnlyTypes.OnlyOnTheServer: it cannot be imported: No module named 'ServerOnlyTypes'
    ...    ServerOnly.Make Only On The Server

A Returned Declared Class That The Client Does Not Have Fails With Pickles
    [Documentation]    A declared type travels as typed JSON in any case, so it fails with pickles, too.
    Start A Typed Server    ${WITH_PICKLES}
    Import The Typed Library    ${WITH_PICKLES}    DeclaredServerOnlyWithPickles
    Declared Class Of The Server Fails    DeclaredServerOnlyWithPickles

A Returned Declared Class That The Client Does Not Have Fails Without Pickles
    Start A Typed Server    ${WITHOUT_PICKLES}    pickles=${False}
    Import The Typed Library    ${WITHOUT_PICKLES}    DeclaredServerOnlyWithoutPickles
    Declared Class Of The Server Fails    DeclaredServerOnlyWithoutPickles

Libdoc Describes A Declared Enum With Its Members
    Start A Typed Server    ${WITH_PICKLES}
    ${typedocs}=    Typedocs In Json Spec    JsonRpcRemote::tcp://127.0.0.1:${WITH_PICKLES}::TypedValuesLib
    ...    ${OUTPUT_DIR}${/}libdoc-typed-values.json    pythonpath=${CURDIR}
    Should Be Equal    ${typedocs}[Color][type]    Enum
    Should Be Equal    ${{[member["name"] for member in $typedocs["Color"]["members"]]}}    ${{["RED", "GREEN"]}}


*** Keywords ***
Start A Typed Server
    [Arguments]    ${port}    ${pickles}=${True}
    Start Jsonrpc Server    TypedValuesLib    port=${port}    pythonpath=${CURDIR}${:}${CURDIR}${/}_server_only
    ...    pickles=${pickles}

Import The Typed Library
    [Arguments]    ${port}    ${alias}    ${pickles}=yes
    Import Library    JsonRpcRemote    tcp://127.0.0.1:${port}    TypedValuesLib    rpc_scope=TEST
    ...    rpc_pickles=${pickles}    AS    ${alias}

Declared Values Make A Round Trip
    [Arguments]    ${alias}
    ${keywords}=    Create List    Same Point    Same Pair    Same Color    Same Datetime    Same Decimal
    ...    Same Bytes    Same Uuid    Same Path    Same Tuple    Same Set    Same Int Keys    Same Float
    FOR    ${keyword}    ${value}    IN ZIP    ${keywords}    ${TYPED_VALUES}    mode=STRICT
        ${result}=    Run Keyword    ${alias}.${keyword}    ${value}
        Should Be The Same Value    ${result}    ${value}
    END

Declared Class Of The Server Fails
    [Arguments]    ${alias}
    Run Keyword And Expect Error
    ...    ValueError: Return value '{'value': 1}' (dictionary) cannot be converted to ServerOnlyTypes.OnlyOnTheServer: it cannot be imported: No module named 'ServerOnlyTypes'
    ...    ${alias}.Make Declared Only On The Server

Should Be The Same Value
    [Arguments]    ${result}    ${expected}
    Should Be True    type($result) is type($expected) and ($result == $expected or $result != $result)
    ...    ${result} is not the same value as ${expected}

Start A Server
    [Arguments]    ${port}    ${pickles}=${True}
    Start Jsonrpc Server    ArgumentValuesLib    port=${port}    pythonpath=${CURDIR}    pickles=${pickles}

Import The Library
    [Documentation]    ``pickles`` is passed on as ``rpc_pickles``, as the text that a suite writes.
    [Arguments]    ${port}    ${alias}    ${pickles}=yes
    Import Library    JsonRpcRemote    tcp://127.0.0.1:${port}    ArgumentValuesLib    rpc_scope=TEST
    ...    rpc_pickles=${pickles}    AS    ${alias}

Tuple Makes A Round Trip
    [Arguments]    ${alias}
    ${result}=    Run Keyword    ${alias}.Same Value    ${{(1, "a")}}
    Should Be Equal    ${result}    ${{(1, "a")}}
    Should Be True    isinstance($result, tuple)
    ${type}=    Run Keyword    ${alias}.Type Name Of    ${{(1, "a")}}
    Should Be Equal    ${type}    tuple
