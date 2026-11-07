# Design

## Context

See proposal.md for the motivation. This builds on `add-stdio-streams` (`e2ed56b`): `open_stdio_connection()`, the move of the standard streams and `_WritePipeProtocol` exist, and only the Windows path is missing. What is known about Windows comes from tests on a Windows 11 VM (Insider build):

- **Pipes:** each end of a pipe is synchronous or overlapped, fixed by whoever creates it. asyncio and `subprocess` give the child a synchronous end. The proactor needs an overlapped one, and `asyncio.windows_utils.PipeHandle` on a synchronous pipe fails with WinError 87.
- **VS Code gives synchronous pipes:** it starts a debug adapter with `cp.spawn()` and only `env` and `cwd` (`src/vs/workbench/contrib/debug/node/debugAdapter.ts`, lines 300 to 313), and Node 26 with these options gave the child synchronous pipes on the VM. VS Code runs this in Electron, which has the same libuv; during this change, VS Code 1.145 on the VM gave a debug adapter synchronous pipes on stdin and stdout as well (see decision 9). RobotCode's debugger runs over stdio by default.
- **No way from a synchronous pipe to I/O completion ports:** `ReOpenFile()` with `FILE_FLAG_OVERLAPPED` failed with `ERROR_PIPE_BUSY` (231) on the pipes of `subprocess.PIPE` and of Node, because it opens the pipe again as a new client, for which no instance is free (VM, 2026-11-07).
- **Duplex:** the proactor's write transport also reads from its handle to notice that the other end closed, so a pipe that only allows writing fails with WinError 5.
- **End of input:** the proactor's read transport stays open after EOF until someone closes it, which `_WritePipeProtocol` does.
- **A second user of an overlapped pipe is dangerous:** a plain `WriteFile()` or `ReadFile()` on an overlapped handle can return early when another operation on the same pipe completes, reporting success with 0 bytes while the kernel still uses the buffer. Measured with two threads on one pipe: thread A writes 20 KiB and thread B 4 MiB, and when the reader finishes A, B returns at once with 0 bytes written, 2 s before its data is taken. Microsoft's documentation of `ReadFile` warns about this.
  - The C runtime locks per file descriptor, so threads that share one descriptor or `sys.stdout` are safe.
  - Two descriptors or two processes are not: two threads with their own `os.dup(1)` failed 7 of 7 runs, and a process and a child that both write to the inherited stdout failed 7 of 7, with wrong data and crashes such as 0xC0000005. Two readers gave a false EOF and a lost message. Normal pipes passed all the write cases.
  - These failures need writes that really pend: lines of 64 KiB and a reader that pauses for 1 s. Short or big writes with a fast reader passed.
  - That memory reuse causes the crashes is an inference. The early return is measured.
  - With the moved streams, none of this can happen in a Python process that uses `open_stdio_connection()`, because only the event loop uses the pipes. So on Windows the move is mandatory rather than useful.

**Results of the prototype,** a copy of the repository with both changes, on the same VM, in one run per version. It had only the path for overlapped pipes; the threads of decision 6 are new:

- **Scenarios of `add-stdio-streams` for `jsonrpc-peer`, and the refusals of this change:** passed on Python 3.12, 3.13, 3.14, 3.15, 3.14t and 3.15t. The scenario The input ends first used a parent with a plain write protocol, because of the close behavior that decision 2 describes. Not tried: No thread for the streams, the window flags and Command that cannot be started.
- **`robotcode run`, as in CI, with all dev dependencies:** 85 of 85 tests on 3.12 and on 3.14t, with the GIL off on 3.14t.
- **Unit tests:** 308 passed on 3.14t. A test still expected an older wording of the error, and the in-process tests that the new tests replace were left out. On 3.12, the same result once bytecode copied from Linux was removed.
- **A server in Node, under Robot Framework:** a suite of 9 tests passed, called with forward slashes, with backslashes and through a `.cmd` file.
- **Earlier version of the prototype:**
  - A soak of 120 minutes on 3.12 with 97 sessions and about 6 million calls had 0 errors and no leftovers.
  - With the streams moved, 23 ways to use stdin, stdout and child processes behaved as over TCP, among them `input()`, `os.write(1)`, native `WriteFile()`, `os.system()`, `multiprocessing` and a child's big output during a 2 MiB result.

