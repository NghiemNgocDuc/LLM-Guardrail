# guardrail-scan — standalone Go port of `scripts/scan_agent_skills.py`

A single static binary (no Python, no dependencies) that scans Cursor agent
skill files for secrets, PII, destructive commands, and internal details. It is
a drop-in replacement for the Python script:

- identical flags (`--root`, paths, `--min-severity`, `--github-actions`,
  `--pre-push`, `--git-range`, `--interactive`)
- identical stdout and exit codes (0 = clean, 1 = blocked)
- interoperable `.cursor/skill-guard-overrides.json` and
  `.cursor/skill-guard-pause.json` files — an override written by one tool is
  honored by the other

## Build

```bash
cd cli/guardrail-scan
make build        # produces ./guardrail-scan
make test         # unit tests + Python parity test (needs python3 on PATH)
make install      # installs into /usr/local/bin (or: PREFIX=$HOME make install)
```

Windows (no make):

```powershell
go build -o guardrail-scan.exe .
go test ./...
```

Cross-compile static binaries:

```bash
make release      # dist/guardrail-scan-{darwin,linux,windows}-{amd64,arm64}
```

## Use

```bash
guardrail-scan                            # scan .cursor/skills/** (default globs)
guardrail-scan --git-range origin/main..HEAD
guardrail-scan --github-actions           # emit ::error annotations (CI)
guardrail-scan --pre-push                 # git pre-push mode (reads refs on stdin)
guardrail-scan --interactive file.md      # per-finding Run once / Always allow / Reject
```

To use it from the pre-push hook, just build the binary:

```bash
cd cli/guardrail-scan && make build
```

`.githooks/pre-push` detects it automatically and falls back to the Python
script when it is absent. Override explicitly with `SKILL_GUARD_BIN=/path/to/binary`.

## Drift protection

The Go implementation is verified against Python by `parity_test.go`, which runs
**both** tools on every file in `fixtures/skills/` and requires identical
stdout, exit codes, and pause files. The Python suite reads the same fixtures
(`tests/test_skill_guardrails_fixtures.py`), and CI runs `go test ./...`
(`ci.yml` → `go-port-tests`). If the two implementations ever diverge, tests
fail automatically.

Add a new detection fixture as `fixtures/skills/<name>.md`; it must pass in
both suites unchanged.

## Known divergences from the Python original

The port is byte-for-byte compatible on the fixture set and in normal use.
Intentional, documented differences:

1. **Default `--root`**: Python defaults to `scripts/../` (its install
   location). The binary defaults to the **git root discovered from the current
   directory** (walking up until `.git/`), falling back to CWD. Same result
   when run from inside the repo — the binary has no install location to
   anchor to.
2. **Regex flavor**: Go uses RE2 (no backtracking). All scanner patterns are
   RE2-compatible and the parity test locks behavior. `\b` in Go is ASCII-based,
   so non-ASCII word characters adjacent to a pattern can differ from Python
   (which is Unicode-aware); skill content is ASCII in practice.
3. **Pause file JSON encoding**: Python writes `ensure_ascii=True` (`\u2014`
   for em-dashes); Go writes raw UTF-8 (valid JSON, equal semantics). The
   parity test compares the pause file field-for-field, not byte-for-byte.
4. **Windows**: the Go binary writes UTF-8 natively; the Python script can
   crash on Windows consoles with `UnicodeEncodeError` on the `↳` character.
   The parity test sets `PYTHONIOENCODING=utf-8` for Python to compare fairly.
5. **Glob case sensitivity**: `_collect_files` matching is case-sensitive on
   all platforms; Python's `pathlib.glob` is case-insensitive on Windows.
   File names in `.cursor/skills/` are `SKILL.md`/`skill.md` in practice.
6. **Output strings**: messages that name the Python entry point
   (`python scripts/report_skill_rejection.py --scan <file>` and the pause
   prompt's `skill_guard_decision.py` line) are kept verbatim so output stays
   byte-identical and chat-control tooling keeps working.
