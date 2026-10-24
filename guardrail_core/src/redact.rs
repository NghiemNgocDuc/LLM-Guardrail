//! PII redaction port — `pii_redactor.py::PIIRedactor.redact` / `.restore`.
//!
//! Mirrors the Python algorithm: inspect each pattern's original candidates,
//! validate card checksums, replace the first remaining occurrence with a placeholder,
//! and record the placeholder → original mapping so the operation is reversible.

use regex::Regex;

pub struct Redaction {
    pub redacted_text: String,
    pub pii_count: usize,
    pub pii_types: Vec<String>,
    /// (placeholder, original) pairs in insertion order — the Python `mapping`
    /// dict preserves the same order.
    pub mapping: Vec<(String, String)>,
}

/// `patterns` entries are (name, regex, placeholder_template). A template's
/// `{n}` is replaced by the global per-scan counter, like Python `.format(n=...)`.
/// Compile failure is an error — the Python call site falls back to the
/// original implementation for that call.
pub fn redact(text: &str, patterns_in: &[(String, String, String)]) -> Result<Redaction, String> {
    let mut redacted = text.to_string();
    let mut mapping: Vec<(String, String)> = Vec::new();
    let mut pii_types: Vec<String> = Vec::new();
    let mut counter = 0usize;

    for (name, regex, placeholder) in patterns_in {
        let re = Regex::new(regex).map_err(|e| format!("invalid pii regex for '{name}': {e}"))?;
        // Inspect every original candidate: an invalid card must not hide a
        // later valid one, and generated placeholders must never be rescanned.
        for m in re.find_iter(text) {
            let original_value = m.as_str().to_string();
            if (name == "credit_card" && !crate::checks::luhn_valid(&original_value))
                || !redacted.contains(&original_value)
            {
                continue;
            }
            counter += 1;
            let ph = placeholder.replace("{n}", &counter.to_string());
            mapping.push((ph.clone(), original_value.clone()));
            if !pii_types.iter().any(|t| t == name) {
                pii_types.push(name.clone());
            }
            redacted = redacted.replacen(&original_value, &ph, 1);
        }
    }

    Ok(Redaction {
        redacted_text: redacted,
        pii_count: counter,
        pii_types,
        mapping,
    })
}

/// Reverse redaction: replace every placeholder with its original, in mapping
/// insertion order (same as the Python dict iteration).
pub fn restore(text: &str, mapping: &[(String, String)]) -> String {
    let mut out = text.to_string();
    for (ph, orig) in mapping {
        out = out.replace(ph.as_str(), orig.as_str());
    }
    out
}