## Goals / Non-Goals

**Goals:**

- A Python process over stdio works on Windows through I/O completion ports, without threads, where the pipes are overlapped, as our client creates them.
- It also works with the synchronous pipes of any other parent, such as VS Code's for a debug adapter, through a thread per direction.
- The client has one code path for starting a server, and POSIX behaves as before.
- Servers in other languages keep working.

**Non-Goals:**

- A thread for an overlapped pipe on an event loop that is not a proactor. Decision 4 says why.
- The hang from the proactor's self pipe, which is not specific to stdio (see Risks).
- Named pipes and Unix domain sockets, which will be the recommended way to connect a local server (NET-1, NET-3). `ProactorEventLoop` has `create_pipe_connection()` and `start_serving_pipe()` for them.

## Decisions

### 1. The client gives every server overlapped duplex pipes

The client cannot tell what a command starts, so it has one kind of pipe for all servers: `windows_utils.pipe(overlapped=(True, True), duplex=True)`, once for stdin and once for stdout.

**Alternatives:**

- **Normal pipes, and threads in the Python server:** Daniel rejected this for the pipes that our client creates. A 256-byte round trip takes 644 µs instead of 273 µs. A thread blocked on a synchronous stdin also freezes a Python child that inherits stdin until the next message arrives (CPython gh-78961): 5.3 s against 0.11 s when measured.
- **Overlapped pipes only for Python servers, through an option in the URI:** this hands the user a detail that they should not need to know, and every other server keeps working without it anyway.

**The cost** is that foreign servers get an unusual handle:

| Program on overlapped pipes | Result |
| --------------------------- | ------ |
| Node | a suite of 9 tests under Robot Framework: same result and about the same time as on normal pipes (1.77 s against 1.59 s for 1000 calls) |
| Go, .NET, Rust, Java, Python, `findstr` | echo tests: same result as on normal pipes |
| msys2 `cat` | works, but is slow: 32 s against 0.5 s for 50 MB |
| docker | not tested |

Libuv under Node checks the handle and uses I/O completion ports for an overlapped one, and threads for a synchronous one. So Node works on both.

### 2. `create_stdio_subprocess()` in `jsonrpcpeer`

```python
process, reader, writer = await create_stdio_subprocess(*argv)
```

- **In the package:** both ends of the pipes belong together, a hand-written Python parent needs the same, and the client should not import a private module of another package.
- **POSIX keeps its path:** it calls `asyncio.create_subprocess_exec(*argv, stdin=PIPE, stdout=PIPE, **kwargs)` and returns `process.stdout` and `process.stdin`, so POSIX behaves as before.
- **Windows:** it creates the pipes, wraps the child's ends with `msvcrt.open_osfhandle()`, passes these to `asyncio.create_subprocess_exec()`, closes them in the parent and builds the pair with `connect()` from `_win32_pipes.py`, which takes the path through I/O completion ports for these pipes. If the start fails, it closes the parent's ends as well.
- **No difference between the platforms:** closing the writer ends the input of the process, and the reader goes on until the process has closed its stdout, on Windows as on POSIX. On Windows, `connect()` builds this pair with `half_close`: its writer leaves the reader alone, and the reader closes its transport itself at the end of the input, because nothing else would.
  - **Why, found in a review (2026-11-07):** the plan coupled the reader to the writer on Windows, as in the pair of `open_stdio_connection()`. But when the process ends, the proactor's write transport notices the closed pipe through its probe read and closes, and with it the reader. If the reader was paused at that moment, with more than 128 KiB unread, the end of the output still in the pipe was lost: up to 8 KB in 9 of 10 runs on the VM, with many small writes before the end. Daniel chose the behavior of POSIX over keeping the coupling for an explicit close only.
  - **What this costs:** as on POSIX, a message that the server still sends after the client has fed the end of the input to its reader, at the end of a session, makes asyncio report `feed_data after feed_eof` in a callback.
  - **The reader closes when it has read the end:** on POSIX, `process.wait()` waits for asyncio's pipes, on Windows not for these, so a caller that ends its event loop right after `process.wait()` without reading to the end can leave the reader to the garbage collector. The tests read to the end; one run on 3.15 had reported such a transport before they did.

### 3. `open_stdio_connection()` on Windows

