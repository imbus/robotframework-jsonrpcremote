// An example server for JsonRpcRemote in Node.js, built on the JSON-RPC library vscode-jsonrpc. It serves the
// library NodeLibrary over TCP, over its stdin and stdout, or over a pipe of the client that starts it.
import * as net from "node:net";
import { parseArgs } from "node:util";
import {
  createMessageConnection,
  type MessageReader,
  type MessageWriter,
  ResponseError,
  SocketMessageReader,
  SocketMessageWriter,
  StreamMessageReader,
  StreamMessageWriter,
} from "vscode-jsonrpc/node";
import {
  ExitNotification,
  FinalizeLibraryRequest,
  ImportLibraryRequest,
  InitializedNotification,
  InitializeRequest,
  type LibraryDefinition,
  LogNotification,
  RobotErrorCodes,
  type RunKeywordParams,
  RunKeywordRequest,
  SetLogLevelNotification,
  ShutdownRequest,
} from "./protocol.ts";

const LIBRARY: LibraryDefinition = {
  name: "NodeLibrary",
  doc: "Keywords written in TypeScript and run by Node.js.",
  keywords: [
    {
      name: "Echo",
      args: [{ name: "message", type: "str", doc: "The message to return." }],
      doc: "Logs the message and returns it.",
    },
    {
      name: "Sum Of",
      // With a declared type, Robot Framework converts the argument on the client, such as "[1, 2]" to a list.
      args: [{ name: "numbers", type: "list[int]", doc: "The numbers to add." }],
      return_type: "int",
      doc: "Returns the sum of the numbers.",
    },
    {
      name: "Fail With",
      args: [{ name: "message", type: "str", doc: "The message of the failure." }],
      doc: "Fails with the message.",
    },
  ],
};

/** An argument by its position, or by its name if the call names it. */
function argument(params: RunKeywordParams, position: number, name: string): unknown {
  const args = params.args ?? [];
  return position < args.length ? args[position] : params.kwargs?.[name];
}

/** Serves one client: a session from robot/initialize to robot/exit. `end` closes the connection. */
function serveClient(reader: MessageReader, writer: MessageWriter, end: () => void): void {
  const connection = createMessageConnection(reader, writer);
  // The handshake, for this connection only.
  let initializeReceived = false;
  let initializedReceived = false;
  let imports = 0;

  function checkHandshake(request: string): void {
    if (!initializeReceived || !initializedReceived) {
      throw new ResponseError(
        RobotErrorCodes.NOT_INITIALIZED,
        `Initialize and Initialized must be received before ${request}.`,
      );
    }
  }

  connection.onRequest(InitializeRequest, (params) => {
    console.error(`initializing ${params.client_info?.name ?? "a client"}`);
    initializeReceived = true;
    // No pickle_protocol: this server reads no pickles, so values arrive as plain and typed JSON.
    return {
      capabilities: { support_exit: true, libraries: [LIBRARY.name] },
      server_info: { name: "NodeExampleServer", version: "1.0" },
    };
  });

  connection.onNotification(InitializedNotification, () => {
    initializedReceived = true;
  });

  // This server sends all its log messages: the client logs those from its log level on.
  connection.onNotification(SetLogLevelNotification, () => {});

  connection.onRequest(ImportLibraryRequest, (params) => {
    checkHandshake("ImportLibrary");
    console.error(`importing ${params.name}`);
    // Any name imports the one library, and every import gets a token of its own.
    return { token: `node-library-${imports++}`, definition: LIBRARY };
  });

  connection.onRequest(RunKeywordRequest, async (params) => {
    checkHandshake("RunKeyword");
    console.error(`running ${params.name}`);
    switch (params.name) {
      case "Echo": {
        const message = argument(params, 0, "message");
        // Sent before the result, so the client logs it under this keyword call.
        await connection.sendNotification(LogNotification, { message: `Echoing ${message}`, level: "INFO" });
        return { result: message };
      }
      case "Sum Of": {
        // A list arrives as plain JSON, since the client sends no pickles to a server that reads none.
        const numbers = argument(params, 0, "numbers") as number[];
        return { result: numbers.reduce((sum, number) => sum + number, 0) };
      }
      case "Fail With":
        // A keyword that fails answers with an error in its result, not with a JSON-RPC error.
        return { error: { message: String(argument(params, 0, "message")), type: "Error" } };
      default:
        throw new ResponseError(
          RobotErrorCodes.KEYWORD_NOT_FOUND,
          `Keyword '${params.name}' not found in library '${LIBRARY.name}'.`,
        );
    }
  });

  connection.onRequest(FinalizeLibraryRequest, (params) => {
    console.error(`finalizing ${params.token}`);
    return {};
  });

  connection.onRequest(ShutdownRequest, () => ({}));

  // After robot/exit, the server closes the connection.
  connection.onNotification(ExitNotification, () => end());

  connection.onClose(() => {
    console.error("client disconnected");
    connection.dispose();
    end();
  });

  connection.listen();
}

