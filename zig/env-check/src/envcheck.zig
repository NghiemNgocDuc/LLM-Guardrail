const std = @import("std");

// env-check: validate an .env file against the repo's .env.example
// conventions.
//
// Conventions enforced (all derived from how .env.example is actually
// written in this repo):
//
//   * one `KEY=value` per line; `#` starts a comment only at line start
//     (the example never uses inline comments, and values like `\n`
//     sequences inside CLERK_JWT_KEY must not be truncated)
//   * key = [A-Za-z_][A-Za-z0-9_]* (case-sensitive)
//   * an EMPTY value in .env.example means "optional / set in real env"
//   * a NON-EMPTY value in .env.example means the key has a working
//     default; omitting it from .env is a warning
//   * `${...}` belongs to docker-compose interpolation, not .env files
//   * placeholder text (`your_*`, `changeme`, `<...>`, `XXXX`) and short
//     SECRET/PASSWORD/TOKEN values are warnings
//
// Exit status: 0 = clean, 1 = errors, 2 = warnings only, 64 = bad usage,
// 74 = unreadable file.

pub const Severity = enum { err, warning };

pub const IssueKind = enum {
    malformed_line,
    empty_key,
    invalid_key,
    duplicate_key,
    unterminated_quote,
    unknown_key,
    interpolation,
    placeholder_value,
    weak_secret,
    missing_key,
    required_missing,
};

pub const Source = enum { env, schema };

pub const Issue = struct {
    source: Source,
    line: usize, // 1-based; 0 = file-level
    severity: Severity,
    kind: IssueKind,
    key: ?[]const u8 = null, // borrowed from the input text
};

pub const Entry = struct {
    line: usize,
    key: []const u8,
    value: []const u8, // trimmed, quotes stripped
};

pub const CheckOptions = struct {
    required: []const []const u8 = &.{},
    minimum_secret_len: usize = 8,
};

pub const CheckResult = struct {
    issues: []Issue,
    error_count: usize,
    warning_count: usize,
    entries: []Entry, // env entries
};

fn severityOf(kind: IssueKind) Severity {
    return switch (kind) {
        .malformed_line, .empty_key, .invalid_key, .duplicate_key, .unterminated_quote, .unknown_key, .interpolation, .required_missing => .err,
        .placeholder_value, .weak_secret, .missing_key => .warning,
    };
}

const Scan = struct {
    entries: std.ArrayList(Entry) = .empty,
    issues: std.ArrayList(Issue) = .empty,
};

fn scan(alloc: std.mem.Allocator, source: Source, text: []const u8) !Scan {
    var scan_res = Scan{};
    errdefer scan_res.entries.deinit(alloc);
    errdefer scan_res.issues.deinit(alloc);

    var seen: std.ArrayList([]const u8) = .empty;
    defer seen.deinit(alloc);

    var it = std.mem.splitScalar(u8, text, '\n');
    var lineno: usize = 0;
    while (it.next()) |raw_line| {
        lineno += 1;
        const line = std.mem.trim(u8, raw_line, " \t\r");
        if (line.len == 0) continue;
        if (line[0] == '#') continue;

        const eq = std.mem.indexOfScalar(u8, line, '=');
        const key_part = if (eq) |e| line[0..e] else line;
        const key = std.mem.trim(u8, key_part, " \t");

        if (eq == null) {
            try scan_res.issues.append(alloc, .{
                .source = source,
                .line = lineno,
                .severity = .err,
                .kind = .malformed_line,
                .key = key,
            });
            continue;
        }
        if (key.len == 0) {
            try scan_res.issues.append(alloc, .{
                .source = source,
                .line = lineno,
                .severity = .err,
                .kind = .empty_key,
                .key = key,
            });
            continue;
        }
        if (!validKey(key)) {
            try scan_res.issues.append(alloc, .{
                .source = source,
                .line = lineno,
                .severity = .err,
                .kind = .invalid_key,
                .key = key,
            });
            continue;
        }

        var value = std.mem.trim(u8, line[eq.? + 1 ..], " \t\r");
        if (value.len >= 2 and (value[0] == '"' or value[0] == '\'')) {
            const q = value[0];
            if (value[value.len - 1] != q) {
                try scan_res.issues.append(alloc, .{
                    .source = source,
                    .line = lineno,
                    .severity = .err,
                    .kind = .unterminated_quote,
                    .key = key,
                });
                continue;
            }
            value = value[1 .. value.len - 1];
        }

        for (seen.items) |k| {
            if (std.mem.eql(u8, k, key)) {
                try scan_res.issues.append(alloc, .{
                    .source = source,
                    .line = lineno,
                    .severity = .err,
                    .kind = .duplicate_key,
                    .key = key,
                });
                break;
            }
        }
        try seen.append(alloc, key);

        try scan_res.entries.append(alloc, .{ .line = lineno, .key = key, .value = value });
    }
    return scan_res;
}