```python
async def open_stdio_connection() -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    _check_stdin()
    _check_stdout()
    _occupy_closed_stderr()
    if sys.platform == "win32":
        from . import _win32_pipes

        _win32_pipes.check_loop()
        read_handle = _win32_pipes.private_handle(0)
        write_handle = _win32_pipes.private_handle(1)
        _move_standard_streams()
        connecting = _win32_pipes.connect(read_handle, write_handle)
    else:
        read_file = os.fdopen(os.dup(0), "rb", 0)
        write_file = os.fdopen(os.dup(1), "wb", 0)
        _move_standard_streams()
        connecting = _connect(read_file, write_file)
    return await connecting
```

```python
async def connect(read_handle: int, write_handle: int) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    """The pair for two private handles: I/O completion ports for an overlapped one, a thread for a synchronous one."""
    loop = asyncio.get_running_loop()
    reader = asyncio.StreamReader(loop=loop)
    read_protocol = asyncio.StreamReaderProtocol(reader, loop=loop)
    if is_overlapped(read_handle):
        read_transport, _ = await loop.connect_read_pipe(lambda: read_protocol, PipeHandle(read_handle))
    else:
        read_transport = _ThreadReadTransport(loop, read_handle, read_protocol)
    write_protocol = _WritePipeProtocol(read_transport)
    if is_overlapped(write_handle):
        write_transport, _ = await loop.connect_write_pipe(lambda: write_protocol, PipeHandle(write_handle))
    else:
        write_transport = _ThreadWriteTransport(loop, write_handle, write_protocol)
    return reader, asyncio.StreamWriter(write_transport, write_protocol, reader, loop)
```

- **`private_handle()`:** it duplicates the handle behind the descriptor with `_winapi.DuplicateHandle(..., False, DUPLICATE_SAME_ACCESS)`, not inheritable, because the proactor needs a handle and not a descriptor of the C runtime. The duplicate refers to the same file object, so it is overlapped or synchronous as the original is.
- **One `return` after the branches:** decision 10 needs the `if`/`else`, and ruff's rule RET505 forbids an `else` after a `return`.
- **`_win32_pipes.py`:** this new private module has all the code that exists only on Windows, the thread transports of decision 6 included, and is imported only there.

### 4. The choice per direction, and the two refusals

- **The choice:** `is_overlapped()` asks `NtQueryInformationFile()` with `FileModeInformation`: a handle with `FILE_SYNCHRONOUS_IO_ALERT` or `FILE_SYNCHRONOUS_IO_NONALERT` is synchronous. Libuv makes the same check. Each direction is chosen on its own.
- **A stream closed at the start:** the checks of `add-stdio-streams` already refuse a stdin or stdout whose `sys.__stdin__` or `sys.__stdout__` is `None`. A Python without standard handles, such as `pythonw.exe` started from a shortcut, gets the refusal for a closed stdin that way, also on Windows.
- **A stdin that is no pipe:** on Windows, `os.isatty()` is true for the null device as well as for a console, so `_check_stdin()` accepts only `S_ISFIFO` there, which `os.fstat()` reports for pipes. The null device and a console get the message for a character device, which names `os.devnull`, so `nul` on Windows. The probe with a selector is skipped there, because no selector watches a pipe on Windows. stdout gets no rule beyond being open, because the thread can write a synchronous stdout of any kind.
- **An overlapped pipe without a proactor:** `check_loop()` raises if one of the handles is overlapped and the running loop is not an `asyncio.ProactorEventLoop`. The alternative is a thread for it as well. But a blocking `ReadFile()` without an `OVERLAPPED` structure on an overlapped handle is what Microsoft warns against. One with it would add code for a case that needs a library to set the selector policy, and the client and a plain `asyncio.run()` use the proactor anyway.
- **Before the move:** both refusals come before the move, so stdin and stdout stay as they are. `check_loop()` asks the handles behind descriptors 0 and 1 before the private duplicates exist, so a refusal leaves no handle to close. Left to the proactor, a synchronous handle would fail later, in a callback, with WinError 87 as a fatal transport error, and nobody would report it as a failed start.
- **Messages:** `stdio mode needs a stdin that can be watched for input, such as a pipe, but stdin is a character device such as nul`, and `stdio on Windows needs the proactor event loop for overlapped pipes`. They do not suggest `--tcp`, because the function is also used without the server.

### 5. The move also reaches the standard handles

