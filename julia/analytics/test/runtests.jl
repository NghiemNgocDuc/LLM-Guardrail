# runtests.jl — GuardrailsAnalytics test suite
#
# Three layers:
#
#   1. PngWriter unit tests: signature, IHDR fields, deterministic bytes.
#   2. Charts unit tests: hand-calculated pixel assertions for known inputs
#      (no database needed).
#   3. Database integration tests (skipped unless ENV["TEST_DATABASE_URL"] is
#      set): create a scratch schema with the 0011 materialized views, seed
#      it with the same dataset as tests/test_analytics_views_db.py, refresh
#      the views, and verify the analytics numbers (and ratios) against
#      hand-calculated values. All analytics queries run through a
#      `read_only=true` connection.
#
# Run:  julia --project=julia/analytics -e 'using Pkg; Pkg.test()'
# or:   julia --project=julia/analytics test/runtests.jl
using Test
using Dates: DateTime
using Dates: Dates
using LibPQ

using GuardrailsAnalytics
using GuardrailsAnalytics: connect_readonly, shares, block_rate_pct
import GuardrailsAnalytics.PngWriter
import GuardrailsAnalytics.Charts

# ── 1. PNG encoder ──────────────────────────────────────────────────────────
@testset "PngWriter" begin
    @test PngWriter.png_header(1, 1) == UInt8[0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A]

    img = Matrix{PngWriter.Pixel}(undef, 3, 4)
    for y in 1:3, x in 1:4
        img[y, x] = ((y * 4 + x), (y * 4 + x) * 2, 0x00)
    end
    path = joinpath(mktempdir(), "test.png")
    PngWriter.write_png(path, img)
    bytes = read(path)

    @test bytes[1:8] == PngWriter.png_header(4, 3)
    be32(i) = (UInt32(bytes[i]) << 24) | (UInt32(bytes[i+1]) << 16) |
              (UInt32(bytes[i+2]) << 8) | UInt32(bytes[i+3])
    # IHDR chunk: length(4) + "IHDR" + 13 payload; payload: width=4, height=3,
    # bit depth 8, color type 2, compression/filter/interlace 0
    @test be32(9) == 13
    @test String(bytes[13:16]) == "IHDR"
    @test be32(17) == 4
    @test be32(21) == 3
    @test bytes[25] == 0x08 && bytes[26] == 0x02 && bytes[27:29] == UInt8[0, 0, 0]
    # the final chunk is IEND: length field, then the marker, then its CRC
    @test be32(length(bytes) - 11) == 0
    @test String(bytes[end-7:end-4]) == "IEND"
    # deterministic: writing twice yields identical bytes
    path2 = joinpath(mktempdir(), "test2.png")
    PngWriter.write_png(path2, img)
    @test read(path) == read(path2)
end

# ── 2. Charts (hand-calculated pixels, no DB) ───────────────────────────────
@testset "Charts geometry and pixels" begin
    width, height = 480, 300
    ml, mt, mb, mr = 64, 16, 28, 8
    g = Charts.bar_geometry([10.0, 30.0], width, height)
    plot_h = height - mt - mb
    @test g.plot_h == plot_h
    # bar heights: 10/30 and 30/30 of the plot height, rounded
    @test g.heights[1] == round(Int, 10 / 30 * plot_h)
    @test g.heights[2] == plot_h
    # tallest bar's top edge sits exactly on the top margin row
    @test g.bar_top[2] == mt

    img = Charts.bar_chart_png(joinpath(mktempdir(), "chart.png"), [10.0, 30.0],
                               ["pii_detected", "toxic_content"], "Test")
    # the tallest bar fills the plot height: pixel at (bar2 center, mt) is the bar color
    cx2 = g.bar_x0[2] + g.bar_width ÷ 2
    @test img[mt, cx2] == Charts.BAR
    # one row above the plot area is background
    @test img[mt - 1, cx2] == Charts.BACK
    # bar 1 is shorter: its top is below bar 2's top
    @test g.bar_top[1] > g.bar_top[2]
    # the baseline row is the axis (ink)
    @test img[g.plot_bottom, ml] == Charts.INK
    # the count label ("100.0%") was drawn above the tallest bar: some
    # non-background pixel exists in the label band over the bar's width
    label_rows = max(1, mt - 8):(mt - 1)
    @test any(img[y, x] != Charts.BACK for y in label_rows,
              x in g.bar_x0[2]:(g.bar_x0[2] + g.bar_width - 1))
    # an all-zero series renders without crashing and no bar pixels appear
    g0 = Charts.bar_geometry([0.0, 0.0], width, height)
    @test g0.heights == [0, 0]
    img0 = Charts.bar_chart_png(joinpath(mktempdir(), "zero.png"), [0.0, 0.0], ["a", "b"], "Zero")
    @test img0[mt, 70] == Charts.BACK
