package main

import (
	"fmt"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"unicode/utf8"
)

// Ported verbatim from guardrails/dangerous_commands.py and guardrails/skill.py.
// (reason_code, check_name, regex, risk_score)

const snippetMax = 72

type pattern struct {
	reasonCode string
	check      string
	re         *regexp.Regexp
	score      float64
}

var dangerousCommandPatterns = []pattern{
	{"rm_rf_destructive", "Destructive recursive delete", regexp.MustCompile(`(?i)\brm\s+(-[a-zA-Z]+\s+)*-rf\b[^\n]*(\s+/\s*|\s+/\*|\s+~|--no-preserve-root|\s+/(?:etc|usr|var|bin|sbin|boot|System32)(?:\s|$))`), 0.98},
	{"drop_sql", "SQL DROP statement", regexp.MustCompile(`(?i)\bDROP\s+(TABLE|DATABASE|SCHEMA)\b`), 0.95},
	{"truncate_sql", "SQL TRUNCATE statement", regexp.MustCompile(`(?i)\bTRUNCATE\s+TABLE\b`), 0.9},
	{"delete_sql_unbounded", "SQL DELETE without WHERE", regexp.MustCompile("(?i)\\bDELETE\\s+FROM\\s+[`'\"]?\\w+[`'\"]?\\s*;"), 0.85},
	{"disk_wipe", "Disk overwrite / format", regexp.MustCompile(`(?i)\bdd\s+if=[^\s]+\s+of=/dev/|\bmkfs\.|format\s+[a-z]:`), 0.98},
	{"curl_pipe_shell", "Remote script piped to shell", regexp.MustCompile(`(?i)\b(curl|wget)\s+[^\n|]+\|\s*(ba)?sh\b`), 0.95},
	{"powershell_iex", "PowerShell invoke-expression", regexp.MustCompile(`(?i)\bInvoke-Expression\b|\biex\s*\(`), 0.92},
	{"powershell_rm_force", "PowerShell recursive force delete", regexp.MustCompile(`(?i)Remove-Item\s+[^\n]*-Recurse[^\n]*-Force`), 0.9},
	{"windows_del_force", "Windows forced delete", regexp.MustCompile(`(?i)\bdel\s+/[fq]s?\b|Format-Volume`), 0.9},
	{"chmod_world_writable_root", "World-writable permissions on root", regexp.MustCompile(`(?i)\bchmod\s+(-R\s+)?777\s+/`), 0.88},
	{"git_destructive", "Destructive git operation", regexp.MustCompile(`(?i)\bgit\s+push\s+[^\n]*--force|\bgit\s+reset\s+--hard|\bgit\s+clean\s+-[a-z]*f`), 0.85},
	{"system_shutdown", "System shutdown or reboot", regexp.MustCompile(`(?i)\b(shutdown|reboot|poweroff|halt)\s+(-[hfr]|/s|now)\b`), 0.88},
	{"fork_bomb", "Fork bomb pattern", regexp.MustCompile(`:\(\)\s*\{\s*:\|:`), 0.99},
	{"eval_exec_injection", "Dynamic eval/exec of shell", regexp.MustCompile("(?i)\\beval\\s+[`$]|\\bexec\\s*\\(\\s*[`$]"), 0.9},
	{"iptables_flush", "Flush firewall rules", regexp.MustCompile(`(?i)\biptables\s+-F\b`), 0.85},
	{"kill_all", "Kill all processes", regexp.MustCompile(`(?i)\bkill(all)?\s+-9\s+(-1|0)\b|\bpkill\s+-9\b`), 0.9},
}

var skillPatterns = []pattern{
	{"gateway_api_key", "Gateway API key", regexp.MustCompile(`\bgrg_[A-Za-z0-9_-]{20,}\b`), 0.95},
	{"database_url", "Database connection URL", regexp.MustCompile(`\b(?:postgres(?:ql)?|mysql|mongodb|redis)(?:\+[a-z0-9]+)?://[^\s"']+`), 0.92},
	{"credential_assignment", "Hard-coded credential", regexp.MustCompile(`(?i)(?:api[_-]?key|secret|password|token|auth)\s*[:=]\s*['"]?[^\s'",#]{8,}`), 0.88},
	{"bearer_token", "Bearer token", regexp.MustCompile(`(?i)Bearer\s+[A-Za-z0-9._\-]{20,}`), 0.9},
	{"env_assignment", ".env-style secret", regexp.MustCompile(`(?im)^(?:[A-Z][A-Z0-9_]*)\s*=\s*[^\s#]+`), 0.75},
	{"private_ip", "Private network address", regexp.MustCompile(`\b(?:10\.\d{1,3}\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3}|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})\b`), 0.55},
	{"internal_path", "Internal filesystem path", regexp.MustCompile(`(?:/[a-z0-9._-]+){2,}(?:\.ssh|/etc/|/var/|/home/)|(?:[A-Z]:\\Users\\)`), 0.5},
}

// secretLinePatterns mirrors the Python dict iteration order (insertion order).
// Prefixes are split to avoid triggering CI secret scanners on pattern strings.
var secretLinePatterns = []struct {
	code string
	re   *regexp.Regexp
}{
	{"groq_api_key", regexp.MustCompile(`\b` + "gsk" + `_[A-Za-z0-9_-]{20,}\b`)},
	{"openai_api_key", regexp.MustCompile(`\bsk` + `-[A-Za-z0-9_-]{20,}\b`)},
	{"github_token", regexp.MustCompile(`\b(?:` + "ghp" + `_|` + "github" + `_pat_)[A-Za-z0-9_]{20,}\b`)},
	{"aws_access_key", regexp.MustCompile(`\bAKIA[0-9A-Z]{16}\b`)},
	{"private_key", regexp.MustCompile(`-----BEGIN (?:RSA|OPENSSH|EC|DSA|PRIVATE) KEY-----`)},
}

