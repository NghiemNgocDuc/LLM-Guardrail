# env-check

A zero-dependency Zig CLI that validates an `.env` file against the
conventions used by this repository's `.env.example`.

## Why Zig

* static, zero-dependency binary: no runtime, no shared libraries
* one toolchain compiles for Linux, macOS and Windows from a single source
  (`zig build -Dtarget=...`), which matters for a repo that also ships
  Python (test-only), Kotlin, Swift, Elixir, Haskell and Julia code

## Checks

| severity | check |
|---|---|
| error | malformed line (no `=`) |
| error | empty key name |
| error | invalid key name (`[A-Za-z_][A-Za-z0-9_]*` only) |
| error | duplicate key |
| error | unterminated quote |
| error | unknown key (not present in the schema file) |
| error | `${...}` interpolation in a value (docker-compose syntax, not .env) |
| error | `--required` key missing from the file |
| warning | placeholder value (`your_*`, `changeme`, `<...>`, `XXXX`) |
| warning | SECRET/PASSWORD/TOKEN value shorter than 8 chars (numeric-only values are treated as counters/expiries, not credentials) |
| warning | key with a non-empty default in the schema is absent |

Conventions encoded in the schema (`--schema .env.example`):

* empty value in the schema  -> key is optional, expected to be filled in
* non-empty value in the schema -> key has a working default; omission is
  only a warning
* `#` starts a comment only at the start of a line (no inline comments;
  values containing `#` such as API keys with fragments are preserved)

## Build & test

```
zig build                 # builds zig-out/bin/env-check(.exe)
zig build test            # unit tests (src/envcheck.zig)
zig build -Dtarget=x86_64-linux-musl -p zig-out-linux
zig build -Dtarget=aarch64-linux-musl -p zig-out-linux-arm
zig build -Dtarget=aarch64-macos -p zig-out-macos
```

Zig 0.15.2 was used. `std.ArrayList` is unmanaged in 0.15 (`.empty`,
allocator passed per call), `std.fs.File.stdout()` replaced
`std.io.getStdOut()`, and `error` is a reserved word so the severity enum
field is named `err`.

Windows note: with Smart App Control (or a Device Guard policy) in
enforce mode, freshly compiled binaries under `.zig-cache` may be blocked
from executing. Workaround used during development: compile the unit-test
binary with `zig test --test-no-exec -target x86_64-linux-musl
-femit-bin=envcheck-test-linux src/envcheck.zig` and run it in a Linux
container (`docker run --rm -v ...:/work alpine /work/envcheck-test-linux`).
The CLI binary in `zig-out/bin` executes normally; the Python integration
tests in `tests/test_env_check_zig.py` exercise the real binary. The
cross-compile tests build the linux/macos artifacts; if `zig` is not on
PATH, set `ZIG_BIN=/path/to/zig.exe` when running pytest. The
x86_64-linux-musl artifact is additionally executed inside an alpine
container and its exit codes are compared against the native binary.

## Usage

```
env-check check <ENV_FILE> --schema <EXAMPLE_FILE> [--required KEY]...
env-check --version
env-check --help
```

Output goes to stderr, one line per issue:
`<file>:<line>: <severity>: <message> '<key>'` (line 0 issues print
without a line number).

Exit status: 0 = clean, 1 = at least one error, 2 = warnings only,
64 = usage error, 74 = unreadable file.