end

@testset "ratio helpers" begin
    @test shares([2, 1]) == [2 / 3, 1 / 3]
    @test block_rate_pct(3, 10) == 30.0
    @test block_rate_pct(0, 0) == 0.0
    @test block_rate_pct(1, 3) == 33.33
end

# ── 3. Database integration (skipped without TEST_DATABASE_URL) ──────────────
const TEST_URL = get(ENV, "TEST_DATABASE_URL", "")
const _DDL = [
    "CREATE TABLE users (id TEXT PRIMARY KEY)",
    "CREATE TABLE api_keys (id TEXT PRIMARY KEY, owner_id TEXT)",
    "CREATE TABLE user_skill_guard_overrides (user_id TEXT PRIMARY KEY, overrides JSONB)",
    "CREATE TABLE request_logs (id TEXT PRIMARY KEY, org_id TEXT, api_key_id TEXT, status TEXT, fired_rule TEXT, prompt_preview TEXT, created_at TIMESTAMPTZ)",
    "CREATE TABLE chat_feedback (request_log_id TEXT PRIMARY KEY, user_id TEXT, rating INT)",
    "CREATE MATERIALIZED VIEW mv_blocked_reasons_daily AS SELECT org_id, CAST(created_at AS DATE) AS day, fired_rule, COUNT(*) AS cnt, MAX(created_at) AS last_occurred_at FROM request_logs WHERE status IN ('input_blocked', 'output_blocked') AND fired_rule IS NOT NULL GROUP BY org_id, CAST(created_at AS DATE), fired_rule",
    "CREATE UNIQUE INDEX uq_mv_blocked_reasons_daily ON mv_blocked_reasons_daily (org_id, day, fired_rule)",
    "CREATE INDEX idx_mv_blocked_reasons_daily_org_day ON mv_blocked_reasons_daily (org_id, day)",
    "CREATE MATERIALIZED VIEW mv_false_positive_candidates_daily AS SELECT rl.org_id, CAST(rl.created_at AS DATE) AS day, rl.fired_rule, rl.id AS request_log_id, rl.status, rl.prompt_preview, rl.created_at, (fb.rating = 1) AS positive_feedback, EXISTS (SELECT 1 FROM jsonb_array_elements_text(COALESCE(ov.overrides->'always_allow_reason_codes', '[]')::jsonb) AS el WHERE el = rl.fired_rule) AS override_hit FROM request_logs rl LEFT JOIN chat_feedback fb ON fb.request_log_id = rl.id LEFT JOIN api_keys ak ON ak.id = rl.api_key_id LEFT JOIN user_skill_guard_overrides ov ON ov.user_id = ak.owner_id WHERE rl.status IN ('input_blocked', 'output_blocked') AND rl.fired_rule IS NOT NULL AND (fb.rating = 1 OR EXISTS (SELECT 1 FROM jsonb_array_elements_text(COALESCE(ov.overrides->'always_allow_reason_codes', '[]')::jsonb) AS el WHERE el = rl.fired_rule))",
    "CREATE UNIQUE INDEX uq_mv_false_positive_candidates_daily ON mv_false_positive_candidates_daily (request_log_id)",
    "CREATE INDEX idx_mv_false_positive_candidates_daily_org_day ON mv_false_positive_candidates_daily (org_id, day)",
]
const _DROP = [
    "DROP MATERIALIZED VIEW IF EXISTS mv_false_positive_candidates_daily",
    "DROP MATERIALIZED VIEW IF EXISTS mv_blocked_reasons_daily",
    "DROP TABLE IF EXISTS chat_feedback, request_logs, user_skill_guard_overrides, api_keys, users CASCADE",
]
const _SEED = [
    "INSERT INTO users (id) VALUES ('u1')",
    "INSERT INTO api_keys (id, owner_id) VALUES ('k1', 'u1'), ('k2', 'u1')",
    "INSERT INTO request_logs (id, org_id, api_key_id, status, fired_rule, prompt_preview, created_at) VALUES " *
    "('r1', 'org-a', 'k1', 'input_blocked', 'pii_detected', 'email in prompt', '2026-08-01 10:00:00+00'), " *
    "('r2', 'org-a', 'k1', 'input_blocked', 'pii_detected', 'another email', '2026-08-02 10:00:00+00'), " *
    "('r3', 'org-a', 'k2', 'input_blocked', 'toxic_content', 'bad word', '2026-08-02 11:00:00+00'), " *
    "('r4', 'org-a', 'k1', 'delivered', NULL, 'fine', '2026-08-02 12:00:00+00'), " *
    "('r5', 'org-b', 'k1', 'output_blocked', 'pii_detected', 'org b', '2026-08-02 13:00:00+00')",
    "INSERT INTO chat_feedback (request_log_id, user_id, rating) VALUES ('r1', 'u1', 1)",
    "INSERT INTO user_skill_guard_overrides (user_id, overrides) VALUES ('u1', '{\"always_allow_reason_codes\": [\"toxic_content\"]}')",
    "REFRESH MATERIALIZED VIEW CONCURRENTLY mv_blocked_reasons_daily",
    "REFRESH MATERIALIZED VIEW CONCURRENTLY mv_false_positive_candidates_daily",
]

