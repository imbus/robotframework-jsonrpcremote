# node-robot-jsonrpcserver

An example server for JsonRpcRemote in Node.js. It is written in TypeScript, which Node.js runs directly, and uses the JSON-RPC library [`vscode-jsonrpc`](https://www.npmjs.com/package/vscode-jsonrpc), whose framing is that of the Language Server Protocol, as in the protocol of JsonRpcRemote. It shows how to write a server in another language than Python: the messages as types in [`src/protocol.ts`](src/protocol.ts), and a handler for each in [`src/server.ts`](src/server.ts).

It serves the library `NodeLibrary` with three keywords:

*   **`Echo`** returns its `message`. Before that, it sends the log message `Echoing <message>`, which the client logs under the keyword call.
*   **`Sum Of`** returns the sum of its argument `numbers`, which it declares as `list[int]`. The list arrives as plain JSON.
*   **`Fail With`** fails with its `message`.

The server reads no pickles and states no `pickle_protocol`, so the client sends it values as plain and typed JSON. It refuses a library import and a keyword call before the handshake with the code `-32000`, and an unknown keyword with `-32001`.

## Install it

It needs Node.js 24 or later, which runs TypeScript without a build step. In this folder:

```bash
npm ci
```

## Run it

```bash
npm start
```

The server listens on `tcp://127.0.0.1:8271` and serves every client that connects. With `--port`, it listens on another port, and with `--port 0` on one that the system chooses; the line `listening on 127.0.0.1:<port>` on stderr gives it:

```bash
node src/server.ts --port 9000
```

With `--stdio`, it serves one client over its stdin and stdout, and with `--pipe ADDRESS`, also written `--pipe=ADDRESS`, it connects to the pipe at that address and serves the client that listens there. In both cases, the client starts the server itself, and the server ends with the connection. The server writes what it reports to stderr, in every transport.

## Use it from Robot Framework

```robot
*** Settings ***
Library    JsonRpcRemote    uri=tcp://127.0.0.1:8271    library_name=NodeLibrary

*** Test Cases ***
Keywords In Node.js
    ${result}=    Echo    Hello World
    Should Be Equal    ${result}    Hello World
    ${sum}=    Sum Of    ${{[1, 2, 39]}}
    Should Be Equal    ${sum}    ${42}
    Run Keyword And Expect Error    Boom    Fail With    Boom
```

Over a pipe, the client starts the server for the session and appends `--pipe=ADDRESS` to the command. The command can be a list, whose first element is the scheme:

```robot
*** Settings ***
Library    JsonRpcRemote    uri=${SERVER}    library_name=NodeLibrary

*** Variables ***
@{SERVER}    pipe:    node    path/to/node-robot-jsonrpcserver/src/server.ts
```

Over stdio, too, with `--stdio`:

```robot
*** Variables ***
@{SERVER}    stdio:    node    path/to/node-robot-jsonrpcserver/src/server.ts    --stdio
```

## Check the types

```bash
npm run check
```

It runs `tsc`, which checks the types and writes no files. Its options in [`tsconfig.json`](tsconfig.json) allow only TypeScript that Node.js can run directly, such as no `enum`.

The [protocol page](https://imbus.github.io/robotframework-jsonrpcremote/reference/protocol/) of the documentation describes the messages that the server handles and runs it with a suite.
