*** Settings ***
Library     Remote
...             http://localhost:8270


*** Test Cases ***
first
    FOR    ${i}    IN RANGE    10
        ${result}    Echo    Hello World
        Should Be Equal    ${result}    echo: Hello World
    END