if isempty(TEST_URL)
    @info "TEST_DATABASE_URL not set — skipping database integration tests"
else
    @testset "database integration (scratch schema)" begin
        admin = LibPQ.Connection(TEST_URL) # schema setup needs writes
        try
            for stmt in _DROP
                LibPQ.execute(admin, stmt)
            end
            for stmt in _DDL
                LibPQ.execute(admin, stmt)
            end
            for stmt in _SEED
                LibPQ.execute(admin, stmt)
            end

            # read-only analytics connection, as the module intends
            conn = connect_readonly(TEST_URL)
            try
                blocked = top_blocked_reasons(conn, "org-a", 90)
                # hand-calculated: org-a blocked = pii_detected 2 (r1, r2), toxic_content 1 (r3)
                @test [(r.fired_rule, r.count) for r in blocked] ==
                      [("pii_detected", 2), ("toxic_content", 1)]
                @test blocked[1].share ≈ 2 / 3
                @test blocked[2].share ≈ 1 / 3
                @test blocked[1].last_occurred_at isa DateTime

                fps = false_positive_by_rule(conn, "org-a", 90)
                # r1: thumbs-up feedback; r3: override hit — both org-a
                @test [(r.fired_rule, r.count) for r in fps] ==
                      [("pii_detected", 1), ("toxic_content", 1)]
                @test fps[1].positive_feedback == 1 && fps[1].override_hit == 0
                @test fps[2].positive_feedback == 0 && fps[2].override_hit == 1
                @test fps[1].share ≈ 1 / 2 && fps[2].share ≈ 1 / 2

                daily = daily_blocked(conn, "org-a", 90)
                @test [(d.day, d.count) for d in daily] ==
                      [(Dates.Date(2026, 8, 1), 1), (Dates.Date(2026, 8, 2), 2)]
                @test daily[1].share ≈ 1 / 3 && daily[2].share ≈ 2 / 3

                # read-only enforcement: writes must fail on this connection
                @test_throws Exception LibPQ.execute(conn, "CREATE TABLE should_not_exist (x INT)")

                # org-scoped and unscoped queries see the same total for org-a
                all_orgs = top_blocked_reasons(conn, nothing, 90)
                org_a_total = sum(r.count for r in blocked)
                @test sum(r.count for r in all_orgs) > org_a_total # org-b adds one

                # charts from real query results: verify bar heights against
                # hand-calculated ratios (pii_detected 2 : toxic_content 1)
                chart_dir = mktempdir()
                counts = [r.count for r in blocked]
                img = Charts.bar_chart_png(joinpath(chart_dir, "blocked.png"),
                                           counts, [r.fired_rule for r in blocked],
                                           "Top blocked reasons")
                g = Charts.bar_geometry(counts)
                # pii_detected is the tallest bar and fills the plot height
                @test g.bar_top[1] == g.plot_top
                @test img[g.plot_top, g.bar_x0[1] + g.bar_width ÷ 2] == Charts.BAR
                # toxic_content bar is exactly half as tall (1 : 2)
                @test g.heights[2] == round(Int, 1 / 2 * g.plot_h)
                @test isfile(joinpath(chart_dir, "blocked.png"))
            finally
                close(conn)
            end
        finally
            for stmt in _DROP
                LibPQ.execute(admin, stmt)
            end
            close(admin)
        end
    end
end
