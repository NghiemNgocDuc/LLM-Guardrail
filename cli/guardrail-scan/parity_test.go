package main

import (
	"encoding/json"
	"os"
	"os/exec"
	"path/filepath"
	"reflect"
	"strings"
	"testing"
)

// buildBinary compiles guardrail-scan into a temp dir and returns its path.
func buildBinary(t *testing.T) string {
	t.Helper()
	dir, err := os.Getwd()
	if err != nil {
		t.Fatal(err)
	}
	exe := filepath.Join(t.TempDir(), "guardrail-scan")
	if filepath.Ext(exe) == "" && os.PathSeparator == '\\' {
		exe += ".exe"
	}
	cmd := exec.Command("go", "build", "-o", exe, ".")
	cmd.Dir = dir
	if out, err := cmd.CombinedOutput(); err != nil {
		t.Fatalf("go build: %v\n%s", err, out)
	}
	return exe
}

func probePython(p string) bool {
	cmd := exec.Command(p, "-c", "import sys; assert sys.version_info >= (3, 8)")
	return cmd.Run() == nil
}

func findPython(root string) string {
	var candidates []string
	for _, name := range []string{"python3", "python"} {
		if p, err := exec.LookPath(name); err == nil {
			candidates = append(candidates, p)
		}
	}
	for _, rel := range []string{filepath.Join("venv", "Scripts", "python.exe"), filepath.Join("venv", "bin", "python3")} {
		candidates = append(candidates, filepath.Join(root, rel))
	}
	for _, c := range candidates {
		if probePython(c) {
			return c
		}
	}
	return ""
}

func runTool(t *testing.T, bin string, root string, args ...string) (string, int) {
	t.Helper()
	cmd := exec.Command(bin, args...)
	cmd.Dir = root
	cmd.Env = append(os.Environ(), "PYTHONIOENCODING=utf-8")
	out, err := cmd.CombinedOutput()
	exit := 0
	if err != nil {
		ee, ok := err.(*exec.ExitError)
		if !ok {
			t.Fatalf("run %s: %v\n%s", bin, err, out)
		}
		exit = ee.ExitCode()
	}
	return string(out), exit
}

// normalizeLines splits output into lines, trimming Windows \r so the Python
// (os.linesep) and Go (\n) writers compare equal.
func normalizeLines(s string) []string {
	raw := strings.Split(s, "\n")
	out := make([]string, 0, len(raw))
	for _, ln := range raw {
		out = append(out, strings.TrimSuffix(ln, "\r"))
	}
	return out
}

func fixtureNames(t *testing.T, root string) []string {
	t.Helper()
	entries, err := os.ReadDir(filepath.Join(root, "fixtures", "skills"))
	if err != nil {
		t.Fatal(err)
	}
	var names []string
	for _, e := range entries {
		if !e.IsDir() {
			names = append(names, e.Name())
		}
	}
	return names
}

// TestPythonParity runs the Python script and the Go binary on every fixture
// file and requires identical stdout and exit codes. This is the drift guard:
// if the two implementations ever diverge, this test fails.
func TestPythonParity(t *testing.T) {
	root := repoRoot(t)
	python := findPython(root)
	if python == "" {
		t.Skip("python not found on PATH")
	}
	goBin := buildBinary(t)
	pyScript := filepath.Join(root, "scripts", "scan_agent_skills.py")

	for _, name := range fixtureNames(t, root) {
		name := name
		t.Run(name, func(t *testing.T) {
			tmp := t.TempDir()
			data, err := os.ReadFile(filepath.Join(root, "fixtures", "skills", name))
			if err != nil {
				t.Fatal(err)
			}
			if err := os.WriteFile(filepath.Join(tmp, name), data, 0o644); err != nil {
				t.Fatal(err)
			}
			target := filepath.Join(tmp, name)

			for _, flagSet := range []string{"", "--github-actions"} {
				args := []string{}
				if flagSet != "" {
					args = append(args, flagSet)
				}
				pausePath := filepath.Join(tmp, ".cursor", "skill-guard-pause.json")
				os.Remove(pausePath)

				pyOut, pyExit := runTool(t, python, tmp, append([]string{pyScript, "--root", tmp}, append(args, target)...)...)

				// Snapshot Python's pause file before Go overwrites it.
				var pyPause []byte
				if _, err := os.Stat(pausePath); err == nil {
					pyPause, _ = os.ReadFile(pausePath)
					os.Remove(pausePath)
				}

				goOut, goExit := runTool(t, goBin, tmp, append(args, "--root", tmp, target)...)

				if pyExit != goExit {
					t.Errorf("exit code mismatch: python=%d go=%d\n--- python ---\n%s\n--- go ---\n%s", pyExit, goExit, pyOut, goOut)
				}
				pyLines := normalizeLines(pyOut)
				goLines := normalizeLines(goOut)
				if !reflect.DeepEqual(pyLines, goLines) {
					t.Errorf("stdout mismatch (flags %q):\n--- python ---\n%s\n--- go ---\n%s", flagSet, pyOut, goOut)
				}

				// Both tools write .cursor/skill-guard-pause.json when blocked:
				// compare it field-for-field (Go emits raw UTF-8, Python
				// ensure_ascii, so byte-for-byte is not expected).
				if pyPause != nil {
					goPause, err := os.ReadFile(pausePath)
					if err != nil {
						t.Fatalf("go pause file missing: %v", err)
					}
					var a, b map[string]any
					if err := json.Unmarshal(pyPause, &a); err != nil {
						t.Fatalf("python pause json: %v", err)
					}
					if err := json.Unmarshal(goPause, &b); err != nil {
						t.Fatalf("go pause json: %v", err)
					}
					if !reflect.DeepEqual(a, b) {
						t.Errorf("pause file mismatch:\n--- python ---\n%s\n--- go ---\n%s", string(pyPause), string(goPause))
					}
					os.Remove(pausePath)
				}
			}
		})
	}
}
