@echo off
rem Starts the Node server of atests/node_keywords.js, as a wrapper script would start a server.
node "%~dp0node_keywords.js" %*