/** Serves every client that connects to the port, each on its own connection. */
function listenOnPort(port: number): void {
  const server = net.createServer((socket) => {
    console.error(`client connected from ${socket.remoteAddress}:${socket.remotePort}`);
    serveClient(new SocketMessageReader(socket), new SocketMessageWriter(socket), () => socket.end());
  });
  server.on("error", (error) => {
    console.error(`cannot listen on 127.0.0.1:${port}: ${error.message}`);
    process.exitCode = 1;
  });
  server.listen(port, "127.0.0.1", () => {
    // With port 0, the system chooses the port, and this line gives it.
    const address = server.address() as net.AddressInfo;
    console.error(`listening on 127.0.0.1:${address.port}`);
  });
}

/** Serves the client that started this server with a stdio: URI, over stdin and stdout. */
function serveStdio(): void {
  // Over stdio, stdout carries the messages: everything else goes to stderr, as with console.error().
  console.error("serving a client over stdin and stdout");
  // The process ends once stdin is closed and nothing is left to write.
  serveClient(new StreamMessageReader(process.stdin), new StreamMessageWriter(process.stdout), () =>
    process.stdin.destroy(),
  );
}

/** Serves the client that started this server with a pipe: URI, over the pipe that the client listens on. */
function servePipe(address: string): void {
  // A named pipe on Windows, a Unix domain socket elsewhere: net.connect() takes both.
  const socket = net.connect(address);
  socket.on("error", (error) => {
    console.error(`pipe ${address}: ${error.message}`);
    process.exitCode = 1;
  });
  socket.on("connect", () => console.error(`connected to the pipe ${address}`));
  // The process ends with the connection.
  serveClient(new SocketMessageReader(socket), new SocketMessageWriter(socket), () => socket.end());
}

const USAGE = "usage: node src/server.ts [--port PORT | --stdio | --pipe ADDRESS]";

function usageError(message: string): never {
  console.error(`${message}\n${USAGE}`);
  process.exit(2);
}

function parseOptions() {
  try {
    // --pipe ADDRESS can also be written --pipe=ADDRESS, as the client passes it for a pipe: URI.
    return parseArgs({
      options: {
        port: { type: "string", default: "8271" },
        stdio: { type: "boolean", default: false },
        pipe: { type: "string" },
      },
    }).values;
  } catch (error) {
    // Such as an unknown option.
    return usageError((error as Error).message);
  }
}

const options = parseOptions();
if (options.pipe !== undefined) {
  if (options.stdio) {
    usageError("--stdio and --pipe exclude each other");
  }
  servePipe(options.pipe);
} else if (options.stdio) {
  serveStdio();
} else {
  if (!/^\d+$/.test(options.port) || Number(options.port) > 65535) {
    usageError(`invalid port: ${options.port}`);
  }
  listenOnPort(Number(options.port));
}
