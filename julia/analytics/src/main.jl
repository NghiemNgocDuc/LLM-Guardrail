#     julia --project=julia/analytics src/main.jl [--db URL] [--org ORG] [--days N] [--out DIR]
#
# Read-only analytics report from the materialized views:
#
#   * top blocked reasons (+ share) — mirrors GET /analytics/top-blocked-reasons
#   * false-positive candidates by rule (+ share) — mirrors GET /analytics/false-positive-candidates
#   * blocked requests per day (+ share)
#
# Writes three PNG charts into `--out` (default: `charts/` in the package
# dir) and prints the CSV rows to stdout. Uses `DATABASE_URL` (or
# `TEST_DATABASE_URL`) when `--db` is not given. Every connection is opened
# with `read_only=true`.
using Pkg
Pkg.activate(dirname(@__DIR__); io=devnull)

using Dates: Dates
using LibPQ
import GuardrailsAnalytics
import GuardrailsAnalytics: connect_readonly, top_blocked_reasons,
    false_positive_by_rule, daily_blocked
import GuardrailsAnalytics.Charts

function parse_args()
    db = get(ENV, "DATABASE_URL", get(ENV, "TEST_DATABASE_URL", ""))
    org = nothing
    days = 7
    out = joinpath(dirname(@__DIR__), "charts")
    args = ARGS
    i = 1
    while i <= length(args)
        if args[i] == "--db"
            db = args[i+1]; i += 2
        elseif args[i] == "--org"
            org = args[i+1]; i += 2
        elseif args[i] == "--days"
            days = parse(Int, args[i+1]); i += 2
        elseif args[i] == "--out"
            out = args[i+1]; i += 2
        else
            println(stderr, "unknown argument: $(args[i])")
            exit(2)
        end
    end
    isempty(db) && (println(stderr, "no database URL: pass --db or set DATABASE_URL"); exit(2))
    return (; db, org, days, out)
end

function main()
    opts = parse_args()
    mkpath(opts.out)
    conn = connect_readonly(opts.db)
    try
        blocked = top_blocked_reasons(conn, opts.org, opts.days; limit=10)
        fps = false_positive_by_rule(conn, opts.org, opts.days; limit=50)
        daily = daily_blocked(conn, opts.org, opts.days)

        println("fired_rule,count,share")
        for r in blocked
            println(r.fired_rule, ",", r.count, ",", round(r.share; digits=4))
        end
        println("fired_rule,disputed_count,positive_feedback,override_hit,share")
        for r in fps
            println(r.fired_rule, ",", r.count, ",", r.positive_feedback, ",", r.override_hit, ",", round(r.share; digits=4))
        end
        println("day,blocked_count,share")
        for d in daily
            println(d.day, ",", d.count, ",", round(d.share; digits=4))
        end

        Charts.bar_chart_png(joinpath(opts.out, "top_blocked_reasons.png"),
                             [r.count for r in blocked], [r.fired_rule for r in blocked],
                             "Top blocked reasons")
        Charts.bar_chart_png(joinpath(opts.out, "false_positive_by_rule.png"),
                             [r.count for r in fps], [r.fired_rule for r in fps],
                             "False positive candidates by rule")
        Charts.bar_chart_png(joinpath(opts.out, "blocked_per_day.png"),
                             [d.count for d in daily], [string(d.day) for d in daily],
                             "Blocked requests per day")
        println("charts written to ", opts.out)
    finally
        close(conn)
    end
end

main()
