*** Settings ***
Documentation     A log message that the server sends while no keyword call is running reaches Robot
...               Framework like one of a local library: a warning from the end of a session appears among
...               the execution errors. The suite that uses the remote library runs in a nested Robot
...               process, so that this suite can read its execution errors. Uses its own server on
...               port 8278, so the shared server used by the other suites is unaffected.
Library           IsolatedServerControl.py
Library           NestedRobot.py
Suite Setup       Start Jsonrpc Server    CloseLogLib    port=${PORT}    pythonpath=${CURDIR}
Suite Teardown    Stop Jsonrpc Server


*** Variables ***
${PORT}           8278


*** Test Cases ***
Warning From The End Of A Session Appears Among The Execution Errors
    ${output}=    Run Nested Suite    ${CURDIR}${/}_nested${/}close_log.robot    ${OUTPUT_DIR}${/}nested-close-log
    ...    PORT:${PORT}
    ${errors}=    Get Execution Errors    ${output}
    Should Contain    ${errors}    CloseLogLib was finalized