fn validKey(key: []const u8) bool {
    if (key.len == 0) return false;
    const c = key[0];
    if (!std.ascii.isAlphabetic(c) and c != '_') return false;
    for (key[1..]) |ch| {
        if (!std.ascii.isAlphanumeric(ch) and ch != '_') return false;
    }
    return true;
}

fn isSecretKey(key: []const u8) bool {
    return std.mem.indexOf(u8, key, "SECRET") != null or
        std.mem.indexOf(u8, key, "PASSWORD") != null or
        std.mem.indexOf(u8, key, "TOKEN") != null;
}

fn isAllDigits(value: []const u8) bool {
    for (value) |ch| {
        if (!std.ascii.isDigit(ch)) return false;
    }
    return true;
}

fn isPlaceholder(value: []const u8) bool {
    if (std.mem.indexOf(u8, value, "your_") != null) return true;
    if (std.mem.indexOf(u8, value, "your-") != null) return true;
    if (std.mem.indexOf(u8, value, "changeme") != null) return true;
    if (std.mem.indexOf(u8, value, "replace_me") != null) return true;
    if (value.len >= 2 and value[0] == '<' and value[value.len - 1] == '>') return true;
    if (std.mem.indexOf(u8, value, "XXXX") != null) return true;
    return false;
}

pub fn check(
    alloc: std.mem.Allocator,
    env_text: []const u8,
    schema_text: []const u8,
    options: CheckOptions,
) !CheckResult {
    var env_scan = try scan(alloc, .env, env_text);
    defer env_scan.entries.deinit(alloc);
    defer env_scan.issues.deinit(alloc);
    var schema_scan = try scan(alloc, .schema, schema_text);
    defer schema_scan.entries.deinit(alloc);
    defer schema_scan.issues.deinit(alloc);

    var issues: std.ArrayList(Issue) = .empty;
    errdefer issues.deinit(alloc);
    try issues.appendSlice(alloc, schema_scan.issues.items);
    try issues.appendSlice(alloc, env_scan.issues.items);

    // env entry present?
    const hasEnv = struct {
        entries: []const Entry,
        fn f(has: *const @This(), key: []const u8) bool {
            for (has.entries) |e| {
                if (std.mem.eql(u8, e.key, key)) return true;
            }
            return false;
        }
    }{ .entries = env_scan.entries.items };

    // unknown keys + value conventions
    for (env_scan.entries.items) |entry| {
        const in_schema = for (schema_scan.entries.items) |s| {
            if (std.mem.eql(u8, s.key, entry.key)) break true;
        } else false;
        if (!in_schema) {
            try issues.append(alloc, .{
                .source = .env,
                .line = entry.line,
                .severity = .err,
                .kind = .unknown_key,
                .key = entry.key,
            });
            continue;
        }
        if (std.mem.indexOf(u8, entry.value, "${") != null) {
            try issues.append(alloc, .{
                .source = .env,
                .line = entry.line,
                .severity = .err,
                .kind = .interpolation,
                .key = entry.key,
            });
        }
        if (entry.value.len > 0 and isPlaceholder(entry.value)) {
            try issues.append(alloc, .{
                .source = .env,
                .line = entry.line,
                .severity = .warning,
                .kind = .placeholder_value,
                .key = entry.key,
            });
        }
        // numeric values are counters/expiries, not credentials
        if (entry.value.len > 0 and isSecretKey(entry.key) and entry.value.len < options.minimum_secret_len and !isAllDigits(entry.value)) {
            try issues.append(alloc, .{
                .source = .env,
                .line = entry.line,
                .severity = .warning,
                .kind = .weak_secret,
                .key = entry.key,
            });
        }
    }

    // missing keys: schema key with a non-empty default absent from env
    for (schema_scan.entries.items) |s| {
        if (s.value.len == 0) continue; // empty example value => optional
        if (!hasEnv.f(s.key)) {
            try issues.append(alloc, .{
                .source = .env,
                .line = 0,
                .severity = .warning,
                .kind = .missing_key,
                .key = s.key,
            });
        }
    }

    // explicitly required keys
    for (options.required) |key| {
        if (!hasEnv.f(key)) {
            try issues.append(alloc, .{
                .source = .env,
                .line = 0,
                .severity = .err,
                .kind = .required_missing,
                .key = key,
            });
        }
    }

    var error_count: usize = 0;
    var warning_count: usize = 0;
    for (issues.items) |i| {
        switch (i.severity) {
            .err => error_count += 1,
            .warning => warning_count += 1,
        }
    }
    return .{
        .issues = try issues.toOwnedSlice(alloc),
        .error_count = error_count,
        .warning_count = warning_count,
        .entries = try env_scan.entries.toOwnedSlice(alloc),
    };
}

