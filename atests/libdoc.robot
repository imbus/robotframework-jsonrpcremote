*** Settings ***
Documentation     Libdoc describes the keywords of a remote library like those of a local one. It runs in a
...               process of its own, and its name and version on the library level are those of JsonRpcRemote.
Library           LibdocSpecs.py
Suite Setup       Read The Spec Of The Local Library


*** Variables ***
${PORT}           8271
${LIBRARY FILE}    ${CURDIR}${/}LibdocLib.py
${REMOTE}         JsonRpcRemote::tcp://127.0.0.1:${PORT}::LibdocLib


*** Test Cases ***
Libdoc Describes Remote Keywords Like Local Ones
    ${remote}=    Keywords In Json Spec    ${REMOTE}    ${OUTPUT_DIR}${/}libdoc-remote.json
    Should Be Equal    ${remote}    ${LOCAL SPEC}

The JSON Spec File Holds The Source And The Line Of A Remote Keyword
    ${remote}=    Keywords In Json Spec    ${REMOTE}    ${OUTPUT_DIR}${/}libdoc-remote.json
    Should Be Equal    ${remote}[Documented][source]    ${LIBRARY FILE}
    Should Be Equal As Integers    ${remote}[Documented][lineno]    ${LOCAL SPEC}[Documented][lineno]

The XML Spec File Holds The Source And The Line Of A Remote Keyword
    ${remote}=    Keywords In Xml Spec    ${REMOTE}    ${OUTPUT_DIR}${/}libdoc-remote.xml
    Should Be Equal    ${remote}[Documented][source]    ${LIBRARY FILE}
    Should Be Equal As Integers    ${remote}[Documented][lineno]    ${LOCAL SPEC}[Documented][lineno]


*** Keywords ***
Read The Spec Of The Local Library
    ${spec}=    Keywords In Json Spec    ${LIBRARY FILE}    ${OUTPUT_DIR}${/}libdoc-local.json
    Should Not Be Empty    ${spec}
    FOR    ${name}    ${keyword}    IN    &{spec}
        Should Be True    ${keyword}[lineno]    ${name} has no line in the spec of the local library.
    END
    VAR    ${LOCAL SPEC}=    ${spec}    scope=SUITE
