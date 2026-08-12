//! Input-check ports: `input.py::_check_secrets`, `_check_pii`,
//! `_check_injection`, `_check_jailbreak`.

use regex::Regex;

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
        if re.is_match(prompt) {
            return Ok(Some(name.clone()));
        }
    }
    Ok(None)
}

/// Lowercase substring matching, as `input.py::_check_injection`. Built-ins
/// are checked in source order first, then policy extras (Python iterates a
/// set, so when several keywords match at once the reported keyword is
/// arbitrary there — we choose a deterministic order instead; single-match
/// inputs report identically).
pub fn check_injection(prompt: &str, extras: &[String]) -> Option<String> {
    let lower = prompt.to_lowercase();
    for kw in patterns::INJECTION_BUILT_INS
        .iter()
        .map(|kw| *kw)
        .chain(extras.iter().map(String::as_str))
    {
        let needle = kw.to_lowercase();
        if lower.contains(&needle) {
            return Some(needle);
        }
    }
    None
}

/// Lowercase substring matching, as `input.py::_check_jailbreak`.
pub fn check_jailbreak(prompt: &str, extras: &[String]) -> Option<String> {
    let lower = prompt.to_lowercase();
    for kw in patterns::JAILBREAK_BUILT_INS
        .iter()
        .map(|kw| *kw)
        .chain(extras.iter().map(String::as_str))
    {
        let needle = kw.to_lowercase();
        if lower.contains(&needle) {
            return Some(needle);
        }
    }
    None
}
