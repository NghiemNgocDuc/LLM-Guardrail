package main

import (
	"bufio"
	"flag"
	"fmt"
	"os"
	"os/exec"
	"path"
	"path/filepath"
	"sort"
	"strings"
	"unicode/utf8"
)

// Standalone Go port of scripts/scan_agent_skills.py. Drop-in replacement:
// same flags, same output, same exit codes.

var defaultGlobs = []string{
	".cursor/skills/**/SKILL.md",
	".cursor/skills/**/*.md",
	".cursor/skills/**/skill.md",
}

var severityRank = map[string]int{
	"medium":   1,
	"high":     2,
	"critical": 3,
}

func stdinIsTTY() bool {
	fi, err := os.Stdin.Stat()
	if err != nil {
		return false
	}
	return fi.Mode()&os.ModeCharDevice != 0
}

func display(root, abs string) string {
	rel, err := filepath.Rel(root, abs)
	if err != nil || strings.HasPrefix(rel, "..") {
		return abs
	}
	return rel
}

// collectFiles walks root applying each glob pattern with ** support
// (Python pathlib glob semantics: ** matches zero or more directories).
func collectFiles(root string, patterns []string) []string {
	seen := make(map[string]struct{})
	var files []string
	for _, pat := range patterns {
		parts := strings.Split(filepath.ToSlash(pat), "/")
		walkParts(root, root, parts, &files, seen)
	}
	sort.Strings(files)
	return files
}

func walkParts(base, dir string, parts []string, out *[]string, seen map[string]struct{}) {
	if len(parts) == 0 {
		if fi, err := os.Stat(dir); err == nil && fi.Mode().IsRegular() {
			if _, ok := seen[dir]; !ok {
				seen[dir] = struct{}{}
				*out = append(*out, dir)
			}
		}
		return
	}
	p := parts[0]
	if p == "**" {
		walkParts(base, dir, parts[1:], out, seen)
		entries, err := os.ReadDir(dir)
		if err != nil {
			return
		}
		for _, e := range entries {
			if e.IsDir() {
				walkParts(base, filepath.Join(dir, e.Name()), parts, out, seen)
			}
		}
		return
	}
	entries, err := os.ReadDir(dir)
	if err != nil {
		return
	}
	for _, e := range entries {
		if ok, _ := path.Match(p, e.Name()); ok {
			walkParts(base, filepath.Join(dir, e.Name()), parts[1:], out, seen)
		}
	}
}

func gitDiffSkillFiles(root, revRange string) []string {
	cmd := exec.Command("git", "diff", "--name-only", "--diff-filter=ACMR", revRange, "--", ".cursor/skills/")
	cmd.Dir = root
	out, err := cmd.Output()
	if err != nil {
		return nil
	}
	seen := make(map[string]struct{})
	var files []string
	for _, line := range strings.Split(string(out), "\n") {
		rel := strings.TrimSpace(line)
		if rel == "" {
			continue
		}
		abs := filepath.Clean(filepath.Join(root, filepath.FromSlash(rel)))
		if fi, err := os.Stat(abs); err == nil && fi.Mode().IsRegular() {
			if _, ok := seen[abs]; !ok {
				seen[abs] = struct{}{}
				files = append(files, abs)
			}
		}
	}
	sort.Strings(files)
	return files
}

// collectFilesForPrePush reads git pre-push hook stdin. Returns nil when no
// skill paths changed (caller prints "OK"), otherwise the files to scan.
func collectFilesForPrePush(root string) []string {
	if stdinIsTTY() {
		return collectFiles(root, defaultGlobs)
	}
	var lines []string
	sc := bufio.NewScanner(os.Stdin)
	for sc.Scan() {
		if ln := strings.TrimSpace(sc.Text()); ln != "" {
			lines = append(lines, ln)
		}
	}
	if len(lines) == 0 {
		return collectFiles(root, defaultGlobs)
	}

	toScan := make(map[string]struct{})
	for _, line := range lines {
		parts := strings.Fields(line)
		if len(parts) < 4 {
			continue
		}
		localSHA := parts[1]
		remoteSHA := parts[3]
		if allZeros(remoteSHA) {
			return collectFiles(root, defaultGlobs)
		}
		for _, f := range gitDiffSkillFiles(root, remoteSHA+".."+localSHA) {
			toScan[f] = struct{}{}
		}
	}
	if len(toScan) == 0 {
		return nil
	}
	files := make([]string, 0, len(toScan))
	for f := range toScan {
		files = append(files, f)
	}
	sort.Strings(files)
	return files
}

func allZeros(s string) bool {
	for _, c := range s {
		if c != '0' {
			return false
		}
	}
	return true
}

func defaultRoot() string {
	dir, err := os.Getwd()
	if err != nil {
		return dir
	}
	for {
		if fi, err := os.Stat(filepath.Join(dir, ".git")); err == nil && fi.IsDir() {
			return dir
		}
		parent := filepath.Dir(dir)
		if parent == dir {
			return dir
		}
		dir = parent
	}
}

