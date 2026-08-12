//! Agent-skill scan port — `skill.py::SkillGuardrail.scan`.
//!
//! Same line-by-line loop, same pattern order, same dedup key
//! `(reason_code, line_number, snippet[:40])`, same stable sort by
//! `(-risk_score, line_number)`, same severity thresholds.

use std::collections::HashSet;

use crate::patterns;
use crate::splitlines::splitlines;

pub struct SkillFinding {
    pub category: String,
    pub check: String,
    pub reason: String,
    pub reason_code: String,
    pub severity: String,
    pub line_number: Option<usize>,
    pub snippet: String,
    pub risk_score: f64,
}

pub struct SkillScan {
    pub findings: Vec<SkillFinding>,
    pub risk_score: f64,
    pub line_count: usize,
    pub char_count: usize,
}

/// `None` when content is empty or whitespace-only (matches the Python early
/// return of `SkillScanResult(safe=True, risk_score=0.0, line_count=0, char_count=0)`).
pub fn scan_skill(content: &str) -> Option<SkillScan> {
    if content.trim().is_empty() {
        return None;
    }

    let lines = splitlines(content);
    let mut findings: Vec<SkillFinding> = Vec::new();
    let mut seen: HashSet<(String, Option<usize>, String)> = HashSet::new();

    for (idx, line) in lines.iter().enumerate() {
        let line_number = Some(idx + 1);

        for (code, check, re, score) in patterns::DANGEROUS_RE.iter() {
            if re.is_match(line) {
                add(
                    &mut findings,
                    &mut seen,
                    "destructive_command",
                    check,
                    &format!("{check} on line {}", line_number.unwrap_or(0)),
                    code,
                    *score,
                    line_number,
                    line,
                );
            }
        }

        for (code, check, re, score) in patterns::SKILL_RE.iter() {
            if re.is_match(line) {
                add(
                    &mut findings,
                    &mut seen,
                    "agent_context",
                    check,
                    &format!("{check} on line {}", line_number.unwrap_or(0)),
                    code,
                    *score,
                    line_number,
                    line,
                );
            }
        }

        for (code, re) in patterns::SECRET_LINE_RE.iter() {
            if re.is_match(line) {
                add(
                    &mut findings,
                    &mut seen,
                    "secret",
                    "Secret Detection",
                    // Python `skill.py::add` always reports reason_code
                    // "secret_detected" for the secret family, keeping the
                    // specific pattern name only in the human-readable reason.
                    &format!("Secret detected: {code} (line {})", line_number.unwrap_or(0)),
                    "secret_detected",
                    0.95,
                    line_number,
                    line,
                );
            }
        }

        for (name, re) in patterns::SKILL_PII_RE.iter() {
            if re.is_match(line) {
                add(
                    &mut findings,
                    &mut seen,
                    "pii",
                    "PII Detection",
                    &format!("PII detected: {name} (line {})", line_number.unwrap_or(0)),
                    "pii_detected",
                    0.85,
                    line_number,
                    line,
                );
            }
        }
    }

    // Python: sorted(findings, key=lambda f: (-f.risk_score, f.line_number or 0))
    // — stable, so ties keep insertion order.
    findings.sort_by(|a, b| {
        b.risk_score
            .total_cmp(&a.risk_score)
            .then(a.line_number.unwrap_or(0).cmp(&b.line_number.unwrap_or(0)))
    });

    let risk_score = findings
        .iter()
        .map(|f| f.risk_score)
        .fold(0.0f64, f64::max);

    Some(SkillScan {
        findings,
        risk_score,
        line_count: lines.len(),
        char_count: content.chars().count(),
    })
}

fn add(
    findings: &mut Vec<SkillFinding>,
    seen: &mut HashSet<(String, Option<usize>, String)>,
    category: &str,
    check: &str,
    reason: &str,
    reason_code: &str,
    risk_score: f64,
    line_number: Option<usize>,
    line: &str,
) {
    let key = (reason_code.to_string(), line_number, line.chars().take(40).collect());
    if !seen.insert(key) {
        return;
    }
    let severity = if risk_score >= 0.9 {
        "critical"
    } else if risk_score >= 0.75 {
        "high"
    } else {
        "medium"
    };
    findings.push(SkillFinding {
        category: category.to_string(),
        check: check.to_string(),
        reason: reason.to_string(),
        reason_code: reason_code.to_string(),
        severity: severity.to_string(),
        line_number,
        snippet: line.to_string(),
        risk_score,
    });
}

/// `skill.py::_redact_snippet` — collapse whitespace, truncate at 72 chars.
pub fn redact_snippet(text: &str) -> String {
    let joined: Vec<&str> = text.split_whitespace().collect();
    let joined = joined.join(" ");
    if joined.chars().count() <= 72 {
        joined
    } else {
        joined.chars().take(69).collect::<String>() + "..."
    }
}
