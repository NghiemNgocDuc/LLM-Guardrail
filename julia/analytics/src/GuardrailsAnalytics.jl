"""
    GuardrailsAnalytics

Read-only analytics over the `mv_blocked_reasons_daily` and
`mv_false_positive_candidates_daily` materialized views created by
`alembic/versions/20260812_0000_0011_analytics_views.py`.

The queries mirror the FastAPI endpoints in `app/routers/analytics.py`
(`/analytics/top-blocked-reasons`, `/analytics/false-positive-candidates`),
so numbers produced here must match the dashboard. Ratios (shares) are
returned alongside raw counts so the PNG charts can be verified against
hand-calculated values.

Everything is read-only: every query is a plain SELECT over the views, and
callers should connect with `LibPQ.Connection(conninfo; read_only=true)`.
The test suite creates the scratch views in a throwaway schema, so no
production data is ever touched.

Uses:
```julia
using GuardrailsAnalytics, LibPQ
conn = LibPQ.Connection(ENV["TEST_DATABASE_URL"]; read_only=true)
top_blocked_reasons(conn, "org-a", 7)          # Vector{BlockedReason}
false_positive_by_rule(conn, "org-a", 7)       # Vector{FalsePositive}
daily_blocked(conn, "org-a", 7)                # Vector{DailyBlocked}
close(conn)
```
"""
module GuardrailsAnalytics

using Dates: Dates, Day, DateTime
using Tables
using LibPQ

include("PngWriter.jl")
include("Charts.jl")

export BlockedReason, FalsePositive, DailyBlocked,
       top_blocked_reasons, false_positive_by_rule, daily_blocked,
       shares, block_rate_pct, connect_readonly

struct BlockedReason
    fired_rule::String
    count::Int
    last_occurred_at::Union{Nothing,DateTime}
    share::Float64
end

struct FalsePositive
    fired_rule::String
    count::Int
    positive_feedback::Int
    override_hit::Int
    share::Float64
end

struct DailyBlocked
    day::Dates.Date
    count::Int
    share::Float64
end

const BLOCKED_STATUSES = ("input_blocked", "output_blocked")

"""
    connect_readonly(conninfo) -> LibPQ.Connection

Open a read-only connection. `default_transaction_read_only=on` is set via the
libpq `options` parameter, so every statement (DDL or DML) runs inside a
read-only transaction and the server rejects writes.
"""
function connect_readonly(conninfo::AbstractString)
    opts = "-c default_transaction_read_only=on"
    enc = replace(replace(opts, " " => "%20"), "=" => "%3D")
    sep = occursin("?", String(conninfo)) ? "&" : "?"
    return LibPQ.Connection(string(conninfo, sep, "options=", enc))
end

function _since_date(days::Integer)
    return Dates.Date(Dates.now(Dates.UTC)) - Day(days)
end

_org_clause(::Nothing) = ("", Any[])
_org_clause(org::AbstractString) = (" AND org_id = \$2", Any[org])

"""
    top_blocked_reasons(conn, org, days; limit=10) -> Vector{BlockedReason}

Mirror of `GET /analytics/top-blocked-reasons`: per-rule totals summed
from the per-org-per-day view rows, most recent occurrence per rule,
sorted by count descending. `share` is `count / total` over the window.
"""
function top_blocked_reasons(conn, org::Union{Nothing,AbstractString}, days::Integer; limit::Integer=10)
    since = _since_date(days)
    sql = """
        SELECT fired_rule, SUM(cnt) AS cnt, MAX(last_occurred_at) AS last_occurred_at
        FROM mv_blocked_reasons_daily
        WHERE day >= \$1$(first(_org_clause(org)))
        GROUP BY fired_rule
        ORDER BY SUM(cnt) DESC, fired_rule
        LIMIT \$$(org === nothing ? 2 : 3)
        """
    params = org === nothing ? Any[since, limit] : Any[since, org, limit]
    result = LibPQ.execute(conn, sql, params)
    rows = collect(Tables.namedtupleiterator(columntable(result)))
    total = sum(r.cnt for r in rows)
    return [BlockedReason(
        String(r.fired_rule),
        Int(r.cnt),
        ismissing(r.last_occurred_at) ? nothing : DateTime(r.last_occurred_at),
        total > 0 ? r.cnt / total : 0.0,
    ) for r in rows]
end

"""
    false_positive_by_rule(conn, org, days; limit=50) -> Vector{FalsePositive}

Mirror of `GET /analytics/false-positive-candidates`: blocked requests that
users disputed (positive feedback or always-allow override), grouped by
fired rule. `share` is `count / total` disputed over the window.
"""
function false_positive_by_rule(conn, org::Union{Nothing,AbstractString}, days::Integer; limit::Integer=50)
    since = _since_date(days)
    sql = """
        SELECT fired_rule, positive_feedback, override_hit
        FROM mv_false_positive_candidates_daily
        WHERE day >= \$1$(first(_org_clause(org)))
        ORDER BY created_at DESC
        LIMIT 500
        """
    params = org === nothing ? Any[since] : Any[since, org]
    result = LibPQ.execute(conn, sql, params)
    rows = columntable(result)

    by_rule = Dict{String,Tuple{Int,Int,Int}}()
    for i in eachindex(rows.fired_rule)
        rule = String(rows.fired_rule[i])
        fb = ismissing(rows.positive_feedback[i]) ? 0 : (rows.positive_feedback[i] ? 1 : 0)
        oh = ismissing(rows.override_hit[i]) ? 0 : (rows.override_hit[i] ? 1 : 0)
        cnt, pos, ovr = get(by_rule, rule, (0, 0, 0))
        by_rule[rule] = (cnt + 1, pos + fb, ovr + oh)
    end
    total = sum(first, values(by_rule)) # == sum of counts
    rules = sort(collect(keys(by_rule)); by=r -> (-by_rule[r][1], r))
    return [FalsePositive(r, by_rule[r][1], by_rule[r][2], by_rule[r][3],
                          total > 0 ? by_rule[r][1] / total : 0.0)
            for r in rules[1:min(limit, end)]]
end

"""
    daily_blocked(conn, org, days) -> Vector{DailyBlocked}

Per-day blocked totals from `mv_blocked_reasons_daily`. `share` is the
fraction of the window's blocked requests that fell on that day.
"""
function daily_blocked(conn, org::Union{Nothing,AbstractString}, days::Integer)
    since = _since_date(days)
    sql = """
        SELECT day, SUM(cnt) AS cnt
        FROM mv_blocked_reasons_daily
        WHERE day >= \$1$(first(_org_clause(org)))
        GROUP BY day
        ORDER BY day
        """
    params = org === nothing ? Any[since] : Any[since, org]
    result = LibPQ.execute(conn, sql, params)
    rows = columntable(result)
    total = sum(rows.cnt)
    return [DailyBlocked(rows.day[i], Int(rows.cnt[i]),
                         total > 0 ? rows.cnt[i] / total : 0.0)
            for i in eachindex(rows.day)]
end

"""
    shares(values) -> Vector{Float64}

Hand-calculable ratio helper used by the chart renderer and tests:
`values ./ sum(values)`.
"""
shares(values::AbstractVector{<:Real}) = [v / sum(values) for v in values]

"""
    block_rate_pct(blocked, total) -> Float64

`blocked / total * 100` rounded to 2 decimals, mirroring
`app.routers.analytics.dashboard` (`block_rate_pct`); `0.0` when
`total == 0`.
"""
block_rate_pct(blocked::Real, total::Real) = total > 0 ? round(blocked / total * 100; digits=2) : 0.0

end # module GuardrailsAnalytics