func printRejection(f SkillFinding, githubActions bool, absPath string) {
	loc := "file"
	if f.LineNumber != nil {
		loc = fmt.Sprintf("line %d", *f.LineNumber)
	}
	fmt.Printf("  [%s] %s (%s)\n", f.Severity, f.Check, loc)
	fmt.Printf("  Why: %s\n", explainFinding(f.ReasonCode, f.Check))
	fmt.Printf("  Snippet: %s\n", f.Snippet)
	if githubActions && absPath != "" {
		rel := filepath.ToSlash(absPath)
		if f.LineNumber != nil {
			fmt.Printf("::error file=%s,line=%d,title=Skill Guard::%s\n", rel, *f.LineNumber, explainFinding(f.ReasonCode, f.Check))
		} else {
			fmt.Printf("::error file=%s,title=Skill Guard::%s\n", rel, explainFinding(f.ReasonCode, f.Check))
		}
	}
}

func parseBatchCommand(raw string) string {
	cmd := strings.ToLower(strings.TrimSpace(raw))
	cmd = strings.ReplaceAll(cmd, "  ", " ")
	switch cmd {
	case "always allow", "always allow all", "allow all", "allow always", "a", "aa":
		return "always_all"
	case "run once", "run once all", "allow once", "ro":
		return "run_once_all"
	}
	return ""
}

var reader = bufio.NewReader(os.Stdin)

func promptLine(prompt string) string {
	fmt.Print(prompt)
	line, err := reader.ReadString('\n')
	if err != nil && line == "" {
		return ""
	}
	return strings.TrimRight(line, "\r\n")
}

func interactiveResolve(root string, blocking []SkillFinding, ov *SkillOverrides) {
	if os.Getenv("SKILL_GUARD_NON_INTERACTIVE") == "1" {
		return
	}

	fmt.Printf("\nSkill Guard: %d issue(s) blocking.\n", len(blocking))
	fmt.Println("  Quick (chat-style): type \"always allow\" or \"always allow all\" once — no per-issue prompts.")
	fmt.Printf("  Or press Enter to choose per issue: [R] run once  [A] always allow  [E] reject\n\n")

	batch := promptLine(`Command ("always allow all" / Enter): `)
	action := parseBatchCommand(batch)
	if action == "always_all" {
		for _, f := range blocking {
			ov.allowAlways(f)
		}
		saveOverrides(root, ov)
		fmt.Printf("  → Always allowed all %d issue(s); saved to %s.\n\n", len(blocking), overridesPath(root))
		return
	}
	if action == "run_once_all" {
		for _, f := range blocking {
			ov.allowOnce(f)
		}
		fmt.Printf("  → Run once: allowed all %d issue(s) for this run only.\n\n", len(blocking))
		return
	}

	for idx, f := range blocking {
		fmt.Printf("--- Issue %d/%d (%s) ---\n", idx+1, len(blocking), findingKey(f))
		printRejection(f, false, "")
		for {
			choice := strings.ToLower(strings.TrimSpace(promptLine("Choice [R/A/E] or phrase: ")))
			switch parseBatchCommand(choice) {
			case "always_all":
				ov.allowAlways(f)
				saveOverrides(root, ov)
				fmt.Printf("  → Always allowed; saved to %s.\n\n", overridesPath(root))
				goto nextIssue
			case "run_once_all":
				ov.allowOnce(f)
				fmt.Printf("  → Allowed for this run only.\n\n")
				goto nextIssue
			}
			switch choice {
			case "r", "run", "run once", "1":
				ov.allowOnce(f)
				fmt.Printf("  → Allowed for this run only.\n\n")
			case "a", "always", "always allow", "2":
				ov.allowAlways(f)
				saveOverrides(root, ov)
				fmt.Printf("  → Always allowed; saved to %s.\n\n", overridesPath(root))
			case "e", "reject", "3":
				fmt.Printf("  → Rejected; agent remains blocked for this issue.\n\n")
			default:
				fmt.Println("  Enter R, A, or E.")
				continue
			}
			break
		}
	nextIssue:
	}
}

func filterByRank(findings []SkillFinding, minRank int) []SkillFinding {
	out := make([]SkillFinding, 0, len(findings))
	for _, f := range findings {
		if severityRank[f.Severity] >= minRank {
			out = append(out, f)
		}
	}
	return out
}

