## v0.2.0 (2026-06-01)

### Feat

- implement finalize/shutdown/exit handshake and graceful server stop
- forward keyword arguments on library import as Robot name=value args
- expose Robot --variable/--variablefile/--outputdir and add a server probe test library
- infer precise from_dict/from_json return types via PEP 747 TypeForm
- update TCP server configuration to support multiple bind addresses
- add LICENSE files and update pyproject.toml for all packages with keywords, classifiers, and project URLs
- implement running keywords and log messages
- implement getting library information over JSONRPC
- add functions for serializing and deserializing objects using pickle
- add marker files for PEP 561
- enhance JsonRpcRemote initialization and add versioning support
- **endpoint**: implement JsonRpcEndpoint for better handling requests and notifications
- **protocol**: initial draft of protocol definition and documentation
- initial version

### Fix

- return Invalid Params (-32602) when handler params cannot be converted
- apply the server's --pythonpath so libraries load from custom dirs
- tolerate malformed error payloads in JsonRpcPeer responses
- harden JSON-RPC message handling and tidy review nits
- reject unsupported server modes with a clean error
- preserve library init argument types instead of stringifying them
- make the client session finalizer fire on garbage collection
- track and cancel in-flight message tasks in JsonRpcPeer
- isolate server log notifications per client and unblock the runner thread
- preserve order and duplicates of library init arguments
- generate unique library tokens per endpoint
- update import statement for TypeAlias from typing_extensions to typing
- update project descriptions in pyproject.toml files for clarity
- update default server port in documentation and code to 8271
- ensure error responses include the correct response ID
- improve error handling in JsonRpcPeer and add connection closure in JsonRpcRemote

### Refactor

- import TypeForm directly instead of via TYPE_CHECKING
- let from_dict accept typing special forms via overloads
- separate initialization and library import
- **jsonrpcpeer**: rewrite io_loop and improve error handling
- rename jsonrpcpeer project and add some examples
- remove some unwanted code in the examples
