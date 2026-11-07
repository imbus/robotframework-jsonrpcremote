// Starts a process with Node's default pipes, as VS Code starts a debug adapter, and sends it one request.
// Usage: node node_default_pipes.js <command> [<argument>...]. Prints the body of the response.
"use strict";
const { spawn } = require("node:child_process");

const [command, ...args] = process.argv.slice(2);
// Without a stdio option, the process gets pipes: synchronous ones on Windows, socket pairs elsewhere.
const child = spawn(command, args);
child.stderr.pipe(process.stderr);

const body = Buffer.from(JSON.stringify({ jsonrpc: "2.0", id: 1, method: "echo", params: { text: "Grüße" } }));
child.stdin.write(Buffer.concat([Buffer.from(`Content-Length: ${body.length}\r\n\r\n`, "ascii"), body]));

let received = Buffer.alloc(0);
let answered = false;
child.stdout.on("data", (chunk) => {
  received = Buffer.concat([received, chunk]);
  const end = received.indexOf("\r\n\r\n");
  if (answered || end < 0) {
    return;
  }
  const length = Number(/Content-Length: *(\d+)/i.exec(received.subarray(0, end).toString("ascii"))[1]);
  if (received.length < end + 4 + length) {
    return;
  }
  answered = true;
  process.stdout.write(received.subarray(end + 4, end + 4 + length));
  // The end of its input ends the process.
  child.stdin.end();
});
child.on("exit", (code) => {
  process.exitCode = answered ? (code ?? 1) : 2;
});
