//! Input-check ports: `input.py::_check_secrets`, `_check_pii`,
//! `_check_injection`, `_check_jailbreak`.

use regex::Regex;
use std::sync::LazyLock;

use crate::patterns;

/// First-matching secret pattern name, or `None`. Same pattern order and
/// first-match-wins semantics as `input.py::_check_secrets`.
pub fn check_secret(prompt: &str) -> Option<String> {
    for (name, re) in patterns::SECRET_RE.iter() {
        if re.is_match(prompt) {
            return Some(name.clone());
        }
    }
    None
}

/// Policy-driven PII regexes (org-defined, from the DB policy). Returns the
/// first pattern name that matches, or `None`. Compile failure (e.g. a Python
/// lookaround the `regex` crate does not support) is an error — the Python
/// call site falls back to the original implementation.
pub fn check_pii(prompt: &str, patterns_in: &[(String, String)]) -> Result<Option<String>, String> {
    for (name, regex) in patterns_in {
        let re = Regex::new(regex).map_err(|e| format!("invalid pii regex for '{name}': {e}"))?;
        if re.find_iter(prompt).any(|m| name != "credit_card" || luhn_valid(m.as_str())) {
            return Ok(Some(name.clone()));
        }
    }
    Ok(None)
}

pub(crate) fn luhn_valid(value: &str) -> bool {
    let digits: Vec<u32> = value.chars().filter_map(|c| c.to_digit(10)).collect();
    if !(13..=19).contains(&digits.len()) {
        return false;
    }
    let total: u32 = digits.iter().rev().enumerate().map(|(index, &digit)| {
        let doubled = if index % 2 == 1 { digit * 2 } else { digit };
        if doubled > 9 { doubled - 9 } else { doubled }
    }).sum();
    total % 10 == 0
}

static CLAUSES: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"[.!?;]\s+|\n+").unwrap());
static MODEL_TARGET: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"\b(?:you|your|yourself|assistant|chatbot|this chat|(?:ai|language) model)\b").unwrap());
static ACTIVATION: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"\b(?:enable|activate|enter|switch|turn on|run in|use|operate|now|enabled|activated)\b").unwrap());
static OVERRIDE: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"\b(?:ignore|disregard|bypass|disable|override|remove|suspend|forget|drop|no longer|without)\b.{0,80}\b(?:instructions?|rules?|restrictions?|safety|safeguards?|guardrails?|polic(?:y|ies)|filters?|ethical|system prompt|censorship)\b").unwrap());
static DIRECT_OVERRIDE: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"\b(?:ignore|disregard|bypass|disable|override)\b.{0,80}\b(?:instructions?|rules?|restrictions?|safety|safeguards?|guardrails?|polic(?:y|ies)|filters?|ethical|system prompt|censorship)\b").unwrap());
static MODE_COMMAND: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"^(?:please\s+)?(?:enable|activate|enter|switch\s+(?:to|into)|turn\s+on|run\s+in|use|operate\s+in)\s+(?:the\s+)?").unwrap());
static EXTERNAL_MODE_TARGET: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"^(?:on|in|for)\s+(?:(?:my|your|the|a|an|our|this|that)\s+)?(?:android|ios|iphone|ipad|windows|macos|linux|wordpress|drupal|shopify|chrome|chromium|firefox|safari|edge|(?:web\s+)?browser|phone|device|emulator|simulator|website|web\s+site|server|router|database|(?:video\s+)?game)\b").unwrap());

fn word_char(c: char) -> bool {
    c.is_alphanumeric() || c == '_'
}

fn keyword_positions<'a>(text: &'a str, keyword: &'a str) -> impl Iterator<Item = (usize, usize)> + 'a {
    text.match_indices(keyword).filter_map(move |(start, matched)| {
        let end = start + matched.len();
        let left = !keyword.chars().next().is_some_and(word_char)
            || text[..start].chars().next_back().map_or(true, |c| !word_char(c));
        let right = !keyword.chars().next_back().is_some_and(word_char)
            || text[end..].chars().next().map_or(true, |c| !word_char(c));
        (left && right).then_some((start, end))
    })
}

fn builtin_matches(lower: &str, keyword: &str) -> bool {
    let mode = matches!(keyword, "admin override" | "debug mode enabled" | "maintenance mode" | "sudo mode" | "developer mode" | "evil mode" | "harm mode" | "no filter mode" | "opposite mode" | "god mode");
    let task = matches!(keyword, "new instructions:" | "your new task is" | "your new instructions are" | "you are no longer");
    if !mode && !task {
        return keyword_positions(lower, keyword).next().is_some();
    }
    if mode && ACTIVATION.is_match(lower) && DIRECT_OVERRIDE.is_match(lower) && keyword_positions(lower, keyword).next().is_some() {
        return true;
    }
    for clause in CLAUSES.split(lower) {
        for (start, end) in keyword_positions(clause, keyword) {
            if task {
                if OVERRIDE.is_match(clause) {
                    return true;
                }
                continue;
            }
            let suffix = clause[end..].trim_start();
            // Only a recognized product target exempts a normal mode request.
            // Arbitrary suffixes (e.g. "for unrestricted replies") do not.
            if EXTERNAL_MODE_TARGET.is_match(suffix) {
                continue;
            }
            if (MODEL_TARGET.is_match(clause) && ACTIVATION.is_match(clause))
                || MODE_COMMAND.find(clause).is_some_and(|m| m.end() == start)
            {
                return true;
            }
        }
    }
    false
}

/// Bounded phrases with contextual built-ins; explicit policy extras remain authoritative.
fn find_keyword(prompt: &str, builtins: &[&str], extras: &[String]) -> Option<String> {
    let lower = prompt.to_lowercase();
    for keyword in builtins {
        if builtin_matches(&lower, keyword) {
            return Some((*keyword).to_string());
        }
    }
    for extra in extras {
        let keyword = extra.trim().to_lowercase();
        if !keyword.is_empty() && keyword_positions(&lower, &keyword).next().is_some() {
            return Some(keyword);
        }
    }
    None
}

/// Mirrors `input.py::_check_injection`, including narrow mode/task context.
pub fn check_injection(prompt: &str, extras: &[String]) -> Option<String> {
    find_keyword(prompt, patterns::INJECTION_BUILT_INS, extras)
}

/// Mirrors `input.py::_check_jailbreak`.
pub fn check_jailbreak(prompt: &str, extras: &[String]) -> Option<String> {
    find_keyword(prompt, patterns::JAILBREAK_BUILT_INS, extras)
}
