*** Settings ***
Documentation     Run by log_levels.robot in a nested Robot process, not on its own: Robot skips directories
...               starting with an underscore. Needs the variable PORT.
Library           JsonRpcRemote    tcp://127.0.0.1:${PORT}    ServerProbeLib


*** Test Cases ***
Uses The Remote Library
    Log At Each Level    marker
