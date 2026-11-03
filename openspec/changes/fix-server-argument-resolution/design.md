# Design

## Context

See proposal.md for the motivation. What the server does today:

- **Keyword call:** `_robot_run_keyword` looks the keyword up with `lib.find_keywords(name)`, gets a runner with `kw.create_runner(name)` and runs a `running.Keyword` with the values as `args` and `named_args`. The runner resolves them with `context.variables`: strings go through variable replacement and unescaping, and everything else passes untouched.
- **Embedded arguments:** for such a keyword, `create_runner` returns an `EmbeddedArgumentsRunner`, which parses values from the name and puts them before `args`. Robot's dynamic API calls the client's `run_keyword` with the name of the definition, such as `Embedded ${value} In The Name`, and the values in `args`. So `${value}` becomes a value, and the real values come after it.
- **Library import:** `_endpoint.py` turns named values into `name=value` strings, and `_robot_import_library` calls `context.namespace.import_library(name, args, token)`. Robot resolves the name, the arguments and the alias, which is the token.

The decisions below were tried out on a copy of the server against Robot Framework 7.2 and 7.5 on Linux, and against 7.5 on Windows 11, with the same results on all three: 44 keyword cases compared with a local library, import arguments, library paths, and `BuiltIn` as a remote library. On Windows, the current server turns a real library path into `C:Usersdaniejsonrpc-9bprobe9PathLib.py`, and the copy imports it.

## Goals / Non-Goals

**Goals:**

- A library gets the same strings as a local library, in keyword calls and imports.
- Keywords with embedded arguments work, on all supported Robot Framework versions.
- The keyword still runs through Robot's runner, with its argument conversion, output capture and status handling.

**Non-Goals:**

- Named values of an import that are not strings keep their type (decision 6).
- New behavior on the client or new fields in the protocol.
- The other defects of the import path, which belong to `fix-server-library-import`.

## Decisions

### 1. Escape the strings, and let Robot resolve them back

`robot.utils.escape` turns a string into the data that resolves to exactly this string. Robot uses it for the same purpose in `VariableReplacer._replace_list_until`, in 7.2 and 7.5. Non-strings pass through it unchanged, and Robot does not look into lists and dicts.

Alternatives:

- **A runner that resolves with `variables=None`:** needs the private method `_resolve_arguments` and does nothing for imports.
- **Calling the method of the keyword directly:** loses the output capture, the status handling and the conversion.
- **A Robot variable per value, passed as `${name}`:** needs no escaping, but sets variables in the namespace on every call.

### 2. Control words stay as they are

`escape` also puts a backslash before a string that is exactly `AND`, `ELSE`, `ELSE IF`, `AS` or `WITH NAME`. For a normal keyword that makes no difference. A keyword such as `Run Keywords` does not resolve its arguments before it looks for `AND`, so `\AND` is not found: in the probe, `Run Keywords` failed and `Run Keyword If` silently skipped its `ELSE` branch. Both work today, so this would be a regression.

So a small helper in `_runner.py` leaves these five words alone and calls `escape` for everything else.

Alternatives:

- **An own regular expression instead of `escape`:** has no control words, but repeats Robot's list of syntax, which `escape` follows by itself.
- **No escaping for run keyword variants:** needs the private `_resolve_args_until`, and their values would still be resolved twice.

For a variant, the arguments it does not resolve stay escaped until the keyword it runs resolves them. That is the same data that a local call has, so the values come out right.

### 3. Robot's data is built in the runner

Escaping needs to happen where `name=value` is put together, because the `=` between name and value must stay unescaped. `_endpoint.py` builds it today but imports nothing from Robot, and it should stay that way. So `import_library` takes `args` and `kw_args` as they came, and `_robot_import_library` builds Robot's data. The stub in `tests/test_endpoint.py` and the calls in `tests/test_runner.py` change with the signature.

Non-strings in `kw_args` stay text through `str(value)`, as today, and are escaped like any other string. A list with a backslash therefore reaches Robot's conversion unchanged.

### 4. The library name and the token are escaped too

`Namespace.import_library` resolves the name and the alias. The token starts with the name, so a path breaks both. Escaping them makes Robot end up with the same strings. `get_library` still gets the unescaped token, which is the name that Robot stores the library under.

### 5. A keyword with embedded arguments is found by its exact name, and runs with the plain runner

```python
kws = [kw for kw in lib.find_keywords(name) if not kw.embedded or kw.name == name]
```

`find_keywords` returns a normal keyword by its normalized name, as today, or all embedded keywords whose pattern fits, among them the keyword with that exact name. The filter leaves that one, or nothing for a name with values filled in. Robot does not allow two keywords with the same name, so at most one remains, and the branch `Multiple keywords named ...` goes away.

`LibraryKeywordRunner(kw)` replaces `create_runner` for these keywords: the values are already in `args`, and there is nothing to parse from the name.

Alternatives:

- **`create_runner` and `runner.embedded_args = ()`:** works too, but parses a name only to throw the result away, and sets an attribute from outside.
- **Keeping names with values filled in:** would be a second way to call a keyword, with values in the name that Robot would resolve again. The protocol page already asks for the name from the definition.
- **Sending the value in the name from the client:** Robot's dynamic API does not give the client the name as written in the suite.

### 6. Named values of an import that are not strings stay text

Locally, `num=${5}` gets the integer `5`. Remotely, it gets `"5"`, unless a type hint converts it. The page on the arguments of a library says so. Only `robot.running.model.Argument` could keep the type in an import, and its docstring calls it temporary and possibly gone in Robot Framework 8.0. The defect is a different one, so it goes into the backlog.

### 7. The Robot suite compares with a local library

`atests/argument_values.robot` imports the same library locally and remotely and compares the results. That says directly what the specs ask for. The template keyword passes the values with list variables through `Run Keyword`, so that it does not resolve them once more. Keywords with embedded arguments get a suite of their own without the template, `atests/embedded_arguments.robot`, because `Run Keyword` would resolve the values in their names a second time, locally as well, and a broken value would then pass. The unit tests state the exact values.

## Risks / Trade-offs

- **[The fix uses more of Robot's internals]** `LibraryKeywordRunner` and `kw.embedded` come on top of what the server uses already. → They exist unchanged from 7.2 to 7.5, and CI runs the minimum and the latest version.
- **[Escaping costs time for large strings]** → Measured: 0.07 s for a string of 20 MB, which is small next to sending it. Resolving costs what it costs today.
- **[Listeners on the server see escaped arguments]** A listener in a library reads `data.args` as `C:\\temp`. → That is what the data of a suite file looks like, too. The keyword itself gets the real value.
- **[A name with values filled in no longer works]** → No client is known to send one, and the answer `KEYWORD_NOT_FOUND` names the keyword.