pub fn messageOf(issue: Issue, buf: []u8) []const u8 {
    const sev = switch (issue.severity) {
        .err => "error",
        .warning => "warning",
    };
    const body = switch (issue.kind) {
        .malformed_line => "malformed line (expected KEY=value)",
        .empty_key => "empty key before '='",
        .invalid_key => "invalid key name (allowed: [A-Za-z_][A-Za-z0-9_]*)",
        .duplicate_key => "duplicate key",
        .unterminated_quote => "unterminated quote",
        .unknown_key => "unknown key (not in .env.example)",
        .interpolation => "value contains '${...}' (docker-compose interpolation, not .env)",
        .placeholder_value => "placeholder value left in",
        .weak_secret => "secret value is shorter than the 8-char floor",
        .missing_key => "missing key (has a non-empty default in .env.example)",
        .required_missing => "required key is missing (--required)",
    };
    if (issue.key) |k| {
        return std.fmt.bufPrint(buf, "{s}: {s} '{s}'", .{ sev, body, k }) catch body;
    }
    return std.fmt.bufPrint(buf, "{s}: {s}", .{ sev, body }) catch body;
}

test "clean env passes" {
    const env_text =
        \\APP_ENV=development
        \\DEBUG=true
        \\LOG_LEVEL=DEBUG
        \\POSTGRES_USER=guardrails
        \\POSTGRES_DB=guardrails
        \\SECRET_KEY=
        \\OPENAI_API_KEY=
        \\STRIPE_WEBHOOK_SECRET=whsec_abcdef0123456789
        \\OPA_URL=http://localhost:8181
    ;
    const schema_text =
        \\APP_ENV=production
        \\DEBUG=false
        \\LOG_LEVEL=INFO
        \\POSTGRES_USER=postgres
        \\POSTGRES_DB=guardrails
        \\SECRET_KEY=
        \\OPENAI_API_KEY=
        \\STRIPE_WEBHOOK_SECRET=
        \\OPA_URL=http://opa:8181
    ;
    const result = try check(std.testing.allocator, env_text, schema_text, .{});
    defer std.testing.allocator.free(result.issues);
    defer std.testing.allocator.free(result.entries);
    try std.testing.expectEqual(@as(usize, 0), result.error_count);
    try std.testing.expectEqual(@as(usize, 0), result.warning_count);
}

test "unknown key and missing default are reported" {
    const env_text = "APP_ENV=development\nFOO_BAR=1\n";
    const schema_text = "APP_ENV=production\nOPA_URL=http://opa:8181\n";
    const result = try check(std.testing.allocator, env_text, schema_text, .{});
    defer std.testing.allocator.free(result.issues);
    defer std.testing.allocator.free(result.entries);
    try std.testing.expectEqual(@as(usize, 1), result.error_count);
    try std.testing.expectEqual(@as(usize, 1), result.warning_count);
    var found_unknown = false;
    var found_missing = false;
    for (result.issues) |i| {
        if (i.kind == .unknown_key) found_unknown = true;
        if (i.kind == .missing_key) found_missing = true;
    }
    try std.testing.expect(found_unknown);
    try std.testing.expect(found_missing);
}

