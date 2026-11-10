// The messages of the protocol that this server receives and sends, with the field names of the wire.
// The protocol page of the documentation describes them all, in the section "Data structures":
// https://imbus.github.io/robotframework-jsonrpcremote/reference/protocol/#data-structures
import { NotificationType, RequestType } from "vscode-jsonrpc/node";

/** The params or the result of a message without fields. */
export type Empty = Record<string, never>;

export interface Info {
  name: string;
  version: string;
}

export interface InitializeParams {
  capabilities?: { pickle_protocol?: number };
  client_info?: Info;
  log_level?: string;
}

export interface InitializeResult {
  capabilities?: {
    support_exit?: boolean;
    libraries?: string[];
    // A server that reads no pickles states no pickle_protocol, and gets values as plain and typed JSON.
    pickle_protocol?: number;
  };
  server_info?: Info;
}

export interface SetLogLevelParams {
  log_level: string;
}

export interface ImportLibraryParams {
  name: string;
  args?: unknown[];
  kw_args?: Record<string, unknown>;
}

export interface ArgumentDefinition {
  name: string;
  /** The type hint as Robot Framework writes it, such as "int" or "list[int]". */
  type?: string;
  has_default?: boolean;
  default?: unknown;
  doc?: string;
}

export interface KeywordDefinition {
  name: string;
  args: ArgumentDefinition[];
  return_type?: string;
  doc?: string;
  tags?: string[];
}

export interface LibraryDefinition {
  name: string;
  keywords: KeywordDefinition[];
  doc?: string;
  version?: string;
}

export interface ImportLibraryResult {
  token: string;
  definition: LibraryDefinition;
}

export interface RunKeywordParams {
  library_token: string;
  name: string;
  args?: unknown[];
  kwargs?: Record<string, unknown>;
}

export interface RunKeywordError {
  /** The client fails the keyword with exactly this message. */
  message: string;
  type?: string;
  traceback?: string;
  mode?: "SKIP" | "CONTINUABLE" | "FATAL";
}

export interface RunKeywordResult {
  result?: unknown;
  error?: RunKeywordError;
}

export interface LogParams {
  message: string;
  level?: "TRACE" | "DEBUG" | "INFO" | "WARN" | "ERROR" | "CONSOLE" | "HTML";
  html?: boolean;
  console?: boolean;
}

export interface FinalizeLibraryParams {
  token: string;
}

// The messages by their names, with the types of their params and results. The client sends all but robot/log.
export const InitializeRequest = new RequestType<InitializeParams, InitializeResult, void>("robot/initialize");
export const InitializedNotification = new NotificationType<Empty>("robot/initialized");
export const SetLogLevelNotification = new NotificationType<SetLogLevelParams>("robot/set_log_level");
export const ImportLibraryRequest = new RequestType<ImportLibraryParams, ImportLibraryResult, void>(
  "robot/import_library",
);
export const RunKeywordRequest = new RequestType<RunKeywordParams, RunKeywordResult, void>("robot/run_keyword");
export const LogNotification = new NotificationType<LogParams>("robot/log");
export const FinalizeLibraryRequest = new RequestType<FinalizeLibraryParams, Empty, void>("robot/finalize_library");
export const ShutdownRequest = new RequestType<Empty, Empty, void>("robot/shutdown");
export const ExitNotification = new NotificationType<Empty>("robot/exit");

/** The error codes of the protocol, next to those of JSON-RPC. */
export const RobotErrorCodes = {
  NOT_INITIALIZED: -32000,
  KEYWORD_NOT_FOUND: -32001,
} as const;
