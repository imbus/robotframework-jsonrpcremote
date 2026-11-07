*** Settings ***
Documentation     The hand-written example server over stdio. It prints on every message, and
...               open_stdio_connection() sends that to its stderr, out of the way of the messages.
Variables         stdio_vars.py
Library           LogCapture.py
Library           JsonRpcRemote    stdio:${OWN_SERVER_COMMAND}    SimpleRobotLibrary
Test Tags         posix


*** Test Cases ***
Echo Returns The Message
    ${result}=    Echo    Grüße
    Should Be Equal    ${result}    Grüße

Message Longer Than The Buffer Of Its Print Calls
    [Documentation]    20,000 characters make the example's print() calls overflow the 8 KiB buffer of
    ...                sys.stdout. On the connection, that text would cost the client the message after it,
    ...                which is the first log message of the keyword.
    ${message}=    Evaluate    'x' * 20000
    ${result}=    Echo    ${message}
    Should Be True    $result == $message
    ${messages}=    Get Captured Log Messages
    Should Contain    ${messages}    RUN_KEYWORD_REQUEST processing...

Repeated Calls
    FOR    ${i}    IN RANGE    10
        ${result}=    Echo    message ${i}
        Should Be Equal    ${result}    message ${i}
    END