func scanFiles(root string, files []string, minRank int, githubActions, interactive bool) int {
	if len(files) == 0 {
		fmt.Println("Skill Guard: no files matched .cursor/skills/** — nothing to scan.")
		return 0
	}

	guard := &SkillGuardrail{}
	ov := loadOverrides(root)
	anyBlocking := false
	var pauseEntries []pauseEntry
	isTTY := stdinIsTTY()

	for _, abs := range files {
		content, err := os.ReadFile(abs)
		if err != nil {
			fmt.Fprintf(os.Stderr, "Skill Guard: cannot read %s: %v\n", abs, err)
			return 1
		}
		if !utf8.Valid(content) {
			fmt.Printf("Skill Guard: skip binary or non-UTF-8 file: %s\n", display(root, abs))
			continue
		}

		result := guard.Scan(string(content))
		decision := applyOverrides(result, ov)
		blocking := filterByRank(decision.Blocking, minRank)
		disp := display(root, abs)

		if interactive && len(blocking) > 0 && isTTY {
			interactiveResolve(root, blocking, ov)
			decision = applyOverrides(result, ov)
			blocking = filterByRank(decision.Blocking, minRank)
		}

		if len(blocking) == 0 {
			note := ""
			if len(decision.Allowed) > 0 {
				note = fmt.Sprintf(" (%d overridden)", len(decision.Allowed))
			}
			fmt.Printf("OK  %s (%d lines, risk %.0f%%)%s\n", disp, result.LineCount, result.RiskScore*100, note)
			continue
		}

		anyBlocking = true
		for _, f := range blocking {
			pauseEntries = append(pauseEntries, pauseEntry{src: disp, finding: f})
		}
		fmt.Printf("\nREJECTED %s — agent blocked (%d issue(s))\n", disp, len(blocking))
		if summary := decision.RejectionSummary(); summary != "" {
			fmt.Println(summary)
		}
		for _, f := range blocking {
			printRejection(f, githubActions, abs)
		}
	}

	if anyBlocking {
		writeChatPause(root, pauseEntries)
		if interactive && isTTY {
			fmt.Println("\nSkill Guard: push blocked. Fix the skill or re-run and choose Run once / Always allow.")
		} else {
			fmt.Println("\nSkill Guard: push blocked. Review in dashboard → Rejected access, or report: python scripts/report_skill_rejection.py --scan <file> (with SKILL_GUARD_API_URL + SKILL_GUARD_ACCESS_TOKEN).")
		}
		return 1
	}

	fmt.Printf("\nSkill Guard: %d file(s) passed — agent may continue.\n", len(files))
	return 0
}

func usageText() string {
	return `usage: guardrail-scan [--root ROOT] [--min-severity {medium,high,critical}]
                     [--github-actions] [--pre-push] [--git-range REV]
                     [--interactive] [path ...]

Scan Cursor agent skill files for secrets, PII, destructive commands, and internal details.

Exit 0 when all files are clean; exit 1 when any finding is reported.

positional arguments:
  path                  explicit files to scan (default: glob under .cursor/skills/)

options:
  --root ROOT           repository root (default: git root discovered from CWD)
  --min-severity {medium,high,critical}
                        minimum severity that fails the run (default: medium)
  --github-actions      emit workflow commands for GitHub Actions annotations
  --pre-push            git pre-push mode: scan .cursor/skills files in outgoing commits (read refs from stdin)
  --git-range REV       only scan skill files changed in a git revision range (e.g. origin/main..HEAD)
  --interactive         prompt for Run once / Always allow / Reject on each blocking finding (TTY only)
`
}

func run(args []string) int {
	fs := flag.NewFlagSet("guardrail-scan", flag.ContinueOnError)
	fs.SetOutput(os.Stderr)
	var (
		rootFlag       = fs.String("root", "", "repository root")
		minSeverity    = fs.String("min-severity", "medium", "minimum severity that fails the run")
		githubActions  = fs.Bool("github-actions", false, "emit GitHub Actions workflow commands")
		prePush        = fs.Bool("pre-push", false, "git pre-push mode (read refs from stdin)")
		gitRange       = fs.String("git-range", "", "only scan skill files changed in a git revision range")
		interactiveFl  = fs.Bool("interactive", false, "prompt per blocking finding (TTY only)")
	)
	fs.Usage = func() { fmt.Fprint(os.Stderr, usageText()) }
	if err := fs.Parse(args); err != nil {
		if err == flag.ErrHelp {
			fmt.Fprint(os.Stdout, usageText())
			return 0
		}
		return 2
	}

	if _, ok := severityRank[*minSeverity]; !ok {
		fmt.Fprintf(os.Stderr, "argument --min-severity: invalid choice: '%s' (choose from 'medium', 'high', 'critical')\n", *minSeverity)
		return 2
	}

	root := *rootFlag
	if root == "" {
		root = defaultRoot()
	}
	if abs, err := filepath.Abs(root); err == nil {
		root = abs
	}
	minRank := severityRank[*minSeverity]
	paths := fs.Args()

	var files []string
	switch {
	case *prePush:
		files = collectFilesForPrePush(root)
		if files == nil {
			fmt.Println("Skill Guard: no .cursor/skills/ changes in this push — OK.")
			return 0
		}
	case *gitRange != "":
		files = gitDiffSkillFiles(root, *gitRange)
		if len(files) == 0 {
			fmt.Printf("Skill Guard: no skill files in git range '%s'.\n", *gitRange)
			return 0
		}
	case len(paths) > 0:
		for _, p := range paths {
			abs, err := filepath.Abs(p)
			if err != nil {
				continue
			}
			if fi, err := os.Stat(abs); err == nil && fi.Mode().IsRegular() {
				files = append(files, abs)
			}
		}
	default:
		files = collectFiles(root, defaultGlobs)
	}

	interactive := *interactiveFl || (*prePush && stdinIsTTY())
	return scanFiles(root, files, minRank, *githubActions, interactive)
}

func main() {
	os.Exit(run(os.Args[1:]))
}