Native code and child processes use the handles from `GetStdHandle()`, not the descriptors of the C runtime. In a console program such as `python.exe`, the C runtime sets these handles itself when `os.dup2()` changes descriptor 0, 1 or 2: on the VM, `GetStdHandle()` returned the handles of the moved descriptors afterwards (2026-11-07). So the move needs no code of its own for them.

A GUI program such as `pythonw.exe` would need `SetStdHandle()`, because its C runtime leaves the handles as they were, and they then name the closed originals, whose values can be reused. But a GUI program has no stdio to connect, so it is no case here (Daniel, 2026-11-07). The plan had a `set_standard_handles()` for it, which went away again.

### 6. A thread for each synchronous direction

- **Why a thread:** a synchronous pipe cannot reach I/O completion ports (see Context), and blocking on it in the event loop would stop every other task. Libuv under Node, and RobotCode today, use a thread for such pipes as well. Overlapped pipes stay without threads, so this costs only where a parent such as VS Code fixes synchronous pipes. There, 644 µs instead of 273 µs per round trip, measured with threads in the spike, do not matter for a debug adapter.
- **`_ThreadReadTransport(asyncio.ReadTransport)`:** a daemon thread reads 64 KiB at a time with `_winapi.ReadFile()` from the private handle, and takes a `BrokenPipeError` as the end of the input, as the C runtime does. It hands each block to the protocol with `loop.call_soon_threadsafe()`, and the end of the input as `eof_received()`. `pause_reading()` and `resume_reading()`, which the `StreamReader` calls for its flow control, stop and start the thread through an `Event`.
- **`_ThreadWriteTransport(asyncio.WriteTransport)`:** `write()` puts the data in a queue, and a daemon thread writes it with `_winapi.WriteFile()` until every byte is written, reporting progress with `call_soon_threadsafe()`.
- **The Windows API, not the C runtime:** the plan had `os.read()` and `os.write()` on a descriptor from `msvcrt.open_osfhandle()`. But through the C runtime, a write to a pipe whose other end has closed it fails with `EINVAL` instead of `BrokenPipeError`, measured on the VM, so `drain()` would not raise a `ConnectionError`. The C runtime also locks a descriptor during a read, so closing it would wait for the read.
  - **Flow control:** above 64 KiB in the queue it calls `pause_writing()` on the protocol, and below 16 KiB `resume_writing()`, the marks of asyncio's own transports, so that `drain()` works.
  - **Closing:** `close()` lets the thread write the rest, close the handle and report `connection_lost()`. `abort()` drops the rest, and a failed write reports `connection_lost()` with its error.
- **`_WritePipeProtocol` from `add-stdio-streams` sits on top unchanged,** so `wait_closed()` and the end of the reader with the writer work as with the other transports.
- **Closing the reader:** `close()` reports the end of the stream at once. A blocking `ReadFile()` does not return by itself, so `close()` calls `CancelSynchronousIo()` on the thread's handle. It repeats that with `loop.call_later()` until the thread has ended, because the thread can be between two reads when the first call comes. The daemon flag is the backstop, so the thread never holds up the end of the process.
- **The freeze of gh-78961:** in the spike, a thread blocked on a read of a synchronous stdin froze a child process at its start until the next message. Here the thread reads only the private duplicate, which no child inherits, and stdin is the null device. So I expect no freeze; the scenario A child process does not wait for the next message checks it.
- **Free-threading:** each thread touches only its own descriptor and hands everything else to the loop, so the job with 3.14t covers it like any other code.

### 7. The splitting of the command, and the proactor

- **`_split_command()` in the client:** `shlex.split()` treats a backslash as an escape, so `C:\path\python.exe` loses its backslashes, which is what fails on Windows today. It uses `shlex.shlex(command, posix=True)` with `whitespace_split = True` and `commenters = ""`, as `shlex.split()` does, and sets `escape = ""` on Windows. Quotes group as before, and POSIX is unchanged.
- **The session's loop:** `_Session._run()` passes `loop_factory=asyncio.ProactorEventLoop` to `asyncio.run()` on Windows, because a selector policy that a library has set would otherwise break the start of the server. This is the default on Windows anyway, so it holds for TCP sessions too, and needs no case for the transport.

### 8. A window only if there is a console to lose

