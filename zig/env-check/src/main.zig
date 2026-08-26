const std = @import("std");
const envcheck = @import("envcheck.zig");

pub fn main() !void {
    var gpa = std.heap.GeneralPurposeAllocator(.{}){};
    defer _ = gpa.deinit();
    const alloc = gpa.allocator();

    const stdout = std.fs.File.stdout();
    const stderr = std.fs.File.stderr();

    const args = try std.process.argsAlloc(alloc);
    defer std.process.argsFree(alloc, args);

    if (args.len >= 2 and (std.mem.eql(u8, args[1], "--version") or std.mem.eql(u8, args[1], "version"))) {
        try stdout.writeAll("env-check 0.1.0\n");
        return;
    }
    if (args.len >= 2 and (std.mem.eql(u8, args[1], "--help") or std.mem.eql(u8, args[1], "help"))) {
        try stdout.writeAll(usage);
        return;
    }

    if (args.len < 2 or !std.mem.eql(u8, args[1], "check")) {
        try stderr.writeAll(usage);
        std.process.exit(64);
    }

    var env_path: ?[]const u8 = null;
    var schema_path: ?[]const u8 = null;
    var minimum_secret_len: usize = 8;
    var required: std.ArrayList([]const u8) = .empty;
    defer required.deinit(alloc);

    var i: usize = 2;
    while (i < args.len) : (i += 1) {
        const a = args[i];
        if (std.mem.eql(u8, a, "--schema")) {
            if (i + 1 >= args.len) {
                try printLine(stderr, "env-check: --schema requires a path\n", .{});
                std.process.exit(64);
            }
            schema_path = args[i + 1];
            i += 1;
        } else if (std.mem.eql(u8, a, "--required")) {
            if (i + 1 >= args.len) {
                try printLine(stderr, "env-check: --required requires a KEY\n", .{});
                std.process.exit(64);
            }
            try required.append(alloc, args[i + 1]);
            i += 1;
        } else if (std.mem.eql(u8, a, "--minimum-secret-len")) {
            if (i + 1 >= args.len) {
                try printLine(stderr, "env-check: --minimum-secret-len requires a number\n", .{});
                std.process.exit(64);
            }
            minimum_secret_len = std.fmt.parseInt(usize, args[i + 1], 10) catch {
                try printLine(stderr, "env-check: --minimum-secret-len wants a positive integer, got '{s}'\n", .{args[i + 1]});
                std.process.exit(64);
            };
            i += 1;
        } else if (a.len > 0 and a[0] == '-') {
            try printLine(stderr, "env-check: unknown option '{s}'\n", .{a});
            std.process.exit(64);
        } else if (env_path == null) {
            env_path = a;
        } else {
            try printLine(stderr, "env-check: unexpected argument '{s}'\n", .{a});
            std.process.exit(64);
        }
    }

    if (env_path == null or schema_path == null) {
        try printLine(stderr, "env-check: need <ENV_FILE> and --schema <EXAMPLE_FILE>\n\n{s}", .{usage});
        std.process.exit(64);
    }

    const env_text = readFile(alloc, env_path.?) orelse {
        try printLine(stderr, "env-check: cannot read '{s}'\n", .{env_path.?});
        std.process.exit(74);
    };
    defer alloc.free(env_text);
    const schema_text = readFile(alloc, schema_path.?) orelse {
        try printLine(stderr, "env-check: cannot read '{s}'\n", .{schema_path.?});
        std.process.exit(74);
    };
    defer alloc.free(schema_text);

    const result = envcheck.check(alloc, env_text, schema_text, .{
        .required = required.items,
        .minimum_secret_len = minimum_secret_len,
    }) catch {
        try stderr.writeAll("env-check: out of memory\n");
        std.process.exit(1);
    };
    defer alloc.free(result.issues);
    defer alloc.free(result.entries);

    for (result.issues) |issue| {
        const file = switch (issue.source) {
            .env => env_path.?,
            .schema => schema_path.?,
        };
        var buf: [512]u8 = undefined;
        const msg = envcheck.messageOf(issue, &buf);
        if (issue.line == 0) {
            try printLine(stderr, "{s}: {s}\n", .{ file, msg });
        } else {
            try printLine(stderr, "{s}:{d}: {s}\n", .{ file, issue.line, msg });
        }
    }

    if (result.error_count > 0) std.process.exit(1);
    if (result.warning_count > 0) std.process.exit(2);
}

fn printLine(file: std.fs.File, comptime fmt: []const u8, args: anytype) !void {
    var buf: [2048]u8 = undefined;
    const line = try std.fmt.bufPrint(&buf, fmt, args);
    try file.writeAll(line);
}

fn readFile(alloc: std.mem.Allocator, path: []const u8) ?[]u8 {
    return std.fs.cwd().readFileAlloc(alloc, path, 1 << 20) catch null;
}

const usage =
    \\usage: env-check check <ENV_FILE> --schema <EXAMPLE_FILE> [--required KEY]...
    \\
    \\Validate an .env file against the .env.example conventions:
    \\  * empty example value => optional key (placeholder to fill in)
    \\  * non-empty example value => working default; omission is a warning
    \\  * unknown keys, malformed lines, duplicates, quotes, '${...}'
    \\    interpolation and placeholder text are flagged
    \\  * SECRET/PASSWORD/TOKEN values under 8 chars are warnings
    \\
    \\Exit status: 0 = clean, 1 = errors, 2 = warnings only.
    \\
    \\Other commands: --version, --help
;
