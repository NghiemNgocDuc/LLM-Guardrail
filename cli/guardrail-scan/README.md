# guardrail-scan

A standalone Go companion for scanning agent instruction files for credentials,
PII, destructive commands, and internal infrastructure details. The binary has
no Python runtime dependency.

**Use the canonical [Python scanner](../../scripts/scan_agent_skills.py) for Git
push gates and current security checks.** The Go implementation is independent;
it does not implement all of the canonical scanner's detection, scoped
prohibition, or committed-history behavior. `.githooks/pre-push` always uses
Python, regardless of whether this binary is installed.

## Build and test

Requires Go 1.22 or newer. Run inside `cli/guardrail-scan`:

```bash
go build -o guardrail-scan .
go test ./...
```

On Windows, use `go build -o guardrail-scan.exe .`.

The Makefile also supports `make build`, `make test`, `make install`, and
`make release` for cross-compiling Linux, macOS, and Windows binaries.

## Scan working files

```bash
guardrail-scan                             # .cursor/skills/** by default
guardrail-scan path/to/SKILL.md
guardrail-scan --github-actions file.md     # workflow annotations
guardrail-scan --interactive file.md        # deliberate local review
```

A clean scan exits 0; blocked content exits 1. Diagnostic excerpts redact
credentials and PII before truncation. Pause files contain a review request;
an external agent must integrate the decision into its own loading behavior.

`--git-range` and `--pre-push` are legacy working-tree selection modes in this
companion. They do not provide the canonical scanner's committed-blob and
outgoing-history guarantees. Use Python when reviewing content for publication:

```bash
python scripts/scan_agent_skills.py --git-range origin/main..HEAD
```

Run that command from the repository root.

## Compatibility checks

`parity_test.go` runs both tools on the shared `fixtures/skills/` corpus and
compares stdout, exit codes, and pause-file fields. It requires Python and the
repository's Python dependencies and skips when a suitable interpreter cannot
be found. Passing this corpus does not establish parity on arbitrary content.

Go uses RE2 and ASCII word boundaries; Python uses Unicode-aware matching.
The binary discovers its default root from the current Git repository, while
Python uses its installation location. Both accept an explicit `--root`.