Without a console of its own, a console program gets a new window, which would pop up for each session. `CREATE_NO_WINDOW` prevents that. But it would cost a client that has a console the log of the server and its Ctrl+C. So `create_stdio_subprocess()` sets the flag only if the caller has no console, and leaves `creationflags` alone if the caller passes them. It asks `GetConsoleCP()`, which returns 0 without a console. `GetConsoleWindow()`, as planned, also returns 0 for a console without a window, which a process started with `CREATE_NO_WINDOW` has and a child can share without a window appearing (VM, 2026-11-07, found in a review).

### 9. Tests

- **`tests/test_stdio_connection.py`:** the module's `skipif(win32)` goes away, and the scenarios of `add-stdio-streams` run on Windows twice: with the overlapped pipes of `create_stdio_subprocess()`, and with the synchronous pipes of a plain `asyncio.create_subprocess_exec()` with `PIPE`, which is what the client does today. For The other end goes away, the parent builds its own pair on pipes of its own, with plain protocols, on every platform, because it closes only the end that it reads, which the pair of `create_stdio_subprocess()` does not offer. New tests with `skipif(sys.platform != "win32")` cover the scenarios that exist only there. The one with Node's default pipes runs on every platform, because elsewhere Node gives a child socket pairs, which is what a debug adapter of VS Code gets there; it skips without `node`, except in CI.
  - **Three tests stay POSIX-only:** those that start Python through `/bin/sh` with `0<&-`, `1>&-` or `2>&-`, so that a standard stream is closed at the start. On Windows, `subprocess` cannot start a process without a standard handle, because it puts in the parent's handle. The check of `sys.__std*__` that they cover is the same code on Windows.
  - **`os.system()` in the test of child processes** builds its command with `shlex.join()`, whose quotes cmd.exe does not understand, so it uses `subprocess.list2cmdline()` on Windows.
- **A real debug session in VS Code,** once on the VM during this change: a minimal extension registers a debugger whose adapter is a Python script on `open_stdio_connection()`. It answers `initialize`, and logs which kind of pipes it has and how many threads serve them. This closes the gap between Node 26 and VS Code's Electron. It is no CI test, because CI has no VS Code.
  - **Result (VS Code 1.145, Python 3.12, 2026-11-07):** stdin and stdout were synchronous pipes, two threads served them, and the session ran from `initialize` through `launch`, `configurationDone` and `threads` to `disconnect`; the adapter exited with code 0. VS Code reports the closing of an adapter's stdout as `read error` to a tracker, for any adapter (`serverProcess.stdout.on("close", ...)` in its extension host).
- **The flags of decision 8:** these are checked with a fake `asyncio.create_subprocess_exec` and a fake console check, because a test cannot see a window. On the VM, a real run without a console confirms it once.
- **`tests/test_client_connection.py`:** the `skipif` markers go away. `os.kill(pid, 0)` would end the process on Windows, so `_pid_exists()` asks with `OpenProcess()` there.
- **`atests/stdio_*.robot`:** the tag `posix` goes away, and `atests/stdio_windows.robot` is removed. `robot.toml` keeps its profiles, because the tests of SIGTERM stay on POSIX; its comment changes.
- **New `atests/stdio_node_server.robot` with `atests/node_keywords.js`,** the server from the prototype, runs in every job. It is the only test of a server in another language, and it is what the protocol is for. It imports the library in its suite setup and skips if `node` is missing, except in CI, where a missing `node` should fail: the runners of all three operating systems have Node. It uses 100 calls rather than 1000, which is enough for this purpose.

### 10. The Windows code is type-checked on Linux

`uv run mypy` on Linux skips everything under `sys.platform == "win32"`, and `mypy --platform win32` checks it. On the current code, with mypy 2.4.1, this reports only the statement after the `raise` in `open_stdio_connection()` (`stdio.py`), which goes away. So the lint job gets the step `uv run mypy --platform win32`. This shapes the code:

- `_win32_pipes.py` starts with `assert sys.platform == "win32"`, so that mypy on Linux skips the module.
- Code after a branch that returns is reported as unreachable on the other platform, so `stdio.py` uses `if`/`else`, as in decision 3.
- mypy does not apply a platform check in a conditional expression, so `_run()` uses an `if` statement for the loop factory.

### 11. The rule for a server of your own goes on the protocol page