test "syntax errors are errors" {
    const env_text = "APP_ENV=development\nnoequals\nSECRET_KEY=\"unterminated\nSECRET_KEY=x\nSECRET_KEY=y\n1BAD=1\n";
    const schema_text = "APP_ENV=production\n";
    const result = try check(std.testing.allocator, env_text, schema_text, .{});
    defer std.testing.allocator.free(result.issues);
    defer std.testing.allocator.free(result.entries);
    try std.testing.expect(result.error_count >= 4);
    var kinds: std.ArrayList(IssueKind) = .empty;
    defer kinds.deinit(std.testing.allocator);
    for (result.issues) |i| {
        if (i.source == .env and !containsKind(kinds.items, i.kind)) try kinds.append(std.testing.allocator, i.kind);
    }
    try std.testing.expect(containsKind(kinds.items, .malformed_line));
    try std.testing.expect(containsKind(kinds.items, .unterminated_quote));
    try std.testing.expect(containsKind(kinds.items, .duplicate_key));
    try std.testing.expect(containsKind(kinds.items, .invalid_key));
}

fn containsKind(kinds: []const IssueKind, kind: IssueKind) bool {
    for (kinds) |k| if (k == kind) return true;
    return false;
}

test "interpolation, placeholder and weak secret" {
    const env_text =
        \\DATABASE_URL=${POSTGRES_USER}:secret@localhost/db
        \\OPA_URL=<your-opa-host>:8181
        \\SECRET_KEY=short
    ;
    const schema_text =
        \\DATABASE_URL=
        \\OPA_URL=http://opa:8181
        \\SECRET_KEY=
    ;
    const result = try check(std.testing.allocator, env_text, schema_text, .{});
    defer std.testing.allocator.free(result.issues);
    defer std.testing.allocator.free(result.entries);
    try std.testing.expectEqual(@as(usize, 1), result.error_count);
    try std.testing.expectEqual(@as(usize, 2), result.warning_count);
}

test "quoted values are accepted" {
    const env_text = "APP_ENV=\"production\"\nDEBUG='true'\n";
    const schema_text = "APP_ENV=production\nDEBUG=false\n";
    const result = try check(std.testing.allocator, env_text, schema_text, .{});
    defer std.testing.allocator.free(result.issues);
    defer std.testing.allocator.free(result.entries);
    try std.testing.expectEqual(@as(usize, 0), result.error_count);
    try std.testing.expectEqual(@as(usize, 0), result.warning_count);
}

test "required keys must be present" {
    const env_text = "APP_ENV=development\n";
    const schema_text = "APP_ENV=production\n";
    const result = try check(std.testing.allocator, env_text, schema_text, .{ .required = &.{"SECRET_KEY"} });
    defer std.testing.allocator.free(result.issues);
    defer std.testing.allocator.free(result.entries);
    try std.testing.expectEqual(@as(usize, 1), result.error_count);
    try std.testing.expectEqual(.required_missing, result.issues[0].kind);
}

test "comments and blank lines are ignored" {
    const env_text = "\n# leading comment\nAPP_ENV=production\n# trailing comment\n";
    const schema_text = "APP_ENV=production\n";
    const result = try check(std.testing.allocator, env_text, schema_text, .{});
    defer std.testing.allocator.free(result.issues);
    defer std.testing.allocator.free(result.entries);
    try std.testing.expectEqual(@as(usize, 0), result.error_count);
    try std.testing.expectEqual(@as(usize, 0), result.warning_count);
}

test "hash inside a value is preserved (no inline comments)" {
    const env_text = "GROQ_API_KEY=re_abcdef123#frag\n";
    const schema_text = "GROQ_API_KEY=\n";
    const result = try check(std.testing.allocator, env_text, schema_text, .{});
    defer std.testing.allocator.free(result.issues);
    defer std.testing.allocator.free(result.entries);
    try std.testing.expectEqual(@as(usize, 0), result.error_count);
    try std.testing.expectEqual(@as(usize, 0), result.warning_count);
}

test "numeric values are not weak secrets" {
    const env_text =
        \\PASSWORD_RESET_EXPIRE_HOURS=6
        \\DEMO_MAX_OUTPUT_TOKENS=1024
        \\FREE_SIGNUP_TOKENS=100
    ;
    const schema_text =
        \\PASSWORD_RESET_EXPIRE_HOURS=24
        \\DEMO_MAX_OUTPUT_TOKENS=1024
        \\FREE_SIGNUP_TOKENS=100
    ;
    const result = try check(std.testing.allocator, env_text, schema_text, .{});
    defer std.testing.allocator.free(result.issues);
    defer std.testing.allocator.free(result.entries);
    try std.testing.expectEqual(@as(usize, 0), result.error_count);
    try std.testing.expectEqual(@as(usize, 0), result.warning_count);
}