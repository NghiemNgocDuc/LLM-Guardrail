# Live request feed service — Phoenix (Elixir) app that LISTENs on the
# Postgres request_log_events NOTIFY channel and fans events out to the
# per-org Phoenix channels that the dashboard's LogsView subscribes to.
FROM elixir:1.18.3-otp-27 AS build

WORKDIR /app
ENV MIX_ENV=prod

RUN mix local.hex --force && mix local.rebar --force

COPY mix.exs mix.lock ./
RUN mix deps.get --only prod && mix deps.compile

COPY config config
COPY lib lib
COPY priv priv
RUN mix compile

FROM elixir:1.18.3-otp-27

WORKDIR /app
ENV MIX_ENV=prod
ENV PHX_SERVER=true

COPY --from=build /app/_build /app/_build
COPY --from=build /app/deps /app/deps
COPY --from=build /app/config /app/config
COPY --from=build /app/lib /app/lib
COPY --from=build /app/priv /app/priv
COPY mix.exs mix.lock ./

EXPOSE 4000

# The service needs no HTTP ingress from the outside world: it only
# consumes Postgres NOTIFY and speaks to the browser through nginx.
CMD ["mix", "run", "--no-halt"]