The guide TCP and stdio drops POSIX only. Since `add-stdio-streams`, the protocol page has the section Over stdin and stdout, with the rule that a server without `open_stdio_connection()` writes nothing but messages to its stdout. The rule for Windows joins it there:

> On Windows, the client creates the stdin and stdout of the server as overlapped pipes, so that a Python server can use I/O completion ports. Programs in other languages read and write them as usual, with one reader and one writer. Do not let anyone else use these pipes: a child process that inherits stdin or stdout, or a second handle in another thread, can lose data or crash the process. Start child processes with their own stdin and stdout.

It is a rule of use, not a gap, so it belongs on the page, and the Python helper keeps to it by itself.

### 12. Handles that a launcher handed down

- **The cause, measured on the VM:** CPython's own launcher, which is the `python.exe` of a venv made with `python -m venv`, and `py.exe`, start Python with inheritable duplicates of their standard handles, and since Python inherits all their handles, the originals come along. So Python holds a second handle to each pipe, which is no descriptor and which the move does not reach. A child process that inherits all handles, as one of `os.system()` or of `subprocess` with `close_fds=False` does, then keeps the connection open after the process ended: the other end saw the end of the stream only when the child ended, 8 s later. The launcher of a venv that uv makes hands nothing down. `uv run --with` uses CPython's launcher, so the test of `add-stdio-streams` for a child process failed in the run with Robot Framework 7.2.
- **The cleanup:** after the move, `keep_from_children()` lists the handles of the process with `NtQueryInformationProcess()` and `ProcessHandleInformation`, finds the inheritable ones that refer to the pipes of the private duplicates with `CompareObjectHandles()` from `kernelbase.dll`, and clears their `HANDLE_FLAG_INHERIT`. It does not close them, because it does not own them. On the VM, the end of the stream then arrived at once.
- **Why in the function:** Daniel chose it over a limit in the backlog (2026-11-07), because the venvs of `python -m venv` are the usual ones on Windows.
- **The test** hands the process further inheritable handles to its pipes itself, so that it does not depend on the launcher that runs it.

## Risks / Trade-offs

- [A foreign server with a child process that inherits stdout and writes big blocks at the same time can get wrong data or crash, which normal pipes would not do] → The rule on the protocol page. The tests were in Python, and it was not tried in another language. A foreign server can also run over TCP.
- [A foreign program has trouble with overlapped pipes, as msys2 is slow and docker is untested] → TCP stays available. A `docker run -i` as a command is what the page already describes, so it should be tried on the VM during this change if docker can be installed there, and otherwise stays open. It stays open: docker is not installed on the VM, Docker Desktop needs a confirmation on the screen and a restart, and Daniel chose to leave it untested rather than install the engine in the WSL distribution there (2026-11-07). The docker CLI is a Go program, and Go programs behaved on overlapped pipes as on normal ones.
- [The thread transports are our own code on asyncio's transport interface, which has more corners than the stream API] → They implement only what `StreamReader`, `StreamWriter` and `_WritePipeProtocol` use, and all scenarios of `add-stdio-streams` run over them on Windows.
- [`CancelSynchronousIo()` cannot stop a read that has not started yet] → It is repeated until the thread has ended, and the thread is a daemon.
- [VS Code's Electron could create other pipes than Node 26] → The debug session on the VM checked it: synchronous pipes, as with Node 26. With overlapped pipes, the function would take the path through I/O completion ports, so the debugger works either way.
- [An overlapped pipe from a foreign parent that does not allow reading on stdout fails with the raw WinError 5] → Nobody does this today. Node's `stdio: 'overlapped'` passed.
- [`asyncio.windows_utils` is undocumented, though in its `__all__`, and `_winapi` is private] → The standard library uses both itself, and CI runs every supported version on Windows.
- [Keyword calls can hang on Windows on any transport, because Robot Framework restarts its proactor loop for each asynchronous keyword and a wakeup can get lost] → This is a separate bug. It happened in 1 of 15 runs of 5,000 calls on the Insider build, and no CI log shows it so far. The new suites add about 300 calls per run on Windows. It stays its own item, and a job that hangs ends at its timeout of 20 minutes.
- [The VM runs an Insider build, and CI runs Windows Server 2025] → The CI run after the push is the check, on all Python versions.

## Migration Plan

None. Stdio did not work on Windows before. POSIX is unchanged.
