//! Python-compatible `str.splitlines()` (no keepends).

/// Splits on the same boundaries as Python's `str.splitlines()`:
/// `\n`, `\r\n`, `\r`, `\v`, `\f`, `\x1c`-`\x1e`, `\x85`, `\u2028`, `\u2029`.
/// Empty input yields an empty vec, matching Python (`"".splitlines() == []`).
pub fn splitlines(s: &str) -> Vec<String> {
    if s.is_empty() {
        return Vec::new();
    }
    let mut lines = Vec::new();
    let mut cur = String::new();
    let mut ends_with_boundary = false;
    let mut chars = s.chars().peekable();
    while let Some(c) = chars.next() {
        match c {
            '\n' => {
                lines.push(std::mem::take(&mut cur));
                ends_with_boundary = true;
            }
            '\r' => {
                if chars.peek() == Some(&'\n') {
                    chars.next();
                }
                lines.push(std::mem::take(&mut cur));
                ends_with_boundary = true;
            }
            '\x0b' | '\x0c' | '\x1c' | '\x1d' | '\x1e' | '\u{85}' | '\u{2028}' | '\u{2029}' => {
                lines.push(std::mem::take(&mut cur));
                ends_with_boundary = true;
            }
            _ => {
                cur.push(c);
                ends_with_boundary = false;
            }
        }
    }
    if !ends_with_boundary {
        lines.push(cur);
    }
    lines
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn empty() {
        assert_eq!(splitlines(""), Vec::<String>::new());
    }

    #[test]
    fn no_trailing_newline() {
        assert_eq!(splitlines("abc"), vec!["abc"]);
    }

    #[test]
    fn lf_and_crlf() {
        assert_eq!(splitlines("a\nb\r\nc"), vec!["a", "b", "c"]);
    }

    #[test]
    fn bare_cr_splits() {
        assert_eq!(splitlines("a\rb"), vec!["a", "b"]);
    }

    #[test]
    fn consecutive_boundaries_yield_empty_lines() {
        assert_eq!(splitlines("a\n\nb"), vec!["a", "", "b"]);
        assert_eq!(splitlines("\n"), vec![""]);
    }

    #[test]
    fn trailing_boundary_yields_no_empty_line() {
        assert_eq!(splitlines("a\n"), vec!["a"]);
        assert_eq!(splitlines("a\nb\n"), vec!["a", "b"]);
        assert_eq!(splitlines("a\r\n"), vec!["a"]);
        assert_eq!(splitlines("a\r"), vec!["a"]);
        assert_eq!(splitlines("a\n\n"), vec!["a", ""]);
        assert_eq!(splitlines("\n\n"), vec!["", ""]);
    }

    #[test]
    fn crlf_is_single_boundary() {
        assert_eq!(splitlines("a\r\n\r\nb"), vec!["a", "", "b"]);
    }
}
