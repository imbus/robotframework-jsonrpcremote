// Keywords written in Node, which the client starts over stdin and stdout: keywords in any language are
// what the protocol is for. It reads stdin and writes stdout with one reader and one writer.
"use strict";

const KEYWORDS = {
  Echo: { args: ["message"], run: async ([message]) => message },
  "Add Numbers": { args: ["first", "second"], run: async ([first, second]) => Number(first) + Number(second) },
  "Fail With": {
    args: ["message"],
    run: async ([message]) => {
      throw new Error(message);
    },
  },
  "Write To The Log": {
    args: ["message"],
    run: async ([message]) => {
      send({ method: "robot/log", params: { message, level: "INFO" } });
      return null;
    },
  },
  "Wait And Return": {
    args: ["milliseconds", "value"],
    run: async ([milliseconds, value]) => {
      await new Promise((resolve) => setTimeout(resolve, Number(milliseconds)));
      return value;
    },
  },
};

const LIBRARY = {
  name: "NodeKeywords",
  keywords: Object.entries(KEYWORDS).map(([name, keyword]) => ({
    name,
    args: keyword.args.map((arg) => ({ name: arg })),
  })),
};

function send(message) {
  const body = Buffer.from(JSON.stringify({ jsonrpc: "2.0", ...message }), "utf8");
  process.stdout.write(Buffer.concat([Buffer.from(`Content-Length: ${body.length}\r\n\r\n`, "ascii"), body]));
}

function failure(code, message) {
  return Object.assign(new Error(message), { code });
}

async function runKeyword({ name, args }) {
  const keyword = KEYWORDS[name];
  if (keyword === undefined) {
    throw failure(-32001, `Keyword '${name}' not found.`);
  }
  try {
    return { result: await keyword.run(args ?? []) };
  } catch (error) {
    return { error: { message: error.message, type: error.name } };
  }
}

async function respond(method, params) {
  switch (method) {
    case "robot/initialize":
      return { capabilities: { support_exit: true }, server_info: { name: "node-keywords", version: "1.0.0" } };
    case "robot/import_library":
      return { token: "node-keywords", definition: LIBRARY };
    case "robot/run_keyword":
      return runKeyword(params);
    case "robot/finalize_library":
    case "robot/shutdown":
      return {};
    default:
      throw failure(-32601, `Method '${method}' not found.`);
  }
}

async function handle({ id, method, params }) {
  if (method === "robot/exit") {
    // Nothing is left to read, so the process ends once stdout has been written.
    process.stdin.destroy();
    return;
  }
  if (id === undefined) {
    return;
  }
  try {
    send({ id, result: await respond(method, params ?? {}) });
  } catch (error) {
    send({ id, error: { code: error.code ?? -32603, message: error.message } });
  }
}

let received = Buffer.alloc(0);
process.stdin.on("data", (chunk) => {
  received = Buffer.concat([received, chunk]);
  for (;;) {
    const end = received.indexOf("\r\n\r\n");
    if (end < 0) {
      return;
    }
    const length = /Content-Length: *(\d+)/i.exec(received.subarray(0, end).toString("ascii"));
    if (length === null) {
      received = received.subarray(end + 4);
      continue;
    }
    const start = end + 4;
    if (received.length < start + Number(length[1])) {
      return;
    }
    const body = received.subarray(start, start + Number(length[1])).toString("utf8");
    received = received.subarray(start + Number(length[1]));
    handle(JSON.parse(body));
  }
});