var piiPatterns = []struct {
	name string
	re   *regexp.Regexp
}{
	{"credit_card", regexp.MustCompile(`\b(?:\d[ -]?){13,16}\b`)},
	{"ssn", regexp.MustCompile(`\b\d{3}-\d{2}-\d{4}\b`)},
	{"email", regexp.MustCompile(`[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}`)},
}

type SkillFinding struct {
	Category   string
	Severity   string
	Check      string
	Reason     string
	ReasonCode string
	LineNumber *int
	Snippet    string
	RiskScore  float64
}

type SkillScanResult struct {
	Safe      bool
	RiskScore float64
	Findings  []SkillFinding
	LineCount int
	CharCount int
}

func severity(score float64) string {
	if score >= 0.9 {
		return "critical"
	}
	if score >= 0.75 {
		return "high"
	}
	return "medium"
}

func redactSnippet(text string) string {
	s := strings.Join(strings.Fields(strings.TrimSpace(text)), " ")
	rs := []rune(s)
	if len(rs) <= snippetMax {
		return s
	}
	return string(rs[:snippetMax-3]) + "..."
}

func truncateRunes(s string, n int) string {
	rs := []rune(s)
	if len(rs) <= n {
		return s
	}
	return string(rs[:n])
}

// pythonSplitlines mirrors str.splitlines() semantics: splits on \r\n, \r, \n,
// \v, \f, \x1c-\x1e, \x85, \u2028, \u2029; a trailing boundary produces no
// trailing empty line.
func pythonSplitlines(s string) []string {
	var lines []string
	cur := make([]rune, 0, 64)
	sawBoundary := false
	i := 0
	n := len(s)
	for i < n {
		r, size := utf8.DecodeRuneInString(s[i:])
		switch r {
		case '\n', '\v', '\f', '\x1c', '\x1d', '\x1e', '\x85', '\u2028', '\u2029':
			sawBoundary = true
			lines = append(lines, string(cur))
			cur = cur[:0]
		case '\r':
			sawBoundary = true
			lines = append(lines, string(cur))
			cur = cur[:0]
			if i+size < n {
				if nr, _ := utf8.DecodeRuneInString(s[i+size:]); nr == '\n' {
					i += size
				}
			}
		default:
			cur = append(cur, r)
		}
		i += size
	}
	if !sawBoundary || len(cur) > 0 {
		lines = append(lines, string(cur))
	}
	return lines
}

type SkillGuardrail struct{}

func (g *SkillGuardrail) Scan(content string) SkillScanResult {
	if content == "" || strings.TrimSpace(content) == "" {
		return SkillScanResult{Safe: true, RiskScore: 0.0, LineCount: 0, CharCount: 0}
	}

	lines := pythonSplitlines(content)
	findings := make([]SkillFinding, 0, 8)
	seen := make(map[string]struct{})

	add := func(category, check, reason, reasonCode string, score float64, lineNumber *int, rawLine string) {
		key := fmt.Sprintf("%s|%d|%s", reasonCode, findingLineRef(lineNumber), truncateRunes(rawLine, 40))
		if _, ok := seen[key]; ok {
			return
		}
		seen[key] = struct{}{}
		findings = append(findings, SkillFinding{
			Category:   category,
			Severity:   severity(score),
			Check:      check,
			Reason:     reason,
			ReasonCode: reasonCode,
			LineNumber: lineNumber,
			Snippet:    redactSnippet(rawLine),
			RiskScore:  score,
		})
	}

	for idx, line := range lines {
		lineNumber := idx + 1
		for _, p := range dangerousCommandPatterns {
			if p.re.MatchString(line) {
				add("destructive_command", p.check, p.check+" on line "+strconv.Itoa(lineNumber), p.reasonCode, p.score, intPtr(lineNumber), line)
			}
		}
		for _, p := range skillPatterns {
			if p.re.MatchString(line) {
				add("agent_context", p.check, p.check+" on line "+strconv.Itoa(lineNumber), p.reasonCode, p.score, intPtr(lineNumber), line)
			}
		}
		for _, p := range secretLinePatterns {
			if p.re.MatchString(line) {
				add("secret", "Secret Detection", "Secret detected: "+p.code+" (line "+strconv.Itoa(lineNumber)+")", "secret_detected", 0.95, intPtr(lineNumber), line)
			}
		}
		for _, p := range piiPatterns {
			if p.re.MatchString(line) {
				add("pii", "PII Detection", "PII detected: "+p.name+" (line "+strconv.Itoa(lineNumber)+")", "pii_detected", 0.85, intPtr(lineNumber), line)
			}
		}
	}

	risk := 0.0
	for _, f := range findings {
		if f.RiskScore > risk {
			risk = f.RiskScore
		}
	}

	sort.SliceStable(findings, func(a, b int) bool {
		if findings[a].RiskScore != findings[b].RiskScore {
			return findings[a].RiskScore > findings[b].RiskScore
		}
		return findingLine(findings[a]) < findingLine(findings[b])
	})

	return SkillScanResult{
		Safe:      len(findings) == 0,
		RiskScore: risk,
		Findings:  findings,
		LineCount: len(lines),
		CharCount: utf8.RuneCountInString(content),
	}
}

func intPtr(n int) *int { return &n }

func findingLine(f SkillFinding) int {
	if f.LineNumber != nil {
		return *f.LineNumber
	}
	return 0
}

func findingLineRef(p *int) int {
	if p != nil {
		return *p
	}
	return 0
}
