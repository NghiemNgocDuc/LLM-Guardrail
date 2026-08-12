package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
)

// Ported from guardrails/skill_overrides.py. Persisted + session allow lists.

const overridesFilename = ".cursor/skill-guard-overrides.json"

func findingKey(f SkillFinding) string {
	return fmt.Sprintf("%s:%d", f.ReasonCode, findingLine(f))
}

type SkillOverrides struct {
	sessionAllowKeys          map[string]struct{}
	alwaysAllowKeys           map[string]struct{}
	alwaysAllowReasonCodes    map[string]struct{}
}

type overridesJSON struct {
	SessionAllowKeys       []string `json:"session_allow_keys"`
	AlwaysAllowKeys        []string `json:"always_allow_keys"`
	AlwaysAllowReasonCodes []string `json:"always_allow_reason_codes"`
}

func emptyOverrides() *SkillOverrides {
	return &SkillOverrides{
		sessionAllowKeys:       make(map[string]struct{}),
		alwaysAllowKeys:        make(map[string]struct{}),
		alwaysAllowReasonCodes: make(map[string]struct{}),
	}
}

func overridesPath(root string) string {
	return filepath.Join(root, filepath.FromSlash(overridesFilename))
}

func loadOverrides(root string) *SkillOverrides {
	ov := emptyOverrides()
	data, err := os.ReadFile(overridesPath(root))
	if err != nil {
		return ov
	}
	var oj overridesJSON
	if err := json.Unmarshal(data, &oj); err != nil {
		return ov
	}
	for _, k := range oj.SessionAllowKeys {
		ov.sessionAllowKeys[k] = struct{}{}
	}
	for _, k := range oj.AlwaysAllowKeys {
		ov.alwaysAllowKeys[k] = struct{}{}
	}
	for _, c := range oj.AlwaysAllowReasonCodes {
		ov.alwaysAllowReasonCodes[c] = struct{}{}
	}
	return ov
}

func overridesToDict(ov *SkillOverrides) overridesJSON {
	oj := overridesJSON{
		SessionAllowKeys:       sortedKeys(ov.sessionAllowKeys),
		AlwaysAllowKeys:        sortedKeys(ov.alwaysAllowKeys),
		AlwaysAllowReasonCodes: sortedKeys(ov.alwaysAllowReasonCodes),
	}
	return oj
}

func sortedKeys(m map[string]struct{}) []string {
	out := make([]string, 0, len(m))
	for k := range m {
		out = append(out, k)
	}
	sort.Strings(out)
	return out
}

func saveOverrides(root string, ov *SkillOverrides) error {
	path := overridesPath(root)
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return err
	}
	var buf bytes.Buffer
	enc := json.NewEncoder(&buf)
	enc.SetEscapeHTML(false)
	enc.SetIndent("", "  ")
	if err := enc.Encode(overridesToDict(ov)); err != nil {
		return err
	}
	return os.WriteFile(path, buf.Bytes(), 0o644)
}

func (ov *SkillOverrides) isAllowed(f SkillFinding) bool {
	key := findingKey(f)
	if _, ok := ov.sessionAllowKeys[key]; ok {
		return true
	}
	if _, ok := ov.alwaysAllowKeys[key]; ok {
		return true
	}
	_, ok := ov.alwaysAllowReasonCodes[f.ReasonCode]
	return ok
}

func (ov *SkillOverrides) allowOnce(f SkillFinding) {
	ov.sessionAllowKeys[findingKey(f)] = struct{}{}
}

func (ov *SkillOverrides) allowAlways(f SkillFinding) {
	ov.alwaysAllowKeys[findingKey(f)] = struct{}{}
	ov.alwaysAllowReasonCodes[f.ReasonCode] = struct{}{}
}

type SkillScanDecision struct {
	Raw      SkillScanResult
	Blocking []SkillFinding
	Allowed  []SkillFinding
	Safe     bool
	Blocked  bool
}

func (d SkillScanDecision) RejectionSummary() string {
	if len(d.Blocking) == 0 {
		return ""
	}
	n := len(d.Blocking)
	kinds := make(map[string]struct{})
	for _, f := range d.Blocking {
		kinds[f.Category] = struct{}{}
	}
	sorted := sortedKeys(kinds)
	return fmt.Sprintf(
		"Agent skill blocked: %d issue(s) — %s. Skill Guard paused — reply in Cursor chat: Run once, Always allow, Reject, or your message.",
		n, joinComma(sorted),
	)
}

func joinComma(items []string) string {
	out := ""
	for i, s := range items {
		if i > 0 {
			out += ", "
		}
		out += s
	}
	return out
}

func applyOverrides(result SkillScanResult, ov *SkillOverrides) SkillScanDecision {
	var blocking, allowed []SkillFinding
	for _, f := range result.Findings {
		if ov.isAllowed(f) {
			allowed = append(allowed, f)
		} else {
			blocking = append(blocking, f)
		}
	}
	safe := len(blocking) == 0
	return SkillScanDecision{
		Raw:      result,
		Blocking: blocking,
		Allowed:  allowed,
		Safe:     safe,
		Blocked:  !safe,
	}
}
