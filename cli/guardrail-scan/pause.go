package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
)

// Ported from guardrails/skill_agent_packet.py: pause file + chat control prompt.

const pauseFile = ".cursor/skill-guard-pause.json"

type pauseEntry struct {
	src     string
	finding SkillFinding
}

// Field order matches finding_to_dict() insertion order so the JSON matches
// Python json.dumps byte-for-byte (modulo ensure_ascii vs raw UTF-8).
type findingOut struct {
	FindingKey string `json:"finding_key"`
	ReasonCode string `json:"reason_code"`
	Severity   string `json:"severity"`
	Check      string `json:"check"`
	LineNumber *int   `json:"line_number"`
	Snippet    string `json:"snippet"`
}

type pausePayload struct {
	AgentStatus   string       `json:"agent_status"`
	ControlLayer  string       `json:"control_layer"`
	Source        string       `json:"source"`
	BlockingCount int          `json:"blocking_count"`
	Findings      []findingOut `json:"findings"`
	ChatPrompt    string       `json:"chat_prompt"`
}

func findingToDict(f SkillFinding) findingOut {
	return findingOut{
		FindingKey: findingKey(f),
		ReasonCode: f.ReasonCode,
		Severity:   f.Severity,
		Check:      f.Check,
		LineNumber: f.LineNumber,
		Snippet:    f.Snippet,
	}
}

func formatChatControlPrompt(findings []findingOut, source string) string {
	var lines []string
	lines = append(lines,
		"## Skill Guard — paused (control layer in **this chat**)",
		"",
		"Do **not** send the user to the web dashboard. Wait for their reply here.",
		"",
		"**Reply with one of:**",
		"1. **Run once** — allow flagged content for this task only",
		"2. **Always allow** — save override; never block these rules again",
		"3. **Reject** — do not use flagged content; help fix the skill",
		"4. **Your own message** — custom instruction (same as option 4 / send to agent)",
		"",
	)
	if source != "" {
		lines = append(lines, "Source: `"+source+"`", "")
	}
	lines = append(lines, "### Flagged items")
	for _, f := range findings {
		sev := f.Severity
		if sev == "" {
			sev = "?"
		}
		code := f.ReasonCode
		if code == "" {
			code = "?"
		}
		loc := "file"
		if f.LineNumber != nil {
			loc = fmt.Sprintf("line %d", *f.LineNumber)
		}
		lines = append(lines, fmt.Sprintf("- **[%s]** `%s` (%s): `%s`", sev, code, loc, f.Snippet))
	}
	lines = append(lines,
		"",
		"After they reply, run `python scripts/skill_guard_decision.py <action> ...` and continue.",
	)
	return strings.Join(lines, "\n")
}

func writeChatPause(root string, entries []pauseEntry) {
	findings := make([]findingOut, 0, len(entries))
	sourceSet := make(map[string]struct{})
	for _, e := range entries {
		findings = append(findings, findingToDict(e.finding))
		sourceSet[e.src] = struct{}{}
	}
	sources := sortedKeys(sourceSet)
	source := joinComma(sources[:min(len(sources), 3)])
	if len(sources) > 3 {
		source += fmt.Sprintf(" (+%d more)", len(sources)-3)
	}

	payload := pausePayload{
		AgentStatus:   "paused",
		ControlLayer:  "cursor_chat",
		Source:        source,
		BlockingCount: len(findings),
		Findings:      findings,
		ChatPrompt:    formatChatControlPrompt(findings, source),
	}

	path := filepath.Join(root, filepath.FromSlash(pauseFile))
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		fmt.Fprintf(os.Stderr, "Skill Guard: cannot create %s: %v\n", filepath.Dir(path), err)
		return
	}
	var buf bytes.Buffer
	enc := json.NewEncoder(&buf)
	enc.SetEscapeHTML(false)
	enc.SetIndent("", "  ")
	if err := enc.Encode(payload); err != nil {
		fmt.Fprintf(os.Stderr, "Skill Guard: cannot write pause file: %v\n", err)
		return
	}
	if err := os.WriteFile(path, buf.Bytes(), 0o644); err != nil {
		fmt.Fprintf(os.Stderr, "Skill Guard: cannot write %s: %v\n", path, err)
		return
	}
	fmt.Println("\n" + payload.ChatPrompt)
	fmt.Printf("\n↳ Wrote %s — user must reply in **Cursor chat** (not the web dashboard).\n\n", path)
}

func min(a, b int) int {
	if a < b {
		return a
	}
	return b
}
