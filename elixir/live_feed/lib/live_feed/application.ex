defmodule LiveFeed.Application do
  # See https://elixir.hexdocs.pm/Application.html
  # for more information on OTP Applications
  @moduledoc false

  use Application

  @impl true
  def start(_type, _args) do
    children = [
      LiveFeedWeb.Telemetry,
      {DNSCluster, query: Application.get_env(:live_feed, :dns_cluster_query) || :ignore},
      {Phoenix.PubSub, name: LiveFeed.PubSub},
      # Postgres: query pool (user/org lookups) + LISTEN connection (feed).
      {Postgrex, postgrex_opts(LiveFeed.Pg)},
      {Postgrex.Notifications, postgrex_opts(LiveFeed.Notify)},
      LiveFeed.NotifyRelay,
      LiveFeedWeb.Endpoint
    ]

    # See https://elixir.hexdocs.pm/Supervisor.html
    # for other strategies and supported options
    opts = [strategy: :one_for_one, name: LiveFeed.Supervisor]
    Supervisor.start_link(children, opts)
  end

  defp postgrex_opts(name) do
    uri = URI.parse(LiveFeed.Auth.config()[:database_url])

    [userinfo_user, userinfo_pass] =
      case uri.userinfo do
        nil -> [nil, nil]
        info -> String.split(info, ":", parts: 2)
      end

    [
      name: name,
      hostname: uri.host,
      port: uri.port || 5432,
      username: userinfo_user,
      password: userinfo_pass,
      database: String.trim_leading(uri.path || "", "/"),
      pool_size: 2
    ]
  end

  # Tell Phoenix to update the endpoint configuration
  # whenever the application is updated.
  @impl true
  def config_change(changed, _new, removed) do
    LiveFeedWeb.Endpoint.config_change(changed, removed)
    :ok
  end
end
