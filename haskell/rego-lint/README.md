# rego-lint — offline Rego syntax linter (Haskell)

A small zero-dependency Haskell CLI that catches Rego syntax errors and
common rule-shape mistakes **before** the OPA sidecar round trip. It is the
optional fast-fail pre-check wired into `opa.validate` (used by both
`POST /policy/validate-rego` and `PATCH /policy`), while the OPA compile
check stays authoritative.

## Why cabal (not stack)

- A single `rego-lint.cabal` + GHC is all that is needed; stack would first
  download a resolver snapshot and its own GHC.
- The official `haskell` Docker image ships GHC and cabal-install, so the
  whole project builds with no extra toolchain.
- The package has one dependency beyond `base` (`hspec`, tests only).

## What it checks

Lexer — illegal characters, unterminated strings, malformed numbers.
Parser — unbalanced/unterminated brackets, stray closing brackets, malformed
`package` / `import` / `default` statements, trailing dots in paths.
Heuristics — missing `package` (mirrors `opa.validate`), statement before
package, duplicate package, and a rule head with no body or value (mirrors
OPA's "rule must have a body or value" parse error).

## Build & test (Docker, reproducible)

```bash
docker run --rm -v "$PWD:/work" -w /work/haskell/rego-lint haskell:9.6 \
  bash -lc "cabal update && cabal build all && cabal test && cabal list-bin rego-lint"
```

`cabal test` runs the Hspec suite (lexer/parser/heuristics + all 11
fixtures in `test/fixtures/`).

## Usage

```
usage: rego-lint [FILE|-]          # '-' = stdin (default)
```

Issues are printed one per line as `FILE:LINE:COL: error: MESSAGE` on
stderr; exit status 0 = clean, 1 = issues, 64 = bad usage, 74 = unreadable
file.

```console
$ rego-lint policy.rego
policy.rego:2:1: error: rule 'allow' must have a body or value
$ echo $?
1
```

## Integration

`guardrails/opa.py:rego_lint` runs `rego-lint -` (stdin) before the OPA
compile check in `validate()`, raising `OPAValidationError` with the
linter's output on failure. It is **optional**: when no binary is on PATH
(or `REGOLINT_BIN` is unset), it is skipped silently and OPA remains the
only gate. `tests/test_rego_lint_integration.py` exercises the CLI on the
fixtures and the fast-fail path (skipped on hosts without the binary).

## Porting note

The linter targets the Rego subset the gateway actually accepts for org
custom rules (rule bodies, `if`, `contains`, `default`, `import`, object
literals). It deliberately does not attempt full Rego semantics — OPA's
compile check is authoritative and remains mandatory.