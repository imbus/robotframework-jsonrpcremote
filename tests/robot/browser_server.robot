*** Settings ***
#Library    Browser
Library   JsonRpcRemote  tcp://192.168.2.95  library_name=Browser

Test Setup    New Browser   headless=False
Test Teardown    Close Browser

*** Test Cases ***
Has Title
    New Page    https://playwright.dev/
    Get Title    contains    Playwright

Get Started Link
    New Page    https://playwright.dev/
    ${element}=    Get Element By Role    LINK    name=Get started
    Click    ${element}
    ${heading}=    Get Element By Role    HEADING    name=Installation
    Get Element States    ${heading}    contains    visible

Get Started Link [Alternative]
    New Page    https://playwright.dev/
    Click    a >> "Get started"
    Get Element States    h1 >> "Installation"    contains    visible

Playwright Test
    New Page    https://playwright.dev/
    Get Title    matches   Playwright
    Get Attribute    "Get started"    href    ==    /docs/intro
    Click    "Get started"
    Get Url    matches    .*intro